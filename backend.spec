# -*- mode: python ; coding: utf-8 -*-
"""
backend.spec — Especificación de PyInstaller para Guto Flow backend.

Genera un directorio self-contained (--onedir) con:
  - backend.exe  (punto de entrada FastAPI / uvicorn)
  - _internal/   (DLLs, paquetes Python, etc.)
  - models/luts/ (perfiles LUT curados, incluidos en el instalador)
  - models/clip_tokenizer/ (tokenizador CLIP bundleado)

Los modelos pesados (CLIP, ArcFace, MediaPipe, YOLO) NO van aquí;
se descargan al %APPDATA%/GutoFlow/ en el primer arranque de la app.

Uso:
  pyinstaller backend.spec --clean --noconfirm
"""
import sys
from pathlib import Path

ROOT = Path(SPECPATH)
BACKEND = ROOT / "backend"

block_cipher = None

# ─────────────────────────────────────────────────────────────────────────────
# Hidden imports — módulos que PyInstaller no puede detectar estáticamente
# ─────────────────────────────────────────────────────────────────────────────
hidden_imports = [
    # FastAPI / uvicorn internals
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",

    # FastAPI / pydantic
    "fastapi",
    "fastapi.middleware.cors",
    "fastapi.responses",
    "pydantic",
    "pydantic.v1",

    # Nuestros routers y servicios (imports dinámicos)
    "routers.system",
    "routers.culling",
    "routers.bursts",
    "routers.calibration",
    "routers.export",
    "routers.media",
    "routers.advanced",
    "routers.setup",
    "services.app_paths",
    "services.model_downloader",
    "services.neural_lut",
    "services.tonal_rescue",
    "services.portrait_relighting",
    "services.skin_retouch",
    "services.embedding_service",
    "services.face_identity",
    "services.face_mesh",
    "services.person_detector",
    "services.clip_text_service",
    "services.xmp_exporter",
    "services.settings_manager",
    "services.thumbnail_store",
    "services.undo_export",
    "services.export_snapshot",
    "services.preset_manager",
    "core.job_manager",

    # ML / visión
    "cv2",
    "numpy",
    "sklearn",
    "sklearn.neighbors",
    "sklearn.preprocessing",
    "onnxruntime",
    "onnxruntime.capi",
    "mediapipe",
    "mediapipe.tasks",
    "mediapipe.tasks.python",
    "mediapipe.tasks.python.vision",

    # Utilities
    "lxml",
    "lxml.etree",
    "PIL",
    "PIL.Image",
    "rawpy",
    "exifread",
]

# ─────────────────────────────────────────────────────────────────────────────
# Datos bundleados (recursos de sólo lectura incluidos en el instalador)
# ─────────────────────────────────────────────────────────────────────────────
datas = [
    # LUTs curados (JSON) — siempre disponibles sin descarga
    (str(BACKEND / "models" / "luts"), "models/luts"),
    # Tokenizador CLIP — pequeño (~3.5 MB), va bundleado
    (str(BACKEND / "models" / "clip_tokenizer"), "models/clip_tokenizer"),
]

# Añadir clip_tokenizer solo si existe (evitar error si no está)
from pathlib import Path as _P
_clip_tok = BACKEND / "models" / "clip_tokenizer"
_luts_dir = BACKEND / "models" / "luts"

datas = []
if _luts_dir.exists():
    datas.append((str(_luts_dir), "models/luts"))
if _clip_tok.exists():
    datas.append((str(_clip_tok), "models/clip_tokenizer"))

# ─────────────────────────────────────────────────────────────────────────────
# Análisis
# ─────────────────────────────────────────────────────────────────────────────
a = Analysis(
    [str(BACKEND / "run.py")],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # excluir lo que definitivamente no se usa en producción
        "tkinter",
        "matplotlib",
        "IPython",
        "jupyter",
        "notebook",
        "pytest",
        "sphinx",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,       # True: útil para ver logs de uvicorn en producción
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="backend",
)
