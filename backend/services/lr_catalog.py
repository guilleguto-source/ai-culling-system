"""
lr_catalog.py — Lector SOLO-LECTURA del catálogo de Lightroom (.lrcat) para el
bootstrap del historial (Fase H). NUNCA escribe en el catálogo.

Fuente autoritativa: incluye las decisiones (rating/banderín) y el revelado de
fotos aunque su XMP nunca se haya volcado a disco. El .lrcat es SQLite; se abre
con mode=ro&immutable=1 para no tocar el WAL/lock si Lightroom está abierto.
"""
import logging
import re
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# Campos de revelado (nombres crs de Lightroom) que sirven para aprender estilo.
DEVELOP_FIELDS = (
    "Exposure2012", "Temperature", "Tint", "Contrast2012", "Highlights2012",
    "Shadows2012", "Whites2012", "Blacks2012", "Clarity2012", "Vibrance",
    "Saturation", "Dehaze",
)
# Campos de recorte (rectángulo normalizado 0..1 + ángulo de enderezado).
CROP_FIELDS = ("CropTop", "CropLeft", "CropBottom", "CropRight", "CropAngle")

# El revelado se guarda como tabla Lua serializada: `Clave = valor,`.
_KV = re.compile(r"(\w+)\s*=\s*(-?\d+(?:\.\d+)?)")

_QUERY = """
SELECT rf.absolutePath, fo.pathFromRoot, fi.baseName, fi.extension,
       i.rating, i.pick, i.captureTime, ds.text
FROM Adobe_images i
JOIN AgLibraryFile fi        ON fi.id_local = i.rootFile
JOIN AgLibraryFolder fo      ON fo.id_local = fi.folder
JOIN AgLibraryRootFolder rf  ON rf.id_local = fo.rootFolder
LEFT JOIN Adobe_imageDevelopSettings ds ON ds.image = i.id_local
WHERE i.captureTime >= ?
"""


def _parse_blob(text: str | None, fields: tuple[str, ...]) -> dict:
    """Extrae los campos numéricos pedidos del blob de revelado."""
    if not text:
        return {}
    found = dict(_KV.findall(text))
    out = {}
    for k in fields:
        if k in found:
            try:
                out[k] = float(found[k])
            except ValueError:
                pass
    return out


def read_catalog(lrcat_path: str, since: str = "2025-02-01"):
    """
    Itera las imágenes del catálogo desde `since` (fecha de captura, ISO).
    Rinde dicts {path, rating, pick, capture_time, develop, crop}. Mismo formato
    que el lector de XMP, para que el bootstrap sea agnóstico de la fuente.
    """
    conn = sqlite3.connect(f"file:{lrcat_path}?mode=ro&immutable=1", uri=True)
    try:
        for absPath, pfr, base, ext, rating, pick, capture, text in conn.execute(_QUERY, (since,)):
            path = f"{absPath or ''}{pfr or ''}{base}.{ext}"
            yield {
                "path": path,
                "rating": int(rating or 0),
                "pick": int(pick or 0),
                "capture_time": capture or "",
                "develop": _parse_blob(text, DEVELOP_FIELDS),
                "crop": _parse_blob(text, CROP_FIELDS),
            }
    finally:
        conn.close()
