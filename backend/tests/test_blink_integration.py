"""
Integración del blink classifier ONNX (Fase 4) en analyze_photo.

Regresión que cubre: el código asignaba `a.eyes_closed = ...` pero eyes_closed
es un @property sin setter en FaceAttributes → AttributeError apenas existiera
blink_detector.onnx. Nunca se había probado con el modelo "presente".
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services import analysis as analysis_mod
from services import face_mesh
from services.face_mesh import FaceAttributes


def _record(tmp_path):
    arr = np.full((120, 160, 3), 128, dtype=np.uint8)
    return SimpleNamespace(path=str(tmp_path / "f.jpg"), filename="f.jpg",
                           is_raw=False, error="", thumb_ai=arr,
                           linked_raw_path=None, phash="", exif_datetime="",
                           iso=100)


@pytest.fixture()
def caras_fake(monkeypatch):
    """Dos caras válidas con geometría 'ojos abiertos' (ear alto, blink bajo)."""
    attrs = [
        FaceAttributes(valid=True, ear=0.30, blink=0.1, smile=0.5, gaze_out=0.1, yaw=0.0),
        FaceAttributes(valid=True, ear=0.30, blink=0.1, smile=0.5, gaze_out=0.1, yaw=0.0),
    ]
    monkeypatch.setattr(face_mesh, "is_available", lambda: True)
    monkeypatch.setattr(face_mesh, "analyze_faces", lambda arr, bboxes, max_faces=8: attrs)
    monkeypatch.setattr(
        analysis_mod, "classify_scene",
        lambda arr, det: SimpleNamespace(
            scene_type=SimpleNamespace(value="portrait"),
            face_bboxes=[[10, 10, 30, 30], [60, 10, 30, 30]],
            eye_landmarks=[[(15, 20), (30, 20)], [(65, 20), (80, 20)]]))
    return attrs


def _analyze(tmp_path):
    return analysis_mod.analyze_photo(
        index=0, record=_record(tmp_path), face_detector=object(),
        eye_session=None, blur_threshold=100.0,
        detect_closed_eyes=True, pre_edit_enabled=False)


def test_con_modelo_blink_no_revienta_y_manda_su_probabilidad(
        tmp_path, caras_fake, monkeypatch):
    from services import blink_classifier
    monkeypatch.setattr(blink_classifier, "is_available", lambda: True)
    # cara 0 cerrada según ONNX (prob abierto 0.1), cara 1 abierta (0.9)
    monkeypatch.setattr(blink_classifier, "predict_eyes_open",
                        lambda arr, bboxes, lms: [0.1, 0.9])

    a = _analyze(tmp_path)   # antes: AttributeError aquí

    # score cara0 = 0.1*0.7 + 1.0*0.3 = 0.37 < 0.45 → cerrada
    # score cara1 = 0.9*0.7 + 1.0*0.3 = 0.93 → abierta
    assert a.closed_eyes_count == 1
    assert a.any_closed_eyes is True
    # la decisión híbrida por cara queda persistida en face_attrs
    assert [d["closed_hybrid"] for d in a.face_attrs] == [True, False]


def test_sin_modelo_blink_fallback_mediapipe_intacto(tmp_path, caras_fake, monkeypatch):
    from services import blink_classifier
    monkeypatch.setattr(blink_classifier, "is_available", lambda: False)

    a = _analyze(tmp_path)

    # geometría dice abiertas (ear 0.30 > umbral): nada cerrado
    assert a.closed_eyes_count == 0
    assert [d["closed_hybrid"] for d in a.face_attrs] == [False, False]
    assert a.valid_face_count == 2
