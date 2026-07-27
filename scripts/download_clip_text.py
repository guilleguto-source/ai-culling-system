import os
import sys
from pathlib import Path

# Inject truststore to fix Windows SSL issues (antivirus/proxy)
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    print("truststore no está instalado. Instalando...")
    os.system(f"{sys.executable} -m pip install truststore")
    import truststore
    truststore.inject_into_ssl()

import urllib.request
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent.parent / "backend" / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_URL = "https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/main/onnx/text_model.onnx"
OUTPUT_PATH = MODELS_DIR / "clip_vit_b32_text.onnx"

def download_model():
    if OUTPUT_PATH.exists():
        logger.info(f"El modelo ya existe en {OUTPUT_PATH}")
        return

    logger.info(f"Descargando {MODEL_URL}...")
    try:
        urllib.request.urlretrieve(MODEL_URL, OUTPUT_PATH)
        logger.info(f"Modelo descargado exitosamente en {OUTPUT_PATH}")
    except Exception as e:
        logger.error(f"Error descargando el modelo: {e}")
        if OUTPUT_PATH.exists():
            OUTPUT_PATH.unlink()

if __name__ == "__main__":
    download_model()
