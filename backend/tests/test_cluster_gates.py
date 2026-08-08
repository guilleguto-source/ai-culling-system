"""Tests de los gates técnicos de cluster (descarte relativo, nunca absoluto)."""
import sys
from pathlib import Path

import numpy as np
import cv2
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.cluster_gates import apply_technical_gates
from services.face_assessment import compute_face_sharpness


# --- apply_technical_gates ---

def test_gate_ojos_descarta_si_hay_alternativa():
    indices = [0, 1, 2]
    attrs = [
        [{"valid": True, "ear": 0.3, "blink": 0.1}],  # Abierto
        [{"valid": True, "ear": 0.1, "blink": 0.8}],  # Cerrado
        [{"valid": True, "ear": 0.3, "blink": 0.1}],  # Abierto
    ]
    sharp = [[], [], []]
    assert apply_technical_gates(indices, attrs, sharp) == [0, 2]


def test_gate_ojos_no_descarta_si_todas_cerradas():
    indices = [0, 1]
    attrs = [
        [{"valid": True, "ear": 0.1, "blink": 0.8}],
        [{"valid": True, "ear": 0.1, "blink": 0.8}],
    ]
    sharp = [[], []]
    assert apply_technical_gates(indices, attrs, sharp) == [0, 1]


def test_gate_nitidez_descarta_cara_borrosa():
    indices = [0, 1, 2]
    attrs = [
        [{"valid": True, "ear": 0.3}],
        [{"valid": True, "ear": 0.3}],
        [{"valid": True, "ear": 0.3}],
    ]
    # Imagen 1 tiene una cara muy borrosa (10) frente a mediana ~200 → umbral 100
    sharp = [[220.0, 210.0], [10.0, 250.0], [190.0]]
    assert apply_technical_gates(indices, attrs, sharp) == [0, 2]


def test_gate_nitidez_no_descarta_si_todas_borrosas():
    indices = [0, 1]
    attrs = [[{"valid": True, "ear": 0.3}], [{"valid": True, "ear": 0.3}]]
    # Ambas igual de borrosas: mediana*0.5 no elimina a ninguna
    sharp = [[12.0], [10.0]]
    assert apply_technical_gates(indices, attrs, sharp) == [0, 1]


def test_fotos_sin_caras_no_participan_del_gate_nitidez():
    indices = [0, 1, 2]
    attrs = [[{"valid": True, "ear": 0.3}], [], [{"valid": True, "ear": 0.3}]]
    sharp = [[200.0], [], [5.0]]  # la 1 no tiene caras
    result = apply_technical_gates(indices, attrs, sharp)
    assert 1 in result           # se conserva
    assert 2 not in result       # cara borrosa descartada


def test_cluster_de_una_foto_pasa_directo():
    assert apply_technical_gates([7], [[{"valid": True, "ear": 0.1}]] * 8, [[]] * 8) == [7]


def test_gates_combinados_nunca_devuelven_vacio():
    indices = [0, 1]
    attrs = [
        [{"valid": True, "ear": 0.1}],
        [{"valid": True, "ear": 0.1}],
    ]
    sharp = [[5.0], [4.0]]
    result = apply_technical_gates(indices, attrs, sharp)
    assert result == [0, 1]


# --- compute_face_sharpness ---

def _synthetic_face_image(blur_face: bool) -> tuple[np.ndarray, list[list[int]]]:
    """Imagen con textura de ruido; la 'cara' es una región central,
    opcionalmente desenfocada con blur gaussiano."""
    rng = np.random.default_rng(42)
    img = rng.integers(0, 255, size=(200, 200, 3), dtype=np.uint8)
    bbox = [60, 60, 80, 80]
    if blur_face:
        x, y, w, h = bbox
        img[y:y + h, x:x + w] = cv2.GaussianBlur(img[y:y + h, x:x + w], (21, 21), 8)
    return img, [bbox]


def test_sharpness_cara_nitida_mayor_que_borrosa():
    img_sharp, bboxes = _synthetic_face_image(blur_face=False)
    img_blur, _ = _synthetic_face_image(blur_face=True)
    s_sharp = compute_face_sharpness(img_sharp, bboxes)[0]
    s_blur = compute_face_sharpness(img_blur, bboxes)[0]
    assert s_sharp > s_blur * 3


def test_sharpness_sin_caras_devuelve_vacio():
    img, _ = _synthetic_face_image(blur_face=False)
    assert compute_face_sharpness(img, []) == []


def test_sharpness_bbox_fuera_de_rango_no_crashea():
    img, _ = _synthetic_face_image(blur_face=False)
    scores = compute_face_sharpness(img, [[190, 190, 50, 50]])
    assert len(scores) == 1 and scores[0] >= 0.0


def test_vip_face_weighting_preserves_photo_when_background_face_blinks():
    """
    Si en la foto 0 el protagonista (VIP) tiene ojos abiertos y una persona al fondo pestañea,
    pero en la foto 1 el protagonista pestañea, la foto 0 DEBE ganar y la foto 1 ser descartada.
    """
    indices = [0, 1]
    # Foto 0: Cara 0 (VIP, área 200x200) ojos abiertos; Cara 1 (fondo, área 30x30) ojos cerrados
    # Foto 1: Cara 0 (VIP, área 200x200) ojos cerrados; Cara 1 (fondo, área 30x30) ojos abiertos
    attrs = [
        [{"valid": True, "ear": 0.3, "blink": 0.1}, {"valid": True, "ear": 0.1, "blink": 0.9}],
        [{"valid": True, "ear": 0.1, "blink": 0.9}, {"valid": True, "ear": 0.3, "blink": 0.1}],
    ]
    bboxes = [
        [[100, 100, 200, 200], [500, 50, 30, 30]],
        [[100, 100, 200, 200], [500, 50, 30, 30]],
    ]
    sharp = [[200.0, 150.0], [200.0, 150.0]]
    result = apply_technical_gates(indices, attrs, sharp, bboxes)
    assert result == [0]

