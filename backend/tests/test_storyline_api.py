"""
Tests del storyline y del formato de URL de thumbnails.

Regresiones que cubren:
- /storyline dependía de un global `current_directory` que NUNCA se asignaba →
  500 en toda llamada (la feature estaba muerta end-to-end).
- Las URLs de thumbnail se armaban a mano con `type=ui` (parámetro inexistente,
  el real es `size`) y sin URL-encodear — rompía con carpetas reales con
  espacios y tildes ("Ale Grau").
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.thumbnail_store import thumb_url
from services.analysis import PhotoAnalysis
from services import analysis_store


@pytest.fixture()
def client():
    import main
    return TestClient(main.app)


# --- thumb_url: única fuente del formato ---

def test_thumb_url_encodea_espacios_y_tildes():
    url = thumb_url("C:/ev/Ale Grau/foto ñoña.jpg")
    assert " " not in url and "ñ" not in url
    assert url.startswith("/thumbnail?path=")
    assert url.endswith("&size=ui")


def test_thumb_url_respeta_size():
    assert thumb_url("C:/ev/a.jpg", size="duel").endswith("&size=duel")


# --- endpoint /storyline ---

def test_storyline_sin_directory_es_422(client):
    assert client.get("/storyline").status_code == 422


def test_storyline_directorio_sin_analisis_devuelve_vacio(client, tmp_path):
    r = client.get("/storyline", params={"directory": str(tmp_path)})
    assert r.status_code == 200
    assert r.json() == {"storyline": []}


def test_storyline_capitulos_por_hueco_temporal(client, tmp_path, monkeypatch):
    """Dos bloques de fotos separados >30 min → dos capítulos, con
    medoid_thumb bien formado (encodeado y con size=)."""
    monkeypatch.setattr(analysis_store, "ANALYSIS_DIR", tmp_path / "an")
    carpeta = str(tmp_path / "Evento De Prueba")   # espacio a propósito

    conn = analysis_store.init_store(carpeta)
    fotos = [
        ("a con espacio.jpg", "2026:07:20 10:00:00"),
        ("b.jpg", "2026:07:20 10:02:00"),
        ("c.jpg", "2026:07:20 11:30:00"),   # +88 min -> capítulo nuevo
    ]
    for i, (nombre, fecha) in enumerate(fotos):
        p = f"{carpeta}/{nombre}"
        analysis_store.save_analysis(
            conn, PhotoAnalysis(index=i, path=p, exif_datetime=fecha, scene_type="portrait"), 1.0)

    r = client.get("/storyline", params={"directory": carpeta})
    assert r.status_code == 200
    caps = r.json()["storyline"]
    assert len(caps) == 2
    assert caps[0]["photo_count"] == 2 and caps[1]["photo_count"] == 1
    for c in caps:
        assert "size=ui" in c["medoid_thumb"]
        assert " " not in c["medoid_thumb"]


# --- /search/semantic: formato del thumb devuelto ---

def test_search_semantic_thumb_bien_formado(client, monkeypatch):
    # main importa search_photos DENTRO del endpoint → parchear el módulo fuente
    monkeypatch.setattr(
        "services.semantic_search.search_photos",
        lambda q, d, limit=50: [{"path": "C:/ev/Ale Grau/x y.jpg", "score": 0.9}],
    )
    r = client.get("/search/semantic",
                   params={"q": "novia", "directory": "C:/ev/Ale Grau"})
    assert r.status_code == 200
    thumb = r.json()["results"][0]["thumb"]
    assert "size=ui" in thumb and "type=" not in thumb
    assert " " not in thumb
