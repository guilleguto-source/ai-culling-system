"""
export_snapshot.py — Persistencia de lo que el sistema exportó a XMP por evento.
Necesario para el sync desde Lightroom: al releer los XMP, la diferencia entre
lo que NOSOTROS escribimos y lo que hay AHORA son las correcciones del usuario.

Un JSON por directorio de evento, en backend/models/exports/ (no ensucia la
carpeta de fotos del usuario).
"""
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

EXPORTS_DIR = Path(__file__).parent.parent / "models" / "exports"


def _snapshot_path(directory: str) -> Path:
    key = hashlib.sha1(str(Path(directory).resolve()).lower().encode("utf-8")).hexdigest()
    return EXPORTS_DIR / f"{key}.json"


def save_snapshot(directory: str, results: list[dict], preset_path: str = "",
                  edits_applied: bool = True) -> None:
    """Guarda {path: label} de lo exportado en el último culling del directorio."""
    items = {
        r["path"]: r["label"]
        for r in results
        if r.get("label") and not r.get("error")
    }
    data = {
        "directory": str(Path(directory).resolve()),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        # False = modo "solo culling": crop/develop propuestos pero no escritos
        "edits_applied": edits_applied,
        "items": items,
        # Crops/develop propuestos: el re-export tras un duelo los reutiliza
        "crops": {
            r["path"]: r["crop"]
            for r in results
            if r.get("crop") and not r.get("error")
        },
        "develops": {
            r["path"]: r["develop"]
            for r in results
            if r.get("develop") and not r.get("error")
        },
        "preset_path": preset_path,
    }
    try:
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        _snapshot_path(directory).write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    except Exception as e:
        logger.error(f"No se pudo guardar el snapshot de export: {e}")


def load_snapshot(directory: str) -> dict | None:
    """Carga el snapshot del directorio, o None si nunca se exportó."""
    sp = _snapshot_path(directory)
    if not sp.exists():
        return None
    try:
        return json.loads(sp.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Snapshot ilegible ({sp.name}): {e}")
        return None


def _save(directory: str, data: dict) -> None:
    try:
        _snapshot_path(directory).write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    except Exception as e:
        logger.error(f"No se pudo actualizar el snapshot: {e}")


def update_labels(directory: str, new_labels: dict[str, str]) -> None:
    """Actualiza labels puntuales del snapshot (p.ej. tras un duelo)."""
    data = load_snapshot(directory)
    if data is None:
        return
    data["items"].update(new_labels)
    _save(directory, data)


def set_edits_applied(directory: str) -> None:
    """Marca que la edición propuesta ya se escribió en los XMP."""
    data = load_snapshot(directory)
    if data is None:
        return
    data["edits_applied"] = True
    _save(directory, data)


def update_synced_stars(directory: str, stars_by_path: dict[str, int]) -> None:
    """
    Registra las estrellas ya sincronizadas desde Lightroom, para que un
    segundo sync no re-genere los mismos ejemplos de entrenamiento.
    """
    data = load_snapshot(directory)
    if data is None:
        return
    data.setdefault("synced_stars", {}).update(stars_by_path)
    _save(directory, data)
