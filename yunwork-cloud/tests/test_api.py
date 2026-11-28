from fastapi.testclient import TestClient
from test_service import FakeDocker, request

from yunwork_cloud.config import Settings
from yunwork_cloud.main import create_app
from yunwork_cloud.service import InstanceManager

SECRET = "controller-secret-with-at-least-32-characters"


def test_control_auth_and_secret_response(tmp_path):
    manager = InstanceManager(Settings(control_secret=SECRET, data_root=tmp_path), FakeDocker())
    client = TestClient(create_app(Settings(control_secret=SECRET, data_root=tmp_path), manager))
    payload = request("api-user").model_dump(by_alias=True)
    payload["connectorToken"] = "connector-token-that-is-long-enough"
    payload["yunworkApiKey"] = "sk-test-secret-key"
    assert client.get("/healthz").json() == {"ok": True}
    unauthorized = client.post("/v1/instances", json=payload)
    assert unauthorized.status_code == 401, unauthorized.text
    headers = {"Authorization": f"Bearer {SECRET}"}
    response = client.post("/v1/instances", json=payload, headers=headers)
    assert response.status_code == 200
    assert "sk-test-secret-key" not in response.text
    assert "connector-token" not in response.text
    instance_id = response.json()["instanceId"]
    assert client.get(f"/v1/instances/{instance_id}", headers=headers).status_code == 200
    assert client.delete(f"/v1/instances/{instance_id}", headers=headers).status_code == 200
    assert client.get(f"/v1/instances/{instance_id}", headers=headers).status_code == 404
