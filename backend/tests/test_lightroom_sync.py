"""Tests del sync desde Lightroom: lectura XMP, snapshot y detección de correcciones."""
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.xmp_reader import read_xmp
from services.xmp_exporter import write_xmp, _build_xmp_packet
from services import export_snapshot


# --- xmp_reader ---

def test_read_sidecar_raw(tmp_path):
    raw = tmp_path / "IMG_001.cr2"
    raw.write_bytes(b"fake raw")
    sidecar = tmp_path / "IMG_001.xmp"
    sidecar.write_bytes(_build_xmp_packet(stars=3, color="Verde", label="selected"))
    result = read_xmp(str(raw))
    assert result == {"stars": 3, "color": "Verde"}


def test_read_sidecar_atributos_estilo_lightroom(tmp_path):
    """Lightroom suele escribir Rating/Label como atributos de rdf:Description."""
    raw = tmp_path / "IMG_002.nef"
    raw.write_bytes(b"fake raw")
    sidecar = tmp_path / "IMG_002.xmp"
    sidecar.write_text(
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/"'
        ' xmp:Rating="5" xmp:Label="Roja"/>'
        "</rdf:RDF></x:xmpmeta>",
        encoding="utf-8",
    )
    result = read_xmp(str(raw))
    assert result == {"stars": 5, "color": "Roja"}


def test_read_sin_xmp_devuelve_none(tmp_path):
    raw = tmp_path / "IMG_003.arw"
    raw.write_bytes(b"fake raw")
    assert read_xmp(str(raw)) is None


def _minimal_jpeg(tmp_path, name="foto.jpg") -> Path:
    """JPEG mínimo válido: SOI + APP0 + SOS + EOI."""
    p = tmp_path / name
    app0 = b"\xff\xe0" + (16).to_bytes(2, "big") + b"JFIF\x00" + b"\x00" * 9
    p.write_bytes(b"\xff\xd8" + app0 + b"\xff\xda\x00\x02" + b"\xff\xd9")
    return p


def test_roundtrip_jpeg_embebido(tmp_path):
    jpg = _minimal_jpeg(tmp_path)
    assert write_xmp(str(jpg), "selected", stars=4, color="Azul", overwrite=True)
    result = read_xmp(str(jpg))
    assert result == {"stars": 4, "color": "Azul"}


# --- export_snapshot ---

def _use_tmp_exports(tmp_path, monkeypatch):
    monkeypatch.setattr(export_snapshot, "EXPORTS_DIR", tmp_path / "exports")


def test_snapshot_roundtrip(tmp_path, monkeypatch):
    _use_tmp_exports(tmp_path, monkeypatch)
    results = [
        {"path": "C:/ev/a.jpg", "label": "selected"},
        {"path": "C:/ev/b.jpg", "label": "duplicates"},
        {"path": "C:/ev/c.jpg", "label": None},          # sin label: fuera
        {"path": "C:/ev/d.jpg", "label": "blurry", "error": "x"},  # error: fuera
    ]
    export_snapshot.save_snapshot("C:/ev", results)
    snap = export_snapshot.load_snapshot("C:/ev")
    assert snap["items"] == {"C:/ev/a.jpg": "selected", "C:/ev/b.jpg": "duplicates"}


def test_snapshot_update_labels_y_synced(tmp_path, monkeypatch):
    _use_tmp_exports(tmp_path, monkeypatch)
    export_snapshot.save_snapshot("C:/ev", [{"path": "C:/ev/a.jpg", "label": "duplicates"}])
    export_snapshot.update_labels("C:/ev", {"C:/ev/a.jpg": "selected"})
    export_snapshot.update_synced_stars("C:/ev", {"C:/ev/a.jpg": 5})
    snap = export_snapshot.load_snapshot("C:/ev")
    assert snap["items"]["C:/ev/a.jpg"] == "selected"
    assert snap["synced_stars"]["C:/ev/a.jpg"] == 5


def test_snapshot_inexistente(tmp_path, monkeypatch):
    _use_tmp_exports(tmp_path, monkeypatch)
    assert export_snapshot.load_snapshot("C:/nunca") is None


# --- Endpoint /reimport_xmp ---

@pytest.fixture()
def client(tmp_path, monkeypatch):
    _use_tmp_exports(tmp_path, monkeypatch)
    import main
    return TestClient(main.app)


def test_reimport_sin_export_previo_404(client):
    res = client.post("/reimport_xmp", json={"directory": "C:/no-existe"})
    assert res.status_code == 404


def test_reimport_detecta_subida_y_bajada(client, tmp_path, monkeypatch):
    from services.taste_model import taste_model

    # Evento con 2 JPGs exportados: a=selected, b=duplicates
    ev = tmp_path / "evento"
    ev.mkdir()
    a = _minimal_jpeg(ev, "a.jpg")
    b = _minimal_jpeg(ev, "b.jpg")

    from services.settings_manager import load_settings
    ratings_map = load_settings()["ratings_mapping"]
    sel_stars = ratings_map["selected"]["stars"]
    dup_stars = ratings_map["duplicates"]["stars"]

    export_snapshot.save_snapshot(str(ev), [
        {"path": str(a), "label": "selected"},
        {"path": str(b), "label": "duplicates"},
    ])
    # El usuario en Lightroom: baja a (selected → 0★), sube b (→ 5★)
    write_xmp(str(a), "duplicates", stars=max(0, sel_stars - 2), color="", overwrite=True)
    write_xmp(str(b), "selected", stars=min(5, dup_stars + 3), color="", overwrite=True)

    added = []
    monkeypatch.setattr(
        taste_model, "add_example",
        lambda emb, label, source, event_dir="": added.append(label),
    )
    from services import embedding_service
    monkeypatch.setattr(embedding_service, "is_available", lambda: True)
    monkeypatch.setattr(
        embedding_service, "embed_path",
        lambda path, img_rgb=None: np.ones(512, dtype=np.float32),
    )

    res = client.post("/reimport_xmp", json={"directory": str(ev)})
    assert res.status_code == 200
    data = res.json()
    assert data["corrections"] == 2
    assert data["upgraded"] == 1 and data["downgraded"] == 1
    assert sorted(added) == [-1, 1]

    # Idempotencia: segundo sync sin cambios nuevos → 0 correcciones
    added.clear()
    res2 = client.post("/reimport_xmp", json={"directory": str(ev)})
    assert res2.json()["corrections"] == 0
    assert added == []
