"""
undo_export.py — Fase O: respaldo previo al export y deshacer.

El export ESCRIBE en los archivos reales del fotógrafo (XMP embebido en los
JPG, sidecars de los RAW). Sin respaldo, un culling mal configurado pisa horas
de trabajo sin vuelta atrás — la barrera de entrada más seria para un
profesional.

Estrategia: antes de tocar nada se guardan los **bytes crudos** del XMP de cada
foto (o la marca de que no tenía). Restaurar es entonces exacto, no una
reconstrucción a partir de campos parseados.

Los respaldos viven en models/undo/<hash-del-evento>/ — no ensucian la carpeta
de fotos del usuario.
"""
import hashlib
import json
import logging
from pathlib import Path

from services.app_paths import get_undo_dir as _get_undo_dir

logger = logging.getLogger(__name__)

UNDO_DIR = _get_undo_dir()
MANIFEST = "manifest.json"


def _event_dir(directory: str) -> Path:
    key = hashlib.sha1(str(Path(directory).resolve()).lower().encode("utf-8")).hexdigest()
    return _get_undo_dir() / key


def _packet_name(path: str) -> str:
    return hashlib.sha1(path.lower().encode("utf-8")).hexdigest() + ".xmp"


def capture_previous_state(directory: str, paths: list[str]) -> dict:
    """
    Respalda el XMP actual de cada foto ANTES del export.

    Si algo falla al leer, propaga la excepción: es preferible abortar el export
    a escribir sin red de seguridad.
    """
    from services.xmp_exporter import read_raw_packet

    dest = _event_dir(directory)
    dest.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str | None] = {}
    con_xmp = 0

    for path in paths:
        packet = read_raw_packet(path)          # puede lanzar → aborta el export
        if packet is None:
            manifest[path] = None               # no tenía XMP
        else:
            nombre = _packet_name(path)
            (dest / nombre).write_bytes(packet)
            manifest[path] = nombre
            con_xmp += 1

    (dest / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                 encoding="utf-8")
    logger.info(f"Respaldo previo: {len(manifest)} fotos ({con_xmp} tenían XMP).")
    return {"respaldadas": len(manifest), "con_xmp_previo": con_xmp}


def has_backup(directory: str) -> bool:
    return (_event_dir(directory) / MANIFEST).exists()


def restore_previous_state(directory: str) -> dict:
    """
    Deshace el último export: devuelve cada foto al XMP que tenía antes.
    Las que no tenían XMP se limpian (sidecar borrado en RAW; paquete neutro
    en JPEG, donde el segmento no se puede quitar sin re-escribir la imagen).
    """
    from services.xmp_exporter import write_raw_packet, clear_xmp

    src = _event_dir(directory)
    mf = src / MANIFEST
    if not mf.exists():
        return {"restauradas": 0, "error": "No hay respaldo para este directorio"}

    manifest: dict = json.loads(mf.read_text(encoding="utf-8"))
    restauradas = limpiadas = fallidas = 0

    for path, nombre in manifest.items():
        try:
            if nombre is None:
                limpiadas += 1 if clear_xmp(path) else 0
            else:
                packet = (src / nombre).read_bytes()
                restauradas += 1 if write_raw_packet(path, packet) else 0
        except Exception as e:
            logger.error(f"No se pudo restaurar {path}: {e}")
            fallidas += 1

    return {"restauradas": restauradas, "limpiadas": limpiadas,
            "fallidas": fallidas, "total": len(manifest)}
