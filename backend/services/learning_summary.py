"""
learning_summary.py — Fase T: el panel "Tu estilo".

Reemplaza al indicador "Backend Engine / Online", que habla de infraestructura
donde debería estar el diferencial del producto: lo que la IA aprendió de ESTE
fotógrafo.

REGLA: solo cifras que salen de una medición real. Nada de "confianza 96%".
Si un dato no existe todavía (p.ej. personas reconocidas sin ArcFace), se
devuelve None y la UI simplemente no lo muestra.
"""
import logging

logger = logging.getLogger(__name__)


def build_summary() -> dict:
    """Resumen de lo aprendido, con datos verificables."""
    out: dict = {}

    # --- Historial aprendido ---
    try:
        from services.history_store import HistoryStore
        store = HistoryStore()
        por_etiqueta = store.counts_by_label()
        out["fotos_historial"] = sum(por_etiqueta.values())
        out["seleccionadas_aprendidas"] = por_etiqueta.get("positive", 0)
        out["descartes_aprendidos"] = por_etiqueta.get("negative", 0)
        escenas = store.counts_by_scene()
        out["escenas"] = len(escenas)
    except Exception as e:
        logger.debug(f"Sin historial: {e}")

    # --- Decisiones que alimentaron el gusto ---
    try:
        from services.taste_model import taste_model
        out["decisiones_gusto"] = taste_model.n_examples
        out["gusto_entrenado"] = taste_model.is_trained
    except Exception as e:
        logger.debug(f"Sin taste model: {e}")

    # --- Estilo de revelado y recorte aprendidos ---
    try:
        from services.develop_style import load_recipes
        from services.crop_style import load_crop_style
        recetas, recortes = load_recipes(), load_crop_style()
        out["escenas_con_receta"] = len(recetas)
        if recortes:
            areas = [r["area"] for r in recortes.values() if "area" in r]
            if areas:
                # Dato tangible y verificable: cuánto del cuadro conserva
                out["recorte_habitual_pct"] = round(sum(areas) / len(areas) * 100)
    except Exception as e:
        logger.debug(f"Sin estilo aprendido: {e}")

    # --- Calibración de rostros (precisión honesta) ---
    try:
        from services.calibration_store import CalibrationStore
        out["caras_calibradas"] = CalibrationStore().count()
    except Exception as e:
        logger.debug(f"Sin calibración: {e}")

    # --- Reconocimiento de personas: solo si el modelo está ---
    try:
        from services import face_identity
        out["reconocimiento_personas"] = face_identity.is_available()
    except Exception:
        out["reconocimiento_personas"] = False

    # --- Último evento sincronizado ---
    try:
        from services.export_snapshot import pending_reminders
        pendientes = pending_reminders()
        out["eventos_pendientes_sync"] = len(pendientes)
        sincronizados = [e["last_synced_at"] for e in pendientes if e.get("last_synced_at")]
        out["ultimo_sync"] = max(sincronizados) if sincronizados else None
    except Exception as e:
        logger.debug(f"Sin snapshots: {e}")

    return out
