"""
recipe_matcher.py — Sistema progresivo de recetas de revelado estilístico por escena (Fase 3).
Combina recetas aprendidas del catálogo del fotógrafo con fallbacks inteligentes
y armonización con pre_edit y tonal rescue.
"""
import logging
from typing import Any
import numpy as np

from services.develop_style import load_recipes, style_for_scene, STYLE_FIELDS

logger = logging.getLogger(__name__)

# Fallbacks estilísticos conservadores por tipo de escena si el fotógrafo
# aún no tiene suficientes fotos aprendidas (menos de MIN_PER_SCENE).
SCENE_DEFAULT_RECIPES: dict[str, dict[str, Any]] = {
    "portrait": {
        "Contrast2012": 5,
        "Clarity2012": -4,       # micro-suavizado estético en piel
        "Vibrance": 8,
        "Shadows2012": 10,
    },
    "couple": {
        "Contrast2012": 6,
        "Clarity2012": -3,
        "Vibrance": 8,
        "Shadows2012": 8,
    },
    "group": {
        "Contrast2012": 8,
        "Clarity2012": 4,
        "Vibrance": 10,
        "Shadows2012": 10,
    },
    "detail": {
        "Contrast2012": 12,
        "Clarity2012": 12,       # realce de textura en detalles/objetos
        "Vibrance": 10,
        "Dehaze": 5,
    },
    "landscape": {
        "Contrast2012": 10,
        "Clarity2012": 10,
        "Vibrance": 15,
        "Dehaze": 8,
    },
    "architecture": {
        "Contrast2012": 10,
        "Clarity2012": 10,
        "Vibrance": 8,
        "Dehaze": 8,
    }
}

DEFAULT_FALLBACK = {
    "Contrast2012": 5,
    "Vibrance": 5,
}


def get_recipe_for_scene(
    scene_type: str | None,
    embedding: np.ndarray | None = None,
    learned_recipes: dict | None = None,
) -> dict[str, Any]:
    """
    Obtiene la receta estilística adecuada para una foto.
    1. Si hay receta aprendida para esa escena, la utiliza.
    2. Si hay embedding y modelo de escenas, busca la escena más cercana.
    3. Si no hay datos aprendidos suficientes, usa los fallbacks estilísticos conservadores.
    """
    recipes = learned_recipes if learned_recipes is not None else load_recipes()
    
    # 1. Intentar escena directa en recetas aprendidas
    if scene_type and scene_type in recipes:
        learned = style_for_scene(scene_type, recipes)
        if learned:
            return learned

    # 2. Intentar embedding visual CLIP si existe
    if embedding is not None:
        try:
            from services.scene_grouping import nearest_scene
            ns = nearest_scene(embedding)
            if ns and ns in recipes:
                learned = style_for_scene(ns, recipes)
                if learned:
                    return learned
            if ns and ns in SCENE_DEFAULT_RECIPES:
                return dict(SCENE_DEFAULT_RECIPES[ns])
        except Exception as e:
            logger.debug(f"No se pudo inferir receta por embedding: {e}")

    # 3. Fallback por tipo de escena detectado
    if scene_type and scene_type in SCENE_DEFAULT_RECIPES:
        return dict(SCENE_DEFAULT_RECIPES[scene_type])

    return dict(DEFAULT_FALLBACK)


def blend_photo_develop(
    base_pre_edit: dict[str, Any] | None,
    scene_recipe: dict[str, Any] | None,
    tonal_rescue: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Combina en orden de prioridad:
    1. Base pre-edit (Exposure2012, IncrementalTemperature, IncrementalTint).
    2. Receta estilística de escena (Contrast2012, Clarity2012, Vibrance, etc.).
    3. Rescate tonal per-foto (Highlights2012, Shadows2012 si hubo recorte real).
    """
    out: dict[str, Any] = {}
    
    # Aplicar receta de escena
    if scene_recipe:
        for k, v in scene_recipe.items():
            if k in STYLE_FIELDS:
                out[k] = v

    # Aplicar correcciones técnicas de pre-edit (exposición y balance de blancos)
    if base_pre_edit:
        for k in ("Exposure2012", "IncrementalTemperature", "IncrementalTint"):
            if k in base_pre_edit:
                out[k] = base_pre_edit[k]

    # Aplicar rescate tonal (las altas luces/sombras rescatadas por recorte real tienen prioridad técnica)
    if tonal_rescue:
        for k, v in tonal_rescue.items():
            out[k] = v

    return out
