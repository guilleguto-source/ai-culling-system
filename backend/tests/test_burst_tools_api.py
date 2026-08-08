"""Tests para los endpoints de herramientas de ráfaga y duelo UX (Fase 3.3)."""
import sys
from pathlib import Path
from fastapi.testclient import TestClient
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app, _job_state


@pytest.fixture
def client():
    return TestClient(app)


def test_face_crops_empty_cluster(client):
    _job_state["results"] = []
    res = client.get("/bursts/999/face_crops")
    assert res.status_code == 200
    data = res.json()
    assert data["cluster_id"] == 999
    assert data["people"] == []


