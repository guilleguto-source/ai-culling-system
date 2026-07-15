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

logger = logging.getLogger(__name__)


def _parse_packet(xmp_bytes: bytes) -> dict | None:
    """Extrae {stars, color} de un paquete XMP. None si no parsea."""
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
    for el in root.iter(f"{{{NS['xmp']}}}Rating"):
        if el.text and el.text.strip().lstrip("-").isdigit():
            stars = int(el.text.strip())
            break
    # Lightroom también escribe Rating/Label como ATRIBUTOS de rdf:Description
    for desc in root.iter(f"{{{NS['rdf']}}}Description"):
        if stars is None:
            attr = desc.get(f"{{{NS['xmp']}}}Rating")
            if attr and attr.strip().lstrip("-").isdigit():
                stars = int(attr.strip())
        if not color:
            color = desc.get(f"{{{NS['xmp']}}}Label", "") or ""
    for el in root.iter(f"{{{NS['xmp']}}}Label"):
        if el.text:
            color = el.text.strip()
            break

    if stars is None and not color:
        return None
    return {"stars": stars if stars is not None else 0, "color": color}


def read_xmp(image_path: str) -> dict | None:
    """
    Lee {stars, color} de una imagen. RAW -> sidecar; JPEG -> embebido.
    None si no hay XMP o no contiene rating/etiqueta.
    """
    p = Path(image_path)
    try:
        if p.suffix.lower() in RAW_EXTENSIONS:
            xmp_path = _get_xmp_path(image_path)
            if not xmp_path.exists():
                return None
            return _parse_packet(xmp_path.read_bytes())
        data = p.read_bytes()
        packet = _extract_jpeg_xmp(data)
        return _parse_packet(packet) if packet is not None else None
    except Exception as e:
        logger.warning(f"No se pudo leer XMP de {p.name}: {e}")
        return None
