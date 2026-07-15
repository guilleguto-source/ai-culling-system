"""Tests del taste model sobre embeddings: almacén SQLite, umbral frío y scoring."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.taste_store import TasteStore
from services.taste_model import TasteModel, MIN_EXAMPLES
from services.embedding_service import EMBEDDING_DIM, MODEL_VERSION


def _store(tmp_path) -> TasteStore:
    return TasteStore(db_path=tmp_path / "taste.db")


def _vec(seed: int, positive: bool) -> np.ndarray:
    """Embeddings sintéticos linealmente separables: signo del primer eje."""
    rng = np.random.default_rng(seed)
    v = rng.normal(0, 0.1, EMBEDDING_DIM).astype(np.float32)
    v[0] = 1.0 if positive else -1.0
    return v / np.linalg.norm(v)


# --- TasteStore ---

def test_store_roundtrip(tmp_path):
    store = _store(tmp_path)
    store.add_example(_vec(1, True), +1, "duel", "C:/evento", model_version=MODEL_VERSION)
    X, y = store.load_examples(EMBEDDING_DIM, MODEL_VERSION)
    assert X.shape == (1, EMBEDDING_DIM)
    assert y.tolist() == [1]


def test_store_excluye_dimension_incompatible(tmp_path):
    store = _store(tmp_path)
    store.add_example(np.ones(64, dtype=np.float32), +1, "duel", model_version="otro-modelo")
    store.add_example(_vec(1, True), +1, "duel", model_version=MODEL_VERSION)
    X, y = store.load_examples(EMBEDDING_DIM, MODEL_VERSION)
    assert len(X) == 1          # el de 64 dims / otro modelo queda fuera


def test_store_db_corrupta_se_recupera(tmp_path):
    db = tmp_path / "taste.db"
    db.write_bytes(b"esto no es sqlite" * 100)
    store = TasteStore(db_path=db)
    store.add_example(_vec(1, True), +1, "duel", model_version=MODEL_VERSION)
    assert store.count(EMBEDDING_DIM, MODEL_VERSION) == 1
    assert (tmp_path / "taste.db.bak").exists()


# --- TasteModel ---

def test_frio_devuelve_neutro(tmp_path):
    tm = TasteModel(store=_store(tmp_path))
    assert not tm.is_trained
    assert tm.predict_score(_vec(1, True)) == 0.5


def test_entrenado_ordena_bien(tmp_path):
    tm = TasteModel(store=_store(tmp_path))
    for i in range(MIN_EXAMPLES // 2 + 1):
        tm.learn_preference(_vec(i, True), _vec(1000 + i, False))
    assert tm.is_trained
    s_pos = tm.predict_score(_vec(9999, True))
    s_neg = tm.predict_score(_vec(8888, False))
    assert s_pos > 0.8 > 0.2 > s_neg


def test_umbral_exacto(tmp_path):
    tm = TasteModel(store=_store(tmp_path))
    for i in range(MIN_EXAMPLES // 2 - 1):   # 48 ejemplos < 50
        tm.learn_preference(_vec(i, True), _vec(500 + i, False))
    assert not tm.is_trained
    tm.learn_preference(_vec(100, True), _vec(600, False))  # 50 → entrenado
    assert tm.is_trained


def test_predict_sin_embedding_es_neutro(tmp_path):
    tm = TasteModel(store=_store(tmp_path))
    for i in range(MIN_EXAMPLES):
        tm.add_example(_vec(i, i % 2 == 0), +1 if i % 2 == 0 else -1, "duel")
    assert tm.predict_score(None) == 0.5


def test_ejemplos_lightroom_cuentan_igual(tmp_path):
    tm = TasteModel(store=_store(tmp_path))
    for i in range(MIN_EXAMPLES // 2 + 1):
        tm.add_example(_vec(i, True), +1, "lightroom", "C:/evento")
        tm.add_example(_vec(700 + i, False), -1, "lightroom", "C:/evento")
    assert tm.is_trained
    assert tm.predict_score(_vec(4321, True)) > 0.5
