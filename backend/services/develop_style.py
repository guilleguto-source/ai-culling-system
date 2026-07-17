"""
develop_style.py — Fase J: aprende el "look" del fotógrafo por tipo de escena.

División de trabajo con pre_edit:
  - pre_edit mide y corrige EXPOSICIÓN y WB desde los píxeles de cada foto
    (corrección técnica, per-foto). Eso NO se aprende: es medición.
  - Esta fase aprende los ajustes ESTILÍSTICOS (curva de tono, color) que el
    fotógrafo aplica de forma consistente por escena: contraste, altas luces,
    sombras, blancos, negros, claridad, vibración, dehaze.

Se aprende de las fotos POSITIVAS (2-3★), excluyendo ediciones extremas. La
receta por escena es la MEDIANA de cada campo (robusta a outliers). Requiere
que la Fase I ya haya asignado escena a las fotos.
"""
import json
import logging
import statistics
from pathlib import Path

from services.history_store import HistoryStore

logger = logging.getLogger(__name__)

# Campos de "look" (crs). Exposición/temperatura/tint quedan para pre_edit.
STYLE_FIELDS = (
    "Contrast2012", "Highlights2012", "Shadows2012", "Whites2012",
    "Blacks2012", "Clarity2012", "Vibrance", "Saturation", "Dehaze",
)
MIN_PER_SCENE = 15   # menos ejemplos que esto: la receta es ruido, no se aprende
RECIPES_PATH = Path(__file__).parent.parent / "models" / "develop_recipes.json"


def learn_recipes(store: HistoryStore | None = None) -> dict:
    """
    Mediana de cada campo de estilo por escena, sobre positivas no-extremas.
    Persiste y devuelve {escena: {campo: valor, "_n": nº ejemplos}}.
    """
    store = store or HistoryStore()
    by_scene: dict[str, list[dict]] = {}
    for path, scene, develop in store.develop_by_scene():
        by_scene.setdefault(scene, []).append(develop)

    recipes: dict[str, dict] = {}
    for scene, devs in by_scene.items():
        if len(devs) < MIN_PER_SCENE:
            continue
        recipe = {"_n": len(devs)}
        for f in STYLE_FIELDS:
            vals = [d[f] for d in devs if f in d]
            if len(vals) >= MIN_PER_SCENE:
                recipe[f] = round(statistics.median(vals), 3)
        recipes[scene] = recipe

    RECIPES_PATH.parent.mkdir(parents=True, exist_ok=True)
    RECIPES_PATH.write_text(json.dumps(recipes, indent=1), encoding="utf-8")
    return recipes


def load_recipes() -> dict:
    if not RECIPES_PATH.exists():
        return {}
    try:
        return json.loads(RECIPES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def style_for_scene(scene: str | None, recipes: dict | None = None) -> dict:
    """Ajustes de estilo (sin el _n) para una escena, o {} si no hay receta."""
    if scene is None:
        return {}
    r = (recipes if recipes is not None else load_recipes()).get(scene, {})
    return {k: v for k, v in r.items() if k != "_n"}


def style_for_embedding(embedding) -> dict:
    """Estilo aprendido para una foto nueva: su escena más cercana → receta."""
    from services.scene_grouping import nearest_scene
    return style_for_scene(nearest_scene(embedding))
