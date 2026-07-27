"""
VLM refiner: nunca enviar originales, y parseo robusto de la respuesta.

Regresión que cubre: se base64-eaba el archivo ORIGINAL (un RAW es
indecodificable para el VLM; un JPG de cámara revienta payload y timeout).
Ahora solo viajan thumbs 'duel' re-encodeados a JPEG; sin thumb → None.
"""
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services import vlm_refiner


def _respuesta_ollama(texto):
    class _Resp:
        def read(self):
            return json.dumps({"response": texto}).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
    return _Resp()


@pytest.fixture()
def con_thumbs(monkeypatch):
    """Simula que el collage se pudo armar (thumbs duel cacheados)."""
    monkeypatch.setattr(vlm_refiner, "_collage_b64", lambda paths: "ZmFrZQ==")


def test_sin_thumb_cacheado_no_manda_originales(monkeypatch):
    monkeypatch.setattr(vlm_refiner, "_collage_b64", lambda paths: None)
    llamadas = []
    monkeypatch.setattr(vlm_refiner.urllib.request, "urlopen",
                        lambda *a, **k: llamadas.append(1))
    assert vlm_refiner.decide_winner(["a.CR2", "b.CR2"]) is None
    assert llamadas == []   # jamás llegó a la red


def test_collage_sin_thumb_de_una_candidata_es_none(monkeypatch):
    """_collage_b64 real: si UNA candidata no tiene thumb, todo el collage
    se descarta (no se arma un collage a medias)."""
    from services import thumbnail_store
    import cv2
    import numpy as np
    ok, jpg = cv2.imencode(".jpg", np.full((40, 60, 3), 90, dtype=np.uint8))
    datos = {"a.jpg": jpg.tobytes(), "b.jpg": None}
    monkeypatch.setattr(thumbnail_store, "read_thumbnail_from_disk",
                        lambda p, size: datos.get(p))
    assert vlm_refiner._collage_b64(["a.jpg", "b.jpg"]) is None
    # con ambas presentes sí arma
    datos["b.jpg"] = jpg.tobytes()
    assert vlm_refiner._collage_b64(["a.jpg", "b.jpg"]) is not None


def test_respuesta_numerica_directa(con_thumbs, monkeypatch):
    monkeypatch.setattr(vlm_refiner.urllib.request, "urlopen",
                        lambda *a, **k: _respuesta_ollama("2"))
    assert vlm_refiner.decide_winner(["a.jpg", "b.jpg", "c.jpg"]) == 2


def test_respuesta_con_texto_alrededor(con_thumbs, monkeypatch):
    monkeypatch.setattr(vlm_refiner.urllib.request, "urlopen",
                        lambda *a, **k: _respuesta_ollama("La mejor es la 1."))
    assert vlm_refiner.decide_winner(["a.jpg", "b.jpg"]) == 1


def test_respuesta_basura_devuelve_none(con_thumbs, monkeypatch):
    monkeypatch.setattr(vlm_refiner.urllib.request, "urlopen",
                        lambda *a, **k: _respuesta_ollama("no puedo decidir"))
    assert vlm_refiner.decide_winner(["a.jpg", "b.jpg"]) is None


def test_indice_fuera_de_rango_se_ignora(con_thumbs, monkeypatch):
    # el modelo dice "7" con 2 candidatas → None, no IndexError silencioso
    monkeypatch.setattr(vlm_refiner.urllib.request, "urlopen",
                        lambda *a, **k: _respuesta_ollama("7"))
    assert vlm_refiner.decide_winner(["a.jpg", "b.jpg"]) is None


def test_ollama_caido_devuelve_none(con_thumbs, monkeypatch):
    def _boom(*a, **k):
        raise urllib.error.URLError("conexión rechazada")
    monkeypatch.setattr(vlm_refiner.urllib.request, "urlopen", _boom)
    assert vlm_refiner.decide_winner(["a.jpg", "b.jpg"]) is None


def test_una_sola_candidata_gana_sin_red(monkeypatch):
    llamadas = []
    monkeypatch.setattr(vlm_refiner.urllib.request, "urlopen",
                        lambda *a, **k: llamadas.append(1))
    assert vlm_refiner.decide_winner(["a.jpg"]) == 0
    assert llamadas == []
