"""Tests de los endpoints de calibración."""
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from services import calibration_store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(calibration_store, "DB_PATH", tmp_path / "cal.db")
    import main
    return TestClient(main.app)


def test_label_guarda_y_stats_reporta(client, tmp_path, monkeypatch):
    # sin bbox no se calcula embedding (evita leer la foto en el test)
    r = client.post("/calibration/label", json={
        "photo_path": "C:/ev/a.jpg", "face_index": 0, "face_bbox": [],
        "labels": {"eyes": "abiertos", "gaze": "fuera"},
        "predictions": {"eyes": "cerrados", "gaze": "fuera"},
    })
    assert r.status_code == 200
    assert r.json()["guardadas"] == 2

    s = client.get("/calibration/stats").json()
    assert s["total"] == 2
    # el detector acertó en gaze y falló en eyes
    assert s["por_atributo"]["eyes"]["precision"] == 0.0
    assert s["por_atributo"]["gaze"]["precision"] == 1.0


def test_label_ignora_valores_invalidos(client):
    r = client.post("/calibration/label", json={
        "photo_path": "C:/ev/b.jpg", "face_index": 0, "face_bbox": [],
        "labels": {"eyes": "guiñando", "pelo": "rizado", "gaze": "camara"},
        "predictions": {},
    })
    assert r.json()["guardadas"] == 1     # solo gaze era válido


def test_candidates_directorio_invalido(client):
    r = client.get("/calibration/candidates", params={"directory": "C:/no-existe"})
    assert r.status_code == 400


def test_candidates_sin_analisis_devuelve_vacio(client, tmp_path, monkeypatch):
    from services import analysis_store
    monkeypatch.setattr(analysis_store, "ANALYSIS_DIR", tmp_path / "an")
    ev = tmp_path / "ev"
    ev.mkdir()
    Image.fromarray(np.zeros((50, 50, 3), dtype=np.uint8)).save(ev / "x.jpg")
    r = client.get("/calibration/candidates", params={"directory": str(ev)})
    assert r.status_code == 200
    assert r.json()["candidatas"] == []


def test_face_crop_foto_inexistente(client):
    r = client.get("/calibration/face",
                   params={"path": "C:/no-existe.jpg", "x": 0, "y": 0, "w": 10, "h": 10})
    assert r.status_code == 404
