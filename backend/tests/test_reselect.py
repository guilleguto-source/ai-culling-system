import pytest
from fastapi.testclient import TestClient
from main import app, _job_state
import time

client = TestClient(app)

def test_reselect_endpoint_starts_job():
    # Debe comportarse igual que /cull, devolviendo job_id
    response = client.post("/reselect", json={"directory": "."})
    
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "started"
    assert data["mode"] == "cull"
    
    # Clean up the job state since background task might run
    _job_state["status"] = "idle"
