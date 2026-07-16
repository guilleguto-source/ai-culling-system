"""Tests de la geometría de auto-crop (propuestas de reencuadre no destructivo)."""
import sys
from pathlib import Path

import numpy as np
import cv2
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.auto_crop import (
    propose_crop, detect_horizon_angle, CropProposal,
    LEVEL_LIMITS, MAX_LEVEL_ANGLE,
)

W, H = 1600, 1067  # típico 3:2


def _face(cx: float, cy: float, size: int = 160) -> list[int]:
    """Bbox de cara centrada en la fracción (cx, cy) de la imagen."""
    return [int(cx * W - size / 2), int(cy * H - size / 2), size, size]


def _lms(face: list[int], nose_offset: float = 0.0) -> list[list[int]]:
    """Landmarks sintéticos: ojos + nariz (offset relativo a distancia interocular)."""
    x, y, fw, fh = face
    le = [x + int(fw * 0.3), y + int(fh * 0.4)]
    re = [x + int(fw * 0.7), y + int(fh * 0.4)]
    eye_dist = re[0] - le[0]
    nose = [int((le[0] + re[0]) / 2 + nose_offset * eye_dist), y + int(fh * 0.65)]
    return [le, re, nose, [le[0], y + fh - 10], [re[0], y + fh - 10]]


# --- Grupos: solo nivelado ---

def test_grupo_sin_inclinacion_no_propone():
    faces = [_face(0.3, 0.5), _face(0.5, 0.5), _face(0.7, 0.5)]
    assert propose_crop("portrait", faces, [], None, (H, W), "agresivo", horizon_angle=0.2) is None


def test_grupo_inclinado_solo_nivela():
    faces = [_face(0.3, 0.5), _face(0.5, 0.5), _face(0.7, 0.5)]
    prop = propose_crop("portrait", faces, [], None, (H, W), "agresivo", horizon_angle=3.0)
    assert prop is not None
    assert prop.angle == -3.0
    # Recorte simétrico y mínimo (solo el que exige la rotación)
    assert prop.left == pytest.approx(1.0 - prop.right, abs=1e-6)
    assert prop.crop_amount <= 0.05


def test_angulo_excesivo_no_se_nivela():
    faces = [_face(0.3, 0.5), _face(0.5, 0.5), _face(0.7, 0.5)]
    assert propose_crop("portrait", faces, [], None, (H, W), "medio",
                        horizon_angle=MAX_LEVEL_ANGLE + 3) is None


# --- Retratos: recomposición ---

def test_cara_descentrada_se_acerca_a_tercios():
    face = _face(0.5, 0.5)   # centrada → el tercio más cercano es 1/3 o 2/3
    prop = propose_crop("portrait", [face], [_lms(face)], None, (H, W), "medio")
    assert prop is not None
    # El sujeto se ACERCA a un punto fuerte (con presupuesto medio el tercio
    # exacto puede no ser alcanzable; se exige mejora clara, no exactitud).
    s = prop.right - prop.left
    achieved_x = (0.5 - prop.left) / s
    dist_before = min(abs(0.5 - 1/3), abs(0.5 - 2/3))
    dist_after = min(abs(achieved_x - 1/3), abs(achieved_x - 2/3))
    assert dist_after < dist_before / 2
    assert prop.crop_amount <= LEVEL_LIMITS["medio"] + 1e-6


def test_nivel_minimo_recorta_menos_que_agresivo():
    face = _face(0.45, 0.45)
    p_min = propose_crop("portrait", [face], [_lms(face)], None, (H, W), "minimo")
    p_agr = propose_crop("portrait", [face], [_lms(face)], None, (H, W), "agresivo")
    for p, lim in ((p_min, "minimo"), (p_agr, "agresivo")):
        if p is not None:
            assert p.crop_amount <= LEVEL_LIMITS[lim] + 1e-6


def test_mirada_deja_aire_hacia_donde_mira():
    # Nariz desplazada a la izquierda → mira a la izquierda → sujeto al tercio derecho
    face = _face(0.5, 0.4)
    prop = propose_crop("portrait", [face], [_lms(face, nose_offset=-0.3)], None, (H, W), "agresivo")
    assert prop is not None
    s = prop.right - prop.left
    achieved_x = (0.5 - prop.left) / s
    assert achieved_x > 0.5  # colocado a la derecha, aire a la izquierda


def test_cara_al_borde_no_se_corta():
    face = _face(0.06, 0.5, size=180)   # pegada al borde izquierdo
    prop = propose_crop("portrait", [face], [_lms(face)], None, (H, W), "agresivo")
    if prop is not None:
        x, y, fw, fh = face
        assert (x - fw * 0.5) / W >= prop.left - 1e-6


def test_cara_ya_en_tercios_no_propone():
    face = _face(1/3, 1/3)
    prop = propose_crop("portrait", [face], [_lms(face)], None, (H, W), "minimo")
    assert prop is None


# --- Detalles: saliencia ---

def test_detalle_saliencia_a_tercios():
    sal = (int(0.45 * W) - 100, int(0.5 * H) - 100, 200, 200)
    prop = propose_crop("detail", [], [], sal, (H, W), "medio")
    assert prop is not None
    assert prop.crop_amount <= LEVEL_LIMITS["medio"] + 1e-6


def test_sin_sujeto_ni_angulo_no_propone():
    assert propose_crop("detail", [], [], None, (H, W), "agresivo") is None


def test_nivel_invalido_no_propone():
    face = _face(0.45, 0.45)
    assert propose_crop("portrait", [face], [_lms(face)], None, (H, W), "off") is None


# --- Horizonte ---

def _horizon_image(angle_deg: float) -> np.ndarray:
    """Cielo blanco / suelo negro separados por una línea inclinada."""
    img = np.zeros((600, 900), dtype=np.uint8)
    for x in range(900):
        y_line = int(300 + math_tan(angle_deg) * (x - 450))
        img[:max(0, min(600, y_line)), x] = 220
    return img


def math_tan(deg: float) -> float:
    import math
    return math.tan(math.radians(deg))


def test_horizonte_3_grados():
    ang = detect_horizon_angle(_horizon_image(3.0))
    assert ang is not None
    assert ang == pytest.approx(3.0, abs=0.8)


def test_horizonte_nivelado_detecta_cero():
    ang = detect_horizon_angle(_horizon_image(0.0))
    assert ang is not None
    assert abs(ang) < 0.5


def test_sin_lineas_devuelve_none():
    rng = np.random.default_rng(3)
    noise = rng.integers(0, 255, size=(600, 900), dtype=np.uint8)
    noise = cv2.GaussianBlur(noise, (31, 31), 12)  # sin bordes largos
    assert detect_horizon_angle(noise) is None


# --- CropProposal ---

def test_cambio_minimo_no_significativo():
    p = CropProposal(0.005, 0.005, 0.995, 0.995, 0.0)
    assert not p.is_meaningful()
