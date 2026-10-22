import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import main
import auth
import store


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(store, "_db", None)
    monkeypatch.setenv("AXIOM_API_KEY", "configured-gateway-key")
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    with TestClient(main.app) as test_client:
        yield test_client
    if store._db is not None:
        store._db.close()
        store._db = None


def test_debug_routes_are_post_only_and_disabled_without_admin_token(client):
    assert client.get("/api/debug/clear").status_code == 405
    assert client.post("/api/debug/clear").status_code == 404


def test_chat_and_openai_compat_require_gateway_auth(client):
    chat = client.post("/api/chat/stream", json={"messages": [{"role": "user", "content": "hi"}]})
    openai = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert chat.status_code == 401
    assert openai.status_code == 401


def test_production_can_use_issued_keys_without_shared_key(client, monkeypatch):
    monkeypatch.setattr(auth, "AUTH_REQUIRED", True)
    monkeypatch.setenv("AXIOM_API_KEY", "")
    issued = store.create_api_key("test", "axm_test_user_key")

    missing = client.get("/api/models")
    valid = client.get("/api/models", headers={"Authorization": f"Bearer {issued['key']}"})
    openai_models = client.get("/v1/models", headers={"Authorization": f"Bearer {issued['key']}"})

    assert missing.status_code == 503
    assert valid.status_code == 200
    assert openai_models.status_code == 200
    assert "axiom" in {model["id"] for model in openai_models.json()["data"]}


def test_admin_can_create_list_and_revoke_user_keys(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "admin-test-token")
    headers = {"X-Admin-Token": "admin-test-token"}

    created = client.post(
        "/api/admin/keys",
        json={"name": "workspace", "daily_requests": 20, "daily_tokens": 1000},
        headers=headers,
    )
    assert created.status_code == 200
    key = created.json()
    assert key["key"]
    assert any(item["id"] == key["id"] for item in client.get("/api/admin/keys", headers=headers).json())
    assert client.delete(f"/api/admin/keys/{key['id']}", headers=headers).json() == {"ok": True}
    assert client.delete(f"/api/admin/keys/{key['id']}", headers=headers).status_code == 404
