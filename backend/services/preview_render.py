"""
preview_render.py — Fase U: ver la pre-edición ANTES de escribirla.

Hoy "Aplicar edición" trabaja a ciegas: el sistema calcula exposición, WB y
recorte, los escribe al XMP, y el fotógrafo recién los ve al abrir Lightroom.
Esto renderiza esa propuesta sobre el thumb para que la evalúe antes.

Es una APROXIMACIÓN de lo que hará Camera Raw (no un motor de revelado): sirve
para decidir "sí/no", no para juzgar el color final. La UI debe decirlo.
"""
import io
import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def _aplicar_exposicion(img: np.ndarray, ev: float) -> np.ndarray:
    """Exposición en stops: cada +1 EV duplica la luz (multiplicar por 2^EV)."""
    if not ev:
        return img
    return np.clip(img.astype(np.float32) * (2.0 ** ev), 0, 255).astype(np.uint8)


def _aplicar_wb(img: np.ndarray, temp: float, tint: float) -> np.ndarray:
    """
    WB incremental de Lightroom (-100..100) aproximado como ganancias por canal:
    temp+ calienta (más rojo, menos azul); tint+ va hacia magenta (menos verde).
    """
    if not temp and not tint:
        return img
    f = img.astype(np.float32)
    f[:, :, 0] *= 1.0 + (temp / 100.0) * 0.30          # R
    f[:, :, 2] *= 1.0 - (temp / 100.0) * 0.30          # B
    f[:, :, 1] *= 1.0 - (tint / 100.0) * 0.20          # G
    return np.clip(f, 0, 255).astype(np.uint8)


def _aplicar_recorte(img: np.ndarray, crop: dict) -> np.ndarray:
    """Recorte con rectángulo normalizado (0..1) + enderezado."""
    h, w = img.shape[:2]
    ang = float(crop.get("angle", 0.0) or 0.0)
    if ang:
        M = cv2.getRotationMatrix2D((w / 2, h / 2), -ang, 1.0)
        img = cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REPLICATE)

    x1 = int(max(0.0, float(crop.get("left", 0.0))) * w)
    y1 = int(max(0.0, float(crop.get("top", 0.0))) * h)
    x2 = int(min(1.0, float(crop.get("right", 1.0))) * w)
    y2 = int(min(1.0, float(crop.get("bottom", 1.0))) * h)
    if x2 - x1 < 10 or y2 - y1 < 10:
        return img
    return img[y1:y2, x1:x2]


def render_preview(image_path: str, develop: dict | None = None,
                   crop: dict | None = None, max_lado: int = 1400) -> bytes | None:
    """
    JPEG con la pre-edición propuesta aplicada sobre la foto. None si no se
    puede cargar. Sin `develop` ni `crop`, devuelve la foto tal cual (permite
    comparar "antes/después" con el mismo pipeline).
    """
    from PIL import Image
    from services.calibration import _load_scaled

    arr = _load_scaled(image_path)
    if arr is None:
        return None

    if develop:
        arr = _aplicar_exposicion(arr, float(develop.get("Exposure2012", 0.0) or 0.0))
        arr = _aplicar_wb(arr,
                          float(develop.get("IncrementalTemperature", 0.0) or 0.0),
                          float(develop.get("IncrementalTint", 0.0) or 0.0))
    if crop:
        arr = _aplicar_recorte(arr, crop)

    h, w = arr.shape[:2]
    escala = max_lado / max(h, w)
    if escala < 1.0:
        arr = cv2.resize(arr, (round(w * escala), round(h * escala)))

    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG", quality=88)
    return buf.getvalue()
