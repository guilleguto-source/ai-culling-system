"""
uniface_config.py — Configuración de perfiles y reglas de IA por tipo de evento.
Define los pesos de análisis, activación de cascada y sensibilidades para cada sesión.
"""
from typing import Dict, Any

EVENT_PRESETS: Dict[str, Dict[str, Any]] = {
    "wedding": {
        "label": "👰 Matrimonio / Boda",
        "detector_base": "scrfd_500m",
        "use_cascade": True,
        "cascade_threshold": 0.75,
        "heavy_detector": "scrfd_10g",
        "prioritize_eyes": True,
        "coverture_strict": True,
        "safety_cap": 0.35,
        "default_selectivity": "standard"
    },
    "kids_party": {
        "label": "🎂 Fiesta Infantil / Cumpleaños",
        "detector_base": "scrfd_500m",
        "use_cascade": True,
        "cascade_threshold": 0.70,
        "heavy_detector": "scrfd_10g",
        "prioritize_eyes": False,  # Más tolerante a ráfagas rápidas y sonrisas
        "coverture_strict": False,
        "safety_cap": 0.25,
        "default_selectivity": "standard"
    },
    "baptism": {
        "label": "🕊️ Bautizo / Comunión",
        "detector_base": "scrfd_500m",
        "use_cascade": True,
        "cascade_threshold": 0.75,
        "heavy_detector": "scrfd_10g",
        "prioritize_eyes": True,
        "coverture_strict": True,
        "safety_cap": 0.30,
        "default_selectivity": "standard"
    },
    "baby_shower": {
        "label": "🍼 Baby Shower / Gender Reveal",
        "detector_base": "scrfd_500m",
        "use_cascade": True,
        "cascade_threshold": 0.75,
        "heavy_detector": "scrfd_10g",
        "prioritize_eyes": True,
        "coverture_strict": False,
        "safety_cap": 0.25,
        "default_selectivity": "standard"
    },
    "family_outdoor": {
        "label": "🌳 Familiar al Aire Libre",
        "detector_base": "scrfd_500m",
        "use_cascade": True,
        "cascade_threshold": 0.75,
        "heavy_detector": "scrfd_10g",
        "prioritize_eyes": True,
        "coverture_strict": True,
        "safety_cap": 0.30,
        "default_selectivity": "standard"
    },
    "night_party": {
        "label": "🌙 Fiesta Nocturna / Evento de Noche",
        "detector_base": "scrfd_500m",
        "use_cascade": True,
        "cascade_threshold": 0.65,  # Tolerante con iluminación difícil / sombras de flash
        "heavy_detector": "scrfd_10g",
        "prioritize_eyes": False,
        "coverture_strict": False,
        "safety_cap": 0.25,
        "default_selectivity": "more"
    },
    "corporate": {
        "label": "💼 Corporativo / Conferencia",
        "detector_base": "scrfd_500m",
        "use_cascade": True,
        "cascade_threshold": 0.80,
        "heavy_detector": "scrfd_10g",
        "prioritize_eyes": True,
        "coverture_strict": False,
        "safety_cap": 0.20,
        "default_selectivity": "few"
    },
    "studio": {
        "label": "📸 Estudio / Retrato",
        "detector_base": "scrfd_10g",  # 10G directo si es estudio de pocas fotos
        "use_cascade": False,
        "cascade_threshold": 0.85,
        "heavy_detector": "scrfd_10g",
        "prioritize_eyes": True,
        "coverture_strict": True,
        "safety_cap": 0.50,
        "default_selectivity": "few"
    }
}

def get_event_preset(event_type: str) -> Dict[str, Any]:
    """Retorna el preset de evento configurado o el de boda/general por defecto."""
    return EVENT_PRESETS.get(event_type, EVENT_PRESETS["wedding"])
