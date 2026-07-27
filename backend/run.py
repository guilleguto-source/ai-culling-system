"""
run.py — Script de arranque del backend para desarrollo y para el proceso Electron.
"""
import argparse

import uvicorn

if __name__ == "__main__":
    # El Electron empaquetado lanza `backend --port=8000`: hay que respetarlo.
    # Antes se ignoraba y funcionaba por coincidencia (ambos usaban 8000).
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=args.port,
        log_level="info",
        reload=False,
    )
