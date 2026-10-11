#!/usr/bin/env python3
"""Vol.2 (directory vol1b/), P66 · start a NeMo Guardrails 0.23.0 server bound to 127.0.0.1.

Mirrors `nemoguardrails server --config <root> --default-config-id <id> --port <port>` (nemoguardrails/cli/__init__.py,
`server`): claims the API deployment type, sets `rails_config_path` and the default config id, then runs uvicorn on the
same FastAPI app. The one difference is the host: the CLI binds 0.0.0.0 (all interfaces); this binds 127.0.0.1.
usage: p66_gr_server.py <configs_root> <default_config_id> <port>
"""
import os, sys

import uvicorn
from nemoguardrails.server import api
from nemoguardrails.telemetry import DeploymentTypeEnum, set_deployment_type

root, config_id, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
set_deployment_type(DeploymentTypeEnum.API.value)
setattr(api.app, "rails_config_path", os.path.expanduser(root.rstrip(os.path.sep)))
api.set_default_config_id(config_id)
uvicorn.run(api.app, port=port, log_level="info", host="127.0.0.1")
