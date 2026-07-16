"""Tests del paquete XMP con pre-edición (preset + develop) y endpoints de presets."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.xmp_exporter import _build_xmp_packet, write_xmp
from services.xmp_reader import read_xmp
from services.preset_manager import load_preset
from tests.test_preset_manager import PRESET_XML

_DEVELOP = {"Exposure2012": 0.35, "IncrementalTemperature": -4.0, "IncrementalTint": 2.0}


@pytest.fixture()
def preset(tmp_path):
    f = tmp_path / "GutoPro Test.xmp"
    f.write_text(PRESET_XML, encoding="utf-8")
    return load_preset(str(f))


def test_packet_desarrollo_completo(preset):
    packet = _build_xmp_packet(3, "Verde", "selected", develop=_DEVELOP, preset=preset)
    s = packet.decode("utf-8")
    # Calculados
    assert "<crs:Exposure2012>+0.35</crs:Exposure2012>" in s
    assert "<crs:IncrementalTemperature>-4.00</crs:IncrementalTemperature>" in s
    assert "<crs:WhiteBalance>Custom</crs:WhiteBalance>" in s
    # Look del preset (ajustes + bloques)
    assert "<crs:Sharpness>15</crs:Sharpness>" in s
    assert "ToneCurvePV2012" in s and "MaskGroupBasedCorrections" in s
    # Requisitos de Camera Raw y lista negra
    assert "AlreadyApplied" in s and "ProcessVersion" in s
    assert "AutoTone" not in s and "PresetType" not in s


def test_packet_develop_sin_preset():
    s = _build_xmp_packet(3, "", "selected", develop=_DEVELOP).decode("utf-8")
    assert "Exposure2012" in s and "ProcessVersion" in s


def test_rating_sigue_legible_con_todo(tmp_path, preset):
    from tests.test_lightroom_sync import _minimal_jpeg
    jpg = _minimal_jpeg(tmp_path)
    crop = {"left": 0.05, "top": 0.0, "right": 0.95, "bottom": 1.0, "angle": 1.2}
    assert write_xmp(str(jpg), "selected", 3, "Azul", overwrite=True,
                     crop=crop, develop=_DEVELOP, preset=preset)
    assert read_xmp(str(jpg)) == {"stars": 3, "color": "Azul"}


def test_raw_omite_wb_incremental(tmp_path, preset):
    raw = tmp_path / "IMG_1.cr2"
    raw.write_bytes(b"fake raw")
    assert write_xmp(str(raw), "selected", 3, "", overwrite=True,
                     develop=_DEVELOP, preset=preset)
    s = (tmp_path / "IMG_1.xmp").read_text(encoding="utf-8")
    assert "Exposure2012" in s
    assert "IncrementalTemperature" not in s and "IncrementalTint" not in s


def test_tamano_paquete_jpeg_bajo_limite_app1(preset):
    packet = _build_xmp_packet(3, "Verde", "selected", develop=_DEVELOP, preset=preset)
    assert len(packet) < 0xFFFF - 100


# --- Endpoints de presets ---

@pytest.fixture()
def client():
    import main
    return TestClient(main.app)


def test_preset_use_invalido_400(client, tmp_path):
    f = tmp_path / "roto.xmp"
    f.write_text("no es xml", encoding="utf-8")
    assert client.post("/presets/use", json={"path": str(f)}).status_code == 400
    assert client.post("/presets/use", json={"path": str(tmp_path / "nope.xmp")}).status_code == 404


def test_preset_get(client):
    res = client.get("/presets")
    assert res.status_code == 200
    data = res.json()
    assert "active" in data and "recent" in data and "exposure_bias" in data
