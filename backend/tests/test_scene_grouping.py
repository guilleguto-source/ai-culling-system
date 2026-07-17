"""
Tests de la Fase I: agrupamiento por escena.

El clustering es el corazón testeable; se prueba con embeddings sintéticos
separables (tres nubes bien distintas → tres clusters). También los métodos del
store para persistir la escena.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.scene_grouping import cluster_embeddings, assign_from_matrix
from services.history_store import HistoryStore


def _tres_nubes(n=20, dim=32, seed=0):
    """Tres grupos separados en el espacio; embeddings L2-normalizados."""
    rng = np.random.default_rng(seed)
    centros = np.eye(3, dim, dtype=np.float32) * 5.0   # ejes 0,1,2 bien lejos
    X, verdad = [], []
    for c in range(3):
        for _ in range(n):
            v = centros[c] + rng.normal(0, 0.1, dim).astype(np.float32)
            X.append(v / np.linalg.norm(v))
            verdad.append(c)
    return np.stack(X), verdad


def test_clustering_separa_nubes():
    X, verdad = _tres_nubes()
    labels, centers = cluster_embeddings(X, k=3)
    assert len(centers) == 3
    # Cada nube verdadera cae en un único cluster (aunque el número cambie).
    for c in range(3):
        etiquetas_c = {labels[i] for i in range(len(labels)) if verdad[i] == c}
        assert len(etiquetas_c) == 1


def test_k_se_acota_a_los_ejemplos():
    X, _ = _tres_nubes(n=1)          # solo 3 puntos
    labels, centers = cluster_embeddings(X, k=10)
    assert len(centers) == 3         # no puede haber más clusters que puntos


def test_assign_from_matrix_medoides_y_tamanos():
    X, _ = _tres_nubes(n=10)
    paths = [f"f{i}.jpg" for i in range(len(X))]
    scene_by_path, summary, centers = assign_from_matrix(paths, X, k=3)
    assert summary["k"] == 3 and len(centers) == 3
    assert sum(summary["sizes"].values()) == len(X)     # partición completa
    assert set(scene_by_path) == set(paths)
    # El medoide de cada cluster es una de sus fotos
    for ci, medoide in summary["medoids"].items():
        assert scene_by_path[medoide] == ci


def test_store_persiste_escena(tmp_path):
    s = HistoryStore(db_path=tmp_path / "h.db")
    s.upsert([
        {"path": "a.jpg", "label": "positive", "rating": 2, "pick": 0,
         "capture_time": "", "develop": {}, "crop": {}, "develop_extreme": 0, "source": "catalog"},
        {"path": "b.jpg", "label": "positive", "rating": 2, "pick": 0,
         "capture_time": "", "develop": {}, "crop": {}, "develop_extreme": 0, "source": "catalog"},
    ])
    assert s.paths_by_label("positive") == ["a.jpg", "b.jpg"]
    s.set_scenes({"a.jpg": "0", "b.jpg": "0"})
    assert s.counts_by_scene() == {"0": 2}
