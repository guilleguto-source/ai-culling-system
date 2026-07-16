"""Tests de enfoque selectivo: rostros suaves con sujeto nítido NO es error."""
import sys
from pathlib import Path

import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.technical_quality import max_region_sharpness


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
