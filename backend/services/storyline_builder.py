import logging
from datetime import datetime
from pathlib import Path
import numpy as np

from services.analysis_store import get_all_analysis
from services import embedding_service
from services.thumbnail_store import thumb_url

logger = logging.getLogger(__name__)

# Storyline 2.0 - Foundation (Sprint 1 & 2)
# Parámetros de segmentación configurables
MIN_SEGMENT_PHOTOS = 30
MIN_SEGMENT_DURATION_MINUTES = 2.0
HARD_GAP_MINUTES = 15.0
CONTEXT_CHANGE_THRESHOLD = 0.45  # Distancia coseno (0 a 2). Mayor significa más diferencia.

def build_storyline(directory: str) -> list[dict]:
    """
    Storyline Engine (V2 Foundation):
    Divide el evento en 'Segmentos/Sucesos' usando:
    1. Tiempo (gaps duros y duración mínima).
    2. Semántica visual (cambios de contexto bruscos).
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
            dt = datetime.strptime(dt_str[:19].replace(":", "-", 2), "%Y-%m-%d %H:%M:%S")
            valid_photos.append({
                "path": p.path, 
                "dt": dt,
                "mtime": p.mtime, 
                "filename": Path(p.path).name,
                "embedding": None
            })
        except Exception:
            continue

    valid_photos.sort(key=lambda x: x["dt"])
    if not valid_photos:
        return []

    # 2. Cargar embeddings (con fallback silencioso)
    for ph in valid_photos:
        vec = embedding_service.load_cached_embedding(ph["path"], ph["mtime"])
        if vec is not None:
            ph["embedding"] = vec

    # 3. Motor Temporal y Semántico (Change Point Detection)
    segments = []
    current_segment = [valid_photos[0]]
    
    # Mantenemos un "contexto reciente" (promedio de los últimos N embeddings) para suavizar
    recent_embeddings = [valid_photos[0]["embedding"]] if valid_photos[0]["embedding"] is not None else []

    for i in range(1, len(valid_photos)):
        curr_photo = valid_photos[i]
        prev_photo = valid_photos[i-1]
        curr_emb = curr_photo["embedding"]
        
        delta_sec = (curr_photo["dt"] - prev_photo["dt"]).total_seconds()
        duration_sec = (curr_photo["dt"] - current_segment[0]["dt"]).total_seconds()
        
        force_cut = False
        
        # Señal A: Hard Gap (Corte por inactividad absoluta)
        if delta_sec > HARD_GAP_MINUTES * 60:
            force_cut = True
            
        # Señal B: Cambio de Contexto Visual (Solo si ya cumplimos los mínimos)
        elif len(current_segment) >= MIN_SEGMENT_PHOTOS and duration_sec >= MIN_SEGMENT_DURATION_MINUTES * 60:
            if curr_emb is not None and recent_embeddings:
                # Promedio del contexto reciente (últimas 5 fotos) para evitar cortes por 1 foto rara
                avg_context = np.mean(recent_embeddings[-5:], axis=0)
                # Normalize context to compute cosine distance
                norm = np.linalg.norm(avg_context)
                if norm > 0:
                    avg_context = avg_context / norm
                    # Distancia coseno
                    context_change = 1.0 - float(np.dot(curr_emb, avg_context))
                    if context_change > CONTEXT_CHANGE_THRESHOLD:
                        logger.debug(f"Storyline: Corte semántico detectado. Cambio: {context_change:.2f}")
                        force_cut = True
        
        if force_cut:
            segments.append(current_segment)
            current_segment = [curr_photo]
            recent_embeddings = []
        else:
            current_segment.append(curr_photo)
            
        if curr_emb is not None:
            recent_embeddings.append(curr_emb)

    if current_segment:
        segments.append(current_segment)

    # 4. Construir la UI Response (Scene Renderer)
    storyline = []
    
    for c_idx, segment in enumerate(segments):
        # El medoide cronológico/visual:
        # Por ahora (V1) seleccionamos la foto del medio del segmento como portada
        medoid_idx = len(segment) // 2
        medoid_path = segment[medoid_idx]["path"]
        
        storyline.append({
            "id": f"segment_{c_idx}",
            "name": f"Momento {c_idx + 1}",  # Preparado para que el usuario pueda editarlo en el futuro
            "start_time": segment[0]["dt"].strftime("%H:%M"),
            "end_time": segment[-1]["dt"].strftime("%H:%M"),
            "photo_count": len(segment),
            "medoid_thumb": thumb_url(medoid_path),
            "medoid_path": medoid_path
        })

    return storyline
