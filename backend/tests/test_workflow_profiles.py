"""
Tests de la Fase V: perfiles de workflow.

Un perfil empaqueta las preferencias de trabajo (selectividad, recorte,
detectores, pre-edición) — NO el mapeo a estrellas/colores de Lightroom, que es
del fotógrafo y no del tipo de evento.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services import workflow_profiles as wp


@pytest.fixture(autouse=True)
def _isolar(tmp_path, monkeypatch):
    monkeypatch.setattr(wp, "_ruta", lambda: tmp_path / "profiles.json")


PREFS = {
    "selectivity_target": "few",
    "auto_crop": "moderado",
    "detect_closed_eyes": True,
    "pre_edit": {"enabled": True, "exposure_bias": 0.5},
    "ratings_mapping": {"selected": {"stars": 2}},   # ajeno al perfil
    "otra_cosa": 123,                                 # tampoco es del perfil
}


def test_guarda_solo_las_claves_del_workflow():
    wp.save_profile("Bodas", PREFS)
    guardado = wp._leer()["Bodas"]
    assert guardado["selectivity_target"] == "few"
    assert guardado["pre_edit"]["exposure_bias"] == 0.5
    # El mapeo de Lightroom y lo ajeno NO viajan en el perfil
    assert "ratings_mapping" not in guardado and "otra_cosa" not in guardado


def test_aplicar_pisa_solo_lo_del_perfil():
    wp.save_profile("Bodas", PREFS)
    actuales = {"selectivity_target": "more", "ratings_mapping": {"x": 1}, "otra_cosa": 999}
    res = wp.apply_profile("Bodas", actuales)
    assert res["selectivity_target"] == "few"        # lo pisa el perfil
    assert res["ratings_mapping"] == {"x": 1}        # se conserva
    assert res["otra_cosa"] == 999                   # se conserva


def test_listar_y_borrar():
    wp.save_profile("Bodas", PREFS)
    wp.save_profile("Infantil", PREFS)
    assert wp.list_profiles() == ["Bodas", "Infantil"]
    assert wp.delete_profile("Bodas") is True
    assert wp.list_profiles() == ["Infantil"]
    assert wp.delete_profile("NoExiste") is False


def test_perfil_inexistente_avisa():
    with pytest.raises(KeyError):
        wp.apply_profile("Fantasma", {})


def test_nombre_vacio_se_rechaza():
    with pytest.raises(ValueError):
        wp.save_profile("   ", PREFS)
