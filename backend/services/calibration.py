"""
calibration.py — Selección de caras a calibrar y recorte para la UI (Fase G2).

Muestreo por incertidumbre: se preguntan primero las caras donde el detector
está en el filo del umbral o sus dos señales (geometría vs blendshape) se
contradicen. Así ~100 etiquetas rinden como ~500 al azar.
"""
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from services import face_mesh
from services.analysis_store import init_store, load_analysis
from services.calibration_store import ATTRIBUTES, CalibrationStore

logger = logging.getLogger(__name__)

CROP_MARGIN = 0.8       # margen alrededor de la cara para dar contexto al ojo humano
CROP_OUT = 512          # tamaño del recorte que se manda a la UI
MIN_FACE_PX = 40        # caras más chicas no se calibran: ni el ojo humano las juzga


@dataclass
class FaceCandidate:
    photo_path: str
    face_index: int
    face_bbox: list
    uncertainty: float
    predictions: dict     # {attribute: valor propuesto por G1}


def candidates(directory: str, limit: int = 50) -> list[FaceCandidate]:
    """
    Caras pendientes de calibrar en un directorio ya analizado, ordenadas por
    incertidumbre (las más dudosas primero). Excluye:
      - caras que MediaPipe no validó (basura de YuNet: decoración, muñecos)
      - caras diminutas (ni una persona podría juzgarlas)
      - caras ya etiquetadas
    """
    conn = init_store(directory)
    ya = CalibrationStore().labeled_faces()
    out: list[FaceCandidate] = []

    for p in sorted(Path(directory).glob("*")):
        if p.suffix.lower() not in (".jpg", ".jpeg"):
            continue
        try:
            a = load_analysis(conn, str(p), os.path.getmtime(p))
        except OSError:
            continue
        if a is None or not a.face_attrs:
            continue

        for i, d in enumerate(a.face_attrs):
            attrs = face_mesh.from_dict(d)
            if not attrs.valid or (str(p), i) in ya:
                continue
            if i >= len(a.face_bboxes):
                continue
            bbox = a.face_bboxes[i]
            if max(bbox[2], bbox[3]) < MIN_FACE_PX:
                continue
            u = max(face_mesh.uncertainty(attrs, at) for at in ATTRIBUTES)
            out.append(FaceCandidate(
                photo_path=str(p), face_index=i, face_bbox=bbox, uncertainty=round(u, 4),
                predictions={at: face_mesh.predict(attrs, at) for at in ATTRIBUTES},
            ))

    out.sort(key=lambda c: -c.uncertainty)
    return out[:limit]


def crop_face(photo_path: str, bbox: list, out_size: int = CROP_OUT) -> bytes | None:
    """Recorte de la cara (con contexto) como JPEG, para mostrar en la UI."""
    from services.ingester import _load_jpg, _extract_raw_preview, RAW_EXTENSIONS
    from PIL import Image
    import io

    p = Path(photo_path)
    arr = _extract_raw_preview(p) if p.suffix.lower() in RAW_EXTENSIONS else _load_jpg(p)
    if arr is None:
        return None

    # Los bboxes se calcularon sobre el thumb de análisis (lado largo 1600):
    # se reescala la foto igual para que las coordenadas coincidan.
    h0, w0 = arr.shape[:2]
    escala = 1600 / max(h0, w0)
    if escala < 1.0:
        arr = cv2.resize(arr, (round(w0 * escala), round(h0 * escala)))

    h, w = arr.shape[:2]
    x, y, fw, fh = bbox
    m = int(max(fw, fh) * CROP_MARGIN)
    x1, y1 = max(0, x - m), max(0, y - m)
    x2, y2 = min(w, x + fw + m), min(h, y + fh + m)
    crop = arr[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    crop = cv2.resize(crop, (out_size, out_size), interpolation=cv2.INTER_CUBIC)
    buf = io.BytesIO()
    Image.fromarray(crop).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def face_embedding(photo_path: str, bbox: list) -> np.ndarray | None:
    """Embedding CLIP del recorte de cara — se guarda con la etiqueta para G3."""
    from services import embedding_service
    if not embedding_service.is_available():
        return None
    jpeg = crop_face(photo_path, bbox, out_size=224)
    if jpeg is None:
        return None
    from PIL import Image
    import io
    arr = np.array(Image.open(io.BytesIO(jpeg)).convert("RGB"))
    return embedding_service.embed(arr)
