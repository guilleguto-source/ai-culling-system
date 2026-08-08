"""
verify_build.py — Smoke test del ejecutable generado por PyInstaller.

Lanza el backend empaquetado y verifica que el endpoint /health responde
correctamente antes de que electron-builder empaquete el instalador.

Uso:
    python scripts/verify_build.py
    python scripts/verify_build.py --exe dist/backend/backend.exe
"""
import argparse
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
DEFAULT_EXE = ROOT / "dist" / "backend" / "backend.exe"
HEALTH_URL = "http://127.0.0.1:8765/health"
TIMEOUT_SECS = 30
TEST_PORT = 8765


def wait_for_health(timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def main():
    parser = argparse.ArgumentParser(description="Verifica el ejecutable del backend.")
    parser.add_argument("--exe", default=str(DEFAULT_EXE), help="Ruta al backend.exe")
    args = parser.parse_args()

    exe = Path(args.exe)
    if not exe.exists():
        print(f"[verify] ERROR: No se encontró el ejecutable en {exe}")
        print("         Asegúrate de haber corrido: npm run build:backend")
        sys.exit(1)

    print(f"[verify] Lanzando {exe.name} en puerto {TEST_PORT}...")
    proc = subprocess.Popen(
        [str(exe), f"--port={TEST_PORT}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        print(f"[verify] Esperando respuesta en {HEALTH_URL} (max {TIMEOUT_SECS}s)...")
        if wait_for_health(TIMEOUT_SECS):
            print("[verify] ✅ Backend responde correctamente. Build válido.")
            sys.exit(0)
        else:
            stdout, stderr = proc.communicate(timeout=3)
            print("[verify] ❌ Backend no respondió en el tiempo esperado.")
            print("STDOUT:", stdout.decode(errors="replace"))
            print("STDERR:", stderr.decode(errors="replace"))
            sys.exit(1)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
