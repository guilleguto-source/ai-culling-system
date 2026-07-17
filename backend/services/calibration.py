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


MARK_COLOR = (255, 176, 46)   # ámbar del acento de la UI (RGB)
_MODELS_DIR = Path(__file__).parent.parent / "models"
_FACE_EMB_CACHE = _MODELS_DIR / "face_emb_cache"


def _load_scaled(photo_path: str) -> np.ndarray | None:
    """
    Carga la foto y la reescala a lado largo 1600 — el mismo espacio en que se
    calcularon los bboxes de análisis, para que las coordenadas coincidan.
    """
    from services.ingester import _load_jpg, _extract_raw_preview, RAW_EXTENSIONS
    p = Path(photo_path)
    arr = _extract_raw_preview(p) if p.suffix.lower() in RAW_EXTENSIONS else _load_jpg(p)
    if arr is None:
        return None
    h0, w0 = arr.shape[:2]
    escala = 1600 / max(h0, w0)
    if escala < 1.0:
        arr = cv2.resize(arr, (round(w0 * escala), round(h0 * escala)))
    return arr


def crop_face(photo_path: str, bbox: list, out_size: int = CROP_OUT,
              mark: bool = False) -> bytes | None:
    """
    Recorte de la cara (con contexto) como JPEG, para mostrar en la UI.

    `mark` dibuja el recuadro de la cara que se está calibrando: con el margen
    de contexto, en una grupal entran varias caras y sin marca no se sabe cuál
    se pregunta. Nunca se activa para el embedding — pintar sobre los píxeles
    que luego se vectorizan enseñaría el recuadro, no la cara.
    """
    from PIL import Image
    import io

    arr = _load_scaled(photo_path)
    if arr is None:
        return None

    h, w = arr.shape[:2]
    x, y, fw, fh = bbox
    m = int(max(fw, fh) * CROP_MARGIN)
    x1, y1 = max(0, x - m), max(0, y - m)
    x2, y2 = min(w, x + fw + m), min(h, y + fh + m)
    crop = arr[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    crop = cv2.resize(crop, (out_size, out_size), interpolation=cv2.INTER_CUBIC)

    if mark:
        # El recorte se estiró a un cuadrado: cada eje lleva su propia escala.
        sx, sy = out_size / (x2 - x1), out_size / (y2 - y1)
        cv2.rectangle(
            crop,
            (round((x - x1) * sx), round((y - y1) * sy)),
            (round((x + fw - x1) * sx), round((y + fh - y1) * sy)),
            MARK_COLOR, max(2, out_size // 170),
        )

    buf = io.BytesIO()
    Image.fromarray(crop).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def face_embedding(photo_path: str, bbox: list) -> np.ndarray | None:
    """
    Embedding CLIP del recorte de cara, con caché en disco por (archivo, mtime,
    bbox). Lo usan tanto la calibración (al guardar la etiqueta) como la
    selección (G3 en cada foto): sin caché, un evento re-leería y re-embebería
    cada cara de disco. La clave incluye el mtime: si el archivo cambia, se
    recalcula.
    """
    import hashlib
    import io

    from PIL import Image

    from services import embedding_service
    if not embedding_service.is_available():
        return None

    try:
        mtime = Path(photo_path).stat().st_mtime
    except OSError:
        mtime = 0.0
    bkey = ",".join(str(int(v)) for v in bbox)
    key = hashlib.sha1(f"{photo_path}|{mtime}|{bkey}".encode("utf-8")).hexdigest()
    cf = _FACE_EMB_CACHE / f"{key}.npy"
    if cf.exists():
        try:
            v = np.load(cf)
            if v.shape == (embedding_service.EMBEDDING_DIM,):
                return v
        except Exception:
            pass   # caché corrupto: recalcular

    jpeg = crop_face(photo_path, bbox, out_size=224)
    if jpeg is None:
        return None
    arr = np.array(Image.open(io.BytesIO(jpeg)).convert("RGB"))
    v = embedding_service.embed(arr)
    if v is not None:
        try:
            _FACE_EMB_CACHE.mkdir(parents=True, exist_ok=True)
            np.save(cf, v)
        except Exception as e:
            logger.warning(f"No se pudo guardar caché de embedding de cara: {e}")
    return v


def face_geometry(photo_path: str, bbox: list) -> "face_mesh.FaceAttributes | None":
    """
    Geometría por-cara (EAR, blink, sonrisa, mirada, yaw) recomputada desde
    disco. Para rellenar (backfill) las features de etiquetas guardadas antes
    del clasificador híbrido, que solo tenían el embedding.
    """
    if not face_mesh.is_available():
        return None
    arr = _load_scaled(photo_path)
    if arr is None:
        return None
    return face_mesh.analyze_face(arr, bbox)


def backfill_features(store: CalibrationStore | None = None) -> int:
    """
    Rellena las features geométricas de las etiquetas viejas (guardadas cuando
    solo se persistía el embedding). Recomputa la geometría una sola vez por
    cara y la escribe en todas sus filas de atributo. Las caras que ya no estén
    en disco, o sin MediaPipe, se dejan sin features: quedan fuera del
    entrenamiento híbrido pero no rompen nada.

    Idempotente y barato tras la primera pasada (la consulta ya no devuelve
    nada), así que puede llamarse desde los endpoints sin coste.
    """
    store = store or CalibrationStore()
    faltantes = store.faces_missing_features(face_mesh.FEATURE_DIM)
    rellenadas = 0
    for photo_path, face_index, bbox in faltantes:
        if not bbox:
            continue
        try:
            a = face_geometry(photo_path, bbox)
        except Exception:
            a = None
        if a is None or not a.valid:
            continue
        store.set_features(photo_path, face_index, face_mesh.feature_vector(a))
        rellenadas += 1
    if rellenadas:
        logger.info(f"Backfill de features geométricas: {rellenadas} caras.")
    return rellenadas
