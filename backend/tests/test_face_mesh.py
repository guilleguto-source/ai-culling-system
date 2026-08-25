"""
Tests de face_mesh (MediaPipe): degradación, filtro de caras falsas y umbrales.

Contexto medido en el evento real que justifica este módulo:
- eye_state.onnx daba 97% de falsos "ojos cerrados"; el mismo ojo devolvía
  0.00 u 0.87 según el recorte, y subir a 4000px no lo arreglaba.
- MediaPipe sobre recortes de YuNet: en IMG_8628 YuNet detectó 43 "caras"
  (decoración) y MediaPipe validó solo 7; en IMG_8375 dio 0 ojos cerrados,
  que coincide con la verdad de campo del fotógrafo.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.legacy import face_mesh
from services.legacy.face_mesh import FaceAttributes


# --- Umbrales sobre el dataclass (sin depender de mediapipe) ---

def test_cara_invalida_no_afirma_nada():
    """Si MediaPipe no encontró cara, no se afirma nada sobre ella."""
    a = FaceAttributes(valid=False, ear=0.0, blink=1.0, smile=1.0, gaze_out=1.0)
    assert not a.eyes_closed
    assert not a.looking_away
    assert not a.smiling


def test_ojos_cerrados_por_geometria():
    a = FaceAttributes(valid=True, ear=0.10, blink=0.1)
    assert a.eyes_closed


def test_ojos_cerrados_por_blendshape():
    """El EAR puede fallar en perfil; el blendshape es la señal independiente."""
    a = FaceAttributes(valid=True, ear=0.25, blink=0.8)
    assert a.eyes_closed


def test_ojos_abiertos_caso_real_img8375():
    """Valores reales de IMG_8375 (verdad de campo: ojos ABIERTOS)."""
    for ear in (0.259, 0.309):
        a = FaceAttributes(valid=True, ear=ear, blink=0.19)
        assert not a.eyes_closed, f"EAR {ear} no debe ser 'cerrado'"


def test_mirada_fuera():
    assert FaceAttributes(valid=True, ear=0.3, gaze_out=0.5).looking_away
    assert FaceAttributes(valid=True, ear=0.3, yaw=0.7).looking_away
    assert not FaceAttributes(valid=True, ear=0.3, gaze_out=0.1, yaw=0.1).looking_away


def test_sonrisa():
    assert FaceAttributes(valid=True, smile=0.6).smiling
    assert not FaceAttributes(valid=True, smile=0.1).smiling


# --- Degradación ---

def test_sin_modelo_devuelve_invalidas(monkeypatch):
    monkeypatch.setattr(face_mesh, "_get_landmarker", lambda: None)
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    attrs = face_mesh.analyze_faces(img, [[10, 10, 50, 50], [100, 100, 60, 60]])
    assert len(attrs) == 2
    assert all(not a.valid for a in attrs)


def test_sin_caras_lista_vacia():
    assert face_mesh.analyze_faces(np.zeros((10, 10, 3), dtype=np.uint8), []) == []


def test_orden_preservado(monkeypatch):
    """analyze_faces respeta el orden de face_bboxes aunque procese por tamaño."""
    monkeypatch.setattr(face_mesh, "is_available", lambda: True)
    llamadas = []

    def fake(img, bbox):
        llamadas.append(bbox)
        return FaceAttributes(valid=True, ear=bbox[2] / 100.0)

    monkeypatch.setattr(face_mesh, "analyze_face", fake)
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    bboxes = [[0, 0, 10, 10], [0, 0, 90, 90], [0, 0, 50, 50]]
    attrs = face_mesh.analyze_faces(img, bboxes)
    # procesa de mayor a menor...
    assert llamadas[0][2] == 90
    # ...pero devuelve en el orden original
    assert [round(a.ear, 2) for a in attrs] == [0.10, 0.90, 0.50]


def test_max_faces_acota_el_coste(monkeypatch):
    monkeypatch.setattr(face_mesh, "is_available", lambda: True)
    monkeypatch.setattr(face_mesh, "analyze_face",
                        lambda img, b: FaceAttributes(valid=True))
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    bboxes = [[0, 0, i + 5, i + 5] for i in range(20)]
    attrs = face_mesh.analyze_faces(img, bboxes, max_faces=3)
    assert sum(1 for a in attrs if a.valid) == 3


# --- Modelo real (solo si está descargado) ---

@pytest.mark.skipif(not face_mesh.MODEL_PATH.exists(),
                    reason="face_landmarker.task no descargado")
def test_modelo_real_disponible():
    assert face_mesh.is_available()


@pytest.mark.skipif(not face_mesh.MODEL_PATH.exists(),
                    reason="face_landmarker.task no descargado")
def test_recorte_sin_cara_se_rechaza():
    """Ruido uniforme no es una cara: MediaPipe debe rechazarlo (esto es lo
    que filtra las 'caras' que YuNet ve en la decoración)."""
    rng = np.random.default_rng(3)
    img = rng.integers(0, 255, size=(400, 600, 3), dtype=np.uint8)
    a = face_mesh.analyze_face(img, [100, 100, 80, 80])
    assert not a.valid
