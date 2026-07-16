"""
Tests del clasificador aprendido de atributos faciales (Fase G3).

Regla de oro: mientras no haya datos suficientes NO opina — manda la
geometría de G1. Un modelo con 20 ejemplos es ruido con confianza.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.calibration_store import CalibrationStore
from services.face_classifier import FaceClassifier, MIN_EXAMPLES, MIN_PER_CLASS
from services.embedding_service import EMBEDDING_DIM


def _clf(tmp_path):
    return FaceClassifier(store=CalibrationStore(db_path=tmp_path / "cal.db"))


def _emb(seed: int, clase: str) -> np.ndarray:
    """Embeddings sintéticos separables: el primer eje codifica la clase."""
    rng = np.random.default_rng(seed)
    v = rng.normal(0, 0.1, EMBEDDING_DIM).astype(np.float32)
    v[0] = {"abiertos": 1.0, "cerrados": -1.0, "entrecerrados": 0.0}[clase]
    return v / np.linalg.norm(v)


def _poblar(c: FaceClassifier, n_por_clase: int, clases=("abiertos", "cerrados")):
    for i in range(n_por_clase):
        for j, cl in enumerate(clases):
            c.store.add_label(f"f{i}_{j}.jpg", 0, "eyes", cl, embedding=_emb(i * 10 + j, cl))
    c.invalidate()


# --- No opina sin datos ---

def test_sin_datos_no_opina(tmp_path):
    c = _clf(tmp_path)
    assert not c.is_ready("eyes")
    assert c.predict("eyes", _emb(1, "abiertos")) == ("", 0.0)


def test_pocos_ejemplos_no_opina(tmp_path):
    c = _clf(tmp_path)
    _poblar(c, n_por_clase=5)          # 10 ejemplos: muy pocos
    assert not c.is_ready("eyes")


def test_una_sola_clase_no_opina(tmp_path):
    """100 ejemplos de 'abiertos' no enseñan a reconocer 'cerrados'."""
    c = _clf(tmp_path)
    for i in range(MIN_EXAMPLES + 10):
        c.store.add_label(f"f{i}.jpg", 0, "eyes", "abiertos", embedding=_emb(i, "abiertos"))
    c.invalidate()
    assert not c.is_ready("eyes")


def test_clase_minoritaria_insuficiente_no_opina(tmp_path):
    c = _clf(tmp_path)
    for i in range(MIN_EXAMPLES):
        c.store.add_label(f"a{i}.jpg", 0, "eyes", "abiertos", embedding=_emb(i, "abiertos"))
    for i in range(MIN_PER_CLASS - 1):   # una menos del mínimo
        c.store.add_label(f"c{i}.jpg", 0, "eyes", "cerrados", embedding=_emb(500 + i, "cerrados"))
    c.invalidate()
    assert not c.is_ready("eyes")


def test_sin_embedding_no_opina(tmp_path):
    c = _clf(tmp_path)
    _poblar(c, n_por_clase=MIN_EXAMPLES)
    assert c.predict("eyes", None) == ("", 0.0)


# --- Aprende cuando hay datos ---

def test_con_datos_suficientes_aprende(tmp_path):
    c = _clf(tmp_path)
    _poblar(c, n_por_clase=MIN_EXAMPLES)
    assert c.is_ready("eyes")
    valor, conf = c.predict("eyes", _emb(9999, "cerrados"))
    assert valor == "cerrados" and conf > 0.7


def test_stats_reporta_progreso(tmp_path):
    c = _clf(tmp_path)
    _poblar(c, n_por_clase=3)
    s = c.stats("eyes")
    assert s["ejemplos"] == 6
    assert s["por_clase"] == {"abiertos": 3, "cerrados": 3}
    assert s["listo"] is False


def test_validacion_cruzada_es_honesta(tmp_path):
    """La precisión se mide en datos NO vistos al entrenar."""
    c = _clf(tmp_path)
    assert c.cross_val_accuracy("eyes") is None      # sin datos
    _poblar(c, n_por_clase=MIN_EXAMPLES)
    acc = c.cross_val_accuracy("eyes")
    assert acc is not None and acc > 0.8             # datos separables


def test_nuevas_etiquetas_reentrenan(tmp_path):
    c = _clf(tmp_path)
    _poblar(c, n_por_clase=MIN_EXAMPLES)
    assert c.is_ready("eyes")
    c.store.add_label("nueva.jpg", 0, "eyes", "cerrados", embedding=_emb(4242, "cerrados"))
    c.invalidate("eyes")
    assert c.stats("eyes")["ejemplos"] == MIN_EXAMPLES * 2 + 1


def test_atributos_independientes(tmp_path):
    """Entrenar 'eyes' no habilita 'mouth'."""
    c = _clf(tmp_path)
    _poblar(c, n_por_clase=MIN_EXAMPLES)
    assert c.is_ready("eyes")
    assert not c.is_ready("mouth")
