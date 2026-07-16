"""Tests de pre-edición: exposición por piel, WB por prioridades y sesiones de luz."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.pre_edit import (
    measure_luminance, estimate_wb, segment_light_sessions, compute_pre_edits,
    PhotoSignature, MAX_EXPOSURE, MAX_WB, SESSION_EXPOSURE_BAND, BREAK_RUN,
    SKIN_TARGET_MIN, TARGET_MID,
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


# --- Medición de luminancia ---

def test_medicion_piel_y_global():
    img, bboxes = _with_face(bg=(30, 30, 30), skin=(190, 150, 128))
    skin, glob = measure_luminance(img, bboxes)
    assert skin is not None and skin > glob   # la piel es más clara que el fondo


def test_medicion_sin_caras():
    skin, glob = measure_luminance(_img((128, 128, 128)), [])
    assert skin is None and 0.1 < glob < 0.35


def _sig_lum(i, skin, glob=0.18, people=True):
    return PhotoSignature(index=i, has_people=people, wb=(0.0, 0.0),
                          skin_lum=skin, global_lum=glob)


def test_piel_oscura_no_se_aclara():
    """Sesión de piel oscura bien expuesta (lum lineal ~0.07): el objetivo es
    la mediana de la sesión, no un target de piel clara → corrección ≈ 0."""
    sigs = [_sig_lum(i, 0.07) for i in range(8)]
    edits = compute_pre_edits(sigs, bias=0.0)
    assert all(abs(edits[i]["Exposure2012"]) <= 0.05 for i in range(8))


def test_foto_subexpuesta_en_sesion_oscura_se_corrige():
    sigs = [_sig_lum(i, 0.07) for i in range(8)]
    sigs.append(_sig_lum(8, 0.02))    # misma gente, foto subexpuesta
    edits = compute_pre_edits(sigs, bias=0.0)
    assert edits[8]["Exposure2012"] > 0.4          # se sube hacia la sesión
    assert edits[8]["Exposure2012"] <= SESSION_EXPOSURE_BAND + 0.01


def test_sesion_entera_subexpuesta_se_levanta_al_minimo_sano():
    """Piel bajo SKIN_TARGET_MIN: ahí sí es subexposición, no tono de piel."""
    sigs = [_sig_lum(i, 0.02) for i in range(6)]
    edits = compute_pre_edits(sigs, bias=0.0)
    import math
    expected = math.log2(SKIN_TARGET_MIN / 0.02)
    assert edits[0]["Exposure2012"] == pytest.approx(expected, abs=0.1)


def test_sin_caras_usa_global():
    sigs = [PhotoSignature(index=i, has_people=False, wb=(0.0, 0.0),
                           skin_lum=None, global_lum=0.05) for i in range(6)]
    edits = compute_pre_edits(sigs, bias=0.0)
    assert edits[0]["Exposure2012"] > 0.5          # global oscuro → sube a tono medio


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
    return PhotoSignature(index=i, has_people=people, wb=wb,
                          skin_lum=None, global_lum=TARGET_MID * (2.0 ** ev))


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
    edits = compute_pre_edits(sigs, bias=0.0)
    assert edits[0]["IncrementalTemperature"] == pytest.approx(6.0)
    assert edits[0]["IncrementalTint"] == pytest.approx(2.0)


def test_detalle_con_luz_distinta_se_edita_aparte():
    sigs = [_sig(i, (2.0, 1.0), people=True) for i in range(8)]
    sigs.append(_sig(8, (14.5, 1.0), people=False))   # detalle: +12.5 de desvío
    edits = compute_pre_edits(sigs, bias=0.0)
    assert edits[8]["IncrementalTemperature"] == pytest.approx(14.5)
    assert edits[0]["IncrementalTemperature"] == pytest.approx(2.0)


def test_exposicion_bias_y_banda_de_sesion():
    sigs = [_sig(i, (0.0, 0.0)) for i in range(6)]
    sigs.append(_sig(6, (0.0, 0.0), ev=-1.4))   # foto muy oscura (necesita +1.4)
    edits = compute_pre_edits(sigs, bias=0.3)
    assert edits[0]["Exposure2012"] == pytest.approx(0.3)
    # La disparada queda acotada a mediana(0.0) + 0.7 + bias 0.3 = 1.0
    assert edits[6]["Exposure2012"] == pytest.approx(SESSION_EXPOSURE_BAND + 0.3)


def test_wb_clamp_final_con_sesgo_de_preset():
    sigs = [_sig(i, (13.0, -13.0)) for i in range(6)]
    edits = compute_pre_edits(sigs, bias=0.0, preset_wb_bias=(5.0, 5.0))
    assert edits[0]["IncrementalTemperature"] == MAX_WB          # 18 → clamp 15
    assert edits[0]["IncrementalTint"] == pytest.approx(-8.0)    # -13+5


def test_sesion_chica_hereda_de_vecina():
    sigs = [_sig(i, (6.0, 2.0)) for i in range(10)]
    sigs += [_sig(10 + i, (-20.0, 12.0)) for i in range(BREAK_RUN)]  # sesión nueva de 4 (<5 votos)
    edits = compute_pre_edits(sigs, bias=0.0)
    # La sesión chica hereda el WB de la grande
    assert edits[12]["IncrementalTemperature"] == pytest.approx(6.0)
