"""Tests del detector de personas (degradación sin modelo + inferencia real si está)."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services import person_detector as pd


def test_sin_modelo_devuelve_vacio(monkeypatch):
    monkeypatch.setattr(pd, "_get_session", lambda: None)
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    assert pd.detect_persons(img) == []
    assert pd.detect_persons(None) == []


@pytest.mark.skipif(not pd.MODEL_PATH.exists(), reason="person_yolov8n.onnx no descargado")
def test_deteccion_real_shapes():
    rng = np.random.default_rng(1)
    img = rng.integers(0, 255, size=(480, 640, 3), dtype=np.uint8)
    boxes = pd.detect_persons(img)   # ruido: no debe crashear; boxes válidas si hay
    for (x, y, w, h) in boxes:
        assert 0 <= x < 640 and 0 <= y < 480 and w > 0 and h > 0
