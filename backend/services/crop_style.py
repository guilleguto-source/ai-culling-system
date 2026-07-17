"""
crop_style.py — Fase K: aprende cómo recorta el fotógrafo, por escena.

v1 (esta): descriptores del rectángulo de recorte que ya está en history.db —
área retenida, desplazamiento del centro (el vertical es un proxy del aire sobre
la cabeza), y ángulo de enderezado. Se aprende la mediana por escena.

v2 (futuro, documentado en el plan): descriptores RELATIVOS a las personas
(headroom real sobre la cabeza, márgenes al cuerpo), que necesitan analizar la
imagen original para las cajas de sujeto; y distinguir un reencuadre real de un
simple cambio de relación de aspecto (requiere las dimensiones originales).
"""
import json
import logging
import statistics
from pathlib import Path

from services.history_store import HistoryStore

logger = logging.getLogger(__name__)

MIN_PER_SCENE = 15
CROP_STYLE_PATH = Path(__file__).parent.parent / "models" / "crop_style.json"


def descriptors(crop: dict) -> dict:
    """Rectángulo normalizado (0..1) → descriptores de composición."""
    top = crop.get("CropTop", 0.0)
    left = crop.get("CropLeft", 0.0)
    bottom = crop.get("CropBottom", 1.0)
    right = crop.get("CropRight", 1.0)
    w = max(0.0, right - left)
    h = max(0.0, bottom - top)
    return {
        "area": round(w * h, 4),                        # fracción retenida
        "offset_x": round((left + right) / 2 - 0.5, 4),  # + = recorta hacia la derecha
        "offset_y": round((top + bottom) / 2 - 0.5, 4),  # - = sujeto arriba (más aire abajo)
        "angle": round(crop.get("CropAngle", 0.0), 4),
    }


def is_real_crop(crop: dict, area_tol: float = 0.98) -> bool:
    """True si el recorte es una decisión de composición, no un ajuste trivial."""
    d = descriptors(crop)
    return d["area"] < area_tol or abs(d["angle"]) > 0.1


def learn_crop_style(store: HistoryStore | None = None) -> dict:
    """Mediana de los descriptores por escena, sobre recortes reales de
    positivas. Persiste y devuelve {escena: {descriptor: valor, _n}}."""
    store = store or HistoryStore()
    by_scene: dict[str, list[dict]] = {}
    for _path, scene, crop in store.crops_by_scene():
        if is_real_crop(crop):
            by_scene.setdefault(scene, []).append(descriptors(crop))

    out: dict[str, dict] = {}
    for scene, ds in by_scene.items():
        if len(ds) < MIN_PER_SCENE:
            continue
        out[scene] = {"_n": len(ds)}
        for key in ("area", "offset_x", "offset_y", "angle"):
            out[scene][key] = round(statistics.median(d[key] for d in ds), 4)

    CROP_STYLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CROP_STYLE_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def load_crop_style() -> dict:
    if not CROP_STYLE_PATH.exists():
        return {}
    try:
        return json.loads(CROP_STYLE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
