"""
mirror_uniface_models.py — Descarga modelos ONNX de UniFace para uso offline.
Resuelve el problema de inicialización cuando el usuario no tiene internet.
"""
import os
import urllib.request
import ssl
from pathlib import Path

# URLs de los modelos de UniFace
MODELS = {
    "scrfd_500m.onnx": "https://github.com/deepinsight/insightface/releases/download/v0.7/scrfd_500m_bnkps.onnx",
    "scrfd_10g.onnx": "https://github.com/deepinsight/insightface/releases/download/v0.7/scrfd_10g_bnkps.onnx",
    "mobilegaze.onnx": "https://github.com/hukkelas/MobileGaze/releases/download/v0.1/mobilegaze.onnx"
}

def download_models(dest_dir: Path):
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    print(f"Descargando modelos a {dest_dir}...")
    
    for filename, url in MODELS.items():
        dest_path = dest_dir / filename
        if dest_path.exists():
            print(f"✅ {filename} ya existe. Omitiendo.")
            continue
            
        print(f"📥 Descargando {filename} desde {url}...")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, context=ctx, timeout=120) as response:
                dest_path.write_bytes(response.read())
            print(f"✅ {filename} descargado exitosamente.")
        except Exception as e:
            print(f"❌ Error descargando {filename}: {e}")

if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent.parent
    models_dir = base_dir / "models" / "uniface"
    download_models(models_dir)
