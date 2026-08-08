"""
test_advanced_router.py — Tests para los endpoints del router /advanced.
"""
from fastapi.testclient import TestClient
from main import app
from core.job_manager import job_manager

client = TestClient(app)


def test_lut_status_endpoint():
    res = client.get("/advanced/lut_status")
    assert res.status_code == 200
    data = res.json()
    assert "available_luts" in data
    assert "current_config" in data


def test_list_luts_endpoint():
    res = client.get("/advanced/luts")
    assert res.status_code == 200
    data = res.json()
    assert "luts" in data
    assert len(data["luts"]) > 0


def test_apply_lut_no_results():
    job_manager.reset()
    res = client.post("/advanced/apply_lut", json={"strength": 0.8})
    assert res.status_code == 400


def test_relight_faces_no_results():
    job_manager.reset()
    res = client.post("/advanced/relight_faces", json={"intensity": 0.5})
    assert res.status_code == 400


def test_skin_retouch_no_results():
    job_manager.reset()
    res = client.post("/advanced/skin_retouch", json={"smoothness": 0.5})
    assert res.status_code == 400
