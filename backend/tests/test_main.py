from fastapi.testclient import TestClient
from main import app
import os

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.0.0"}

def test_settings_endpoints():
    get_res = client.get("/settings")
    assert get_res.status_code == 200
    assert "model_name" in get_res.json()

    payload = {
        "model_name": "yolov8m",
        "confidence_threshold": 0.65,
        "output_dir": "./culled_test"
    }
    post_res = client.post("/settings", json=payload)
    assert post_res.status_code == 200
    assert post_res.json()["success"] is True
    assert post_res.json()["settings"]["model_name"] == "yolov8m"
    assert post_res.json()["settings"]["confidence_threshold"] == 0.65
    assert post_res.json()["settings"]["output_dir"] == "./culled_test"

def test_ingest_and_status():
    payload = {
        "paths": ["path/to/img1.jpg", "path/to/img2.jpg"]
    }
    ingest_res = client.post("/ingest", json=payload)
    assert ingest_res.status_code == 200
    assert "jobId" in ingest_res.json()

    status_res = client.get("/status")
    assert status_res.status_code == 200
    assert "jobId" in status_res.json()
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
