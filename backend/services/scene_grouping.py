"""
scene_grouping.py — Fase I: descubre las categorías de escena reales del
fotógrafo agrupando los embeddings CLIP de sus fotos seleccionadas.

Solo tenemos el encoder VISUAL de CLIP (no el de texto), así que no hay
zero-shot con prompts: el camino es clustering no supervisado. Las categorías
emergen de los datos (atardecer, retrato interior, grupal, detalle…) y cada
cluster queda con una foto medoide como representante para nombrarlo en la UI.

Alimenta la Fase J (revelado por escena) y K (recorte por escena).
"""
import logging
from pathlib import Path

import numpy as np

from services.history_store import HistoryStore

logger = logging.getLogger(__name__)

DEFAULT_K = 10
_CENTROIDS_PATH = Path(__file__).parent.parent / "models" / "scene_centroids.npy"


def save_centroids(centers: np.ndarray) -> None:
    _CENTROIDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.save(_CENTROIDS_PATH, np.asarray(centers, dtype=np.float32))


def load_centroids() -> np.ndarray | None:
    if not _CENTROIDS_PATH.exists():
        return None
    try:
        return np.load(_CENTROIDS_PATH)
    except Exception:
        return None


def nearest_scene(embedding: np.ndarray | None) -> str | None:
    """Escena (id) más cercana a un embedding, según los centroides guardados.
    Permite asignar una foto NUEVA (en el culling) a una categoría aprendida."""
    if embedding is None:
        return None
    centers = load_centroids()
    if centers is None or len(centers) == 0:
        return None
    d = np.linalg.norm(centers - np.asarray(embedding, dtype=np.float32), axis=1)
    return str(int(np.argmin(d)))


def cluster_embeddings(X: np.ndarray, k: int = DEFAULT_K, seed: int = 0):
    """KMeans sobre embeddings (ya L2-normalizados → equivale a coseno).
    Devuelve (labels, centroides). k se acota si hay menos ejemplos que k."""
    from sklearn.cluster import KMeans
    k = max(1, min(k, len(X)))
    km = KMeans(n_clusters=k, random_state=seed, n_init=10)
    labels = km.fit_predict(X)
    return labels, km.cluster_centers_


def assign_from_matrix(paths: list[str], X: np.ndarray, k: int = DEFAULT_K):
    """
    Agrupa (paths, X) y arma el resultado: escena por foto, tamaño de cada
    cluster y su medoide (la foto más central, representante para la UI).
    Función pura — el corazón testeable de la fase.
    """
    labels, centers = cluster_embeddings(X, k)
    scene_by_path = {p: str(int(l)) for p, l in zip(paths, labels)}
    sizes: dict[str, int] = {}
    medoids: dict[str, str] = {}
    for ci in range(len(centers)):
        idxs = [i for i, l in enumerate(labels) if l == ci]
        if not idxs:
            continue
        sizes[str(ci)] = len(idxs)
        dists = [float(np.linalg.norm(X[i] - centers[ci])) for i in idxs]
        medoids[str(ci)] = paths[idxs[int(np.argmin(dists))]]
    return scene_by_path, {"k": len(centers), "sizes": sizes, "medoids": medoids}, centers


def embed_history(store: HistoryStore | None = None, label: str = "positive",
                  limit: int | None = None) -> dict:
    """
    Lote pesado: calcula (y cachea) el embedding CLIP de las fotos de una
    etiqueta. Reusa el caché en disco, así que es reanudable — re-correr solo
    procesa lo que falta. Requisito de `assign_scenes`.
    """
    from services import embedding_service
    from services.calibration import _load_scaled

    if not embedding_service.is_available():
        return {"error": "CLIP no disponible", "embedded": 0}

    store = store or HistoryStore()
    paths = store.paths_by_label(label)
    if limit:
        paths = paths[:limit]

    embedded = skipped = 0
    for p in paths:
        if embedding_service.embed_path(p, None) is not None:   # ya en caché
            embedded += 1
            continue
        try:
            arr = _load_scaled(p)
        except Exception:
            arr = None
        if arr is None or embedding_service.embed_path(p, arr) is None:
            skipped += 1
        else:
            embedded += 1
    return {"embedded": embedded, "skipped": skipped, "total": len(paths)}


def assign_scenes(store: HistoryStore | None = None, k: int = DEFAULT_K,
                  label: str = "positive") -> dict:
    """
    Agrupa las fotos que YA tienen embedding en caché y persiste su escena.
    Barato (no re-embebe): correr `embed_history` antes.
    """
    from services import embedding_service
    store = store or HistoryStore()

    vecs, kept = [], []
    for p in store.paths_by_label(label):
        v = embedding_service.embed_path(p, None)
        if v is not None:
            vecs.append(v)
            kept.append(p)
    if not vecs:
        return {"clustered": 0, "note": "sin embeddings; corré /history/embed primero"}

    scene_by_path, summary, centers = assign_from_matrix(kept, np.stack(vecs), k)
    store.set_scenes(scene_by_path)
    save_centroids(centers)   # para asignar fotos nuevas a su escena en el culling
    return {"clustered": len(kept), **summary}
