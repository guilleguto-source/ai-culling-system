"""
xmp_exporter.py — Generador de archivos XMP sidecar compatibles con Adobe Lightroom.
Escribe calificaciones de estrellas, etiquetas de color y estado pick/reject.
Respeta la configuración de sobrescritura del usuario.
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
    "xmpDM":  "http://ns.adobe.com/xmp/1.0/DynamicMedia/",
    "tiff":   "http://ns.adobe.com/tiff/1.0/",
    "exif":   "http://ns.adobe.com/exif/1.0/",
}

# Mapeo de nombres de color del sistema a etiquetas XMP de Lightroom
COLOR_LABEL_MAP = {
    "Red":    "Red",
    "Yellow": "Yellow",
    "Green":  "Green",
    "Blue":   "Blue",
    "Purple": "Purple",
    "":       "",
    None:     "",
}

# Mapeo de label interno a pick status XMP
PICK_STATUS_MAP = {
    "selected":    "1",   # Pick (bandera verde en Lightroom)
    "highlighted": "1",   # Pick
    "blurry":      "-1",  # Reject (bandera roja)
    "closed_eyes": "-1",  # Reject
    "duplicates":  "0",   # Unflagged
}


def _get_xmp_path(image_path: str) -> Path:
    """Retorna la ruta del archivo .xmp sidecar para una imagen dada."""
    p = Path(image_path)
    return p.parent / (p.stem + ".xmp")


def _build_xmp_xml(
    stars: int,
    color: str,
    label: str,
) -> bytes:
    """
    Construye un documento XML XMP completo desde cero.

    Args:
        stars: Calificación 0-5.
        color: Nombre del color en inglés (Red, Yellow, Green, Blue, Purple).
        label: Categoría interna (selected, highlighted, blurry, etc.)

    Returns:
        Bytes del documento XML codificado en UTF-8.
    """
    # Registrar namespaces
    for prefix, uri in NS.items():
        etree.register_namespace(prefix, uri)

    # Elemento raíz x:xmpmeta
    xmpmeta = etree.Element(
        f"{{{NS['x']}}}xmpmeta",
        nsmap={"x": NS["x"], "rdf": NS["rdf"]},
    )
    xmpmeta.set(f"{{{NS['x']}}}xmptk", "AI Culling System 1.0")

    rdf = etree.SubElement(xmpmeta, f"{{{NS['rdf']}}}RDF")
    desc = etree.SubElement(
        rdf,
        f"{{{NS['rdf']}}}Description",
        nsmap={
            "rdf":   NS["rdf"],
            "xmp":   NS["xmp"],
            "xmpDM": NS["xmpDM"],
            "tiff":  NS["tiff"],
            "exif":  NS["exif"],
        },
    )
    desc.set(f"{{{NS['rdf']}}}about", "")

    # xmp:Rating (0-5 estrellas)
    rating_el = etree.SubElement(desc, f"{{{NS['xmp']}}}Rating")
    rating_el.text = str(max(0, min(5, stars)))

    # xmp:Label (color)
    color_label = COLOR_LABEL_MAP.get(color, "")
    if color_label:
        label_el = etree.SubElement(desc, f"{{{NS['xmp']}}}Label")
        label_el.text = color_label

    # xmp:PickStatus (pick/reject/unflagged)  — extensión Lightroom
    pick_val = PICK_STATUS_MAP.get(label, "0")
    pick_el = etree.SubElement(desc, f"{{{NS['xmp']}}}PickStatus")
    pick_el.text = pick_val

    return etree.tostring(
        xmpmeta,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=True,
    )


def _read_existing_xmp(xmp_path: Path) -> etree._Element | None:
    """Intenta parsear un archivo XMP existente. Retorna None si falla."""
    try:
        tree = etree.parse(str(xmp_path))
        return tree.getroot()
    except Exception as e:
        logger.warning(f"No se pudo leer XMP existente {xmp_path.name}: {e}")
        return None


def _has_existing_rating(root: etree._Element) -> bool:
    """Verifica si el XMP existente ya tiene una calificación de Rating."""
    rating_tag = f"{{{NS['xmp']}}}Rating"
    for elem in root.iter(rating_tag):
        if elem.text is not None:
            return True
    return False


def write_xmp(
    image_path: str,
    label: str,
    stars: int,
    color: str,
    overwrite: bool = False,
) -> bool:
    """
    Escribe (o actualiza) el archivo .xmp sidecar para una imagen.

    Args:
        image_path: Ruta completa al archivo de imagen.
        label: Categoría de culling (selected, blurry, duplicates, etc.)
        stars: Número de estrellas (0-5).
        color: Nombre del color de etiqueta.
        overwrite: Si True, sobreescribe ratings existentes; si False, los preserva.

    Returns:
        True si el archivo fue escrito, False si fue omitido o falló.
    """
    xmp_path = _get_xmp_path(image_path)

    # Si existe el XMP y overwrite=False, verificar si ya tiene rating
    if xmp_path.exists() and not overwrite:
        existing = _read_existing_xmp(xmp_path)
        if existing is not None and _has_existing_rating(existing):
            logger.debug(f"Preservando rating existente en {xmp_path.name}")
            return False

    # Construir y escribir el XMP
    try:
        xml_bytes = _build_xmp_xml(stars, color, label)
        xmp_path.write_bytes(xml_bytes)
        logger.debug(f"XMP escrito: {xmp_path.name} [{label}/{stars}★/{color}]")
        return True
    except Exception as e:
        logger.error(f"Error escribiendo XMP para {image_path}: {e}")
        return False


def export_results_to_xmp(
    results: list[dict],
    ratings_mapping: dict,
    overwrite: bool = False,
) -> dict:
    """
    Exporta todos los resultados de culling como archivos .xmp sidecar.

    Args:
        results: Lista de resultados del pipeline (de main.py).
        ratings_mapping: Mapeo label → {stars, color} de settings.json.
        overwrite: Si True, sobreescribe XMP existentes.

    Returns:
        Dict con estadísticas: {written, skipped, errors, total}
    """
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
        stars = mapping.get("stars", 0)
        color = mapping.get("color", "")

        ok = write_xmp(
            image_path=result["path"],
            label=label,
            stars=stars,
            color=color,
            overwrite=overwrite,
        )
        if ok:
            written += 1
        else:
            skipped += 1

    logger.info(
        f"Exportación XMP: {written} escritos, {skipped} omitidos, {errors} errores "
        f"de {len(results)} total"
    )
    return {
        "written": written,
        "skipped": skipped,
        "errors": errors,
        "total": len(results),
    }
