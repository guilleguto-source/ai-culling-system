"""
test_recipe_matcher.py — Tests para el módulo de Recipe Matcher (Fase 3).
"""
import pytest
from services.recipe_matcher import get_recipe_for_scene, blend_photo_develop


def test_fallback_recipe_by_scene():
    """Si no hay recetas aprendidas, debe devolver los defaults estéticos según la escena."""
    portrait_recipe = get_recipe_for_scene("portrait", learned_recipes={})
    assert portrait_recipe["Contrast2012"] == 5
    assert portrait_recipe["Clarity2012"] == -4
    assert portrait_recipe["Vibrance"] == 8
    
    detail_recipe = get_recipe_for_scene("detail", learned_recipes={})
    assert detail_recipe["Contrast2012"] == 12
    assert detail_recipe["Clarity2012"] == 12


def test_learned_recipe_overrides_fallback():
    """Si hay una receta aprendida para la escena, debe tener prioridad sobre el fallback."""
    learned = {
        "portrait": {
            "Contrast2012": 15,
            "Clarity2012": 0,
            "Vibrance": 20,
            "_n": 30,
        }
    }
    recipe = get_recipe_for_scene("portrait", learned_recipes=learned)
    assert recipe["Contrast2012"] == 15
    assert recipe["Vibrance"] == 20
    assert "_n" not in recipe


def test_blend_photo_develop_priority():
    """
    Verifica que blend_photo_develop combine adecuadamente:
    - pre_edit: Exposure2012, IncrementalTemperature
    - recipe: Contrast2012, Clarity2012, Vibrance
    - tonal_rescue: Highlights2012, Shadows2012
    """
    base_edit = {
        "Exposure2012": 0.35,
        "IncrementalTemperature": -5.0,
        "IncrementalTint": 2.0,
    }
    recipe = {
        "Contrast2012": 10,
        "Clarity2012": -5,
        "Vibrance": 12,
        "Highlights2012": -10, # La receta tiene un valor genérico
    }
    tonal = {
        "Highlights2012": -65, # El rescate per-foto por quemado real debe tener prioridad
        "Whites2012": -20,
    }
    
    final = blend_photo_develop(base_edit, recipe, tonal)
    
    # Pre-edit
    assert final["Exposure2012"] == 0.35
    assert final["IncrementalTemperature"] == -5.0
    
    # Recipe
    assert final["Contrast2012"] == 10
    assert final["Clarity2012"] == -5
    assert final["Vibrance"] == 12
    
    # Tonal rescue override
    assert final["Highlights2012"] == -65
    assert final["Whites2012"] == -20
