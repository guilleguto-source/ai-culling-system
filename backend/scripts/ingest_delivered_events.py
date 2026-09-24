"""
ingest_delivered_events.py — Escaneo e ingesta recursiva de fotos entregadas a clientes.

Ignora carpetas excluidas (ej. 'ruth') y omite archivos ya procesados previamente.
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import json
import logging
import cv2

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.history_store import HistoryStore
from services.taste_model import taste_model
from services.embedding_service import embed, is_available as is_clip_available

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest_delivered")


def extract_exif(img_path: Path) -> dict:
    metadata = {
        "capture_time": None,
        "camera": None,
        "lens": None,
        "iso": None,
        "f_stop": None,
        "shutter": None,
        "focal": None
    }
    try:
        from PIL import Image, ExifTags
        with Image.open(img_path) as img:
            exif_raw = img._getexif()
            if exif_raw:
                exif = {ExifTags.TAGS.get(k, k): v for k, v in exif_raw.items()}
                dt_str = exif.get("DateTimeOriginal") or exif.get("DateTime")
                if dt_str:
                    try:
                        clean_dt = str(dt_str).replace("-", ":")
                        parts = clean_dt.split(" ")
                        d_parts = parts[0].split(":")
                        iso_str = f"{d_parts[0]}-{d_parts[1]}-{d_parts[2]}T{parts[1]}"
                        metadata["capture_time"] = iso_str
                    except Exception:
                        metadata["capture_time"] = str(dt_str)
                
                make = str(exif.get("Make", "")).strip()
                model = str(exif.get("Model", "")).strip()
                if model:
                    metadata["camera"] = f"{make} {model}".strip() if make and make not in model else model
                
                metadata["lens"] = str(exif.get("LensModel", "")).strip() or None
                metadata["iso"] = exif.get("ISOSpeedRatings") or exif.get("PhotographicSensitivity")
                
                f_num = exif.get("FNumber")
                if f_num:
                    metadata["f_stop"] = float(f_num) if isinstance(f_num, (int, float)) else float(f_num[0]) / float(f_num[1]) if isinstance(f_num, tuple) else None
                
                focal = exif.get("FocalLength")
                if focal:
                    metadata["focal"] = float(focal) if isinstance(focal, (int, float)) else float(focal[0]) / float(focal[1]) if isinstance(focal, tuple) else None
    except Exception as e:
        logger.debug(f"Error EXIF en {img_path.name}: {e}")
        
    return metadata


def run_recursive_ingest(directories: list[str], ignore_patterns: list[str] = None):
    if ignore_patterns is None:
        ignore_patterns = ["ruth"]

    store = HistoryStore()
    has_clip = is_clip_available()
    
    # Cargar paths existentes en HistoryStore para no re-procesar los ya indexados
    with store._conn() as conn:
        existing_paths = set(r[0] for r in conn.execute("SELECT path FROM history").fetchall())
    
    logger.info(f"Iniciando escaneo recursivo. Ya en base de datos: {len(existing_paths)} fotos.")
    logger.info(f"Ignorando patrones: {ignore_patterns}. CLIP disponible: {has_clip}")

    all_jpg_files = []
    
    for base_dir_str in directories:
        base_dir = Path(base_dir_str)
        if not base_dir.exists():
            continue
        
        logger.info(f"Buscando fotos recursivamente en {base_dir}...")
        for ext in ("*.jpg", "*.jpeg", "*.JPG", "*.JPEG"):
            for f in base_dir.rglob(ext):
                # Verificar exclusiones
                path_str_lower = str(f).lower()
                if any(ign.lower() in path_str_lower for ign in ignore_patterns):
                    continue
                all_jpg_files.append(f)

    # Eliminar duplicados de lista de archivos
    all_jpg_files = list(set(all_jpg_files))
    new_files = [f for f in all_jpg_files if str(f) not in existing_paths]
    
    logger.info(f"Total fotos encontradas (sin Ruth): {len(all_jpg_files)}")
    logger.info(f"Fotos nuevas por procesar: {len(new_files)}")
    
    if not new_files:
        logger.info("Todas las fotos ya fueron procesadas previamente.")
        return

    batch_size = 100
    current_batch = []
    total_added = 0
    clip_count = 0

    for i, img_file in enumerate(new_files, 1):
        # Determinar nombre del evento (directorio padre o carpeta superior)
        event_name = img_file.parent.name
        
        exif = extract_exif(img_file)
        current_batch.append({
            "path": str(img_file),
            "label": "positive",
            "rating": 3,
            "pick": 1,
            "capture_time": exif["capture_time"] or datetime.now().isoformat(),
            "develop": {
                "Exposure2012": 0.0,
                "Camera": exif["camera"],
                "Lens": exif["lens"],
                "ISO": exif["iso"],
                "Focal": exif["focal"],
                "FStop": exif["f_stop"]
            },
            "crop": {},
            "develop_extreme": 0,
            "source": f"delivered_export:{event_name}",
            "scene": event_name
        })

        if has_clip:
            try:
                img_bgr = cv2.imread(str(img_file))
                if img_bgr is not None:
                    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                    emb = embed(img_rgb)
                    if emb is not None:
                        taste_model.add_example(emb, +1, source="delivered_export", event_dir=str(img_file.parent))
                        clip_count += 1
            except Exception as e:
                logger.debug(f"Error CLIP en {img_file.name}: {e}")

        if len(current_batch) >= batch_size or i == len(new_files):
            store.upsert(current_batch)
            total_added += len(current_batch)
            logger.info(f"Progreso: {total_added}/{len(new_files)} fotos nuevas procesadas ({clip_count} vectores CLIP generados).")
            current_batch = []

    logger.info("\n" + "=" * 50)
    logger.info(f"✨ PROCESAMIENTO RECURSIVO COMPLETADO")
    logger.info(f"Fotos nuevas añadidas (+1 Keepers): {total_added}")
    logger.info(f"Vectores de estilo generados: {clip_count}")
    logger.info("=" * 50)


if __name__ == "__main__":
    target_dirs = [
        r"C:\Users\Guill\OneDrive\Escritorio\Eventos",
        r"D:\Respaldo 2026\Desktop\Eventos"
    ]
    run_recursive_ingest(target_dirs, ignore_patterns=["ruth"])
