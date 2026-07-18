"""
Tests de la Fase U: datos de toma y previsualización de la pre-edición.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.exif_info import read_exif
from services.preview_render import (
    _aplicar_exposicion, _aplicar_wb, _aplicar_recorte, render_preview)
from tests.test_lightroom_sync import _minimal_jpeg


# --- EXIF ---

def test_sin_exif_devuelve_vacio(tmp_path):
    """Un JPEG mínimo sin metadatos no debe romper: devuelve {}."""
    assert read_exif(str(_minimal_jpeg(tmp_path))) == {}


def test_archivo_inexistente_no_rompe(tmp_path):
    assert read_exif(str(tmp_path / "no_existe.jpg")) == {}


# --- Render de la pre-edición ---

def _img(v=100):
    return np.full((60, 80, 3), v, dtype=np.uint8)


def test_exposicion_un_stop_duplica():
    salida = _aplicar_exposicion(_img(50), 1.0)
    assert int(salida[0, 0, 0]) == 100          # +1 EV = x2


def test_exposicion_satura_sin_desbordar():
    salida = _aplicar_exposicion(_img(200), 2.0)
    assert int(salida[0, 0, 0]) == 255          # se acota, no da la vuelta


def test_exposicion_cero_no_toca_nada():
    original = _img(123)
    assert np.array_equal(_aplicar_exposicion(original, 0.0), original)


def test_wb_calido_sube_rojo_y_baja_azul():
    salida = _aplicar_wb(_img(100), temp=50, tint=0)
    assert salida[0, 0, 0] > 100 and salida[0, 0, 2] < 100


def test_recorte_normalizado_recorta():
    salida = _aplicar_recorte(_img(), {"left": 0.25, "top": 0.0, "right": 0.75, "bottom": 1.0})
    assert salida.shape[1] == 40 and salida.shape[0] == 60   # la mitad del ancho


def test_recorte_degenerado_no_rompe():
    """Un rectángulo inválido devuelve la imagen entera, no una vacía."""
    salida = _aplicar_recorte(_img(), {"left": 0.5, "top": 0.5, "right": 0.5, "bottom": 0.5})
    assert salida.size > 0


def test_preview_de_archivo_ilegible_es_none(tmp_path):
    assert render_preview(str(tmp_path / "no_existe.jpg")) is None
