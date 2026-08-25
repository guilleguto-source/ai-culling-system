"""Tests del servicio de embeddings: caché y degradación sin modelo SigLIP."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services import embedding_service as es
from services import siglip_service


def _img(h=300, w=400):
    rng = np.random.default_rng(7)
    return rng.integers(0, 255, size=(h, w, 3), dtype=np.uint8)


# --- Degradación sin modelo ---

def test_sin_modelo_embed_devuelve_none(monkeypatch):
    monkeypatch.setattr(siglip_service, "_load_model", lambda: (None, None))
    assert es.embed(_img()) is None


def test_sin_modelo_embed_path_devuelve_none(tmp_path, monkeypatch):
    monkeypatch.setattr(siglip_service, "_load_model", lambda: (None, None))
    monkeypatch.setattr(siglip_service, "CACHE_DIR", tmp_path / "cache")
    f = tmp_path / "foto.jpg"
    f.write_bytes(b"fake")
    assert es.embed_path(str(f), _img()) is None


# --- Caché en disco (con embed simulado) ---

def _fake_vec():
    v = np.arange(es.EMBEDDING_DIM, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_cache_guarda_y_reutiliza(tmp_path, monkeypatch):
    monkeypatch.setattr(siglip_service, "CACHE_DIR", tmp_path / "cache")
    calls = {"n": 0}

    def fake_embed(img):
        calls["n"] += 1
        return _fake_vec()

    monkeypatch.setattr(siglip_service, "embed", fake_embed)
    f = tmp_path / "foto.jpg"
    f.write_bytes(b"fake")

    v1 = es.embed_path(str(f), _img())
    v2 = es.embed_path(str(f), _img())   # segunda llamada: caché hit
    assert calls["n"] == 1
    np.testing.assert_array_almost_equal(v1, v2)


def test_cache_invalida_si_cambia_mtime(tmp_path, monkeypatch):
    import os
    monkeypatch.setattr(siglip_service, "CACHE_DIR", tmp_path / "cache")
    calls = {"n": 0}

    def fake_embed(img):
        calls["n"] += 1
        return _fake_vec()

    monkeypatch.setattr(siglip_service, "embed", fake_embed)
    f = tmp_path / "foto.jpg"
    f.write_bytes(b"fake")

    es.embed_path(str(f), _img())
    os.utime(f, (0, 12345))              # mtime cambia → clave nueva
    es.embed_path(str(f), _img())
    assert calls["n"] == 2


def test_cache_hit_sin_pixeles(tmp_path, monkeypatch):
    """Con caché ya poblado, embed_path funciona sin pasar la imagen."""
    monkeypatch.setattr(siglip_service, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(siglip_service, "embed", lambda img: _fake_vec())
    f = tmp_path / "foto.jpg"
    f.write_bytes(b"fake")

    es.embed_path(str(f), _img())
    v = es.embed_path(str(f), img_rgb=None)
    assert v is not None and v.shape == (es.EMBEDDING_DIM,)


# --- Batching ---

def test_embed_batch_sin_modelo(monkeypatch):
    monkeypatch.setattr(siglip_service, "_load_model", lambda: (None, None))
    res = es.embed_batch([_img(), _img()])
    assert res == [None, None]


def test_embed_paths_batch_con_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(siglip_service, "CACHE_DIR", tmp_path / "cache")
    f1 = tmp_path / "f1.jpg"
    f2 = tmp_path / "f2.jpg"
    f1.write_bytes(b"1")
    f2.write_bytes(b"2")

    def fake_embed_batch(imgs, batch_size=32):
        return [_fake_vec() for _ in imgs]

    monkeypatch.setattr(siglip_service, "embed_batch", fake_embed_batch)

    items = [(str(f1), _img()), (str(f2), _img())]
    res1 = es.embed_paths_batch(items)
    assert len(res1) == 2
    assert res1[0] is not None and res1[1] is not None

    # Segunda llamada: carga desde caché sin re-computar
    monkeypatch.setattr(siglip_service, "embed_batch", lambda imgs, batch_size=32: pytest.fail("No debería re-calcular"))
    res2 = es.embed_paths_batch(items)
    assert len(res2) == 2
    np.testing.assert_array_almost_equal(res1[0], res2[0])


# --- Modelo real (solo si el ONNX está descargado) ---

@pytest.mark.skipif(not es.is_available(), reason="Modelo SigLIP no disponible")
def test_embedding_real_shape_norma_determinismo():
    img = _img()
    v1 = es.embed(img)
    v2 = es.embed(img)
    assert v1.shape == (es.EMBEDDING_DIM,)
    assert abs(float(np.linalg.norm(v1)) - 1.0) < 1e-3
    np.testing.assert_array_almost_equal(v1, v2)

