import logging
import base64
from pathlib import Path
import json
import urllib.request
import urllib.error
from typing import List, Optional

logger = logging.getLogger(__name__)

# Configuración por defecto apuntando a Ollama local (ej. modelo LLaVA o llama3-vision)
# Esto mantiene el sistema 100% privado y local como prefiere el usuario.
OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3.2-vision"

def _encode_image(image_path: str) -> str:
    """Codifica la imagen a base64 para enviarla al VLM."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def decide_winner(image_paths: List[str]) -> Optional[int]:
    """
    Recibe una lista de rutas de imágenes (candidatas empatadas) y consulta al VLM
    para elegir la mejor basándose en emoción y micro-expresión facial.
    Retorna el índice de la imagen ganadora (0 a len-1), o None si falla.
    """
    if not image_paths or len(image_paths) < 2:
        return 0 if image_paths else None

    # Solo enviamos las primeras 2 o 3 para no saturar el contexto
    candidates = image_paths[:3]
    images_b64 = [_encode_image(p) for p in candidates]

    prompt = (
        "Eres un fotógrafo profesional evaluando una ráfaga de fotos casi idénticas. "
        "Revisa detalladamente las micro-expresiones faciales, la emoción transmitida y la pose. "
        "Responde ÚNICAMENTE con el número de índice (0, 1, o 2) correspondiente a la mejor foto. "
        "No des explicaciones, solo el número."
    )

    # Payload para Ollama
    payload = {
        "model": DEFAULT_MODEL,
        "prompt": prompt,
        "images": images_b64,
        "stream": False,
        "options": {
            "temperature": 0.1
        }
    }

    try:
        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
            response_text = result.get("response", "").strip()
            
            # Extraer el primer dígito de la respuesta
            for char in response_text:
                if char.isdigit():
                    idx = int(char)
                    if 0 <= idx < len(candidates):
                        return idx
                        
    except (urllib.error.URLError, TimeoutError, Exception) as e:
        logger.warning(f"VLM Refiner no disponible o falló: {e}")
        return None
        
    return None
