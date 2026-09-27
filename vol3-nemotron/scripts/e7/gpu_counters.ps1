# GPU memory attribution on Windows (WDDM) via the built-in performance counters.
#
# Why: under WDDM, `nvidia-smi --query-compute-apps` reports used_gpu_memory as [N/A], so it cannot say how
# much GPU memory a given process holds, or whether part of it was moved to shared system memory.
# The Windows counters "\GPU Process Memory(*)\Dedicated Usage" and "\Shared Usage" do report that per process.
# A Docker Desktop (WSL2) container's GPU memory appears under the WSL2 VM's host process.
#
# Output never contains the machine name or adapter LUIDs: only pid, process name, and values in MiB.
#
#   -Mode snapshot -Out <file.json>                      one full snapshot
#   -Mode sample   -Out <file.jsonl> -PidFile <f> -StopFile <f> [-IntervalSec 3]
#        appends one JSON line per interval until the stop file exists (every line is already on disk)
#        per-process GPU engine utilization is collected only for pids listed in the pid file (one per line)
param(
  [Parameter(Mandatory=$true)][ValidateSet('snapshot','sample')][string]$Mode,
  [Parameter(Mandatory=$true)][string]$Out,
  [string]$PidFile = '',
  [string]$StopFile = '',
  [double]$IntervalSec = 3
)
$ErrorActionPreference = 'SilentlyContinue'

function Get-Memory {
  $s = Get-Counter -Counter '\GPU Process Memory(*)\Dedicated Usage','\GPU Process Memory(*)\Shared Usage'
  $by = @{}
  foreach ($c in $s.CounterSamples) {
    $p = [regex]::Match($c.InstanceName, 'pid_(\d+)').Groups[1].Value
    if (-not $p) { continue }
    if (-not $by.ContainsKey($p)) { $by[$p] = @{ dedicated = 0.0; shared = 0.0 } }
    if ($c.Path -match 'dedicated usage$') { $by[$p].dedicated += $c.CookedValue } else { $by[$p].shared += $c.CookedValue }
  }
  $rows = @()
  foreach ($k in $by.Keys) {
    $d = $by[$k].dedicated / 1MB; $sh = $by[$k].shared / 1MB
    if ($d -ge 100 -or $sh -ge 100) {
      $name = (Get-Process -Id ([int]$k)).ProcessName
      $rows += [ordered]@{ pid = [int]$k; name = $name; dedicated_mib = [math]::Round($d, 1); shared_mib = [math]::Round($sh, 1) }
    }
  }
  return ,$rows
}

function Get-Adapter {
  $s = Get-Counter -Counter '\GPU Adapter Memory(*)\Dedicated Usage','\GPU Adapter Memory(*)\Shared Usage'
  $by = @{}
  foreach ($c in $s.CounterSamples) {
    $key = [regex]::Match($c.InstanceName, 'luid_[^_]+_[^_]+').Value
    if (-not $by.ContainsKey($key)) { $by[$key] = @{ dedicated = 0.0; shared = 0.0 } }
    if ($c.Path -match 'dedicated usage$') { $by[$key].dedicated += $c.CookedValue } else { $by[$key].shared += $c.CookedValue }
  }
  # report the adapter with the largest dedicated usage (the discrete GPU); LUID omitted
  $top = $by.Values | Sort-Object { $_.dedicated } -Descending | Select-Object -First 1
  return [ordered]@{ dedicated_mib = [math]::Round($top.dedicated / 1MB, 1); shared_mib = [math]::Round($top.shared / 1MB, 1); adapters_seen = $by.Count }
}

function Get-EngineUtil([int[]]$pids) {
  $out = @()
  foreach ($p in $pids) {
    $s = Get-Counter -Counter "\GPU Engine(pid_$($p)_*)\Utilization Percentage"
    $tot = 0.0; $mx = 0.0; $types = @{}
    foreach ($c in $s.CounterSamples) {
      $v = $c.CookedValue; $tot += $v; if ($v -gt $mx) { $mx = $v }
      $t = [regex]::Match($c.InstanceName, 'engtype_(.+)$').Groups[1].Value
      if ($v -gt 0) { $types[$t] = [math]::Round(($types[$t] + $v), 2) }
    }
    $out += [ordered]@{ pid = $p; util_sum_pct = [math]::Round($tot, 2); util_max_engine_pct = [math]::Round($mx, 2); nonzero_by_engtype = $types; engines = $s.CounterSamples.Count }
  }
  return ,$out
}

function Get-Smi {
  $l = (& nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,driver_version --format=csv,noheader,nounits) -split ','
  return [ordered]@{ memory_used_mib = [int]$l[0].Trim(); memory_total_mib = [int]$l[1].Trim(); util_pct = [int]$l[2].Trim(); driver = $l[3].Trim() }
}

function Snap([int[]]$pids) {
  $t0 = Get-Date
  $o = [ordered]@{
    t = $t0.ToString('o')
    smi = Get-Smi
    adapter = Get-Adapter
    processes = Get-Memory
  }
  if ($pids.Count -gt 0) { $o.engine_util = Get-EngineUtil $pids }
  $o.collect_ms = [math]::Round(((Get-Date) - $t0).TotalMilliseconds, 0)
  return $o
}

if ($Mode -eq 'snapshot') {
  $pids = @(); if ($PidFile -and (Test-Path $PidFile)) { $pids = @(Get-Content $PidFile | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ }) }
  (Snap $pids | ConvertTo-Json -Depth 6 -Compress) | Set-Content -Path $Out -Encoding UTF8
  exit 0
}

# sample mode
$self = Get-Process -Id $PID
$cpu0 = $self.TotalProcessorTime.TotalSeconds; $wall0 = Get-Date
while (-not (Test-Path $StopFile)) {
  $pids = @(); if ($PidFile -and (Test-Path $PidFile)) { $pids = @(Get-Content $PidFile | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ }) }
  $line = Snap $pids | ConvertTo-Json -Depth 6 -Compress
  Add-Content -Path $Out -Value $line -Encoding UTF8
  $spent = ((Get-Date) - [datetime]::Parse(($line | ConvertFrom-Json).t)).TotalSeconds
  $rest = $IntervalSec - $spent; if ($rest -gt 0) { Start-Sleep -Milliseconds ([int]($rest * 1000)) }
}
$self.Refresh()
$sum = [ordered]@{ t = (Get-Date).ToString('o'); sampler_summary = [ordered]@{ wall_s = [math]::Round(((Get-Date) - $wall0).TotalSeconds, 1); cpu_s = [math]::Round($self.TotalProcessorTime.TotalSeconds - $cpu0, 1); logical_cpus = [Environment]::ProcessorCount } }
Add-Content -Path $Out -Value ($sum | ConvertTo-Json -Compress) -Encoding UTF8
