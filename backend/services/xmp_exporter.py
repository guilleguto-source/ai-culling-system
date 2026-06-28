"""
xmp_exporter.py — Escritura de metadatos XMP compatibles con Adobe Lightroom.

Doble ruta:
  - RAW  -> archivo sidecar .xmp junto a la imagen.
  - JPEG -> XMP embebido en el segmento APP1 del archivo (Python puro, sin exiftool).
            Lightroom NO lee sidecars para JPEG, por eso debe ir embebido.

Las etiquetas de color se toman tal cual de la configuración (settings.json),
para que coincidan con el "Conjunto de etiquetas de color" del Lightroom del usuario
(p. ej. "Verde"/"Rojo" en español).
"""
import logging
from pathlib import Path

from lxml import etree

logger = logging.getLogger(__name__)

# Namespaces XMP estándar de Adobe
NS = {
    "x":      "adobe:ns:meta/",
    "rdf":    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "xmp":    "http://ns.adobe.com/xap/1.0/",
}

# Mapeo de label interno a pick status XMP (extensión Lightroom)
PICK_STATUS_MAP = {
    "selected":    "1",   # Pick
    "highlighted": "1",   # Pick
    "blurry":      "-1",  # Reject
    "closed_eyes": "-1",  # Reject
    "duplicates":  "0",   # Unflagged
}

RAW_EXTENSIONS = {
    ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2",
    ".raf", ".orf", ".rw2", ".dng", ".pef", ".kdc", ".mrw",
}

# Firma del segmento APP1 que identifica un paquete XMP dentro de un JPEG
XMP_APP1_SIG = b"http://ns.adobe.com/xap/1.0/\x00"
_XPACKET_OPEN = b'<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
_XPACKET_CLOSE = b'\n<?xpacket end="w"?>'


def _is_raw(path: Path) -> bool:
    return path.suffix.lower() in RAW_EXTENSIONS


def _get_xmp_path(image_path: str) -> Path:
    """Ruta del sidecar .xmp para una imagen (solo RAW)."""
    p = Path(image_path)
    return p.parent / (p.stem + ".xmp")


def _build_xmp_packet(stars: int, color: str, label: str) -> bytes:
    """Construye un paquete XMP completo (con envoltura xpacket) listo para
    sidecar o para embeber en APP1. El color se escribe tal cual venga de settings."""
    xmpmeta = etree.Element(f"{{{NS['x']}}}xmpmeta", nsmap={"x": NS["x"]})
    xmpmeta.set(f"{{{NS['x']}}}xmptk", "AI Culling System 1.0")

    rdf = etree.SubElement(xmpmeta, f"{{{NS['rdf']}}}RDF", nsmap={"rdf": NS["rdf"]})
    desc = etree.SubElement(
        rdf, f"{{{NS['rdf']}}}Description", nsmap={"rdf": NS["rdf"], "xmp": NS["xmp"]})
    desc.set(f"{{{NS['rdf']}}}about", "")

    rating_el = etree.SubElement(desc, f"{{{NS['xmp']}}}Rating")
    rating_el.text = str(max(0, min(5, stars)))

    if color:                                   # etiqueta dinámica (tal cual settings)
        label_el = etree.SubElement(desc, f"{{{NS['xmp']}}}Label")
        label_el.text = color

    pick_el = etree.SubElement(desc, f"{{{NS['xmp']}}}PickStatus")
    pick_el.text = PICK_STATUS_MAP.get(label, "0")

    body = etree.tostring(xmpmeta, encoding="utf-8", xml_declaration=False)
    return _XPACKET_OPEN + body + _XPACKET_CLOSE


# --- JPEG: lectura/escritura del segmento APP1 (Python puro) ---

def _iter_jpeg_segments(data: bytes):
    """Genera (marker, seg_start, seg_end) de cada segmento con longitud del JPEG,
    deteniéndose en SOS/EOI. seg_end es exclusivo."""
    i = 2  # tras SOI (FF D8)
    n = len(data)
    while i + 1 < n:
        if data[i] != 0xFF:
            break
        marker = data[i + 1]
        if marker in (0xDA, 0xD9):           # SOS o EOI -> fin de cabecera
            break
        if 0xD0 <= marker <= 0xD7 or marker in (0x01, 0xD8):  # marcadores sin longitud
            i += 2
            continue
        seg_len = int.from_bytes(data[i + 2:i + 4], "big")
        yield marker, i, i + 2 + seg_len
        i += 2 + seg_len


def _extract_jpeg_xmp(data: bytes) -> bytes | None:
    """Devuelve el paquete XMP embebido (sin la firma) si existe, o None."""
    for marker, start, end in _iter_jpeg_segments(data):
        if marker == 0xE1 and data[start + 4:start + 4 + len(XMP_APP1_SIG)] == XMP_APP1_SIG:
            return data[start + 4 + len(XMP_APP1_SIG):end]
    return None


def _strip_jpeg_xmp(data: bytes) -> bytes:
    """Devuelve los bytes del JPEG sin ningún segmento APP1-XMP previo."""
    out = bytearray(data[:2])  # SOI
    i = 2
    n = len(data)
    while i + 1 < n:
        if data[i] != 0xFF:
            out.extend(data[i:])
            return bytes(out)
        marker = data[i + 1]
        if marker in (0xDA, 0xD9):
            out.extend(data[i:])
            return bytes(out)
        if 0xD0 <= marker <= 0xD7 or marker in (0x01, 0xD8):
            out.extend(data[i:i + 2])
            i += 2
            continue
        seg_len = int.from_bytes(data[i + 2:i + 4], "big")
        seg_end = i + 2 + seg_len
        is_xmp = (marker == 0xE1
                  and data[i + 4:i + 4 + len(XMP_APP1_SIG)] == XMP_APP1_SIG)
        if not is_xmp:
            out.extend(data[i:seg_end])
        i = seg_end
    out.extend(data[i:])
    return bytes(out)


def _embed_xmp_in_jpeg(path: Path, xmp_packet: bytes) -> None:
    """Inserta el paquete XMP como segmento APP1 (tras SOI), quitando uno previo."""
    data = path.read_bytes()
    if data[:2] != b"\xff\xd8":
        raise ValueError(f"No es un JPEG válido: {path.name}")
    payload = XMP_APP1_SIG + xmp_packet
    if len(payload) + 2 > 0xFFFF:
        raise ValueError("Paquete XMP demasiado grande para un único APP1")
    app1 = b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload
    base = _strip_jpeg_xmp(data)
    path.write_bytes(base[:2] + app1 + base[2:])   # APP1 justo después de SOI


# --- Comprobación de rating existente (overwrite=False) ---

def _packet_has_rating(xmp_bytes: bytes) -> bool:
    try:
        root = etree.fromstring(xmp_bytes)
    except Exception:
        return False
    return any(el.text for el in root.iter(f"{{{NS['xmp']}}}Rating"))


def _sidecar_has_rating(xmp_path: Path) -> bool:
    try:
        root = etree.parse(str(xmp_path)).getroot()
    except Exception:
        return False
    return any(el.text for el in root.iter(f"{{{NS['xmp']}}}Rating"))


# --- API pública ---

def write_xmp(image_path: str, label: str, stars: int, color: str,
              overwrite: bool = False) -> bool:
    """Escribe el rating/etiqueta. RAW -> sidecar; JPEG -> embebido. Respeta overwrite."""
    p = Path(image_path)
    try:
        packet = _build_xmp_packet(stars, color, label)
        if _is_raw(p):
            xmp_path = _get_xmp_path(image_path)
            if xmp_path.exists() and not overwrite and _sidecar_has_rating(xmp_path):
                return False
            xmp_path.write_bytes(packet)
        else:
            if not overwrite:
                existing = _extract_jpeg_xmp(p.read_bytes())
                if existing is not None and _packet_has_rating(existing):
                    return False
            _embed_xmp_in_jpeg(p, packet)
        logger.debug(f"XMP {p.name} [{label}/{stars}★/{color}]")
        return True
    except Exception as e:
        logger.error(f"Error escribiendo XMP para {image_path}: {e}")
        return False


def export_results_to_xmp(results: list[dict], ratings_mapping: dict,
                          overwrite: bool = False) -> dict:
    """Exporta todos los resultados. Devuelve {written, skipped, errors, total}."""
    written = skipped = errors = 0
    for result in results:
        if result.get("error"):
            errors += 1
            continue
        label = result.get("label")
        if not label:
            skipped += 1
            continue
        mapping = ratings_mapping.get(label, {})
        ok = write_xmp(
            image_path=result["path"],
            label=label,
            stars=mapping.get("stars", 0),
            color=mapping.get("color", ""),
            overwrite=overwrite,
        )
        written += ok
        skipped += (not ok)
    logger.info(
        f"Exportación XMP: {written} escritos, {skipped} omitidos, {errors} errores "
        f"de {len(results)} total")
    return {"written": written, "skipped": skipped, "errors": errors, "total": len(results)}
