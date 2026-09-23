import logging
from datetime import datetime
from pathlib import Path
import numpy as np
import json
import hashlib

from services.analysis_store import get_all_analysis
from services.app_paths import get_analysis_dir
from services import embedding_service
from services.thumbnail_store import thumb_url

logger = logging.getLogger(__name__)

# Storyline 2.0 - Parámetros de segmentación ajustados
MIN_SEGMENT_PHOTOS = 6                  # Min fotos para considerar un segmento consolidado
MIN_SEGMENT_DURATION_MINUTES = 1.0      # Min duración de un segmento antes de permitir un soft cut por escena
MIN_SEMANTIC_PHOTOS = 3                 # Min fotos antes de empezar a chequear cambios semánticos

HARD_GAP_MINUTES = 3.0                  # Inactividad absoluta (corte seguro)
SOFT_GAP_MINUTES = 1.0                  # Pausa notable en sesión activa
CONTEXT_CHANGE_THRESHOLD = 0.12         # Sensibilidad semántica estándar
STRONG_SCENE_CHANGE = 0.18              # Cambio drástico de ambiente/escena corta

def get_overrides_path(directory: str) -> Path:
    dir_hash = hashlib.md5(directory.encode('utf-8')).hexdigest()
    get_analysis_dir().mkdir(parents=True, exist_ok=True)
    return get_analysis_dir() / f"{dir_hash}_storyline_overrides.json"

def load_overrides(directory: str) -> dict:
    p = get_overrides_path(directory)
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error cargando overrides: {e}")
    return {}

def save_override(directory: str, photo_path: str, chapter_id: str):
    overrides = load_overrides(directory)
    overrides[photo_path] = chapter_id
    p = get_overrides_path(directory)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2)


def build_photo_chapter_map_from_records(records: list, analyses: list | None = None) -> dict[int, str]:
    """
    Construye un mapa rápido {idx_foto: chapter_id} para segmentar el evento
    en capítulos cronológicos (pacing) usando los EXIF datetime de los records.
    """
    if not records:
        return {}

    parsed = []
    for idx, r in enumerate(records):
        dt = None
        dt_str = getattr(r, "exif_datetime", None)
        if dt_str:
            for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(str(dt_str).strip()[:19], fmt)
                    break
                except Exception:
                    pass
        parsed.append((idx, dt))

    chapter_map: dict[int, str] = {}
    current_chapter_idx = 0
    last_dt = None

    for idx, dt in parsed:
        is_detail = analyses and analyses[idx].scene_type == "detail"
        if is_detail:
            chapter_map[idx] = "capitulo_broll"
            continue

        if dt is not None and last_dt is not None:
            delta_sec = (dt - last_dt).total_seconds()
            if delta_sec > HARD_GAP_MINUTES * 60:
                current_chapter_idx += 1
        
        chapter_map[idx] = f"capitulo_{current_chapter_idx}"
        if dt is not None:
            last_dt = dt

    return chapter_map


def build_storyline(directory: str) -> list[dict]:
    """
    Storyline Engine (V2):
    Divide el evento en 'Segmentos' y luego aplica overrides manuales.
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
                "embedding": None,
                "scene_type": p.scene_type,
            })
        except Exception:
            continue

    valid_photos.sort(key=lambda x: x["dt"])
    if not valid_photos:
        return []

    # 2. Cargar embeddings
    for ph in valid_photos:
        vec = embedding_service.load_cached_embedding(ph["path"], ph["mtime"])
        if vec is not None:
            ph["embedding"] = vec

    # 3. Motor Temporal y Semántico
    segments = []
    current_segment = [valid_photos[0]]
    recent_embeddings = [valid_photos[0]["embedding"]] if valid_photos[0]["embedding"] is not None else []

    for i in range(1, len(valid_photos)):
        curr_photo = valid_photos[i]
        prev_photo = valid_photos[i-1]
        curr_emb = curr_photo["embedding"]
        
        delta_sec = (curr_photo["dt"] - prev_photo["dt"]).total_seconds()
        duration_sec = (curr_photo["dt"] - current_segment[0]["dt"]).total_seconds()
        
        force_cut = False
        
        # Señal A: Hard Gap (Inactividad absoluta >= 5 min)
        if delta_sec > HARD_GAP_MINUTES * 60:
            force_cut = True
            
        # Señal B: Soft Gap (Pausa notable >= 2 min con suficientes fotos en el segmento)
        elif delta_sec > SOFT_GAP_MINUTES * 60 and len(current_segment) >= MIN_SEMANTIC_PHOTOS:
            force_cut = True
            
        # Señal C: Cambio Semántico de Escena
        elif len(current_segment) >= MIN_SEMANTIC_PHOTOS:
            if curr_emb is not None and recent_embeddings:
                avg_context = np.mean(recent_embeddings[-3:], axis=0)
                norm = np.linalg.norm(avg_context)
                if norm > 0:
                    avg_context = avg_context / norm
                    context_change = 1.0 - float(np.dot(curr_emb, avg_context))
                    # C1. Cambio drástico de escena (ej. cambio de habitación / mesa de dulces / exterior)
                    if context_change > STRONG_SCENE_CHANGE:
                        force_cut = True
                    # C2. Cambio acumulado moderado con duración mínima de segmento
                    elif len(current_segment) >= MIN_SEGMENT_PHOTOS and duration_sec >= MIN_SEGMENT_DURATION_MINUTES * 60 and context_change > CONTEXT_CHANGE_THRESHOLD:
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

    # 3.5 Extraer "B-Roll / Detalles" en un segmento especial
    broll_segment = []
    main_segments = []
    for segment in segments:
        main_seg = []
        for p in segment:
            if p.get("scene_type") == "detail":
                broll_segment.append(p)
            else:
                main_seg.append(p)
        if main_seg:
            main_segments.append(main_seg)
    
    if broll_segment:
        # B-Roll as a single separate segment at the end
        main_segments.append(broll_segment)

    segments = main_segments

    # 4. Asignar IDs y crear diccionarios de segmentos iniciales
    # Para permitir reasignación, usamos un mapa.
    chapter_map = {}
    for c_idx, segment in enumerate(segments):
        c_id = f"segment_{c_idx}"
        paths = [p["path"] for p in segment]
        
        # Ordenamos temporalmente solo para sacar el medoid cronológico y horas
        segment.sort(key=lambda x: x["dt"])
        medoid_path = segment[len(segment) // 2]["path"]
        
        chapter_map[c_id] = {
            "id": c_id,
            "name": f"Momento {c_idx + 1}",
            "start_time": segment[0]["dt"].strftime("%H:%M"),
            "end_time": segment[-1]["dt"].strftime("%H:%M"),
            "photo_count": len(paths),
            "medoid_thumb": thumb_url(medoid_path),
            "medoid_path": medoid_path,
            "paths": paths
        }

    # 5. Aplicar Overrides Manuales (si los hay)
    overrides = load_overrides(directory)
    if overrides:
        # Remover de su lugar original y poner en el nuevo
        for p_path, new_cid in overrides.items():
            if new_cid not in chapter_map:
                continue # Capítulo destino no existe
                
            # Buscar dónde estaba
            for cid, c_data in chapter_map.items():
                if p_path in c_data["paths"] and cid != new_cid:
                    c_data["paths"].remove(p_path)
                    chapter_map[new_cid]["paths"].append(p_path)
                    break

        # Recalcular photo_count y eliminar capítulos vacíos si quedaron
        for cid in list(chapter_map.keys()):
            chapter_map[cid]["photo_count"] = len(chapter_map[cid]["paths"])
            if chapter_map[cid]["photo_count"] == 0:
                del chapter_map[cid]

    # Convertir a lista y devolver
    return list(chapter_map.values())
