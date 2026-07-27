import logging
import base64
from pathlib import Path
import json
import urllib.request
import urllib.error
from typing import List, Optional

logger = logging.getLogger(__name__)

# Configuración por defecto apuntando a Ollama local.
# Esto mantiene el sistema 100% privado y local como prefiere el usuario.
OLLAMA_URL = "http://localhost:11434/api/generate"
# OJO: llama3.2-vision (mllama) dejó de cargar en Ollama >= 0.32 ("unknown
# model architecture"). El modelo se elige en settings (vlm_model) para poder
# cambiarlo sin tocar código.
DEFAULT_MODEL = "qwen2.5vl:7b"


def _model_name() -> str:
    """Modelo de visión a usar: preferencia del usuario o el default."""
    try:
        from services.settings_manager import load_settings
        prefs = load_settings().get("selection_preferences", {})
        return prefs.get("vlm_model") or DEFAULT_MODEL
    except Exception:
        return DEFAULT_MODEL

# Alto de cada panel del collage que viaja al VLM.
PANEL_H = 512


def _collage_b64(image_paths: List[str]) -> Optional[str]:
    """
    UN solo collage lado-a-lado con las candidatas, numeradas 0..N arriba,
    a partir de los thumbs 'duel' cacheados.

    Por qué collage y no varias imágenes (medido en vivo con qwen2.5vl:7b):
    - por separado el veredicto FLIP-FLOPEABA entre corridas idénticas;
      el collage único dio 4/4 estable con temperature 0.1;
    - un solo bloque de visión cabe holgado en el contexto y Ollama cachea
      el prompt → ~3s por decisión con el modelo caliente.

    NUNCA se envía el archivo original: un RAW es indecodificable para el VLM
    y un JPG de cámara (20-40 MB) revienta payload y timeout. Si falta el
    thumb de alguna candidata → None (no se degrada a originales).
    """
    from services.thumbnail_store import read_thumbnail_from_disk
    import cv2
    import numpy as np

    paneles = []
    for i, p in enumerate(image_paths):
        data = read_thumbnail_from_disk(p, "duel")
        if not data:
            return None
        arr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            return None
        h, w = arr.shape[:2]
        arr = cv2.resize(arr, (max(1, int(w * PANEL_H / h)), PANEL_H),
                         interpolation=cv2.INTER_AREA)
        banda = np.full((60, arr.shape[1], 3), 255, dtype=np.uint8)
        cv2.putText(banda, str(i), (max(0, arr.shape[1] // 2 - 15), 48),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 0, 0), 4)
        paneles.append(np.vstack([banda, arr]))

    collage = np.hstack(paneles)
    ok, jpg = cv2.imencode(".jpg", collage, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        return None
    return base64.b64encode(jpg.tobytes()).decode("utf-8")


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
    collage = _collage_b64(candidates)
    if collage is None:
        # Falta algún thumb en caché: no degradar a mandar originales.
        logger.info("VLM: sin thumbnail cacheado para alguna candidata; se omite el refinamiento.")
        return None

    prompt = (
        "Collage de una ráfaga: fotos casi idénticas, numeradas arriba (0, 1, 2). "
        "Eres un fotógrafo profesional: elige la mejor por micro-expresión facial, "
        "ojos abiertos, emoción y pose. "
        "Responde ÚNICAMENTE con el número de la mejor foto. Sin explicaciones."
    )

    # Payload para Ollama
    payload = {
        "model": _model_name(),
        "prompt": prompt,
        "images": [collage],
        "stream": False,
        # Mantener el modelo cargado entre empates: el arranque en frío tarda
        # ~50s; caliente responde en segundos.
        "keep_alive": "15m",
        "options": {
            "temperature": 0.1,
            # Margen para el bloque de visión del collage (el default de 4096
            # se quedaba corto con imágenes grandes → 400 exceed_context_size).
            "num_ctx": 8192,
        }
    }

    try:
        req = urllib.request.Request(
            OLLAMA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        # 180s de tope: la PRIMERA evaluación (prompt frío) tardó ~65s medidos
        # en CPU; las siguientes ~3s por el caché de prompt de Ollama. Es
        # opt-in y solo corre en empates reñidos.
        with urllib.request.urlopen(req, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
            response_text = result.get("response", "").strip()

            # Extraer el primer dígito de la respuesta
            for char in response_text:
                if char.isdigit():
                    idx = int(char)
                    if 0 <= idx < len(candidates):
                        return idx

    except (urllib.error.URLError, TimeoutError) as e:
        logger.warning(f"VLM Refiner no disponible: {e}")
        return None
    except Exception:
        logger.exception("VLM Refiner falló inesperadamente")
        return None

    return None
