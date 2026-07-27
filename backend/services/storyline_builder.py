import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
import numpy as np

from services.analysis_store import get_all_analysis
from services import embedding_service
from services.scene_grouping import cluster_embeddings

logger = logging.getLogger(__name__)

def build_storyline(directory: str, gap_minutes: int = 30, max_subchapters: int = 5) -> list[dict]:
    """
    Construye el storyline dividiendo cronológicamente (basado en huecos de tiempo)
    y subdividiendo visualmente cada capítulo.
    """
    photos = get_all_analysis(directory)
    if not photos:
        return []

    # 1. Parsear fechas y ordenar
    valid_photos = []
    for p in photos:
        dt_str = p.exif_datetime
        if not dt_str:
            continue
        try:
            # Formato común EXIF: "YYYY:MM:DD HH:MM:SS"
            dt = datetime.strptime(dt_str[:19].replace(":", "-", 2), "%Y-%m-%d %H:%M:%S")
            valid_photos.append({"path": p.path, "dt": dt,
                                 "mtime": p.mtime, "filename": Path(p.path).name})
        except Exception:
            continue

    valid_photos.sort(key=lambda x: x["dt"])

    if not valid_photos:
        return []

    # 2. División Temporal Inicial (Capítulos Principales)
    chapters = []
    current_chapter = [valid_photos[0]]
    
    for i in range(1, len(valid_photos)):
        delta = valid_photos[i]["dt"] - valid_photos[i-1]["dt"]
        if delta.total_seconds() > gap_minutes * 60:
            chapters.append(current_chapter)
            current_chapter = []
        current_chapter.append(valid_photos[i])
        
    if current_chapter:
        chapters.append(current_chapter)

    # 3. Subdivisión Visual (Escenas dentro del Capítulo) y Medoides
    storyline = []
    
    for c_idx, chapter_photos in enumerate(chapters):
        paths = [p["path"] for p in chapter_photos]

        # Recuperar embeddings ya cacheados (mtime en memoria: sin re-stat del NAS)
        vecs = []
        kept_paths = []
        for ph in chapter_photos:
            vec = embedding_service.load_cached_embedding(ph["path"], ph["mtime"])
            if vec is not None:
                vecs.append(vec)
                kept_paths.append(ph["path"])

        medoid_path = paths[len(paths) // 2] # Fallback medoid temporal
        
        if vecs:
            X = np.stack(vecs)
            k = min(max_subchapters, len(vecs))
            labels, centers = cluster_embeddings(X, k=k)
            
            # El medoide principal del capítulo es el del cluster más grande
            sizes = [sum(1 for l in labels if l == ci) for ci in range(k)]
            biggest_cluster = int(np.argmax(sizes))
            
            # Encontrar foto más central del cluster más grande
            idxs = [i for i, l in enumerate(labels) if l == biggest_cluster]
            dists = [float(np.linalg.norm(X[i] - centers[biggest_cluster])) for i in idxs]
            medoid_path = kept_paths[idxs[int(np.argmin(dists))]]

        storyline.append({
            "id": f"chapter_{c_idx}",
            "start_time": chapter_photos[0]["dt"].strftime("%H:%M"),
            "end_time": chapter_photos[-1]["dt"].strftime("%H:%M"),
            "photo_count": len(chapter_photos),
            # size (no type) es el parámetro real del endpoint; la ruta va
            # URL-encodeada porque las carpetas reales tienen espacios y tildes.
            "medoid_thumb": f"/thumbnail?path={quote(medoid_path)}&size=ui",
            "medoid_path": medoid_path
        })

    return storyline
