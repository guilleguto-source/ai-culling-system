"""
routers/bursts.py — Endpoints de herramientas de ráfaga, recortes faciales alineados, duelo V1 vs V2 y aprendizaje de gustos.
"""
import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from core.job_manager import job_manager
from services.settings_manager import load_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Bursts"])


def _safe_getmtime(path) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


# --- Schemas ---

class LearnPreferenceRequest(BaseModel):
    winner_path: str
    loser_path: str


# --- Endpoints ---

@router.post("/learn_preference")
def learn_preference(data: LearnPreferenceRequest):
    from services.ingester import _load_jpg, _extract_raw_preview, RAW_EXTENSIONS
    from services.taste_model import taste_model
    from services import embedding_service

    def get_embedding(path_str):
        emb = embedding_service.embed_path(path_str, img_rgb=None)
        if emb is not None:
            return emb
        p = Path(path_str)
        arr = _extract_raw_preview(p) if p.suffix.lower() in RAW_EXTENSIONS else _load_jpg(p)
        return embedding_service.embed_path(path_str, arr) if arr is not None else None

    learned = False
    if embedding_service.is_available():
        w_emb = get_embedding(data.winner_path)
        l_emb = get_embedding(data.loser_path)
        if w_emb is not None and l_emb is not None:
            event_dir = str(Path(data.winner_path).parent)
            taste_model.learn_preference(w_emb, l_emb, source="duel", event_dir=event_dir)
            learned = True
    if not learned:
        logger.warning("Duelo sin aprendizaje: embeddings no disponibles.")

    settings = load_settings()
    ratings_map = settings["ratings_mapping"]

    def _with_siblings(path_str: str) -> list[str]:
        p = Path(path_str)
        out = [str(p)]
        if p.parent.is_dir():
            for sib in p.parent.glob(p.stem + ".*"):
                if sib != p and sib.suffix.lower() != p.suffix.lower():
                    out.append(str(sib))
        return out

    from services.export_snapshot import load_snapshot
    from services.preset_manager import load_preset
    snap = load_snapshot(str(Path(data.winner_path).parent))
    edits_on = bool(snap and snap.get("edits_applied", True))
    crops = snap.get("crops", {}) if snap and edits_on else {}
    develops = snap.get("develops", {}) if snap and edits_on else {}
    preset_path = snap.get("preset_path", "") if snap and edits_on else ""
    preset_data = load_preset(preset_path) if preset_path and Path(preset_path).exists() else None

    rewrite = []
    for label in ("selected", "duplicates"):
        src = data.winner_path if label == "selected" else data.loser_path
        m = ratings_map.get(label, {})
        for path_str in _with_siblings(src):
            rewrite.append({
                "path": path_str,
                "label": label,
                "stars": m.get("stars", 0),
                "color": m.get("color", ""),
                "crop": crops.get(path_str),
                "develop": develops.get(path_str) or (
                    develops.get(data.loser_path) if label == "selected" else None
                ),
            })

    from services.xmp_exporter import export_results_to_xmp
    from services.export_snapshot import update_labels
    xmp_stats = export_results_to_xmp(rewrite, ratings_map, overwrite=True,
                                      preset=preset_data)
    update_labels(
        str(Path(data.winner_path).parent),
        {r["path"]: r["label"] for r in rewrite},
    )
    return {"success": True, "learned": learned, "xmp": xmp_stats}


@router.get("/bursts/{cluster_id}/face_crops")
def get_burst_face_crops(cluster_id: int, directory: str | None = None):
    """
    Retorna los recortes faciales de todas las fotos de una ráfaga agrupados por identidad/persona.
    Permite al fotógrafo ver en 1 segundo los rostros alineados (Narrative Select style).
    """
    from services.analysis_store import init_store, load_analysis

    photos = [r for r in job_manager.get("results", []) if r.get("cluster_id") == cluster_id]
    if not photos and not directory:
        return {"cluster_id": cluster_id, "people": []}

    dir_path = directory or (str(Path(photos[0]["path"]).parent) if photos else "")
    conn = init_store(dir_path) if dir_path else None

    cluster_faces = []
    for r in photos:
        p_path = r["path"]
        analysis = None
        if conn:
            analysis = load_analysis(conn, p_path, _safe_getmtime(p_path))

        if not analysis or not analysis.face_bboxes:
            continue

        for f_idx, bbox in enumerate(analysis.face_bboxes):
            attrs = analysis.face_attrs[f_idx] if f_idx < len(analysis.face_attrs) else {}
            if analysis.face_identities and f_idx < len(analysis.face_identities):
                ident = f"persona_{analysis.face_identities[f_idx]}"
            else:
                ident = f"persona_{f_idx}"

            cluster_faces.append({
                "person_id": ident,
                "photo_path": p_path,
                "face_index": f_idx,
                "face_bbox": bbox,
                "is_representative": bool(r.get("is_cluster_representative")),
                "score": round(float(r.get("score", 0.0)), 2),
                "is_eyes_open": attrs.get("eyes", "abiertos") == "abiertos" if isinstance(attrs, dict) else True,
                "is_smiling": attrs.get("expression", "") == "sonrisa" if isinstance(attrs, dict) else False,
                "is_looking_at_camera": attrs.get("gaze", "camara") == "camara" if isinstance(attrs, dict) else True,
                "blur_score": round(float(analysis.blur_score or 0.0), 1),
            })

    people_map: dict[str, list[dict]] = {}
    for cf in cluster_faces:
        pid = cf["person_id"]
        if pid not in people_map:
            people_map[pid] = []
        people_map[pid].append(cf)

    people_list = [
        {"person_id": pid, "crops": crops}
        for pid, crops in people_map.items()
    ]
    return {"cluster_id": cluster_id, "people": people_list}


@router.get("/bursts/face_crop_img")
def get_face_crop_img(path: str, x: int, y: int, w: int, h: int, size: int = 256):
    """Retorna el recorte JPEG centrado en el rostro para la grilla facial."""
    from services.calibration import crop_face
    jpeg = crop_face(path, [x, y, w, h], out_size=size, mark=False)
    if jpeg is None:
        raise HTTPException(status_code=404, detail="No se pudo recortar la cara")
    return Response(content=jpeg, media_type="image/jpeg")



