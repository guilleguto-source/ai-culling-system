"""Tests de pre-edición: exposición por piel, WB por prioridades y sesiones de luz."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.pre_edit import (
    estimate_exposure, estimate_wb, segment_light_sessions, compute_pre_edits,
    PhotoSignature, MAX_EXPOSURE, MAX_WB, SESSION_EXPOSURE_BAND, BREAK_RUN,
)


def _img(rgb: tuple[int, int, int], h=400, w=600) -> np.ndarray:
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = rgb
    return img


def _with_face(bg: tuple, skin: tuple) -> tuple[np.ndarray, list[list[int]]]:
    img = _img(bg)
    bbox = [200, 100, 160, 200]
    x, y, fw, fh = bbox
    img[y:y + fh, x:x + fw] = skin
    return img, [bbox]


# --- Exposición ---

def test_piel_oscura_sube_exposicion():
    img, bboxes = _with_face(bg=(30, 30, 30), skin=(90, 70, 60))   # piel subexpuesta
    stops = estimate_exposure(img, bboxes)
    assert stops > 0.5


def test_piel_quemada_baja_exposicion():
    img, bboxes = _with_face(bg=(200, 200, 200), skin=(250, 235, 225))
    stops = estimate_exposure(img, bboxes)
    assert stops < -0.3


def test_exposicion_ignora_fondo_si_hay_cara():
    # Fondo negro no debe subir la exposición si la piel está bien
    img_ok, bboxes = _with_face(bg=(5, 5, 5), skin=(185, 150, 130))  # piel ~correcta
    stops = estimate_exposure(img_ok, bboxes)
    assert abs(stops) < 0.4


def test_exposicion_clamp():
    img, bboxes = _with_face(bg=(0, 0, 0), skin=(6, 5, 5))
    assert estimate_exposure(img, bboxes) == MAX_EXPOSURE


def test_sin_caras_usa_global():
    oscuro = _img((25, 25, 25))
    assert estimate_exposure(oscuro, []) > 0.5


# --- WB ---

def test_wb_dominante_calida_enfria():
    """Foto con blancos amarillentos → temp negativa (hacia azul)."""
    img = _img((100, 100, 100))
    img[:80, :] = (250, 240, 200)   # zona "blanca" cálida no quemada... (>250 filtrado)
    img[:80, :] = (245, 235, 195)
    temp, tint = estimate_wb(img, [])
    assert temp < -3


def test_wb_dominante_verde_da_magenta():
    img = _img((90, 90, 90))
    img[:80, :] = (225, 245, 225)   # blancos verdosos
    temp, tint = estimate_wb(img, [])
    assert tint > 3


def test_wb_sin_blancos_ni_caras_no_vota():
    img = _img((180, 40, 40))       # todo saturado
    assert estimate_wb(img, []) is None


def test_wb_piel_neutra_correccion_pequena():
    img, bboxes = _with_face(bg=(20, 20, 20), skin=(190, 140, 118))  # B/R≈0.62, gm≈1.1
    temp, tint = estimate_wb(img, bboxes)
    assert abs(temp) < 6 and abs(tint) < 6


# --- Sesiones de luz ---

def _sig(i, wb, ev=0.0, people=True):
    return PhotoSignature(index=i, has_people=people, wb=wb, lum_ev=ev)


def test_detalles_no_rompen_sesion():
    """Escenario del usuario: 50 fotos de 6 grupos + detalles/close-ups en medio."""
    sigs = []
    n = 0
    for _ in range(25):
        sigs.append(_sig(n, (5.0, 2.0))); n += 1
    # 2 detalles con estimación rara y un close-up sin voto
    sigs.append(_sig(n, (25.0, -20.0), people=False)); n += 1
    sigs.append(_sig(n, None, people=False)); n += 1
    sigs.append(_sig(n, (28.0, -18.0), people=False)); n += 1
    for _ in range(25):
        sigs.append(_sig(n, (6.0, 3.0))); n += 1
    sessions = segment_light_sessions(sigs)
    assert len(sessions) == 1
    assert len(sessions[0]) == len(sigs)


def test_cambio_sostenido_corta_sesion():
    sigs = [_sig(i, (5.0, 2.0)) for i in range(20)]
    sigs += [_sig(20 + i, (-25.0, 15.0)) for i in range(BREAK_RUN + 6)]
    sessions = segment_light_sessions(sigs)
    assert len(sessions) == 2
    assert len(sessions[1]) >= BREAK_RUN


def test_cola_corta_desviada_no_corta():
    sigs = [_sig(i, (5.0, 2.0)) for i in range(20)]
    sigs += [_sig(20 + i, (-25.0, 15.0)) for i in range(BREAK_RUN - 1)]
    assert len(segment_light_sessions(sigs)) == 1


# --- compute_pre_edits ---

def test_pieles_mandan_el_wb_de_sesion():
    # 6 fotos de gente con WB ~(6,2) y 5 detalles con WB muy distinto (mismo EV,
    # desviación < umbral de corte): la sesión aplica el de las pieles.
    sigs = [_sig(i, (6.0, 2.0), people=True) for i in range(6)]
    sigs += [_sig(6 + i, (14.0, 10.0), people=False) for i in range(5)]
    edits = compute_pre_edits(sigs, [0.0] * len(sigs), bias=0.0)
    assert edits[0]["IncrementalTemperature"] == pytest.approx(6.0)
    assert edits[0]["IncrementalTint"] == pytest.approx(2.0)


def test_detalle_con_luz_distinta_se_edita_aparte():
    sigs = [_sig(i, (2.0, 1.0), people=True) for i in range(8)]
    sigs.append(_sig(8, (14.5, 1.0), people=False))   # detalle: +12.5 de desvío
    edits = compute_pre_edits(sigs, [0.0] * 9, bias=0.0)
    assert edits[8]["IncrementalTemperature"] == pytest.approx(14.5)
    assert edits[0]["IncrementalTemperature"] == pytest.approx(2.0)


def test_exposicion_bias_y_banda_de_sesion():
    sigs = [_sig(i, (0.0, 0.0)) for i in range(7)]
    stops = [0.0, 0.1, -0.1, 0.0, 0.05, 0.0, 1.4]   # la última se dispara
    edits = compute_pre_edits(sigs, stops, bias=0.3)
    assert edits[0]["Exposure2012"] == pytest.approx(0.3)
    # La disparada queda acotada a mediana(0.0) + 0.7 + bias 0.3 = 1.0
    assert edits[6]["Exposure2012"] == pytest.approx(SESSION_EXPOSURE_BAND + 0.3)


def test_wb_clamp_final_con_sesgo_de_preset():
    sigs = [_sig(i, (13.0, -13.0)) for i in range(6)]
    edits = compute_pre_edits(sigs, [0.0] * 6, bias=0.0, preset_wb_bias=(5.0, 5.0))
    assert edits[0]["IncrementalTemperature"] == MAX_WB          # 18 → clamp 15
    assert edits[0]["IncrementalTint"] == pytest.approx(-8.0)    # -13+5


def test_sesion_chica_hereda_de_vecina():
    sigs = [_sig(i, (6.0, 2.0)) for i in range(10)]
    sigs += [_sig(10 + i, (-20.0, 12.0)) for i in range(BREAK_RUN)]  # sesión nueva de 4 (<5 votos)
    edits = compute_pre_edits(sigs, [0.0] * len(sigs), bias=0.0)
    # La sesión chica hereda el WB de la grande
    assert edits[12]["IncrementalTemperature"] == pytest.approx(6.0)
