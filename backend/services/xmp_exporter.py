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
import os
from pathlib import Path
import time

from lxml import etree

logger = logging.getLogger(__name__)

# Namespaces XMP estándar de Adobe
NS = {
    "x":      "adobe:ns:meta/",
    "rdf":    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "xmp":    "http://ns.adobe.com/xap/1.0/",
    "crs":    "http://ns.adobe.com/camera-raw-settings/1.0/",
}

# Mapeo de label interno a pick status XMP (extensión Lightroom).
# Fallback: el banderín real viene de ratings_mapping[label]["flag"]
# (configurable en Settings): "pick" | "reject" | "none".
PICK_STATUS_MAP = {
    "selected":    "1",   # Pick
    "highlighted": "1",   # Pick
    "blurry":      "-1",  # Reject
    "closed_eyes": "-1",  # Reject
    "duplicates":  "0",   # Unflagged
}
FLAG_TO_PICK = {"pick": "1", "reject": "-1", "none": "0"}

# Campos de "look" que puede aportar el estilo aprendido por escena (Fase J).
# Exposición/WB NO están: los calcula pre_edit desde los píxeles.
STYLE_FIELDS = (
    "Contrast2012", "Highlights2012", "Shadows2012", "Whites2012",
    "Blacks2012", "Clarity2012", "Vibrance", "Saturation", "Dehaze",
)

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


def _build_xmp_packet(stars: int, color: str, label: str,
                      crop: dict | None = None,
                      develop: dict | None = None,
                      preset=None,
                      flag: str | None = None,
                      lut_adjustments: dict | None = None,
                      tonal_rescue: dict | None = None,
                      paint_corrections: list | None = None) -> bytes:
    """Construye un paquete XMP completo (con envoltura xpacket) listo para
    sidecar o para embeber en APP1. El color se escribe tal cual venga de settings.
    `crop`: dict {left, top, right, bottom, angle} — reencuadre NO destructivo.
    `develop`: dict con ajustes crs calculados (Exposure2012,
    IncrementalTemperature, IncrementalTint) — pre-edición por foto.
    `preset`: PresetData (preset_manager) — el "look" del usuario; sus campos
    se escriben primero.
    `lut_adjustments`: dict crs de Neural 3D-LUT (tono/contraste aprendido).
    `tonal_rescue`: dict crs de rescate de altas luces y sombras.
    `paint_corrections`: elementos XML o máscaras locales (relighting / skin)."""
    import copy as _copy

    xmpmeta = etree.Element(f"{{{NS['x']}}}xmpmeta", nsmap={"x": NS["x"]})
    xmpmeta.set(f"{{{NS['x']}}}xmptk", "AI Culling System 1.0")

    rdf = etree.SubElement(xmpmeta, f"{{{NS['rdf']}}}RDF", nsmap={"rdf": NS["rdf"]})
    desc = etree.SubElement(
        rdf, f"{{{NS['rdf']}}}Description",
        nsmap={"rdf": NS["rdf"], "xmp": NS["xmp"], "crs": NS["crs"]})
    desc.set(f"{{{NS['rdf']}}}about", "")

    rating_el = etree.SubElement(desc, f"{{{NS['xmp']}}}Rating")
    rating_el.text = str(max(0, min(5, stars)))

    # ALWAYS write Label to force Lightroom to clear outdated colors if empty
    label_el = etree.SubElement(desc, f"{{{NS['xmp']}}}Label")
    label_el.text = color if color else ""

    pick_el = etree.SubElement(desc, f"{{{NS['xmp']}}}PickStatus")
    if flag in FLAG_TO_PICK:
        pick_el.text = FLAG_TO_PICK[flag]
    else:
        pick_el.text = PICK_STATUS_MAP.get(label, "0")

    crs_fields: dict[str, str] = {}

    # 1. Preset del usuario (look base): sus ajustes van primero
    if preset is not None:
        crs_fields.update(preset.settings)

    # 2. Neural 3D-LUT / Estilo aprendido: pisa/reemplaza tono y color base
    if lut_adjustments:
        for key, val in lut_adjustments.items():
            if val is not None:
                crs_fields[key] = f"{val:g}"

    # 3. Rescate Tonal automático: suma/compensa altas luces y sombras
    if tonal_rescue:
        for key, val in tonal_rescue.items():
            if key in crs_fields:
                try:
                    cur = float(crs_fields[key])
                    combined = max(-100, min(100, int(round(cur + float(val)))))
                    crs_fields[key] = str(combined)
                except ValueError:
                    crs_fields[key] = str(val)
            else:
                crs_fields[key] = str(val)

    # 4. Pre-edición calculada (exposición/WB): pisa al preset y LUT
    if develop:
        for key in ("Exposure2012", "IncrementalTemperature", "IncrementalTint"):
            if develop.get(key) is not None:
                crs_fields[key] = f"{develop[key]:+.2f}"
        if "IncrementalTemperature" in crs_fields or "IncrementalTint" in crs_fields:
            crs_fields.setdefault("WhiteBalance", "Custom")
        # Estilo aprendido por escena clásico (fallback si no hubo LUT)
        if not lut_adjustments:
            for key in STYLE_FIELDS:
                if develop.get(key) is not None:
                    crs_fields.setdefault(key, f"{develop[key]:g}")

    # 5. Crop (geometría): manda sobre todo
    if crop:
        crs_fields.update({
            "HasCrop": "True",
            "CropLeft": f"{crop['left']:.6f}",
            "CropTop": f"{crop['top']:.6f}",
            "CropRight": f"{crop['right']:.6f}",
            "CropBottom": f"{crop['bottom']:.6f}",
            "CropAngle": f"{crop.get('angle', 0.0):.4f}",
            "CropConstrainToWarp": "0",
        })

    if crs_fields or paint_corrections or (preset is not None and preset.elements):
        # Sin ProcessVersion + AlreadyApplied=False, Camera Raw ignora el
        # bloque crs en JPEGs (asume que los ajustes ya están aplicados).
        crs_fields.setdefault("Version", "15.4")
        crs_fields.setdefault("ProcessVersion", "15.4")
        crs_fields["AlreadyApplied"] = "False"
        crs_fields.setdefault("HasSettings", "True")
        for name, value in crs_fields.items():
            el = etree.SubElement(desc, f"{{{NS['crs']}}}{name}")
            el.text = value
        # Bloques XML del preset (curvas, HSL point colors, máscaras IA)
        if preset is not None:
            for element in preset.elements:
                desc.append(_copy.deepcopy(element))
        # Máscaras de corrección local (relighting / skin retouch)
        if paint_corrections:
            for element in paint_corrections:
                desc.append(_copy.deepcopy(element))

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


def _atomic_write(target_path: Path, data: bytes, retries: int = 3, retry_delay: float = 0.5) -> None:
    """
    Escribe datos en un archivo temporal (.tmp) y luego realiza un renombre atómico
    (os.replace) hacia el archivo de destino. Incluye reintentos ante bloqueos o cortes de red SMB/NAS.
    Garantiza que el archivo de destino nunca quede a medias o corrupto.
    """
    tmp_path = target_path.with_name(f"{target_path.name}.{os.getpid()}_{int(time.time() * 1000)}.tmp")
    last_err = None
    for attempt in range(retries):
        try:
            tmp_path.write_bytes(data)
            os.replace(tmp_path, target_path)
            return
        except OSError as e:
            last_err = e
            logger.warning(f"Reintento {attempt + 1}/{retries} en escritura atómica para {target_path.name}: {e}")
            time.sleep(retry_delay * (attempt + 1))
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
    if last_err:
        raise last_err


def _embed_xmp_in_jpeg(path: Path, xmp_packet: bytes) -> None:
    """Inserta el paquete XMP como segmento APP1, quitando uno previo de forma atómica.
    El XMP va DESPUÉS del APP1-Exif si existe (el estándar exige Exif como
    primer APP1; con el XMP primero, exifread y otros lectores no ven el EXIF)."""
    data = path.read_bytes()
    if data[:2] != b"\xff\xd8":
        raise ValueError(f"No es un JPEG válido: {path.name}")
    payload = XMP_APP1_SIG + xmp_packet
    if len(payload) + 2 > 0xFFFF:
        raise ValueError("Paquete XMP demasiado grande para un único APP1")
    app1 = b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload
    base = _strip_jpeg_xmp(data)

    insert_at = 2  # tras SOI por defecto
    for marker, start, end in _iter_jpeg_segments(base):
        if marker == 0xE1 and base[start + 4:start + 10] == b"Exif\x00\x00":
            insert_at = end   # justo después del APP1-Exif
            break
    modified_jpeg = base[:insert_at] + app1 + base[insert_at:]
    _atomic_write(path, modified_jpeg)


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
              overwrite: bool = False, crop: dict | None = None,
              develop: dict | None = None, preset=None,
              flag: str | None = None,
              lut_adjustments: dict | None = None,
              tonal_rescue: dict | None = None,
              paint_corrections: list | None = None) -> bool:
    """Escribe el rating/etiqueta de forma atómica. RAW -> sidecar; JPEG -> embebido. Respeta overwrite."""
    p = Path(image_path)
    try:
        if develop and _is_raw(p):
            # Incremental WB no existe para RAW (usa Kelvin): solo exposición
            develop = {k: v for k, v in develop.items()
                       if k not in ("IncrementalTemperature", "IncrementalTint")}
        packet = _build_xmp_packet(
            stars, color, label, crop=crop,
            develop=develop, preset=preset, flag=flag,
            lut_adjustments=lut_adjustments,
            tonal_rescue=tonal_rescue,
            paint_corrections=paint_corrections,
        )
        if _is_raw(p):
            xmp_path = _get_xmp_path(image_path)
            if xmp_path.exists() and not overwrite and _sidecar_has_rating(xmp_path):
                return False
            _atomic_write(xmp_path, packet)
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


def read_raw_packet(image_path: str) -> bytes | None:
    """
    Paquete XMP crudo de una foto (sidecar en RAW, embebido en JPEG), o None si
    no tiene. Base del respaldo previo al export: guardar los bytes tal cual
    permite una restauración exacta, no reconstruida.
    """
    p = Path(image_path)
    try:
        if _is_raw(p):
            xp = _get_xmp_path(image_path)
            return xp.read_bytes() if xp.exists() else None
        return _extract_jpeg_xmp(p.read_bytes())
    except Exception as e:
        logger.error(f"No se pudo leer el XMP crudo de {p.name}: {e}")
        raise


def write_raw_packet(image_path: str, packet: bytes) -> bool:
    """Escribe un paquete XMP tal cual de forma atómica (restauración de un respaldo)."""
    p = Path(image_path)
    try:
        if _is_raw(p):
            _atomic_write(_get_xmp_path(image_path), packet)
        else:
            _embed_xmp_in_jpeg(p, packet)
        return True
    except Exception as e:
        logger.error(f"No se pudo restaurar el XMP de {p.name}: {e}")
        return False


def clear_xmp(image_path: str) -> bool:
    """
    Deja la foto sin nuestras marcas, para restaurar un archivo que NO tenía
    XMP antes. En RAW borra el sidecar (queda como estaba). En JPEG el segmento
    no se puede quitar sin re-escribir la imagen, así que se deja un paquete
    neutro (sin rating, etiqueta ni banderín).
    """
    p = Path(image_path)
    try:
        if _is_raw(p):
            _get_xmp_path(image_path).unlink(missing_ok=True)
            return True
        return write_raw_packet(image_path, _build_xmp_packet(0, "", "", flag="none"))
    except Exception as e:
        logger.error(f"No se pudo limpiar el XMP de {p.name}: {e}")
        return False


def export_results_to_xmp(results: list[dict], ratings_mapping: dict,
                          overwrite: bool = False, preset=None,
                          lut_adjustments: dict | None = None) -> dict:
    """Exporta todos los resultados en paralelo. Devuelve {written, skipped, errors, total}.
    `preset` (PresetData) y `lut_adjustments` se aplican a fotos con `develop`."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _export_single(result: dict) -> str:
        if result.get("error"):
            return "error"
        label = result.get("label")
        if not label:
            return "skipped"
        mapping = ratings_mapping.get(label, {})
        develop = result.get("develop")
        # lut_adjustments per photo if provided in result, or global
        item_lut = result.get("lut_adjustments") or (lut_adjustments if develop else None)
        item_rescue = result.get("tonal_rescue")
        item_paint = result.get("paint_corrections")
        ok = write_xmp(
            image_path=result["path"],
            label=label,
            stars=mapping.get("stars", 0),
            color=mapping.get("color", ""),
            overwrite=overwrite,
            crop=result.get("crop"),
            develop=develop,
            preset=preset if develop else None,
            flag=mapping.get("flag"),
            lut_adjustments=item_lut,
            tonal_rescue=item_rescue,
            paint_corrections=item_paint,
        )
        return "written" if ok else "skipped"

    written = skipped = errors = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_export_single, r) for r in results]
        for future in as_completed(futures):
            res = future.result()
            if res == "written":
                written += 1
            elif res == "skipped":
                skipped += 1
            else:
                errors += 1

    logger.info(
        f"Exportación XMP: {written} escritos, {skipped} omitidos, {errors} errores "
        f"de {len(results)} total")
    return {"written": written, "skipped": skipped, "errors": errors, "total": len(results)}
