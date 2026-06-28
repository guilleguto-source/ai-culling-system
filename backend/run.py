"""
run.py — Script de arranque del backend para desarrollo y para el proceso Electron.
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8765,
        log_level="info",
        reload=False,
    )
