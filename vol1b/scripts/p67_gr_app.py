#!/usr/bin/env python3
"""Vol.2 (directory vol1b/), P67 · the NeMo Guardrails 0.23.0 server app behind an import string, so that uvicorn can start
several worker processes (uvicorn needs an import string for workers > 1; every worker imports this module itself).

On import, each worker sets what p66_gr_server.py sets once in its single process: the API deployment type,
`rails_config_path` and the default config id, from P67_GR_ROOT and P67_GR_CONFIG_ID. It then prints one line,
`P67_WORKER pid=<pid> config_id=<id> config_sha256=<sha256 of <root>/<id>/config.yml as read by this worker>`.

`app` wraps the Guardrails app in one ASGI function that adds two response headers, x-p67-worker-pid and
x-p67-config-sha256, so a client can tell which worker answered. Nothing else in the request or the response changes.

`CountedH11` is uvicorn's h11 protocol (the one this environment uses: httptools is not installed) with two lines of
logging added and no change in behaviour. When uvicorn closes an idle keep-alive connection it prints
`P67_KEEPALIVE_CLOSE pid=<pid>`. When a connection is lost with an exception it prints
`P67_CONN_LOST pid=<pid> exc=<type> mid_request=<0|1>`. Uvicorn logs neither at level info.
"""
import hashlib, os

from nemoguardrails.server import api
from nemoguardrails.telemetry import DeploymentTypeEnum, set_deployment_type
from uvicorn.protocols.http.h11_impl import H11Protocol

ROOT, CID = os.environ["P67_GR_ROOT"], os.environ["P67_GR_CONFIG_ID"]
set_deployment_type(DeploymentTypeEnum.API.value)
setattr(api.app, "rails_config_path", os.path.expanduser(ROOT.rstrip(os.path.sep)))
api.set_default_config_id(CID)
PID = str(os.getpid())
CSHA = hashlib.sha256(open(os.path.join(ROOT, CID, "config.yml"), "rb").read()).hexdigest()
print(f"P67_WORKER pid={PID} config_id={CID} config_sha256={CSHA}", flush=True)
HDR = [(b"x-p67-worker-pid", PID.encode()), (b"x-p67-config-sha256", CSHA.encode())]


async def app(scope, receive, send):
    if scope["type"] != "http":
        return await api.app(scope, receive, send)

    async def send_(m):
        if m["type"] == "http.response.start":
            m = dict(m, headers=list(m.get("headers") or []) + HDR)
        await send(m)
    await api.app(scope, receive, send_)


class CountedH11(H11Protocol):
    def timeout_keep_alive_handler(self):
        if not self.transport.is_closing():
            print(f"P67_KEEPALIVE_CLOSE pid={PID}", flush=True)
        super().timeout_keep_alive_handler()

    def connection_lost(self, exc):
        if exc is not None:
            mid = int(bool(self.cycle is not None and not self.cycle.response_complete))
            print(f"P67_CONN_LOST pid={PID} exc={type(exc).__name__} mid_request={mid}", flush=True)
        super().connection_lost(exc)
