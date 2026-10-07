"""Authenticated loopback API and dependency-free status dashboard."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import os
import secrets
import tempfile
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from stack_integration import __version__
from stack_integration.config import Settings
from stack_integration.contracts.models import Run, Task
from stack_integration.controller import CollaborationController
from stack_integration.storage.database import NotFoundError

DASHBOARD_STYLE = """
:root{color-scheme:dark;--bg:#0c111b;--panel:#151e2d;--line:#263247;--text:#e8edf5;
--muted:#9aa7bb;--ok:#77d9a5;--bad:#ff9898;--warn:#ffd27a;--accent:#9ecbff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,sans-serif}
main{max-width:1100px;margin:2.5rem auto;padding:0 1rem}
h1{font-size:1.6rem;margin:0 0 .25rem}h2{font-size:1.15rem;margin:2rem 0 .5rem}
p{color:var(--muted);margin:.25rem 0 1rem}
form{display:flex;gap:.5rem;flex-wrap:wrap;align-items:center}
button,input{font:inherit;padding:.55rem .7rem;border-radius:.4rem;border:1px solid #53627a;
background:var(--panel);color:inherit}
button{cursor:pointer}input[type=password]{flex:1;min-width:14rem}
label{color:var(--muted);display:flex;gap:.35rem;align-items:center}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;margin-top:1rem}
th,td{text-align:left;padding:.6rem;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600}
tr.run{cursor:pointer}tr.run:hover{background:var(--panel)}
code{color:var(--accent);word-break:break-all}
.completed,.integrated,.verified,.passed,.approve{color:var(--ok)}
.failed,.cancelled,.error,.request_changes{color:var(--bad)}
.blocked,.awaiting_input,.changes_requested,.paused,.abstain{color:var(--warn)}
.pill{display:inline-block;margin:0 .35rem .2rem 0;white-space:nowrap}
#message{min-height:1.5rem}
"""

DASHBOARD_SCRIPT = """
const $ = (selector) => document.querySelector(selector);
let timer = null;
function esc(value) {
  const node = document.createElement('div');
  node.textContent = value == null ? '' : String(value);
  return node.innerHTML;
}
function token() {
  const value = $('#token').value.trim();
  try { if (value) sessionStorage.setItem('stack-agent-token', value); } catch (e) {}
  return value;
}
function pills(counts) {
  return Object.entries(counts || {})
    .map(([key, value]) => `<span class="pill ${esc(key)}">${esc(key)}: ${esc(value)}</span>`)
    .join('') || '<span class="pill">none</span>';
}
async function api(path) {
  const response = await fetch(path, {headers: {Authorization: 'Bearer ' + token()}});
  if (response.status === 401) throw new Error('Authentication failed');
  if (!response.ok) throw new Error('Request failed: ' + response.status);
  return response.json();
}
async function load() {
  try {
    const runs = await api('/api/runs');
    $('#message').textContent = runs.length ? '' : 'No runs recorded yet.';
    $('#runs').innerHTML = runs.map((run) => `<tr class="run" data-id="${esc(run.id)}">
      <td><code>${esc(run.id)}</code></td>
      <td class="${esc(run.status)}">${esc(run.status)}</td>
      <td>${esc(run.objective)}</td><td>${pills(run.task_summary)}</td></tr>`).join('');
    document.querySelectorAll('tr.run').forEach((row) =>
      row.addEventListener('click', () => detail(row.dataset.id)));
  } catch (error) {
    $('#message').textContent = error.message;
  }
}
async function detail(runId) {
  try {
    const report = await api('/api/runs/' + encodeURIComponent(runId));
    const run = report.run;
    $('#detail-title').textContent = 'Run ' + run.id;
    $('#detail-meta').innerHTML = `<span class="${esc(run.status)}">${esc(run.status)}</span>
      · base <code>${esc(run.base_revision.slice(0, 12))}</code>
      ${run.integration_ref ? '· result <code>' + esc(run.integration_ref) + '</code>' : ''}
      <br>reviews ${pills(report.summary.reviews)} checks ${pills(report.summary.checks)}`;
    $('#tasks').innerHTML = report.tasks.map((task) => `<tr>
      <td><code>${esc(task.id)}</code></td><td>${esc(task.owner_provider)}</td>
      <td class="${esc(task.status)}">${esc(task.status)}</td><td>${esc(task.attempt)}</td>
      <td>${esc(task.description)}</td></tr>`).join('');
    $('#detail').hidden = false;
  } catch (error) {
    $('#message').textContent = error.message;
  }
}
$('#login').addEventListener('submit', (event) => { event.preventDefault(); load(); });
$('#auto').addEventListener('change', (event) => {
  clearInterval(timer);
  if (event.target.checked) timer = setInterval(load, 5000);
});
try {
  const saved = sessionStorage.getItem('stack-agent-token');
  if (saved) { $('#token').value = saved; load(); }
} catch (e) {}
"""

DASHBOARD = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stack Agent</title><style>{DASHBOARD_STYLE}</style></head><body><main>
<h1>Stack Agent Controller</h1>
<p>Authoritative local run state. Provider prose cannot change these statuses.</p>
<form id="login"><input id="token" type="password" autocomplete="off"
placeholder="Operator bearer token"><button type="submit">Load</button>
<label><input id="auto" type="checkbox"> auto-refresh</label></form>
<p id="message" role="status"></p>
<div class="table-wrap"><table><thead><tr><th>Run</th><th>Status</th><th>Objective</th>
<th>Tasks</th></tr></thead><tbody id="runs"></tbody></table></div>
<section id="detail" hidden><h2 id="detail-title"></h2><p id="detail-meta"></p>
<div class="table-wrap"><table><thead><tr><th>Task</th><th>Provider</th><th>Status</th>
<th>Attempt</th><th>Description</th></tr></thead><tbody id="tasks"></tbody></table></div>
</section></main><script>{DASHBOARD_SCRIPT}</script></body></html>"""


def _csp_hash(source: str) -> str:
    digest = hashlib.sha256(source.encode()).digest()
    return "'sha256-" + base64.b64encode(digest).decode() + "'"


CONTENT_SECURITY_POLICY = (
    "default-src 'none'; "
    f"script-src {_csp_hash(DASHBOARD_SCRIPT)}; "
    f"style-src {_csp_hash(DASHBOARD_STYLE)}; "
    "connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'none'"
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def ensure_operator_token(settings: Settings) -> str:
    path = settings.state_root / "operator.token"
    if path.exists():
        token = path.read_text().strip()
        if token:
            return token
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    if path.exists():
        with tempfile.NamedTemporaryFile(
            "w", dir=path.parent, prefix=".operator-token-", delete=False
        ) as target:
            temporary = target.name
            target.write(token + "\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    else:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as target:
            target.write(token + "\n")
    return token


def create_app(settings: Settings | None = None, token: str | None = None) -> FastAPI:
    active_settings = settings or Settings.load()
    expected_token = token or ensure_operator_token(active_settings)
    if not expected_token:
        raise RuntimeError("operator token must not be empty")
    state: dict[str, CollaborationController] = {}
    state_lock = threading.Lock()

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        with state_lock:
            existing = state.pop("controller", None)
        if existing is not None:
            existing.close()

    app = FastAPI(
        title="Stack Integration Engine",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    def controller() -> CollaborationController:
        # One read-side controller per app: opening a controller per request re-ran
        # migrations and rebuilt every component on each poll.
        with state_lock:
            if "controller" not in state:
                state["controller"] = CollaborationController(active_settings)
            return state["controller"]

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    def authenticate(authorization: Annotated[str | None, Header()] = None) -> None:
        scheme, _, supplied = (authorization or "").partition(" ")
        if (
            scheme.lower() != "bearer"
            or not supplied
            or not secrets.compare_digest(supplied.strip(), expected_token)
        ):
            raise HTTPException(
                status_code=401,
                detail="invalid operator token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        return DASHBOARD

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/runs", dependencies=[Depends(authenticate)])
    def list_runs() -> list[dict[str, object]]:
        active = controller()
        response: list[dict[str, object]] = []
        for run in active.database.list("run", Run):
            summary: dict[str, int] = {}
            for task in active.database.list(
                "task", Task, project_id=run.project_id, run_id=run.id
            ):
                summary[task.status.value] = summary.get(task.status.value, 0) + 1
            response.append(
                {
                    "id": run.id,
                    "status": run.status.value,
                    "objective": run.objective,
                    "created_at": run.created_at.isoformat(),
                    "integration_ref": run.integration_ref,
                    "task_summary": summary,
                }
            )
        return response

    @app.get("/api/runs/{run_id}", dependencies=[Depends(authenticate)])
    def get_run(run_id: str) -> dict[str, Any]:
        try:
            return controller().run_report(run_id)
        except NotFoundError as error:
            raise HTTPException(status_code=404, detail="run not found") from error

    return app
