from __future__ import annotations
from .types import PhotoMetrics
from .analysis.embedding import hamming
from .presets import Preset


def group_bursts(photos: list[PhotoMetrics], preset: Preset) -> list[list[int]]:
    """Agrupa índices de fotos consecutivas en el tiempo y perceptualmente similares."""
    if not photos:
        return []
    order = sorted(range(len(photos)), key=lambda i: photos[i].timestamp)
    groups: list[list[int]] = []
    current: list[int] = [order[0]]
    for idx in order[1:]:
        prev, cur = photos[current[-1]], photos[idx]
        same_time = (cur.timestamp - prev.timestamp) <= preset.burst_time_window_s
        similar = hamming(cur.phash, prev.phash) <= preset.phash_max_distance
        if same_time and similar:
            current.append(idx)
        else:
            groups.append(current)
            current = [idx]
    groups.append(current)
    return groups
