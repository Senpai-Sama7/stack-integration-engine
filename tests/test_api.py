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
