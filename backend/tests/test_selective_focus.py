"""Tests de enfoque selectivo: rostros suaves con sujeto nítido NO es error."""
import sys
from pathlib import Path

import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.technical_quality import (
    max_region_sharpness,
    _cpbd_sharpness,
    evaluate_blur,
    evaluate_technical_quality,
)


def _textured_block(h, w, seed=1):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 255, size=(h, w, 3), dtype=np.uint8)


def test_enfoque_selectivo_detecta_bloque_nitido():
    """Imagen mayormente desenfocada pero con una zona nítida (el 'ramo')."""
    img = cv2.GaussianBlur(_textured_block(600, 900), (31, 31), 10)
    img[400:600, 0:300] = _textured_block(200, 300, seed=2)   # zona nítida
    assert max_region_sharpness(img) > 500


def test_toma_erronea_nada_nitido():
    """Todo el cuadro movido: ningún bloque nítido."""
    img = cv2.GaussianBlur(_textured_block(600, 900), (31, 31), 10)
    assert max_region_sharpness(img) < 50


def test_imagen_nitida_valor_alto():
    assert max_region_sharpness(_textured_block(400, 600)) > 1000


def test_cpbd_sharpness_distinguishes_bokeh_from_blurry():
    """Prueba que CPBD distingue un objeto nítido con bokeh de una foto completamente borrosa."""
    # Objeto nítido con bordes claros sobre fondo desenfocado
    img_bokeh = np.zeros((400, 400), dtype=np.uint8)
    cv2.circle(img_bokeh, (200, 200), 50, 255, -1)
    cv2.rectangle(img_bokeh, (170, 170), (230, 230), 128, -1)

    # Versión completamente borrosa
    img_blurry = cv2.GaussianBlur(img_bokeh, (41, 41), 12.0)

    score_bokeh = _cpbd_sharpness(img_bokeh)
    score_blurry = _cpbd_sharpness(img_blurry)

    assert score_bokeh > 0.5, f"CPBD en bokeh debería ser alto, dio {score_bokeh}"
    assert score_blurry < 0.1, f"CPBD en borrosa debería ser bajo, dio {score_blurry}"


def test_cpbd_rescues_selective_focus_portrait():
    """Verifica que evaluate_blur rescata una foto con sujeto nítido pero fondo desenfocado."""
    # Creamos un bloque nítido (sujeto)
    img_rgb = np.zeros((300, 300, 3), dtype=np.uint8)
    cv2.circle(img_rgb, (150, 150), 40, (255, 255, 255), -1)
    cv2.rectangle(img_rgb, (130, 130), (170, 170), (100, 200, 150), -1)

    # Evaluamos con un umbral alto de Laplaciano
    is_blurry, blur_score, label, cpbd_score = evaluate_blur(
        img_rgb=img_rgb,
        scene_type="detail",
        face_bboxes=[],
        saliency_region=(0, 0, 300, 300),
        blur_threshold=1000.0,  # Laplaciano no alcanzará 1000 en fondo negro
        iso=100,
    )
    # Gracias a CPBD >= 0.25, la foto debe ser rescatada (is_blurry = False)
    assert not is_blurry, "La foto con sujeto nítido debió ser rescatada por CPBD"
    assert cpbd_score >= 0.25
