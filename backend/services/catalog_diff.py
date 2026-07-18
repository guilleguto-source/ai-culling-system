"""
catalog_diff.py — Fase R: detectar cambios de Lightroom que aún NO están en los
archivos.

El sync lee XMP del disco, pero Lightroom guarda todo en su catálogo hasta que
el usuario hace "Guardar metadatos en archivo" (Ctrl+S) o activa el auto-XMP.
Si no lo hace, sincronizamos archivos sin cambios y no aprendemos nada — y hoy
solo nos damos cuenta DESPUÉS, con un sync vacío.

Esto compara el catálogo (fuente de verdad de Lightroom) contra el XMP en disco
y avisa ANTES, de forma accionable. Solo lectura: nunca toca el .lrcat.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def find_pending_changes(lrcat_path: str, directory: str, since: str = "2025-02-01",
                         limit: int | None = None) -> dict:
    """
    Compara rating/banderín del catálogo contra el XMP en disco, para las fotos
    de `directory`.

    Returns:
        {pendientes, revisadas, ejemplos:[{path, catalogo, archivo}]}
        `pendientes` > 0 significa: Lightroom tiene cambios sin volcar.
    """
    from services.lr_catalog import read_catalog
    from services.xmp_reader import read_xmp

    objetivo = str(Path(directory).resolve()).lower()
    pendientes, revisadas = 0, 0
    ejemplos: list[dict] = []

    for rec in read_catalog(lrcat_path, since):
        path = rec["path"]
        try:
            if not str(Path(path).resolve()).lower().startswith(objetivo):
                continue
        except (OSError, ValueError):
            continue

        if not Path(path).exists():
            continue
        revisadas += 1

        en_archivo = read_xmp(path)
        estrellas_archivo = en_archivo["stars"] if en_archivo else 0
        estrellas_catalogo = rec["rating"]

        if estrellas_catalogo != estrellas_archivo:
            pendientes += 1
            if len(ejemplos) < 5:
                ejemplos.append({
                    "path": path,
                    "catalogo": estrellas_catalogo,
                    "archivo": estrellas_archivo,
                })
        if limit and revisadas >= limit:
            break

    return {"pendientes": pendientes, "revisadas": revisadas, "ejemplos": ejemplos}


def mensaje_para_usuario(res: dict) -> str:
    """Aviso accionable, o cadena vacía si no hay nada pendiente."""
    n = res.get("pendientes", 0)
    if not n:
        return ""
    return (f"Lightroom tiene {n} cambio(s) que todavía no están en los archivos. "
            "En Lightroom: seleccioná las fotos y hacé Metadatos → Guardar "
            "metadatos en archivo (Ctrl+S), o activá 'Escribir cambios "
            "automáticamente en XMP'. Después volvé a sincronizar.")
