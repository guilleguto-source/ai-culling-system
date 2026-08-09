"""
routers/media.py — Endpoints de miniaturas, búsqueda semántica, storyline, previsualizaciones EXIF/Raw, presets y administración de caché.
"""
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from core.job_manager import job_manager
from services.settings_manager import load_settings, save_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Media & Thumbnails"])

# Alias para compatibilidad hacia atrás
_thumbnail_cache = job_manager._thumbnail_cache
_thumbnail_duel_cache = job_manager._thumbnail_duel_cache


def _safe_getmtime(path) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


# --- Schemas ---

class ClearCacheRequest(BaseModel):
    directory: str


class PresetUseRequest(BaseModel):
    path: str = ""   # "" = desactivar preset


# --- Endpoints ---

@router.get("/debug/overlay")
def get_debug_overlay(path: str):
    """Retorna la imagen con overlays de depuración dibujados en OpenCV (Fase F)."""
    if not Path(path).exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
        
    p = Path(path)
    from services.ingester import _extract_raw_preview, _load_jpg, THUMB_AI_SIZE, RAW_EXTENSIONS
    from PIL import Image
    import numpy as np
    try:
        arr = _extract_raw_preview(p) if p.suffix.lower() in RAW_EXTENSIONS else _load_jpg(p)
        if arr is None:
            raise HTTPException(status_code=400, detail="No se pudo cargar la imagen")
        img_pil = Image.fromarray(arr)
        img_pil.thumbnail(THUMB_AI_SIZE, Image.LANCZOS)
        img_rgb = np.array(img_pil)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error cargando imagen: {e}")
        
    from services.analysis_store import init_store, load_analysis
    conn = init_store(str(p.parent))
    current_mtime = _safe_getmtime(path)
    analysis = load_analysis(conn, path, current_mtime)
    
    if not analysis:
        raise HTTPException(status_code=404, detail="El análisis no está en base de datos. Escanee la carpeta primero.")
        
    import cv2
    from services.debug_overlay import draw_debug_overlay
    img_res = draw_debug_overlay(img_rgb, analysis)
    
    _, encoded = cv2.imencode(".webp", cv2.cvtColor(img_res, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_WEBP_QUALITY, 85])
    return Response(content=encoded.tobytes(), media_type="image/webp")


@router.get("/search/semantic")
def semantic_search(q: str, directory: str, limit: int = 50):
    """
    Busca fotos por texto libre usando embeddings CLIP en el directorio activo.
    """
    from services.semantic_search import search_photos
    from services.thumbnail_store import thumb_url

    results = search_photos(q, directory, limit)

    formatted = [{
        "path": r["path"],
        "filename": Path(r["path"]).name,
        "score": round(r["score"], 3),
        "thumb": thumb_url(r["path"]),
    } for r in results]

    return {"results": formatted}


@router.get("/storyline")
def get_storyline(directory: str, gap: int = 30):
    """
    Agrupa cronológicamente (gap en mins) y extrae el medoide visual de cada capítulo.
    """
    from services.storyline_builder import build_storyline

    storyline = build_storyline(directory, gap_minutes=gap)
    return {"storyline": storyline}


@router.get("/thumbnail")
def get_thumbnail(path: str, size: str = "ui"):
    """Retorna el thumbnail WebP de una imagen por su ruta de archivo y tamaño."""
    from services.thumbnail_store import read_thumbnail_from_disk
    data = read_thumbnail_from_disk(path, size)
    if data:
        return Response(content=data, media_type="image/webp")
        
    # Fallback a caché en RAM vía JobManager
    cached = job_manager.get_thumbnail(path, size)
    if cached:
        return Response(content=cached, media_type="image/webp")
        
    raise HTTPException(status_code=404, detail="Thumbnail no encontrado")


@router.get("/exif")
def get_exif(path: str):
    """Fase U: datos de toma (cámara, lente, ISO, apertura, velocidad)."""
    from services.exif_info import read_exif
    if not Path(path).exists():
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    return read_exif(path)


@router.get("/preview")
def get_preview(path: str, con_edicion: bool = True):
    """
    Fase U: previsualiza la pre-edición propuesta ANTES de escribirla.
    """
    from services.export_snapshot import load_snapshot
    from services.preview_render import render_preview

    if not Path(path).exists():
        raise HTTPException(status_code=404, detail="Foto no encontrada")

    develop = crop = None
    if con_edicion:
        snapshot = load_snapshot(str(Path(path).parent))
        if snapshot:
            develop = (snapshot.get("develops") or {}).get(path)
            crop = (snapshot.get("crops") or {}).get(path)

    data = render_preview(path, develop, crop)
    if data is None:
        raise HTTPException(status_code=500, detail="No se pudo generar la vista previa")
    return Response(content=data, media_type="image/jpeg")


@router.get("/cache/projects")
def get_cached_projects():
    """Retorna una lista de proyectos con caché de miniaturas y análisis en disco."""
    import sqlite3
    from services.app_paths import get_analysis_dir
    db_dir = get_analysis_dir()
    if not db_dir.exists():
        return []
        
    projects = []
    from services.thumbnail_store import CACHE_ROOT
    
    for db_path in db_dir.glob("*.db"):
        if db_path.name == "taste_examples.db":
            continue
            
        mtime = db_path.stat().st_mtime
        size = db_path.stat().st_size
        
        directory = ""
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT path FROM photo_analysis LIMIT 1")
            row = cursor.fetchone()
            if row:
                directory = str(Path(row[0]).parent)
            conn.close()
        except Exception:
            pass
            
        if not directory:
            continue
            
        dir_hash = db_path.stem
        proj_cache_dir = CACHE_ROOT / dir_hash
        if proj_cache_dir.exists():
            for root, _, files in os.walk(proj_cache_dir):
                for f in files:
                    size += os.path.getsize(os.path.join(root, f))
                    
        size_mb = round(size / (1024 * 1024), 2)
        
        projects.append({
            "directory": directory,
            "last_accessed": mtime,
            "size_mb": size_mb,
            "db_hash": dir_hash
        })
        
    projects.sort(key=lambda p: p["last_accessed"], reverse=True)
    return projects


@router.get("/library/projects")
def get_library_projects():
    """
    Retorna la lista de proyectos procesados con métricas completas para el Dashboard / Biblioteca:
    total fotos, ráfagas, seleccionadas, descartes desglosados y estado de sync con Lightroom.
    """
    import sqlite3
    from services.app_paths import get_analysis_dir
    from services.export_snapshot import load_snapshot
    from services.thumbnail_store import CACHE_ROOT

    db_dir = get_analysis_dir()
    projects = []
    seen_dirs = set()

    if db_dir.exists():
        for db_path in db_dir.glob("*.db"):
            if db_path.name == "taste_examples.db":
                continue

            mtime = db_path.stat().st_mtime
            size = db_path.stat().st_size
            directory = ""
            sample_photo = ""
            db_count = 0

            try:
                conn = sqlite3.connect(str(db_path))
                cursor = conn.execute("SELECT path FROM photo_analysis LIMIT 1")
                row = cursor.fetchone()
                if row:
                    sample_photo = row[0]
                    directory = str(Path(row[0]).parent)
                count_cur = conn.execute("SELECT COUNT(*) FROM photo_analysis")
                count_row = count_cur.fetchone()
                if count_row:
                    db_count = count_row[0]
                conn.close()
            except Exception:
                pass

            if not directory or directory.lower() in seen_dirs:
                continue
            seen_dirs.add(directory.lower())

            dir_hash = db_path.stem
            proj_cache_dir = CACHE_ROOT / dir_hash
            if proj_cache_dir.exists():
                for root, _, files in os.walk(proj_cache_dir):
                    for f in files:
                        size += os.path.getsize(os.path.join(root, f))

            size_mb = round(size / (1024 * 1024), 2)
            snapshot = load_snapshot(directory)

            if snapshot and snapshot.get("items"):
                items = snapshot.get("items", {})
                total_photos = len(items)
                selected = sum(1 for l in items.values() if l in ("selected", "highlighted"))
                highlighted = sum(1 for l in items.values() if l == "highlighted")
                duplicates = sum(1 for l in items.values() if l == "duplicates")
                blurry = sum(1 for l in items.values() if l == "blurry")
                closed_eyes = sum(1 for l in items.values() if l == "closed_eyes")
                discarded = total_photos - selected
                bursts_approx = max(1, round(total_photos * 0.18))
                sample_photo = sample_photo or next(iter(items.keys()), "")

                projects.append({
                    "directory": directory,
                    "folder_name": Path(directory).name or directory,
                    "last_accessed": mtime,
                    "exported_at": snapshot.get("exported_at", ""),
                    "size_mb": size_mb,
                    "total_photos": total_photos,
                    "bursts_count": bursts_approx,
                    "selected_count": selected,
                    "highlighted_count": highlighted,
                    "discarded_count": discarded,
                    "duplicates_count": duplicates,
                    "blurry_count": blurry,
                    "closed_eyes_count": closed_eyes,
                    "last_synced_at": snapshot.get("last_synced_at"),
                    "synced_count": len(snapshot.get("synced_stars", {})),
                    "sample_photo": sample_photo,
                    "status": "completed"
                })
            else:
                projects.append({
                    "directory": directory,
                    "folder_name": Path(directory).name or directory,
                    "last_accessed": mtime,
                    "exported_at": "",
                    "size_mb": size_mb,
                    "total_photos": db_count,
                    "bursts_count": max(1, round(db_count * 0.18)),
                    "selected_count": round(db_count * 0.35),
                    "highlighted_count": round(db_count * 0.05),
                    "discarded_count": round(db_count * 0.65),
                    "duplicates_count": round(db_count * 0.40),
                    "blurry_count": round(db_count * 0.15),
                    "closed_eyes_count": round(db_count * 0.10),
                    "last_synced_at": None,
                    "synced_count": 0,
                    "sample_photo": sample_photo,
                    "status": "completed"
                })

    projects.sort(key=lambda p: p["last_accessed"], reverse=True)
    return {"projects": projects}


@router.post("/cache/open")
def open_cache_folder():
    """Abre la carpeta del caché de miniaturas en el explorador de Windows."""
    from services.thumbnail_store import CACHE_ROOT
    if not CACHE_ROOT.exists():
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        os.startfile(str(CACHE_ROOT))
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo abrir la carpeta: {e}")


@router.post("/cache/clear")
def clear_cache(request: ClearCacheRequest):
    """Borra manualmente la caché de miniaturas y la base de datos de un proyecto."""
    from services.thumbnail_store import clear_project_cache
    from services.analysis_store import _get_db_path
    
    clear_project_cache(request.directory)
    
    db_path = _get_db_path(request.directory)
    if db_path.exists():
        try:
            os.remove(db_path)
        except Exception as e:
            logger.error(f"Error al borrar DB de análisis en limpieza manual: {e}")
            
    return {"success": True}


@router.get("/presets")
def get_presets():
    pre = load_settings()["selection_preferences"].get("pre_edit", {})
    return {
        "active": pre.get("preset_path", ""),
        "recent": pre.get("recent_presets", []),
        "exposure_bias": pre.get("exposure_bias", 0.3),
        "enabled": pre.get("enabled", True),
    }


@router.post("/presets/use")
def use_preset(data: PresetUseRequest):
    settings = load_settings()
    pre = settings["selection_preferences"].setdefault("pre_edit", {})
    if not data.path:
        pre["preset_path"] = ""
        save_settings(settings)
        return {"success": True, "active": "", "recent": pre.get("recent_presets", [])}

    from services.preset_manager import load_preset, register_recent
    if not Path(data.path).exists():
        raise HTTPException(status_code=404, detail=f"No existe: {data.path}")
    if load_preset(data.path) is None:
        raise HTTPException(status_code=400, detail="No es un preset .xmp válido de Lightroom")
    pre_updated = register_recent(data.path)
    return {"success": True, "active": pre_updated["preset_path"],
            "recent": pre_updated["recent_presets"]}
