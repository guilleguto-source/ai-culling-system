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
            "closed_eyes": {"stars": 0, "color": "Morada"},
            "duplicates": {"stars": 0, "color": "Morada"},
        },
        "selection_preferences": {},
    }
    sp = tmp_path / "settings.json"
    sp.write_text(json.dumps(old), encoding="utf-8")
    monkeypatch.setattr(settings_manager, "_get_settings_path", lambda: sp)

    s = settings_manager.load_settings()
    rm = s["ratings_mapping"]
    assert s["settings_version"] == 3
    assert rm["selected"]["flag"] == "pick"
    assert rm["blurry"]["flag"] == "reject"
    assert rm["duplicates"]["flag"] == "none"
    assert rm["duplicates"]["color"] == ""          # Trash sin color
    assert rm["closed_eyes"]["color"] == "Morada"   # las demás no cambian


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
