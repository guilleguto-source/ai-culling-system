"""
neural_lut.py — Motor de Color Grading y Neural 3D-LUT Adaptativo (Fase 3).

Aprende el estilo y gradación tonal directamente desde las ediciones históricas
(almacenadas en develop_recipes.json y history.db) para cada tipo de escena,
con fallback inteligente a perfiles LUT curados cuando aún no hay suficientes ejemplos.

Campos que gestiona (Look & Color Grading):
  Contrast2012, Highlights2012, Shadows2012, Whites2012, Blacks2012,
  Clarity2012, Vibrance, Saturation

Exclusión:
  Exposure2012, IncrementalTemperature, IncrementalTint, Dehaze,
  curvas complejas o máscaras IA (gestionados por pre_edit y preset_manager).
"""
import json
import logging
from pathlib import Path
from typing import Any

from services.develop_style import load_recipes, style_for_embedding, style_for_scene

from services.app_paths import get_resource as _get_resource

logger = logging.getLogger(__name__)

LUTS_DIR = _get_resource("models/luts")

LUT_STYLE_FIELDS = (
    "Contrast2012",
    "Highlights2012",
    "Shadows2012",
    "Whites2012",
    "Blacks2012",
    "Clarity2012",
    "Vibrance",
    "Saturation",
)


def list_available_luts() -> list[dict[str, Any]]:
    """Lista todos los perfiles LUT curados disponibles."""
    luts = []
    if LUTS_DIR.exists():
        for p in sorted(LUTS_DIR.glob("*.lut.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                luts.append({
                    "id": p.stem.replace(".lut", ""),
                    "name": data.get("name", p.stem),
                    "display_name": data.get("display_name", p.stem),
                    "description": data.get("description", ""),
                    "settings": data.get("settings", {}),
                })
            except Exception as e:
                logger.warning(f"Error cargando LUT {p.name}: {e}")
    return luts


def load_lut_profile(name: str) -> dict[str, Any]:
    """Carga un perfil LUT curado por nombre."""
    target = LUTS_DIR / f"{name}.lut.json"
    if not target.exists():
        # Intentar match por stem
        for p in LUTS_DIR.glob("*.lut.json"):
            if p.stem.replace(".lut", "") == name:
                target = p
                break
    if target.exists():
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Error leyendo {target}: {e}")
    return {}


def get_learned_style(
    scene: str | None = None,
    embedding: Any = None,
    fallback_name: str = "warm_golden",
    custom_lut: str | None = None,
) -> tuple[dict[str, float], str]:
    """
    Obtiene los ajustes de estilo.
    Prioridad:
      1. Custom LUT explícito si se solicita.
      2. Receta aprendida de sesiones pasadas para la escena/embedding.
      3. Fallback LUT curado.
    Retorna: (settings_dict, source_description)
    """
    if custom_lut:
        lut_data = load_lut_profile(custom_lut)
        if lut_data and "settings" in lut_data:
            return lut_data["settings"], f"custom:{custom_lut}"

    # 1. Intentar receta aprendida de la escena
    learned: dict = {}
    if embedding is not None:
        try:
            learned = style_for_embedding(embedding)
        except Exception as e:
            logger.debug(f"No se pudo obtener estilo por embedding: {e}")
    elif scene is not None:
        learned = style_for_scene(scene)

    if learned:
        # Filtrar solo los campos soportados
        filtered = {k: float(v) for k, v in learned.items() if k in LUT_STYLE_FIELDS}
        if filtered:
            return filtered, f"learned:{scene or 'cluster'}"

    # 2. Fallback a LUT curado
    fallback_data = load_lut_profile(fallback_name)
    if fallback_data and "settings" in fallback_data:
        return fallback_data["settings"], f"fallback:{fallback_name}"

    # 3. Fallback neutro absoluto
    neutral_data = load_lut_profile("neutral")
    return neutral_data.get("settings", {}), "fallback:neutral"


def compute_lut_adjustments(
    scene: str | None = None,
    embedding: Any = None,
    strength: float = 1.0,
    fallback_lut: str = "warm_golden",
    custom_lut: str | None = None,
) -> dict[str, float]:
    """
    Calcula los ajustes de color grading / 3D-LUT escalados por `strength` (0.0 a 1.0).
    Retorna diccionario crs listo para fusionar en XMP.
    """
    base_settings, _ = get_learned_style(
        scene=scene,
        embedding=embedding,
        fallback_name=fallback_lut,
        custom_lut=custom_lut,
    )
    if not base_settings:
        return {}

    scaled: dict[str, float] = {}
    strength_clamped = max(0.0, min(1.5, float(strength)))
    for k, v in base_settings.items():
        if k in LUT_STYLE_FIELDS:
            adj = round(float(v) * strength_clamped, 2)
            if adj != 0.0:
                scaled[k] = adj

    return scaled


def get_lut_status() -> dict[str, Any]:
    """Retorna el estado del aprendizaje de estilos y perfiles LUT disponibles."""
    recipes = load_recipes()
    total_learned_scenes = len(recipes)
    total_samples = sum(r.get("_n", 0) for r in recipes.values())
    available = list_available_luts()

    return {
        "total_learned_scenes": total_learned_scenes,
        "total_learned_samples": total_samples,
        "recipes_summary": {
            k: {"samples": v.get("_n", 0), "fields": [f for f in v if f != "_n"]}
            for k, v in recipes.items()
        },
        "available_luts": available,
    }
