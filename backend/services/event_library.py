import json
import logging
from pathlib import Path

from services.app_paths import get_user_data_dir

logger = logging.getLogger(__name__)

LIBRARY_FILE = get_user_data_dir() / "event_library.json"

def _load_library() -> dict:
    if not LIBRARY_FILE.exists():
        # Default vocabulary
        return {
            "vocabulary": [
                "Fotos posadas",
                "Detalles",
                "Decoración",
                "Mesa de dulces",
                "Pastel",
                "Ceremonia",
                "Fiesta",
                "Baile",
                "Concurso",
                "Fútbol",
                "Familia",
                "Regalos"
            ],
            "events": {}
        }
    try:
        with open(LIBRARY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error cargando Event Library: {e}")
        return {"vocabulary": [], "events": {}}

def _save_library(data: dict) -> None:
    try:
        LIBRARY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LIBRARY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error guardando Event Library: {e}")

def get_vocabulary() -> list[str]:
    """Devuelve la lista de nombres de sucesos conocidos para autocompletado."""
    data = _load_library()
    return data.get("vocabulary", [])

def add_vocabulary_term(term: str) -> None:
    """Añade un nuevo término al vocabulario si no existe."""
    if not term or not term.strip():
        return
    term = term.strip()
    data = _load_library()
    vocab = set(data.get("vocabulary", []))
    if term not in vocab:
        data.setdefault("vocabulary", []).append(term)
        _save_library(data)
