"""
Tests de la Fase N: explicabilidad de la decisión.

Regla de oro: el sistema NUNCA debe afirmar "mejor score" cuando quien decidió
fue un gate técnico — la ganadora puede tener score menor que una descartada.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.analysis import PhotoAnalysis
from services.cluster_gates import apply_technical_gates_explained, GATE_OJOS, GATE_NITIDEZ
from services.decision import build_reasons


# --- Los gates explican por qué descartaron ---

def test_gate_ojos_reporta_motivo():
    # foto 1 con ojos cerrados, foto 0 sin ellos
    sobreviven, motivos = apply_technical_gates_explained(
        [0, 1], closed_flags=[False, True], face_sharpness=[[], []])
    assert sobreviven == [0]
    assert motivos == {1: GATE_OJOS}


def test_gate_nitidez_reporta_motivo():
    # foto 1 con rostro muy blando frente a la mediana del cluster
    sobreviven, motivos = apply_technical_gates_explained(
        [0, 1, 2], closed_flags=[False] * 3,
        face_sharpness=[[100.0], [5.0], [120.0]])
    assert 1 not in sobreviven
    assert motivos[1] == GATE_NITIDEZ


def test_si_todas_fallan_no_hay_motivos():
    """Si todas tienen ojos cerrados, el gate no se aplica: nadie 'perdió'."""
    sobreviven, motivos = apply_technical_gates_explained(
        [0, 1], closed_flags=[True, True], face_sharpness=[[], []])
    assert sorted(sobreviven) == [0, 1] and motivos == {}


# --- Las razones no mienten ---

def _analisis(n=3, **kw):
    return [PhotoAnalysis(index=i, path=f"f{i}.jpg", **kw) for i in range(n)]


def test_ganadora_por_gate_no_dice_mejor_score():
    a = _analisis()
    razones = build_reasons(
        idx=0, is_representative=True, analyses=a, rep_index=0,
        gate_reasons={1: GATE_OJOS}, decided_by={0: "gate"}, solo_en_cluster=False)
    assert any("sin defectos" in r for r in razones)
    assert not any("score" in r.lower() for r in razones)


def test_ganadora_por_gusto_lo_dice():
    a = _analisis()
    razones = build_reasons(0, True, a, 0, {}, {0: "gusto"}, solo_en_cluster=False)
    assert any("sueles elegir" in r for r in razones)


def test_perdedora_explica_el_gate():
    a = _analisis()
    razones = build_reasons(1, False, a, 0, {1: GATE_OJOS}, {0: "gate"}, solo_en_cluster=False)
    assert any("Ojos cerrados" in r for r in razones)


def test_foto_sola_en_su_cluster_no_tiene_razones():
    """Sin ráfaga no hay comparación que explicar."""
    a = _analisis()
    assert build_reasons(0, True, a, 0, {}, {}, solo_en_cluster=True) == []


def test_perdedora_sin_defectos_es_honesta():
    """Si no hay nada objetivo en contra, no se inventa un defecto."""
    a = _analisis()
    razones = build_reasons(1, False, a, 0, {}, {0: "score"}, solo_en_cluster=False)
    assert razones == ["Alternativa válida — la elegida puntuó algo mejor"]
