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
    """Convierte un pHash hexadecimal a array de 64 bits usando np.unpackbits."""
    try:
        raw_bytes = bytes.fromhex(str(hash_str).strip())
        if len(raw_bytes) < 8:
            raw_bytes = raw_bytes.ljust(8, b"\x00")
        return np.unpackbits(np.frombuffer(raw_bytes[:8], dtype=np.uint8))
    except Exception:
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
    burst_ids: list[int | None] | None = None,
) -> list[ImageCluster]:
    """
    Agrupa imágenes en ráfagas/grupos de similitud de forma optimizada O(n·k)
    mediante ventana temporal deslizante y componentes conexos (Union-Find).

    Estrategia:
    1. Separa las imágenes por tipo de escena ("portrait" | "detail").
    2. Dentro de cada tipo, ordena por timestamp EXIF y compara únicamente dentro
       de una ventana temporal deslizante (|Δt| <= 2 * max_time_gap_seconds).
    3. Imágenes sin fecha EXIF o hashes inválidos se evalúan de forma segura.

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
    if burst_ids is None:
        burst_ids = [None] * n

    # --- Adaptive Threshold ---
    valid_ts = sorted([t for t in timestamps if t > 0])
    if len(valid_ts) > 10:
        dts = np.diff(valid_ts)
        median_dt = float(np.median(dts[dts < 60.0])) # ignorar saltos > 1 min
        if median_dt < 1.5:
            max_time_gap_seconds = min(max_time_gap_seconds, 2.0)
            epsilon_hash = min(epsilon_hash, 10)
        elif median_dt > 4.0:
            max_time_gap_seconds = max(max_time_gap_seconds, 6.0)
            epsilon_hash = max(epsilon_hash, 14)
    # --------------------------

    # Estructura Union-Find con compresión de caminos
    parent = list(range(n))

    def find(i: int) -> int:
        path = []
        while parent[i] != i:
            path.append(i)
            i = parent[i]
        for node in path:
            parent[node] = i
        return i

    def union(i: int, j: int) -> None:
        root_i, root_j = find(i), find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    # Agrupar índices por tipo de escena
    scene_groups: dict[str, list[int]] = {}
    for idx, sc in enumerate(scene_types):
        scene_groups.setdefault(sc, []).append(idx)

    max_dt_allowed = 2.0 * max_time_gap_seconds

    for sc, indices in scene_groups.items():
        has_time = [i for i in indices if timestamps[i] > 0]
        no_time = [i for i in indices if timestamps[i] <= 0]

        # 1. Comparar fotos con timestamp cronológico en ventana deslizante
        has_time.sort(key=lambda idx: timestamps[idx])
        for k in range(len(has_time)):
            i = has_time[k]
            t_i = timestamps[i]
            h_i = hash_bits[i]
            for m in range(k + 1, len(has_time)):
                j = has_time[m]
                dt = timestamps[j] - t_i
                if dt > max_dt_allowed:
                    break
                h_dist = int(np.sum(h_i != hash_bits[j]))
                
                # Si las fotos tienen el mismo Burst ID (y no es None), forzamos la unión
                b_i = burst_ids[i]
                b_j = burst_ids[j]
                if b_i is not None and b_i == b_j:
                    union(i, j)
                    continue

                # Si las fotos fueron tomadas con <= 1.5s de diferencia, es la misma ráfaga
                # incluso si el pHash cambia drásticamente por cambio de orientación (Horizontal vs Vertical).
                if dt <= 1.5:
                    union(i, j)
                else:
                    combined = h_dist + (dt / max_time_gap_seconds) * (epsilon_hash / 2)
                    if combined <= epsilon_hash:
                        union(i, j)

        # 2. Comparar fotos sin timestamp (o 0) con el grupo
        for i in no_time:
            h_i = hash_bits[i]
            for j in indices:
                if i != j:
                    h_dist = int(np.sum(h_i != hash_bits[j]))
                    if h_dist <= epsilon_hash:
                        union(i, j)

    # Construir clusters a partir de las raíces de Union-Find
    clusters_dict: dict[int, list[int]] = {}
    for idx in range(n):
        root = find(idx)
        clusters_dict.setdefault(root, []).append(idx)

    # Ordenar clusters según el primer índice que aparece
    sorted_groups = sorted(clusters_dict.values(), key=lambda g: min(g))

    clusters = []
    for cluster_id, indices in enumerate(sorted_groups):
        scene = scene_types[indices[0]] if indices else "detail"
        clusters.append(ImageCluster(
            cluster_id=int(cluster_id),
            scene_type=scene,
            image_indices=indices,
        ))

    logger.info(
        f"Clustering O(n·k): {n} imágenes → {len(clusters)} grupos "
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


def find_exact_duplicates(
    phashes: list[str],
    exif_datetimes: list[str] | None = None,
    max_hamming_distance: int = 2,
    max_time_gap_seconds: float = 3.0,
) -> dict[int, int]:
    """
    Identifica fotos que son duplicados exactos o cuasi-idénticos (pHash dist <= max_hamming_distance).
    Retorna un diccionario {indice_duplicado: indice_original_maestro}.
    
    Permite detectar ráfagas continuas donde varias fotos son prácticamente el mismo encuadre.
    """
    n = len(phashes)
    if n <= 1:
        return {}

    hash_bits = [_hash_to_bits(h) for h in phashes]
    timestamps = [_parse_exif_datetime(dt) for dt in exif_datetimes] if exif_datetimes else [0.0] * n

    duplicates_map: dict[int, int] = {}
    indices = list(range(n))
    if any(t > 0 for t in timestamps):
        indices.sort(key=lambda idx: (timestamps[idx] if timestamps[idx] > 0 else float("inf"), idx))

    for k in range(len(indices)):
        i = indices[k]
        if i in duplicates_map:
            continue
        h_i = hash_bits[i]
        t_i = timestamps[i]

        for m in range(k + 1, len(indices)):
            j = indices[m]
            if j in duplicates_map:
                continue

            t_j = timestamps[j]
            if t_i > 0 and t_j > 0 and (t_j - t_i) > max_time_gap_seconds:
                break

            h_dist = int(np.sum(h_i != hash_bits[j]))
            if h_dist <= max_hamming_distance:
                duplicates_map[j] = i

    return duplicates_map

