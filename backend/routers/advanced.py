"""
routers/advanced.py — Endpoints para módulos de revelado avanzado post-culling (Fase 3).
"""
import logging
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.job_manager import job_manager
from services.neural_lut import compute_lut_adjustments, get_lut_status, list_available_luts
from services.portrait_relighting import build_relighting_xmp_elements, calculate_face_relighting
from services.settings_manager import load_settings
from services.skin_retouch import build_skin_retouch_xmp_elements, calculate_skin_retouch
from services.tonal_rescue import suggest_tonal_adjustments, TonalReport
from services.xmp_exporter import write_xmp

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/advanced", tags=["Advanced"])


# --- Schemas ---

class ApplyLutRequest(BaseModel):
    lut_id: Optional[str] = None
    strength: float = 1.0
    image_paths: Optional[List[str]] = None  # None = todas las seleccionadas


class RelightRequest(BaseModel):
    intensity: float = 0.5
    image_paths: Optional[List[str]] = None


class SkinRetouchRequest(BaseModel):
    smoothness: float = 0.5
    image_paths: Optional[List[str]] = None


class TonalRescueRequest(BaseModel):
    highlights_threshold: float = 0.05
    shadows_threshold: float = 0.10
    image_paths: Optional[List[str]] = None


# --- Endpoints ---

@router.get("/lut_status")
def get_status():
    """Retorna el estado de recetas aprendidas y configuración de LUT."""
    settings = load_settings()
    lut_cfg = settings.get("selection_preferences", {}).get("pre_edit", {}).get("neural_lut", {})
    status = get_lut_status()
    status["current_config"] = lut_cfg
    return status


@router.get("/luts")
def get_luts():
    """Lista los perfiles LUT curados disponibles."""
    return {"luts": list_available_luts()}


@router.post("/apply_lut")
def apply_lut(req: ApplyLutRequest):
    """Aplica o recalcula el Neural LUT / Color Grading sobre las fotos seleccionadas."""
    status, results, _ = job_manager.get_results()
    if not results:
        raise HTTPException(status_code=400, detail="No hay resultados de culling activos")

    settings = load_settings()
    ratings_map = settings.get("ratings_mapping", {})
    target_paths = set(req.image_paths) if req.image_paths else None

    applied_count = 0
    for r in results:
        if r.get("error"):
            continue
        path = r.get("path", "")
        if target_paths and path not in target_paths:
            continue
        if not target_paths and r.get("label") not in ("selected", "highlighted"):
            continue

        adj = compute_lut_adjustments(
            scene=r.get("scene_type"),
            strength=req.strength,
            fallback_lut=req.lut_id or "warm_golden",
            custom_lut=req.lut_id,
        )

        r["lut_adjustments"] = adj
        develop = r.get("develop") or {}
        for k, v in adj.items():
            develop[k] = v
        r["develop"] = develop

        label = r.get("label", "selected")
        mapping = ratings_map.get(label, {})
        write_xmp(
            image_path=path,
            label=label,
            stars=mapping.get("stars", 2),
            color=mapping.get("color", ""),
            overwrite=True,
            crop=r.get("crop"),
            develop=develop,
            flag=mapping.get("flag"),
            lut_adjustments=adj,
            tonal_rescue=r.get("tonal_rescue"),
        )
        applied_count += 1

    return {"status": "success", "applied_count": applied_count}


@router.post("/relight_faces")
def relight_faces(req: RelightRequest):
    """Calcula y escribe la re-iluminación facial local para las fotos indicadas."""
    status, results, _ = job_manager.get_results()
    if not results:
        raise HTTPException(status_code=400, detail="No hay resultados de culling activos")

    settings = load_settings()
    ratings_map = settings.get("ratings_mapping", {})
    target_paths = set(req.image_paths) if req.image_paths else None

    applied_count = 0
    for r in results:
        if r.get("error"):
            continue
        path = r.get("path", "")
        if target_paths and path not in target_paths:
            continue
        if not target_paths and r.get("label") not in ("selected", "highlighted"):
            continue

        bboxes = r.get("face_bboxes", [])
        if not bboxes:
            continue

        proposals = calculate_face_relighting(bboxes, intensity=req.intensity)
        if not proposals:
            continue

        paint_elements = build_relighting_xmp_elements(proposals)
        r["paint_corrections"] = paint_elements

        label = r.get("label", "selected")
        mapping = ratings_map.get(label, {})
        write_xmp(
            image_path=path,
            label=label,
            stars=mapping.get("stars", 2),
            color=mapping.get("color", ""),
            overwrite=True,
            crop=r.get("crop"),
            develop=r.get("develop"),
            flag=mapping.get("flag"),
            lut_adjustments=r.get("lut_adjustments"),
            tonal_rescue=r.get("tonal_rescue"),
            paint_corrections=paint_elements,
        )
        applied_count += 1

    return {"status": "success", "applied_count": applied_count}


@router.post("/skin_retouch")
def skin_retouch(req: SkinRetouchRequest):
    """Calcula y escribe el retoque de piel suave no destructivo."""
    status, results, _ = job_manager.get_results()
    if not results:
        raise HTTPException(status_code=400, detail="No hay resultados de culling activos")

    settings = load_settings()
    ratings_map = settings.get("ratings_mapping", {})
    target_paths = set(req.image_paths) if req.image_paths else None

    applied_count = 0
    for r in results:
        if r.get("error"):
            continue
        path = r.get("path", "")
        if target_paths and path not in target_paths:
            continue
        if not target_paths and r.get("label") not in ("selected", "highlighted"):
            continue

        has_faces = bool(r.get("face_bboxes"))
        proposal = calculate_skin_retouch(has_skin=has_faces, smoothness=req.smoothness)
        if not proposal.skin_detected:
            continue

        paint_elements = build_skin_retouch_xmp_elements(proposal)
        r["skin_retouch_elements"] = paint_elements

        label = r.get("label", "selected")
        mapping = ratings_map.get(label, {})
        write_xmp(
            image_path=path,
            label=label,
            stars=mapping.get("stars", 2),
            color=mapping.get("color", ""),
            overwrite=True,
            crop=r.get("crop"),
            develop=r.get("develop"),
            flag=mapping.get("flag"),
            lut_adjustments=r.get("lut_adjustments"),
            tonal_rescue=r.get("tonal_rescue"),
            paint_corrections=paint_elements,
        )
        applied_count += 1

    return {"status": "success", "applied_count": applied_count}
