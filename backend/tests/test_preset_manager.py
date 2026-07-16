"""Tests del preset manager: parseo, lista negra y recientes (MRU)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services import preset_manager
from services.preset_manager import load_preset, register_recent

# Fixture reducida con la estructura real de un preset LR moderno
# (mismo formato que "GutoPro Day.xmp" del usuario).
PRESET_XML = """<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 7.0">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
   crs:PresetType="Normal"
   crs:UUID="9DCBAF6F7D08B947880779F1D068B287"
   crs:SupportsAmount="True"
   crs:ShowInPresets="True"
   crs:Version="18.3"
   crs:ProcessVersion="15.4"
   crs:WhiteBalance="Custom"
   crs:IncrementalTemperature="+5"
   crs:IncrementalTint="+5"
   crs:Sharpness="15"
   crs:HueAdjustmentRed="+5"
   crs:AutoTone="True"
   crs:AutoLateralCA="1"
   crs:Exposure2012="+0.5"
   crs:Table_6938C31B="basura"
   crs:HasSettings="True"
   crs:CropConstrainToWarp="0">
   <crs:Name>
    <rdf:Alt><rdf:li xml:lang="x-default">GutoPro Test</rdf:li></rdf:Alt>
   </crs:Name>
   <crs:Group>
    <rdf:Alt><rdf:li xml:lang="x-default">User</rdf:li></rdf:Alt>
   </crs:Group>
   <crs:ToneCurvePV2012>
    <rdf:Seq><rdf:li>0, 0</rdf:li><rdf:li>255, 255</rdf:li></rdf:Seq>
   </crs:ToneCurvePV2012>
   <crs:MaskGroupBasedCorrections>
    <rdf:Seq><rdf:li><rdf:Description crs:What="Correction"/></rdf:li></rdf:Seq>
   </crs:MaskGroupBasedCorrections>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>"""


@pytest.fixture()
def preset_file(tmp_path):
    f = tmp_path / "GutoPro Test.xmp"
    f.write_text(PRESET_XML, encoding="utf-8")
    return f


def test_parseo_basico(preset_file):
    p = load_preset(str(preset_file))
    assert p is not None
    assert p.name == "GutoPro Test"
    assert p.settings["Sharpness"] == "15"
    assert p.settings["HueAdjustmentRed"] == "+5"
    assert p.settings["ProcessVersion"] == "15.4"


def test_lista_negra(preset_file):
    p = load_preset(str(preset_file))
    for campo in ("PresetType", "UUID", "SupportsAmount", "ShowInPresets",
                  "AutoTone", "WhiteBalance", "Exposure2012",
                  "Table_6938C31B", "HasSettings", "CropConstrainToWarp",
                  "IncrementalTemperature", "IncrementalTint", "Version"):
        assert campo not in p.settings, campo


def test_auto_lateral_ca_se_conserva(preset_file):
    """AutoLateralCA es corrección de lente (look), no AutoTone."""
    p = load_preset(str(preset_file))
    assert p.settings.get("AutoLateralCA") == "1"


def test_wb_bias_extraido(preset_file):
    p = load_preset(str(preset_file))
    assert p.wb_bias == (5.0, 5.0)


def test_elementos_conservan_curva_y_mascaras(preset_file):
    p = load_preset(str(preset_file))
    names = [e.tag.split('}')[1] for e in p.elements]
    assert "ToneCurvePV2012" in names
    assert "MaskGroupBasedCorrections" in names
    assert "Name" not in names and "Group" not in names


def test_preset_ilegible_devuelve_none(tmp_path):
    f = tmp_path / "roto.xmp"
    f.write_text("esto no es xml", encoding="utf-8")
    assert load_preset(str(f)) is None


def test_register_recent_mru(preset_file, tmp_path, monkeypatch):
    monkeypatch.setattr(preset_manager, "PRESETS_DIR", tmp_path / "presets")
    saved = {}
    monkeypatch.setattr(preset_manager, "load_settings",
                        lambda: {"selection_preferences": dict(saved)})
    monkeypatch.setattr(preset_manager, "save_settings",
                        lambda s: saved.update(s["selection_preferences"]) or True)

    pre = register_recent(str(preset_file))
    assert pre["recent_presets"][0]["name"] == "GutoPro Test"
    assert (tmp_path / "presets" / "GutoPro Test.xmp").exists()

    # 6 presets → solo quedan 5, el último usado primero
    for i in range(6):
        f = tmp_path / f"p{i}.xmp"
        f.write_text(PRESET_XML, encoding="utf-8")
        pre = register_recent(str(f))
    assert len(pre["recent_presets"]) == 5
    assert pre["recent_presets"][0]["name"] == "p5"
