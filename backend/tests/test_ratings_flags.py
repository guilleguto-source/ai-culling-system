"""Tests de banderines XMP configurables y migración v3 de ratings."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.xmp_exporter import _build_xmp_packet
from services import settings_manager


def _pick(packet: bytes) -> str:
    s = packet.decode("utf-8")
    return s.split("<xmp:PickStatus>")[1].split("</xmp:PickStatus>")[0]


def test_flag_configurable_pisa_el_default():
    assert _pick(_build_xmp_packet(0, "", "duplicates", flag="reject")) == "-1"
    assert _pick(_build_xmp_packet(2, "Verde", "selected", flag="none")) == "0"
    assert _pick(_build_xmp_packet(3, "Azul", "highlighted", flag="pick")) == "1"


def test_sin_flag_usa_default_por_label():
    assert _pick(_build_xmp_packet(2, "Verde", "selected")) == "1"
    assert _pick(_build_xmp_packet(0, "Roja", "blurry")) == "-1"
    assert _pick(_build_xmp_packet(0, "", "duplicates")) == "0"


def test_migracion_v3_flags_y_trash_sin_color(tmp_path, monkeypatch):
    old = {
        "settings_version": 2,
        "ratings_mapping": {
            "selected": {"stars": 2, "color": "Verde"},
            "highlighted": {"stars": 3, "color": "Azul"},
            "blurry": {"stars": 0, "color": "Roja"},
            "closed_eyes": {"stars": 0, "color": "Morado"},
            "duplicates": {"stars": 0, "color": "Morado"},
        },
        "selection_preferences": {},
    }
    sp = tmp_path / "settings.json"
    sp.write_text(json.dumps(old), encoding="utf-8")
    monkeypatch.setattr(settings_manager, "_get_settings_path", lambda: sp)

    s = settings_manager.load_settings()
    rm = s["ratings_mapping"]
    assert s["settings_version"] == 6
    assert rm["selected"]["flag"] == "pick"
    assert rm["blurry"]["flag"] == "reject"
    assert rm["blurry"]["color"] == "Rojo"          # v4: masculino (set real de LR)
    assert rm["duplicates"]["flag"] == "none"
    assert rm["duplicates"]["color"] == ""          # duplicadas nunca se marcan
    assert rm["closed_eyes"]["color"] == ""         # v6 limpia closed_eyes
    assert rm["closed_eyes"]["flag"] == "none"


def test_migracion_v5_corrige_rojo_mal_puesto_en_duplicadas(tmp_path, monkeypatch):
    """El nombre 'Trash' de la UI llevó a poner Rojo+rechazada en `duplicates`
    (fotos buenas que perdieron su ráfaga). v5 mueve el rojo a los descartes.
    Luego v6 vuelve a limpiar closed_eyes."""
    old = {
        "settings_version": 4,
        "ratings_mapping": {
            "selected": {"stars": 2, "color": "Verde", "flag": "pick"},
            "highlighted": {"stars": 3, "color": "Azul", "flag": "pick"},
            "blurry": {"stars": 0, "color": "", "flag": "none"},
            "closed_eyes": {"stars": 0, "color": "", "flag": "none"},
            "duplicates": {"stars": 0, "color": "Rojo", "flag": "reject"},
        },
        "selection_preferences": {},
    }
    sp = tmp_path / "settings.json"
    sp.write_text(json.dumps(old), encoding="utf-8")
    monkeypatch.setattr(settings_manager, "_get_settings_path", lambda: sp)

    rm = settings_manager.load_settings()["ratings_mapping"]
    assert rm["duplicates"] == {"stars": 0, "color": "", "flag": "none"}
    assert rm["blurry"]["color"] == "Rojo" and rm["blurry"]["flag"] == "reject"
    assert rm["closed_eyes"]["color"] == "" and rm["closed_eyes"]["flag"] == "none"


def test_normalize_colors_canoniza_genero_e_idioma():
    """El set de LR del usuario es masculino; femenino o inglés no pinta.
    save_settings normaliza siempre, pase lo que pase en el frontend."""
    s = {"ratings_mapping": {
        "a": {"color": "Roja"}, "b": {"color": "Morada"}, "c": {"color": "Amarilla"},
        "d": {"color": "Green"}, "e": {"color": "azul"}, "f": {"color": ""},
    }}
    settings_manager.normalize_colors(s)
    rm = s["ratings_mapping"]
    assert rm["a"]["color"] == "Rojo"
    assert rm["b"]["color"] == "Morado"
    assert rm["c"]["color"] == "Amarillo"
    assert rm["d"]["color"] == "Verde"
    assert rm["e"]["color"] == "Azul"
    assert rm["f"]["color"] == ""          # sin color se respeta


def test_save_settings_normaliza(tmp_path, monkeypatch):
    sp = tmp_path / "settings.json"
    monkeypatch.setattr(settings_manager, "_get_settings_path", lambda: sp)
    settings_manager.save_settings({
        "ratings_mapping": {"duplicates": {"stars": 0, "color": "Roja", "flag": "reject"}},
        "selection_preferences": {},
    })
    saved = json.loads(sp.read_text(encoding="utf-8"))
    assert saved["ratings_mapping"]["duplicates"]["color"] == "Rojo"


def test_migracion_completa_desde_v1(tmp_path, monkeypatch):
    old = {
        "ratings_mapping": {
            "selected": {"stars": 3, "color": "Green"},
            "duplicates": {"stars": 0, "color": "Purple"},
        },
        "selection_preferences": {},
    }
    sp = tmp_path / "settings.json"
    sp.write_text(json.dumps(old), encoding="utf-8")
    monkeypatch.setattr(settings_manager, "_get_settings_path", lambda: sp)

    rm = settings_manager.load_settings()["ratings_mapping"]
    assert rm["selected"] == {"stars": 2, "color": "Verde", "flag": "pick"}
    assert rm["duplicates"]["color"] == "" and rm["duplicates"]["flag"] == "none"
