"""
xmp_reader.py — Lectura de ratings/etiquetas XMP escritos por Lightroom (o por
nosotros). Contraparte de xmp_exporter:
  - RAW  -> sidecar .xmp junto a la imagen.
  - JPEG -> XMP embebido en el segmento APP1.

Se usa para el sync desde Lightroom: detectar qué fotos re-calificó el usuario
después del culling y convertir esas correcciones en ejemplos de entrenamiento.
"""
import logging
from pathlib import Path

from lxml import etree

from services.xmp_exporter import NS, RAW_EXTENSIONS, _extract_jpeg_xmp, _get_xmp_path
from services.lr_catalog import DEVELOP_FIELDS, CROP_FIELDS

logger = logging.getLogger(__name__)


def _crs_fields(desc, fields: tuple[str, ...]) -> dict:
    """Lee campos crs (revelado/recorte) de un rdf:Description como números."""
    out = {}
    for f in fields:
        v = desc.get(f"{{{NS['crs']}}}{f}")
        if v is None:
            continue
        try:
            out[f] = float(v)
        except ValueError:
            pass
    return out


def _parse_packet(xmp_bytes: bytes, full: bool = False) -> dict | None:
    """
    Extrae {stars, color} de un paquete XMP (None si no parsea). Con full=True
    agrega {develop, crop} (ajustes crs), para el bootstrap del historial.
    """
    try:
        # El paquete puede venir con envoltura <?xpacket ...?>; lxml la tolera
        # si recortamos a partir del primer '<' de xmpmeta/RDF.
        start = xmp_bytes.find(b"<x:xmpmeta")
        if start == -1:
            start = xmp_bytes.find(b"<rdf:RDF")
        if start == -1:
            return None
        end = xmp_bytes.rfind(b"</x:xmpmeta>")
        payload = xmp_bytes[start:end + len(b"</x:xmpmeta>")] if end != -1 else xmp_bytes[start:]
        root = etree.fromstring(payload)
    except Exception:
        return None

    stars = None
    color = ""
    develop: dict = {}
    crop: dict = {}
    for el in root.iter(f"{{{NS['xmp']}}}Rating"):
        if el.text and el.text.strip().lstrip("-").isdigit():
            stars = int(el.text.strip())
            break
    # Lightroom también escribe Rating/Label y los ajustes crs como ATRIBUTOS
    # de rdf:Description.
    for desc in root.iter(f"{{{NS['rdf']}}}Description"):
        if stars is None:
            attr = desc.get(f"{{{NS['xmp']}}}Rating")
            if attr and attr.strip().lstrip("-").isdigit():
                stars = int(attr.strip())
        if not color:
            color = desc.get(f"{{{NS['xmp']}}}Label", "") or ""
        if full:
            if not develop:
                develop = _crs_fields(desc, DEVELOP_FIELDS)
            if not crop:
                crop = _crs_fields(desc, CROP_FIELDS)
    for el in root.iter(f"{{{NS['xmp']}}}Label"):
        if el.text:
            color = el.text.strip()
            break

    if stars is None and not color and not develop and not crop:
        return None
    out = {"stars": stars if stars is not None else 0, "color": color}
    if full:
        out["develop"] = develop
        out["crop"] = crop
    return out


def read_xmp(image_path: str, full: bool = False) -> dict | None:
    """
    Lee {stars, color} de una imagen. RAW -> sidecar; JPEG -> embebido.
    None si no hay XMP o no contiene rating/etiqueta. Con full=True agrega
    {develop, crop} para el bootstrap del historial.
    """
    p = Path(image_path)
    try:
        if p.suffix.lower() in RAW_EXTENSIONS:
            xmp_path = _get_xmp_path(image_path)
            if not xmp_path.exists():
                return None
            return _parse_packet(xmp_path.read_bytes(), full)
        data = p.read_bytes()
        packet = _extract_jpeg_xmp(data)
        return _parse_packet(packet, full) if packet is not None else None
    except Exception as e:
        logger.warning(f"No se pudo leer XMP de {p.name}: {e}")
        return None
