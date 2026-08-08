"""
routers/calibration.py — Endpoints de calibración de atributos faciales (Fase G2).
"""
import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Calibration"])


def _safe_getmtime(path) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


# --- Schemas ---

class LabelRequest(BaseModel):
    photo_path: str
    face_index: int
    face_bbox: list = []
    labels: dict          # {"eyes": "abiertos", "gaze": "camara", ...}
    predictions: dict = {} # lo que propuso el detector (para medir acuerdo)


# --- Endpoints ---

@router.get("/calibration/candidates")
def calibration_candidates(directory: str, limit: int = 30):
    """Caras pendientes de calibrar, las más dudosas primero."""
    from services.calibration import candidates
    from services.calibration_store import ATTRIBUTES, CalibrationStore
    if not Path(directory).is_dir():
        raise HTTPException(status_code=400, detail=f"Directorio no válido: {directory}")
    cands = candidates(directory, limit=limit)
    store = CalibrationStore()
    return {
        "atributos": ATTRIBUTES,
        "etiquetadas": store.count(),
        "candidatas": [
            {"photo_path": c.photo_path, "face_index": c.face_index,
             "face_bbox": c.face_bbox, "uncertainty": c.uncertainty,
             "predictions": c.predictions}
            for c in cands
        ],
    }


@router.get("/calibration/face")
def calibration_face(path: str, x: int, y: int, w: int, h: int):
    """Recorte de una cara para mostrar en la vista de calibración."""
    from services.calibration import crop_face
    jpeg = crop_face(path, [x, y, w, h], mark=True)
    if jpeg is None:
        raise HTTPException(status_code=404, detail="No se pudo recortar la cara")
    return Response(content=jpeg, media_type="image/jpeg")


@router.post("/calibration/label")
def calibration_label(data: LabelRequest):
    """Guarda la verdad de campo del fotógrafo para una cara."""
    from services.calibration import face_embedding
    from services.calibration_store import CalibrationStore, ATTRIBUTES
    from services import face_mesh
    from services.analysis_store import init_store, load_analysis

    store = CalibrationStore()
    # Embedding y geometría se calculan una vez por cara y se reutilizan en
    # todos los atributos: juntos forman el vector híbrido que entrena G3.
    emb = face_embedding(data.photo_path, data.face_bbox) if data.face_bbox else None
    feats = None
    try:
        directory = str(Path(data.photo_path).parent)
        a = load_analysis(init_store(directory), data.photo_path,
                          _safe_getmtime(data.photo_path))
        if a and 0 <= data.face_index < len(a.face_attrs):
            feats = face_mesh.feature_vector(face_mesh.from_dict(a.face_attrs[data.face_index]))
    except Exception:
        feats = None

    guardadas = 0
    for attribute, value in data.labels.items():
        if attribute not in ATTRIBUTES or value not in ATTRIBUTES[attribute]:
            continue
        store.add_label(
            photo_path=data.photo_path, face_index=data.face_index,
            attribute=attribute, value=value,
            predicted=data.predictions.get(attribute, ""),
            face_bbox=data.face_bbox, embedding=emb, features=feats,
        )
        guardadas += 1

    from services.face_classifier import face_classifier
    face_classifier.invalidate()
    return {"success": True, "guardadas": guardadas, "total": store.count()}


@router.get("/calibration/stats")
def calibration_stats():
    """
    Precisión REAL sobre las fotos del usuario: la de la geometría (G1) medida
    contra sus etiquetas, y la del clasificador aprendido (G3) en validación
    cruzada.
    """
    from services.calibration_store import CalibrationStore, ATTRIBUTES
    from services.face_classifier import face_classifier, MIN_EXAMPLES
    from services.calibration import backfill_features

    store = CalibrationStore()
    if backfill_features(store):
        face_classifier.invalidate()

    out = {}
    for at in ATTRIBUTES:
        geo = store.agreement(at)
        aprendido = face_classifier.cross_val_accuracy(at)
        out[at] = {
            **geo,
            "geometria": geo["precision"],
            "aprendido": aprendido,
            "faltan": max(0, MIN_EXAMPLES - store.count(at)),
        }
    return {"total": store.count(), "por_atributo": out}
