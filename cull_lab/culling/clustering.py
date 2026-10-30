"""
CullLab Burst Clustering & Sequence Grouper
Inspirado en el motor de agrupación de Aftershoot (fuxx_clustering) y Narrative Select.
Agrupa secuencias por delta temporal (Δt <= 2.0s) y distancia visual de embeddings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Sequence


@dataclass
class PhotoMetadata:
    """Metadatos de entrada mínimos requeridos para clusterización y selección."""
    id: str
    file_path: str
    timestamp: float                    # Timestamp POSIX (segundos con decimales)
    focus_score: float = 5.0            # Escala de foco 0 a 10 (Narrative style)
    eye_score: float = 1.0              # Escala ocular -0.5 a 1.0
    aesthetic_score: float = 5.0        # Escala estética 0 a 10
    embedding: Optional[Sequence[float]] = None # Vector 512D normalizado (MobileCLIP)


@dataclass
class CullingClassification:
    """Clasificación resultante para una foto dentro de un cluster."""
    is_top_pick: bool = False
    is_alternate: bool = False
    is_duplicate: bool = False
    is_rejected: bool = False
    combined_score: float = 0.0


@dataclass
class PhotoCluster:
    """Agrupación de fotos pertenecientes a una misma ráfaga o escena."""
    cluster_id: str
    photos: List[PhotoMetadata] = field(default_factory=list)
    classifications: dict[str, CullingClassification] = field(default_factory=dict)
    top_pick_id: Optional[str] = None


class BurstClusterer:
    """
    Motor híbrido de agrupación de ráfagas por tiempo y similitud visual.
    """

    def __init__(
        self,
        max_time_gap: float = 2.0,          # Segundos máximos entre disparos consecutivos
        visual_similarity_thresh: float = 0.82, # Similitud coseno mínima para ráfaga visual
        weight_focus: float = 0.45,
        weight_eyes: float = 0.35,
        weight_aesthetic: float = 0.20,
    ):
        self.max_time_gap = max_time_gap
        self.visual_similarity_thresh = visual_similarity_thresh
        self.w_focus = weight_focus
        self.w_eyes = weight_eyes
        self.w_aes = weight_aesthetic

    def cluster_photos(self, photos: List[PhotoMetadata]) -> List[PhotoCluster]:
        """
        Ordena fotos por timestamp y las particiona en clusters de ráfaga.
        Aplica selección de 'Top Pick' y 'Alternates' dentro de cada grupo.
        """
        if not photos:
            return []

        # 1. Orden cronológico estricto
        sorted_photos = sorted(photos, key=lambda p: p.timestamp)

        clusters: List[PhotoCluster] = []
        current_cluster: List[PhotoMetadata] = [sorted_photos[0]]

        for prev, curr in zip(sorted_photos[:-1], sorted_photos[1:]):
            time_delta = curr.timestamp - prev.timestamp

            # Si el salto supera el umbral temporal, nueva ráfaga
            if time_delta > self.max_time_gap:
                clusters.append(self._finalize_cluster(f"burst_{len(clusters)+1}", current_cluster))
                current_cluster = [curr]
                continue

            # Si hay embeddings disponibles, verificar salto visual drástico (giro de 180°)
            if prev.embedding is not None and curr.embedding is not None:
                sim = self._cosine_similarity(prev.embedding, curr.embedding)
                if sim < self.visual_similarity_thresh:
                    clusters.append(self._finalize_cluster(f"burst_{len(clusters)+1}", current_cluster))
                    current_cluster = [curr]
                    continue

            current_cluster.append(curr)

        if current_cluster:
            clusters.append(self._finalize_cluster(f"burst_{len(clusters)+1}", current_cluster))

        return clusters

    def _finalize_cluster(self, cluster_id: str, photos: List[PhotoMetadata]) -> PhotoCluster:
        """Calcula el score ponderado de cada foto y elige la mejor de la ráfaga."""
        cluster = PhotoCluster(cluster_id=cluster_id, photos=photos)

        scored: List[tuple[PhotoMetadata, float]] = []
        for p in photos:
            # Normalizar ojo a escala 0..10 (-0.5 a 1.0 -> 0.0 a 10.0)
            norm_eye = max(0.0, (p.eye_score + 0.5) / 1.5) * 10.0
            combined = (
                p.focus_score * self.w_focus
                + norm_eye * self.w_eyes
                + p.aesthetic_score * self.w_aes
            )
            scored.append((p, combined))

        # Ordenar por score descendente
        scored.sort(key=lambda x: x[1], reverse=True)

        # La primera es el Top Pick
        best_photo, best_score = scored[0]
        cluster.top_pick_id = best_photo.id

        for idx, (photo, score) in enumerate(scored):
            is_top = (idx == 0)
            # Alternates son fotos con calidad cercana (dentro del 10% del mejor)
            is_alt = (idx > 0) and (score >= best_score * 0.90) and (photo.eye_score >= 0.5)
            is_dup = (idx > 0) and not is_alt
            is_rej = (photo.focus_score < 3.0) or (photo.eye_score < 0.0)

            cluster.classifications[photo.id] = CullingClassification(
                is_top_pick=is_top,
                is_alternate=is_alt,
                is_duplicate=is_dup,
                is_rejected=is_rej,
                combined_score=score,
            )

        return cluster

    @staticmethod
    def _cosine_similarity(v1: Sequence[float], v2: Sequence[float]) -> float:
        """Calcula similitud coseno entre dos vectores numéricos."""
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if norm1 <= 1e-8 or norm2 <= 1e-8:
            return 0.0
        return dot / (norm1 * norm2)
