"""
history_bootstrap.py — Fase H1: convierte el historial del fotógrafo (catálogo
Lightroom o XMP en disco) en registros etiquetados, sin analizar imágenes.

Aplica la convención de selección del usuario (ver memoria
photo-selector-rating-convention). NO computa embeddings ni geometría: eso es
H2 (gusto) y las fases J/K. Barato: se puede correr en seco para ver qué saldría.
"""
import logging
import os
from pathlib import Path

from services.history_store import HistoryStore

logger = logging.getLogger(__name__)

# Convención del usuario (solo desde 2025-02-01):
#   2★ / 3★         → seleccionada (3★ = highlight)
#   1★ / negro(-1)  → descartada
#   4★ / 5★         → marcador de "por dónde quedé": IGNORAR
#   0★ sin negro    → sin revisar / ambigua
# Colores y banderín blanco NO se usan.
DATE_FLOOR = "2025-02-01"

# Corrección de exposición por encima de esto = error del usuario en fotos muy
# oscuras, no su estilo. Se etiqueta como extrema para excluirla del revelado.
EXTREME_EV = 1.0


def classify(rating: int, pick: int) -> str:
    """Etiqueta de una foto según rating (0-5) y banderín (pick: -1/0/1)."""
    if pick == -1:
        return "negative"          # banderín negro = a borrar
    if rating >= 4:
        return "ignore"            # 4★/5★ = marcador, no calidad
    if rating >= 2:
        return "positive"          # 2★ interesante, 3★ highlight
    if rating == 1:
        return "negative"          # bajada al editar, no convenció
    return "unreviewed"            # 0★ sin banderín


def is_extreme_develop(develop: dict) -> bool:
    """True si la corrección de exposición es un arreglo extremo, no estilo."""
    return abs(develop.get("Exposure2012", 0.0)) > EXTREME_EV


def _to_row(rec: dict, source: str) -> dict:
    return {
        "path": rec["path"],
        "label": classify(rec["rating"], rec["pick"]),
        "rating": rec["rating"],
        "pick": rec["pick"],
        "capture_time": rec["capture_time"],
        "develop": rec["develop"],
        "crop": rec["crop"],
        "develop_extreme": int(is_extreme_develop(rec["develop"])),
        "source": source,
    }


def _summarize(rows: list[dict]) -> dict:
    by_label: dict[str, int] = {}
    for r in rows:
        by_label[r["label"]] = by_label.get(r["label"], 0) + 1
    return {
        "total": len(rows),
        "por_etiqueta": by_label,
        "con_revelado": sum(1 for r in rows if r["develop"]),
        "con_recorte": sum(1 for r in rows if r["crop"]),
        "revelado_extremo": sum(1 for r in rows if r["develop_extreme"]),
    }


def bootstrap_from_catalog(lrcat_path: str, since: str = DATE_FLOOR,
                           dry_run: bool = True, store: HistoryStore | None = None) -> dict:
    """Lee el catálogo, etiqueta cada foto y (si no es dry_run) persiste."""
    from services.lr_catalog import read_catalog
    rows = [_to_row(rec, "catalog") for rec in read_catalog(lrcat_path, since)]
    if not dry_run and rows:
        (store or HistoryStore()).upsert(rows)
    return {"source": "catalog", "dry_run": dry_run, **_summarize(rows)}


def _iter_xmp_dir(root: str, since: str):
    """Recorre un directorio leyendo rating/revelado/recorte del XMP en disco."""
    from services.xmp_reader import read_xmp
    from services.xmp_exporter import RAW_EXTENSIONS
    exts = {".jpg", ".jpeg"} | RAW_EXTENSIONS
    for p in Path(root).rglob("*"):
        if p.suffix.lower() not in exts:
            continue
        data = read_xmp(str(p), full=True)
        if data is None:
            continue
        try:
            capture = ""  # el XMP no siempre trae fecha fiable; se filtra por mtime
            if since and _mtime_iso(p) < since:
                continue
        except OSError:
            continue
        yield {
            "path": str(p),
            "rating": data.get("stars", 0),
            "pick": 0,   # el banderín no viaja en XMP estándar de forma fiable
            "capture_time": capture,
            "develop": data.get("develop", {}),
            "crop": data.get("crop", {}),
        }


def _mtime_iso(p: Path) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(os.path.getmtime(p), timezone.utc).date().isoformat()


def bootstrap_from_xmp(root: str, since: str = DATE_FLOOR,
                       dry_run: bool = True, store: HistoryStore | None = None) -> dict:
    """Fuente alternativa cuando no hay catálogo: barre XMP en disco (más lento
    y sin banderín; solo cubre eventos donde se guardó la metadata)."""
    rows = [_to_row(rec, "xmp") for rec in _iter_xmp_dir(root, since)]
    if not dry_run and rows:
        (store or HistoryStore()).upsert(rows)
    return {"source": "xmp", "dry_run": dry_run, **_summarize(rows)}
