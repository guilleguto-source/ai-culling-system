"""Tests del flujo culling → revisar → aplicar edición (/apply_edits)."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from services import export_snapshot
from services.xmp_exporter import _extract_jpeg_xmp
from services.xmp_reader import read_xmp
from tests.test_lightroom_sync import _minimal_jpeg


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(export_snapshot, "EXPORTS_DIR", tmp_path / "exports")
    import main
    return TestClient(main.app)


def _snapshot_con_edicion_pendiente(ev_dir, a, b, c):
    export_snapshot.save_snapshot(str(ev_dir), [
        {"path": str(a), "label": "selected",
         "crop": {"left": 0.05, "top": 0.0, "right": 0.95, "bottom": 1.0, "angle": 1.5},
         "develop": {"Exposure2012": 0.3, "IncrementalTemperature": 5.0, "IncrementalTint": 2.0}},
        {"path": str(b), "label": "highlighted",
         "crop": None,
         "develop": {"Exposure2012": -0.2, "IncrementalTemperature": 5.0, "IncrementalTint": 2.0}},
        {"path": str(c), "label": "duplicates", "crop": None, "develop": None},
    ], preset_path="", edits_applied=False)


def test_apply_edits_escribe_solo_en_seleccionadas(client, tmp_path):
    ev = tmp_path / "evento"
    ev.mkdir()
    a = _minimal_jpeg(ev, "a.jpg")
    b = _minimal_jpeg(ev, "b.jpg")
    c = _minimal_jpeg(ev, "c.jpg")
    _snapshot_con_edicion_pendiente(ev, a, b, c)

    res = client.post("/apply_edits", json={"directory": str(ev)})
    assert res.status_code == 200
    data = res.json()
    assert data["edited"] == 2

    xmp_a = _extract_jpeg_xmp(a.read_bytes()).decode("utf-8")
    assert "HasCrop" in xmp_a and "Exposure2012" in xmp_a
    xmp_b = _extract_jpeg_xmp(b.read_bytes()).decode("utf-8")
    assert "Exposure2012" in xmp_b and "HasCrop" not in xmp_b
    assert _extract_jpeg_xmp(c.read_bytes()) is None   # duplicates: sin tocar

    # El snapshot queda marcado y el rating sobrevive
    snap = export_snapshot.load_snapshot(str(ev))
    assert snap["edits_applied"] is True
    assert read_xmp(str(a))["stars"] >= 0


def test_apply_edits_sin_snapshot_404(client):
    assert client.post("/apply_edits", json={"directory": "C:/nada"}).status_code == 404


def test_snapshot_marca_edicion_pendiente(tmp_path, monkeypatch):
    monkeypatch.setattr(export_snapshot, "EXPORTS_DIR", tmp_path / "exports")
    export_snapshot.save_snapshot("C:/ev", [{"path": "C:/ev/x.jpg", "label": "selected"}],
                                  edits_applied=False)
    assert export_snapshot.load_snapshot("C:/ev")["edits_applied"] is False
    export_snapshot.set_edits_applied("C:/ev")
    assert export_snapshot.load_snapshot("C:/ev")["edits_applied"] is True
