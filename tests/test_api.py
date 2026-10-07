from fastapi.testclient import TestClient

from stack_integration.api import create_app
from stack_integration.api.main import ensure_operator_token
from stack_integration.config import Settings


def test_api_requires_token_and_dashboard_has_no_state(tmp_path):
    settings = Settings.load(tmp_path / "state")
    app = create_app(settings, token="test-token")
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/api/runs").status_code == 401
    response = client.get("/api/runs", headers={"Authorization": "Bearer test-token"})
    assert response.status_code == 200
    assert response.json() == []


def test_empty_operator_token_is_regenerated(tmp_path):
    settings = Settings.load(tmp_path / "state")
    token_path = settings.state_root / "operator.token"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text("\n")
    token = ensure_operator_token(settings)
    assert token
    assert token_path.read_text().strip() == token


def test_dashboard_is_locked_down_with_hash_based_csp(tmp_path):
    import base64
    import hashlib
    import re

    from stack_integration.api.main import DASHBOARD_SCRIPT

    client = TestClient(create_app(Settings.load(tmp_path / "state"), token="t"))
    response = client.get("/")
    policy = response.headers["content-security-policy"]
    script = re.search(r"<script>(.*)</script>", response.text, re.DOTALL).group(1)
    assert script == DASHBOARD_SCRIPT
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    assert f"'sha256-{digest}'" in policy
    assert "unsafe-inline" not in policy
    assert response.headers["x-frame-options"] == "DENY"
    assert client.get("/health").headers["cache-control"] == "no-store"
    assert client.get("/docs").status_code == 404


def test_run_listing_and_detail(tmp_path):
    import subprocess

    from stack_integration.controller import CollaborationController

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "README.md").write_text("x\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-qm", "b"],
        cwd=repo,
        check=True,
    )
    settings = Settings.load(tmp_path / "state")
    controller = CollaborationController(settings)
    try:
        run = controller.create_run(repo, "objective", ["REQ-1"])
        controller.add_tasks(run.id, [{"id": "t1", "description": "d", "provider": "codex"}])
    finally:
        controller.close()
    with TestClient(create_app(settings, token="t")) as client:
        headers = {"Authorization": "bearer t"}
        listing = client.get("/api/runs", headers=headers).json()
        assert listing[0]["task_summary"] == {"ready": 1}
        detail = client.get(f"/api/runs/{run.id}", headers=headers).json()
        assert detail["summary"]["tasks"] == {"ready": 1}
        assert client.get("/api/runs/run_missing", headers=headers).status_code == 404
        assert client.get("/api/runs", headers={"Authorization": "Basic t"}).status_code == 401
