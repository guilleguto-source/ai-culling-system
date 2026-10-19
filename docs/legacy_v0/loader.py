from __future__ import annotations
import datetime
import os
from collections import defaultdict
from pathlib import Path
import cv2
import numpy as np

RAW_EXTS = {".cr2", ".cr3", ".nef", ".arw", ".raf", ".rw2", ".orf", ".dng"}
JPEG_EXTS = {".jpg", ".jpeg"}
MAX_DIM = 2500
_EXIF_DATETIME_ORIGINAL = 36867
_EXIF_DATETIME = 306


def is_raw(path: Path) -> bool:
    return path.suffix.lower() in RAW_EXTS


def _resize(img: np.ndarray, max_dim: int = MAX_DIM) -> np.ndarray:
    h, w = img.shape[:2]
    scale = max_dim / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def load_image(path: Path) -> np.ndarray:
    if is_raw(path):
        return _load_raw_preview(path)
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"No se pudo leer la imagen: {path}")
    return _resize(img)


def _load_raw_preview(path: Path) -> np.ndarray:
    import rawpy
    with rawpy.imread(str(path)) as raw:
        try:
            thumb = raw.extract_thumb()
            if thumb.format == rawpy.ThumbFormat.JPEG:
                arr = cv2.imdecode(np.frombuffer(thumb.data, np.uint8), cv2.IMREAD_COLOR)
                if arr is not None:
                    return _resize(arr)
        except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
            pass
        rgb = raw.postprocess(half_size=True)
        return _resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def capture_timestamp(path: Path) -> float:
    try:
        from PIL import Image
        exif = Image.open(path).getexif()
        dt = exif.get(_EXIF_DATETIME_ORIGINAL) or exif.get(_EXIF_DATETIME)
        if dt:
            return datetime.datetime.strptime(dt, "%Y:%m:%d %H:%M:%S").timestamp()
    except Exception:
        pass
    return os.path.getmtime(path)


def discover_units(folder: Path) -> list[tuple[Path, list[Path], Path]]:
    """Agrupa archivos por (stem en minúsculas). Devuelve [(primary, companions, analysis_source)].
    analysis_source = JPG hermano si el primary es RAW y existe; si no, el primary."""
    by_stem: dict[str, list[Path]] = defaultdict(list)
    for p in folder.iterdir():
        if p.suffix.lower() in (JPEG_EXTS | RAW_EXTS):
            by_stem[p.stem.lower()].append(p)
    units: list[tuple[Path, list[Path], Path]] = []
    for files in by_stem.values():
        files.sort(key=lambda p: 0 if p.suffix.lower() in RAW_EXTS else 1)
        primary = files[0]
        companions = files[1:]
        jpg = next((f for f in files if f.suffix.lower() in JPEG_EXTS), None)
        analysis_source = jpg if (is_raw(primary) and jpg is not None) else primary
        units.append((primary, companions, analysis_source))
    return sorted(units, key=lambda u: u[0].name)
