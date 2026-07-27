"""
Defaults del pre-revelado calibrados contra el historial real (2026-07-27).

Medido: el bias +0.3 acertaba en 21% vs 79% de no-tocar; el WB por piel opera
en espacio incremental que el usuario (RAW) no usa; el enderezado erraba 4.8°.
Estos tests fijan el comportamiento nuevo: banda muerta de exposición, auto_wb
apagable, y enderezado desacoplado del crop.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.pre_edit import PhotoSignature, compute_pre_edits


def _sig(i, skin=None, glob=0.18, people=True, wb=(0.0, 0.0), clip=0.0):
    return PhotoSignature(index=i, has_people=people, wb=wb,
                          skin_lum=skin, global_lum=glob, clip_frac=clip)


def test_banda_muerta_anula_microcorrecciones():
    """Una corrección chica (~0.1 EV) cae dentro de la banda muerta → 0."""
    # sesión con piel apenas desviada del target → corrección pequeña
    sigs = [_sig(i, skin=0.16) for i in range(6)]
    sigs.append(_sig(6, skin=0.15))   # levísima diferencia
    edits = compute_pre_edits(sigs, bias=0.0, exposure_deadband=0.15)
    assert all(abs(edits[i]["Exposure2012"]) < 0.001 for i in edits)


def test_banda_muerta_no_bloquea_correcciones_reales():
    """Una foto claramente subexpuesta en su sesión SÍ se corrige pese a la banda."""
    sigs = [_sig(i, skin=0.18) for i in range(6)]
    sigs.append(_sig(6, skin=0.05))   # muy oscura respecto a la sesión
    edits = compute_pre_edits(sigs, bias=0.0, exposure_deadband=0.15)
    assert edits[6]["Exposure2012"] > 0.15


def test_auto_wb_off_solo_deja_el_sesgo_del_preset():
    """Con auto_wb=False, la corrección WB por piel/sesión no se aplica;
    solo sobrevive el sesgo del preset."""
    sigs = [_sig(i, skin=0.18, wb=(20.0, -15.0)) for i in range(6)]  # dominante fuerte
    edits_on = compute_pre_edits(sigs, bias=0.0, auto_wb=True)
    edits_off = compute_pre_edits(sigs, bias=0.0, auto_wb=False)
    edits_preset = compute_pre_edits(sigs, bias=0.0, auto_wb=False,
                                     preset_wb_bias=(5.0, 0.0))
    assert abs(edits_on[0]["IncrementalTemperature"]) > 5     # adaptativo corrige
    assert edits_off[0]["IncrementalTemperature"] == 0.0      # apagado: neutro
    assert edits_off[0]["IncrementalTint"] == 0.0
    assert edits_preset[0]["IncrementalTemperature"] == 5.0   # solo el preset


def test_auto_wb_on_es_el_comportamiento_anterior():
    """Regresión: auto_wb=True (default de la función) mantiene la corrección
    adaptativa de siempre."""
    sigs = [_sig(i, skin=0.18, wb=(18.0, 0.0)) for i in range(6)]
    edits = compute_pre_edits(sigs, bias=0.0)   # default auto_wb=True
    assert edits[0]["IncrementalTemperature"] != 0.0
