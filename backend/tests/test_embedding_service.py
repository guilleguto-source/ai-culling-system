"""Tests del servicio de embeddings: preprocesado, caché y degradación sin ONNX."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services import embedding_service as es


def _img(h=300, w=400):
    rng = np.random.default_rng(7)
    return rng.integers(0, 255, size=(h, w, 3), dtype=np.uint8)


# --- Preprocesado ---

def test_preprocess_shape_y_tipo():
    x = es._preprocess(_img())
    assert x.shape == (1, 3, 224, 224)
    assert x.dtype == np.float32


def test_preprocess_imagen_vertical():
    x = es._preprocess(_img(h=500, w=250))
    assert x.shape == (1, 3, 224, 224)


# --- Degradación sin modelo ONNX ---

def test_sin_modelo_embed_devuelve_none(monkeypatch):
    monkeypatch.setattr(es, "_get_session", lambda: None)
    assert es.embed(_img()) is None


def test_sin_modelo_embed_path_devuelve_none(tmp_path, monkeypatch):
    monkeypatch.setattr(es, "_get_session", lambda: None)
    monkeypatch.setattr(es, "CACHE_DIR", tmp_path / "cache")
    f = tmp_path / "foto.jpg"
    f.write_bytes(b"fake")
    assert es.embed_path(str(f), _img()) is None


# --- Caché en disco (con embed simulado) ---

def _fake_vec():
    v = np.arange(es.EMBEDDING_DIM, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_cache_guarda_y_reutiliza(tmp_path, monkeypatch):
    monkeypatch.setattr(es, "CACHE_DIR", tmp_path / "cache")
    calls = {"n": 0}

    def fake_embed(img):
        calls["n"] += 1
        return _fake_vec()

    monkeypatch.setattr(es, "embed", fake_embed)
    f = tmp_path / "foto.jpg"
    f.write_bytes(b"fake")

    v1 = es.embed_path(str(f), _img())
    v2 = es.embed_path(str(f), _img())   # segunda llamada: caché hit
    assert calls["n"] == 1
    np.testing.assert_array_almost_equal(v1, v2)


def test_cache_invalida_si_cambia_mtime(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(es, "CACHE_DIR", tmp_path / "cache")
    calls = {"n": 0}

    def fake_embed(img):
        calls["n"] += 1
        return _fake_vec()

    monkeypatch.setattr(es, "embed", fake_embed)
    f = tmp_path / "foto.jpg"
    f.write_bytes(b"fake")

    es.embed_path(str(f), _img())
    os.utime(f, (0, 12345))              # mtime cambia → clave nueva
    es.embed_path(str(f), _img())
    assert calls["n"] == 2


def test_cache_hit_sin_pixeles(tmp_path, monkeypatch):
    """Con caché ya poblado, embed_path funciona sin pasar la imagen."""
    monkeypatch.setattr(es, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(es, "embed", lambda img: _fake_vec())
    f = tmp_path / "foto.jpg"
    f.write_bytes(b"fake")

    es.embed_path(str(f), _img())
    v = es.embed_path(str(f), img_rgb=None)
    assert v is not None and v.shape == (es.EMBEDDING_DIM,)


# --- Modelo real (solo si el ONNX está descargado) ---

@pytest.mark.skipif(not es.CLIP_MODEL_PATH.exists(), reason="clip_vit_b32_visual.onnx no descargado")
def test_embedding_real_shape_norma_determinismo():
    img = _img()
    v1 = es.embed(img)
    v2 = es.embed(img)
    assert v1.shape == (es.EMBEDDING_DIM,)
    assert abs(float(np.linalg.norm(v1)) - 1.0) < 1e-3
    np.testing.assert_array_almost_equal(v1, v2)
