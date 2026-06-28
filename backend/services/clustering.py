"""
clustering.py — Agrupamiento de imágenes por similitud visual y temporal.
Usa pHash + timestamps EXIF + DBSCAN para identificar ráfagas y duplicados.
Los grupos de objetos/detalles se separan de los grupos de retratos.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from sklearn.cluster import DBSCAN

logger = logging.getLogger(__name__)

EXIF_DATETIME_FORMATS = [
    "%Y:%m:%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
]


@dataclass
class ImageCluster:
    cluster_id: int
    scene_type: str                    # "portrait" | "detail"
    image_indices: list[int]           # Índices en la lista original de records
    representative_index: int = -1     # Índice de la imagen "ganadora" del grupo


def _parse_exif_datetime(dt_str: str) -> float:
    """Convierte una fecha EXIF a timestamp Unix. Retorna 0.0 si no puede parsear."""
    for fmt in EXIF_DATETIME_FORMATS:
        try:
            return datetime.strptime(dt_str.strip(), fmt).timestamp()
        except ValueError:
            continue
    return 0.0


def _hash_to_bits(hash_str: str) -> np.ndarray:
    """Convierte un pHash hexadecimal a array de bits para calcular distancia de Hamming."""
    try:
        val = int(hash_str, 16)
        bits = [(val >> i) & 1 for i in range(64)]
        return np.array(bits, dtype=np.uint8)
    except (ValueError, TypeError):
        return np.zeros(64, dtype=np.uint8)


def _hamming_distance(a: np.ndarray, b: np.ndarray) -> int:
    """Distancia de Hamming entre dos arrays de bits."""
    return int(np.sum(a != b))


def cluster_images(
    phashes: list[str],
    exif_datetimes: list[str],
    scene_types: list[str],
    epsilon_hash: int = 12,
    max_time_gap_seconds: float = 5.0,
) -> list[ImageCluster]:
    """
    Agrupa imágenes en ráfagas/grupos de similitud.

    Estrategia:
    1. Separa las imágenes en dos grupos: retratos y detalles.
    2. Dentro de cada grupo, agrupa por similitud de pHash (distancia Hamming ≤ epsilon)
       y proximidad temporal (diferencia de tiempo EXIF ≤ max_time_gap_seconds).
    3. Imágenes sin fecha EXIF o con hash inválido se tratan como grupos individuales.

    Args:
        phashes: Lista de pHash hexadecimales.
        exif_datetimes: Lista de strings de fecha EXIF.
        scene_types: Lista de "portrait" | "detail" por imagen.
        epsilon_hash: Distancia máxima de Hamming para considerarlas similares.
        max_time_gap_seconds: Diferencia máxima de tiempo para agrupar.

    Returns:
        Lista de ImageCluster.
    """
    n = len(phashes)
    if n == 0:
        return []

    # Convertir hashes y fechas
    hash_bits = [_hash_to_bits(h) for h in phashes]
    timestamps = [_parse_exif_datetime(dt) for dt in exif_datetimes]

    # Construir matriz de distancia combinada (hash + temporal)
    # Normalizamos ambas métricas a [0,1] y las combinamos
    distance_matrix = np.zeros((n, n), dtype=np.float32)

    for i in range(n):
        for j in range(i + 1, n):
            # Solo agrupar imágenes del mismo tipo de escena
            if scene_types[i] != scene_types[j]:
                distance_matrix[i, j] = 9999.0
                distance_matrix[j, i] = 9999.0
                continue

            hash_dist = _hamming_distance(hash_bits[i], hash_bits[j])

            # Distancia temporal (en segundos), ignorando si alguna es 0 (sin EXIF)
            t_i, t_j = timestamps[i], timestamps[j]
            if t_i > 0 and t_j > 0:
                time_dist = abs(t_i - t_j)
            else:
                time_dist = 0.0  # Sin EXIF: no penalizar por tiempo

            # Combinar: si el hash es muy diferente O el tiempo es muy lejano → no agrupar
            combined = hash_dist + (time_dist / max_time_gap_seconds) * (epsilon_hash / 2)
            distance_matrix[i, j] = combined
            distance_matrix[j, i] = combined

    # DBSCAN con la matriz de distancia precalculada
    db = DBSCAN(
        eps=epsilon_hash,
        min_samples=1,
        metric="precomputed",
    )
    labels = db.fit_predict(distance_matrix)

    # Construir clusters
    clusters_dict: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        if label not in clusters_dict:
            clusters_dict[label] = []
        clusters_dict[label].append(idx)

    clusters = []
    for cluster_id, indices in sorted(clusters_dict.items()):
      # Determinar el tipo de escena del cluster (todos deberían ser iguales)
      scene = scene_types[indices[0]] if indices else "detail"
      clusters.append(ImageCluster(
          cluster_id=int(cluster_id),
          scene_type=scene,
          image_indices=indices,
      ))

    logger.info(
        f"Clustering: {n} imágenes → {len(clusters)} grupos "
        f"({sum(1 for c in clusters if c.scene_type == 'portrait')} retratos, "
        f"{sum(1 for c in clusters if c.scene_type == 'detail')} detalles)"
    )
    return clusters


def assign_cluster_representatives(
    clusters: list[ImageCluster],
    blur_scores: list[float],
    aesthetic_scores: list[float],
) -> list[ImageCluster]:
    """
    Asigna el representante (ganador) de cada cluster basándose en
    una puntuación combinada de nitidez y estética.

    La imagen con mayor puntuación combinada dentro del grupo se convierte
    en el "Seleccionado"; el resto son "Duplicados" si el grupo tiene más de 1.
    """
    for cluster in clusters:
        if not cluster.image_indices:
            continue

        if len(cluster.image_indices) == 1:
            cluster.representative_index = cluster.image_indices[0]
            continue

        # Puntuación combinada: 60% nitidez + 40% estética (normalizado)
        scores = []
        for idx in cluster.image_indices:
            blur = blur_scores[idx] if idx < len(blur_scores) else 0.0
            aesthetic = aesthetic_scores[idx] if idx < len(aesthetic_scores) else 0.0
            combined = 0.6 * blur + 0.4 * aesthetic * 100  # Escalar estética a rango similar
            scores.append(combined)

        best_local_idx = int(np.argmax(scores))
        cluster.representative_index = cluster.image_indices[best_local_idx]

    return clusters
