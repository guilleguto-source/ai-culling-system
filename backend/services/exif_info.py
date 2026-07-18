"""
exif_info.py — Fase U: datos de toma (cámara, lente, ISO, apertura, velocidad).

El ingester solo lee la FECHA de captura, que es lo que el pipeline necesita.
Esto lee el resto para mostrarlo en la UI: al revisar una foto dudosa, saber que
salió a ISO 6400 y 1/30 explica el ruido y el movimiento sin adivinar.

Solo lectura y tolerante: si falta un campo, no aparece.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Tag EXIF → clave legible que consume la UI.
_CAMPOS = {
    "Image Model": "camara",
    "EXIF LensModel": "lente",
    "EXIF FNumber": "apertura",
    "EXIF ISOSpeedRatings": "iso",
    "EXIF ExposureTime": "velocidad",
    "EXIF FocalLength": "focal",
}


def _fraccion_a_float(valor) -> float | None:
    """Los tags EXIF vienen como Ratio (28/10). Devuelve su valor decimal."""
    try:
        r = valor.values[0]
        return float(r.num) / float(r.den) if hasattr(r, "den") and r.den else float(r)
    except Exception:
        return None


def read_exif(image_path: str) -> dict:
    """Datos de toma legibles. {} si el archivo no tiene EXIF o no se puede leer."""
    import exifread

    out: dict = {}
    try:
        with open(image_path, "rb") as f:
            tags = exifread.process_file(f, details=False)
    except (OSError, Exception) as e:
        logger.debug(f"Sin EXIF en {Path(image_path).name}: {e}")
        return out

    for tag, clave in _CAMPOS.items():
        if tag not in tags:
            continue
        valor = tags[tag]
        if clave == "apertura":
            f_num = _fraccion_a_float(valor)
            if f_num:
                out["apertura"] = f"f/{f_num:g}"
        elif clave == "velocidad":
            seg = _fraccion_a_float(valor)
            if seg:
                out["velocidad"] = f"1/{round(1 / seg)}s" if seg < 1 else f"{seg:g}s"
        elif clave == "focal":
            mm = _fraccion_a_float(valor)
            if mm:
                out["focal"] = f"{mm:g}mm"
        else:
            texto = str(valor).strip()
            if texto:
                out[clave] = texto
    return out
