"""
routers/export.py — Endpoints de exportación XMP, pre-edición diferida, sincronización y aprendizaje desde Lightroom y análisis histórico.
"""
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.settings_manager import load_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Export & Lightroom"])


# --- Schemas ---

class ApplyEditsRequest(BaseModel):
    directory: str


class ReimportRequest(BaseModel):
    directory: str


class CatalogDiffRequest(BaseModel):
    directory: str
    catalog_path: str
    since: str = "2025-02-01"
    limit: int | None = None


class UndoRequest(BaseModel):
    directory: str


class SyncReminderRequest(BaseModel):
    directory: str
    hours: float = 8.0


class HistoryBootstrapRequest(BaseModel):
    catalog_path: str = ""
    root: str = ""
    since: str = "2025-02-01"
    dry_run: bool = True


class HistoryScenesRequest(BaseModel):
    k: int = 10
    label: str = "positive"
    limit: int | None = None


# --- Endpoints ---

@router.post("/apply_edits")
def apply_edits(data: ApplyEditsRequest):
    """
    Escribe la edición propuesta (crop + preset + WB + exposición) en las
    fotos actualmente selected/highlighted del snapshot — instantáneo, sin
    re-analizar.
    """
    from services.export_snapshot import load_snapshot, set_edits_applied
    from services.preset_manager import load_preset
    from services.xmp_exporter import export_results_to_xmp

    snap = load_snapshot(data.directory)
    if snap is None:
        raise HTTPException(status_code=404, detail="Este directorio no tiene un culling previo")

    ratings_map = load_settings()["ratings_mapping"]
    crops = snap.get("crops", {})
    develops = snap.get("develops", {})
    preset_path = snap.get("preset_path", "")
    preset_data = load_preset(preset_path) if preset_path and Path(preset_path).exists() else None

    rewrite = []
    for path_str, label in snap["items"].items():
        if label not in ("selected", "highlighted"):
            continue
        m = ratings_map.get(label, {})
        rewrite.append({
            "path": path_str,
            "label": label,
            "stars": m.get("stars", 0),
            "color": m.get("color", ""),
            "crop": crops.get(path_str),
            "develop": develops.get(path_str),
        })

    if not rewrite:
        raise HTTPException(status_code=400, detail="No hay fotos seleccionadas en el snapshot")

    xmp_stats = export_results_to_xmp(rewrite, ratings_map, overwrite=True, preset=preset_data)
    set_edits_applied(data.directory)

    # Re-sellar mtimes para mantener válido el caché
    from services.analysis_store import init_store, refresh_mtimes
    try:
        refresh_mtimes(init_store(data.directory), [r["path"] for r in rewrite])
    except Exception as e:
        logger.warning(f"No se pudo re-sellar el análisis tras aplicar edición: {e}")

    return {
        "success": True,
        "edited": len(rewrite),
        "preset": preset_data.name if preset_data else None,
        "xmp": xmp_stats,
    }


@router.post("/reimport_xmp")
def reimport_xmp(data: ReimportRequest):
    """
    Relee los XMP de un directorio ya exportado y convierte las correcciones
    del usuario en Lightroom en ejemplos de entrenamiento.
    """
    from services.export_snapshot import load_snapshot, update_synced_stars
    from services.xmp_reader import read_xmp
    from services.ingester import _load_jpg, _extract_raw_preview, RAW_EXTENSIONS
    from services.taste_model import taste_model
    from services import embedding_service

    snapshot = load_snapshot(data.directory)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Este directorio no tiene un export previo")

    ratings_map = load_settings()["ratings_mapping"]
    synced = snapshot.get("synced_stars", {})

    groups: dict[tuple, list[str]] = {}
    for path_str in snapshot["items"]:
        p = Path(path_str)
        groups.setdefault((str(p.parent).lower(), p.stem.lower()), []).append(path_str)

    def get_embedding(path_str):
        emb = embedding_service.embed_path(path_str, img_rgb=None)
        if emb is not None:
            return emb
        p = Path(path_str)
        arr = _extract_raw_preview(p) if p.suffix.lower() in RAW_EXTENSIONS else _load_jpg(p)
        return embedding_service.embed_path(path_str, arr) if arr is not None else None

    from services.scene_grouping import nearest_scene

    upgraded = downgraded = 0
    learned = 0
    new_synced: dict[str, int] = {}
    keepers: list[dict] = []
    emb_available = embedding_service.is_available()

    for members in groups.values():
        members.sort(key=lambda s: Path(s).suffix.lower() in RAW_EXTENSIONS)
        primary = members[0]
        exported_label = snapshot["items"][primary]
        baseline = synced.get(primary, ratings_map.get(exported_label, {}).get("stars", 0))

        xmps = {m: read_xmp(m, full=True) for m in members}
        current = next((x for x in xmps.values() if x and x["stars"] != baseline), None)
        edited = (next((x for x in xmps.values() if x and (x.get("develop") or x.get("crop"))), None)
                  or next((x for x in xmps.values() if x), None))
        stars_now = edited["stars"] if edited else baseline

        emb = get_embedding(primary) if emb_available and (current or stars_now >= 2) else None

        if current is not None:
            sign = +1 if current["stars"] > baseline else -1
            upgraded += sign > 0
            downgraded += sign < 0
            new_synced[primary] = current["stars"]
            if emb is not None:
                taste_model.add_example(emb, sign, "lightroom", event_dir=data.directory)
                learned += 1

        if edited is not None and stars_now >= 2 and (edited.get("develop") or edited.get("crop")):
            keepers.append({
                "path": primary, "rating": stars_now,
                "develop": edited.get("develop", {}), "crop": edited.get("crop", {}),
                "scene": nearest_scene(emb) or "",
            })

    if new_synced:
        update_synced_stars(data.directory, new_synced)

    from services.sync_learning import learn_styles_from_event
    estilo = learn_styles_from_event(keepers)

    from services.export_snapshot import mark_synced
    mark_synced(data.directory)

    total_corrections = upgraded + downgraded
    return {
        "success": True,
        "corrections": total_corrections,
        "upgraded": upgraded,
        "downgraded": downgraded,
        "learned": learned,
        "embeddings_available": emb_available,
        "total_examples": taste_model.n_examples,
        "estilo_aprendido": estilo,
        "hint": ("¿Guardaste los metadatos en Lightroom? En Lightroom: "
                 "Metadatos → Guardar metadatos en archivo (Ctrl+S), o activa "
                 "'Escribir cambios automáticamente en XMP'.")
                if total_corrections == 0 else "",
    }


@router.post("/lightroom/pending_changes")
def lightroom_pending_changes(data: CatalogDiffRequest):
    """
    Fase R: avisa si Lightroom tiene cambios que aún no se volcaron al archivo.
    """
    from services.catalog_diff import find_pending_changes, mensaje_para_usuario
    if not Path(data.catalog_path).exists():
        raise HTTPException(status_code=404, detail="No se encontró el catálogo")
    res = find_pending_changes(data.catalog_path, data.directory, data.since, data.limit)
    return {**res, "mensaje": mensaje_para_usuario(res)}


@router.post("/undo_export")
def undo_export(data: UndoRequest):
    """
    Fase O: deshace el último export, devolviendo cada foto al XMP que tenía antes.
    """
    from services.undo_export import restore_previous_state, has_backup
    if not has_backup(data.directory):
        raise HTTPException(status_code=404,
                            detail="No hay respaldo previo para este directorio")
    return restore_previous_state(data.directory)


@router.get("/undo_export/available")
def undo_available(directory: str):
    from services.undo_export import has_backup
    return {"disponible": has_backup(directory)}


@router.get("/sync/pending")
def sync_pending():
    """Eventos culleados que toca recordar sincronizar desde Lightroom."""
    from services.export_snapshot import pending_reminders
    return {"events": pending_reminders()}


@router.post("/sync/snooze")
def sync_snooze(data: SyncReminderRequest):
    """Posponer el recordatorio de un evento (p.ej. 8 h)."""
    from services.export_snapshot import snooze_reminder
    snooze_reminder(data.directory, data.hours)
    return {"success": True}


@router.post("/sync/dismiss")
def sync_dismiss(data: SyncReminderRequest):
    """Apagar el recordatorio de un evento ('ya terminé')."""
    from services.export_snapshot import dismiss_reminder
    dismiss_reminder(data.directory)
    return {"success": True}


@router.post("/history/bootstrap")
def history_bootstrap(data: HistoryBootstrapRequest):
    """
    Fase H1: etiquetar el historial (catálogo Lightroom o XMP) según la convención de rating.
    """
    from services.history_bootstrap import bootstrap_from_catalog, bootstrap_from_xmp
    if data.catalog_path:
        return bootstrap_from_catalog(data.catalog_path, data.since, data.dry_run)
    if data.root:
        return bootstrap_from_xmp(data.root, data.since, data.dry_run)
    raise HTTPException(status_code=400, detail="Indica catalog_path o root")


@router.post("/history/embed")
def history_embed(data: HistoryScenesRequest):
    """Fase I: calcula/cachea los embeddings CLIP del historial."""
    from services.scene_grouping import embed_history
    return embed_history(label=data.label, limit=data.limit)


@router.post("/history/scenes")
def history_scenes(data: HistoryScenesRequest):
    """Fase I: agrupa por escena las fotos ya embebidas y persiste la categoría."""
    from services.scene_grouping import assign_scenes
    return assign_scenes(k=data.k, label=data.label)


@router.post("/history/feed-taste")
def history_feed_taste(data: HistoryScenesRequest):
    """Fase H2: alimenta el taste model con positivas (+1) y negativas (-1)."""
    from services.history_taste import feed_taste_from_history
    return feed_taste_from_history(limit=data.limit)


@router.post("/history/feed-taste-pairs")
def history_feed_taste_pairs():
    """
    Fase Q: alimenta el gusto con pares ganadora/perdedora DENTRO de cada ráfaga revisada.
    """
    from services.history_taste import feed_pairwise_from_history
    return feed_pairwise_from_history()


@router.post("/history/develop-style")
def history_develop_style():
    """Fase J: aprende el 'look' (contraste, tono, color) por escena."""
    from services.develop_style import learn_recipes
    recipes = learn_recipes()
    return {"escenas_con_receta": len(recipes),
            "recetas": {s: {k: v for k, v in r.items()} for s, r in recipes.items()}}


@router.post("/history/crop-style")
def history_crop_style():
    """Fase K: aprende tendencias de recorte (área, encuadre, ángulo) por escena."""
    from services.crop_style import learn_crop_style
    estilos = learn_crop_style()
    return {"escenas_con_estilo": len(estilos), "estilos": estilos}


@router.get("/learning/summary")
def learning_summary():
    """Fase T: panel 'Tu estilo' — solo cifras reales, nada inventado."""
    from services.learning_summary import build_summary
    return build_summary()
