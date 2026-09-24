from fastapi.testclient import TestClient
from main import app
import os
from pathlib import Path

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    # el proceso recién importado nunca debe reportarse desactualizado
    assert data["stale_code"] is False

def test_settings_endpoints():
    get_res = client.get("/settings")
    assert get_res.status_code == 200
    assert "ratings_mapping" in get_res.json()

    payload = {
        "ratings_mapping": {
            "selected": {"stars": 2, "color": "Verde", "flag": "pick"}
        }
    }
    post_res = client.post("/settings", json=payload)
    assert post_res.status_code == 200
    assert post_res.json()["success"] is True
    assert post_res.json()["settings"]["ratings_mapping"]["selected"]["stars"] == 2

def test_ingest_and_status(tmp_path):
    # create a mock directory so the check in start_ingest passes
    payload = {
        "directory": str(tmp_path),
        "mode": "cull"
    }
    ingest_res = client.post("/ingest", json=payload)
    assert ingest_res.status_code == 200
    assert "job_id" in ingest_res.json()

    status_res = client.get("/status")
    assert status_res.status_code == 200
    assert "job_id" in status_res.json()
    assert "status" in status_res.json()
    assert "progress" in status_res.json()

def test_shutdown_endpoint(monkeypatch):
    killed = []
    def mock_kill(pid, sig):
        killed.append((pid, sig))
    
    monkeypatch.setattr(os, "kill", mock_kill)

    response = client.post("/shutdown")
    assert response.status_code == 200
    assert response.json() == {"success": True}


def test_vip_subjects_endpoints(tmp_path):
    d = str(tmp_path)
    res = client.get(f"/vip-subjects?directory={d}")
    assert res.status_code == 200
    assert "subjects" in res.json()
    assert isinstance(res.json()["subjects"], list)

    rename_res = client.post("/vip-subjects/rename", json={
        "directory": d,
        "identity_id": 1,
        "name": "Novia"
    })
    assert rename_res.status_code == 200
    assert rename_res.json()["name"] == "Novia"
    assert rename_res.json()["status"] == "success"

