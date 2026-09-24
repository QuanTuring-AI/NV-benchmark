#!/bin/sh
# Runs INSIDE a throwaway container. The key arrives by --env-file and is used only as a curl credential; nothing
# below prints it. For each repository: obtain a pull-scope token, then page through /v2/<repo>/tags/list following
# the Link header until exhausted. Output: HTTP status per page, then the full tag list.
set -u
for repo in "$@"; do
  tok=$(curl -s -u "\$oauthtoken:${NGC_API_KEY}" "https://nvcr.io/proxy_auth?scope=repository:${repo}:pull" | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')
  url="https://nvcr.io/v2/${repo}/tags/list?n=1000"; pages=0; all=""
  while [ -n "$url" ] && [ $pages -lt 20 ]; do
    code=$(curl -s -D /tmp/h -o /tmp/out -w '%{http_code}' -H "Authorization: Bearer ${tok}" "$url")
    pages=$((pages+1))
    [ "$code" = 200 ] || { echo "=== ${repo} page ${pages} HTTP ${code}"; cat /tmp/out; echo; break; }
    all="${all}
$(cat /tmp/out)"
    next=$(grep -i '^link:' /tmp/h | sed -n 's/.*<\([^>]*\)>.*/\1/p' | head -1)
    case "$next" in /*) url="https://nvcr.io${next}";; "") url="";; *) url="$next";; esac
  done
  echo "=== ${repo} · pages ${pages} · last HTTP ${code}"
  printf '%s\n' "$all"
done
