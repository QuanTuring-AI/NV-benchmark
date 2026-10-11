#!/usr/bin/env python3
"""Vol.2 (directory vol1b/), P67 · start a NeMo Guardrails 0.23.0 server bound to 127.0.0.1 with W worker processes and
uvicorn's keep-alive timeout K seconds.

The same server as p66_gr_server.py (the CLI's `server` with --default-config-id, host 127.0.0.1, log level info), with
two settings exposed: `workers` (uvicorn's default 1) and `timeout_keep_alive` (uvicorn's default 5 s). Differences from
p66_gr_server.py, identical for every P67 server:
- uvicorn needs the app as an import string for workers > 1, so the app is p67_gr_app:app, which each worker imports
  and configures itself;
- the HTTP protocol is p67_gr_app:CountedH11, uvicorn's h11 protocol with two log lines added;
- the access-log line carries the worker's pid.
usage: p67_gr_server.py <configs_root> <default_config_id> <port> <workers> <timeout_keep_alive_s>
"""
import copy, os, sys

import uvicorn
from uvicorn.config import LOGGING_CONFIG

HERE = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":   # the guard keeps spawned workers from re-running this block
    root, config_id, port, workers, keep_alive = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
    os.environ["P67_GR_ROOT"], os.environ["P67_GR_CONFIG_ID"] = root, config_id
    log_config = copy.deepcopy(LOGGING_CONFIG)
    log_config["formatters"]["access"]["fmt"] = '%(levelprefix)s pid=%(process)d %(client_addr)s - "%(request_line)s" %(status_code)s'
    uvicorn.run("p67_gr_app:app", app_dir=HERE, host="127.0.0.1", port=port, log_level="info", log_config=log_config,
                http="p67_gr_app:CountedH11", workers=workers, timeout_keep_alive=keep_alive)
