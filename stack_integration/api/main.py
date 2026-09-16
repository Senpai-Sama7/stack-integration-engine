"""Authenticated loopback API and dependency-free status dashboard."""

# ruff: noqa: E501

from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse

from stack_integration.config import Settings
from stack_integration.contracts.models import Run, Task
from stack_integration.controller import CollaborationController

DASHBOARD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Stack Agent</title><style>
:root{color-scheme:dark;background:#0c111b;color:#e8edf5;font:15px system-ui}
body{max-width:1100px;margin:3rem auto;padding:0 1.25rem}h1{font-size:1.7rem}
button,input{font:inherit;padding:.6rem;border-radius:.4rem;border:1px solid #53627a;background:#151e2d;color:inherit}
table{width:100%;border-collapse:collapse;margin-top:1.5rem}th,td{text-align:left;padding:.7rem;border-bottom:1px solid #263247}
.ok{color:#77d9a5}.bad{color:#ff9898}code{color:#9ecbff}
</style></head><body><h1>Stack Agent Controller</h1>
<p>Authoritative local run state. Provider prose cannot change these statuses.</p>
<input id="token" type="password" placeholder="Operator bearer token"><button onclick="load()">Load</button>
<p id="message"></p><table><thead><tr><th>Run</th><th>Status</th><th>Objective</th><th>Tasks</th></tr></thead><tbody id="runs"></tbody></table>
<script>
async function load(){const token=document.querySelector('#token').value;
 const response=await fetch('/api/runs',{headers:{Authorization:'Bearer '+token}});
 if(!response.ok){document.querySelector('#message').textContent='Authentication failed';return}
 const rows=await response.json();document.querySelector('#message').textContent='';
 document.querySelector('#runs').innerHTML=rows.map(x=>`<tr><td><code>${x.id}</code></td><td class="${x.status==='completed'?'ok':'bad'}">${x.status}</td><td>${esc(x.objective)}</td><td>${x.task_summary}</td></tr>`).join('')}
function esc(s){const e=document.createElement('div');e.textContent=s;return e.innerHTML}
</script></body></html>"""


def ensure_operator_token(settings: Settings) -> str:
    path = settings.state_root / "operator.token"
    if path.exists():
        existing = path.read_text().strip()
        if existing:
            return existing
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as target:
        target.write(token + "\n")
    return token


def create_app(settings: Settings | None = None, token: str | None = None) -> FastAPI:
    active_settings = settings or Settings.load()
    expected_token = token or ensure_operator_token(active_settings)
    if not expected_token:
        raise RuntimeError("operator token must not be empty")
    app = FastAPI(title="Stack Integration Engine", version="0.2.0")

    def authenticate(authorization: Annotated[str | None, Header()] = None) -> None:
        supplied = authorization.removeprefix("Bearer ") if authorization else ""
        if not supplied or not secrets.compare_digest(supplied, expected_token):
            raise HTTPException(status_code=401, detail="invalid operator token")

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        return DASHBOARD

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/runs", dependencies=[Depends(authenticate)])
    def list_runs() -> list[dict[str, object]]:
        controller = CollaborationController(active_settings)
        try:
            runs = controller.database.list("run", Run)
            response: list[dict[str, object]] = []
            for run in runs:
                tasks = controller.database.list(
                    "task", Task, project_id=run.project_id, run_id=run.id
                )
                summary: dict[str, int] = {}
                for task in tasks:
                    summary[task.status.value] = summary.get(task.status.value, 0) + 1
                response.append(
                    {
                        "id": run.id,
                        "status": run.status.value,
                        "objective": run.objective,
                        "task_summary": summary,
                    }
                )
            return response
        finally:
            controller.close()

    @app.get("/api/runs/{run_id}", dependencies=[Depends(authenticate)])
    def get_run(run_id: str) -> dict[str, object]:
        controller = CollaborationController(active_settings)
        try:
            try:
                return controller.run_report(run_id)
            except KeyError as error:
                raise HTTPException(status_code=404, detail="run not found") from error
        finally:
            controller.close()

    return app
