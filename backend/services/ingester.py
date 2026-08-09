"""
ingester.py — Motor de ingesta de imágenes JPG y RAW.
Extrae previews JPEG embebidos de archivos RAW para evitar decodificación completa.
Genera thumbnails para la UI y para los modelos de IA.
"""
import io
import os
import logging
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

# Control de sobre-suscripción de hilos en bibliotecas C/C++
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENCV_NUM_THREADS", "1")

import rawpy
import imageio.v3 as iio
from PIL import Image, ImageOps
import exifread
import imagehash
import numpy as np

logger = logging.getLogger(__name__)

# Extensiones soportadas
RAW_EXTENSIONS = {
    ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2",
    ".raf", ".orf", ".rw2", ".dng", ".pef", ".kdc", ".mrw",
}
JPG_EXTENSIONS = {".jpg", ".jpeg"}
SUPPORTED_EXTENSIONS = RAW_EXTENSIONS | JPG_EXTENSIONS

# Tamaños de thumbnail
THUMB_UI_SIZE = (320, 240)    # Para la galería de la UI
THUMB_DUEL_SIZE = (1600, 1600) # Para comparaciones A/B de alta resolución en la UI
# Para análisis de IA: debe ser suficientemente grande para que YuNet detecte
# rostros en fotos de grupo (a 224px las caras quedan diminutas y no se detectan).
# Aspecto preservado; lado largo = 1600.
# NOTA (Fase 3): mantener todos los thumb_ai en memoria a la vez no escala a miles
# de fotos; conviene procesar en streaming. Aceptable por ahora.
THUMB_AI_SIZE = (1600, 1600)


@dataclass
class ImageRecord:
    """Representa una imagen procesada con todos sus metadatos."""
    path: str
    filename: str
    is_raw: bool
    thumb_ui: bytes = field(repr=False, default=b"")   # WebP bytes para UI Grid
    thumb_duel: bytes = field(repr=False, default=b"") # WebP bytes para UI Duel
    thumb_ai: np.ndarray = field(repr=False, default=None)  # Array para IA
    phash: str = ""
    exif_datetime: str = ""
    iso: int = 100
    width: int = 0
    height: int = 0
    error: str = ""
    linked_raw_path: str | None = None  # Ruta al RAW original si se procesó un JPG emparejado


def discover_images(directory: str) -> list[Path]:
    """
    Descubre todos los archivos de imagen soportados en un directorio (recursivo).
    """
    root = Path(directory)
    if not root.is_dir():
        raise ValueError(f"Directorio no válido: {directory}")

    found = [
        p for p in root.rglob("*")
        if p.suffix.lower() in SUPPORTED_EXTENSIONS and not p.name.startswith(".")
    ]
    logger.info(f"Encontradas {len(found)} imágenes en {directory}")
    return sorted(found)


def _extract_raw_preview(path: Path) -> np.ndarray | None:
    """
    Extrae el JPEG embebido de un archivo RAW usando rawpy.
    Este preview de alta calidad está disponible sin decodificar los datos del sensor.
    """
    try:
        with rawpy.imread(str(path)) as raw:
            thumb = raw.extract_thumb()
            if thumb.format == rawpy.ThumbFormat.JPEG:
                img = Image.open(io.BytesIO(thumb.data))
                # Respetar la orientación EXIF del preview embebido.
                img = ImageOps.exif_transpose(img)
                return np.array(img.convert("RGB"))
            elif thumb.format == rawpy.ThumbFormat.BITMAP:
                return thumb.data
    except Exception as e:
        logger.warning(f"rawpy no pudo extraer preview de {path.name}: {e}")

    # Fallback: decodificación rápida de baja calidad
    try:
        with rawpy.imread(str(path)) as raw:
            arr = raw.postprocess(
                use_camera_wb=True,
                half_size=True,         # Media resolución para velocidad
                no_auto_bright=True,
            )
            return arr
    except Exception as e:
        logger.error(f"Fallo total al procesar RAW {path.name}: {e}")
        return None


def _load_jpg(path: Path) -> np.ndarray | None:
    """Carga un archivo JPG como array numpy."""
    try:
        img = Image.open(path)
        # Aplicar la rotación indicada en EXIF (Orientation) y descartar el tag,
        # para que verticales/horizontales se muestren como fueron tomadas.
        img = ImageOps.exif_transpose(img).convert("RGB")
        return np.array(img)
    except Exception as e:
        logger.error(f"Error cargando JPG {path.name}: {e}")
        return None


def _make_thumbnails(arr: np.ndarray) -> tuple[bytes, bytes, np.ndarray, str]:
    """
    Genera thumbnails en cascada desde mayor a menor resolución reutilizando operaciones:
    - thumb_duel: bytes WebP en alta resolución (1600x1600) para el Duelo A/B.
    - thumb_ai: array numpy redimensionado para modelos de IA.
    - thumb_ui: bytes WebP para la galería (grid, 320x240).
    - phash_str: pHash calculado sobre la versión reducida (10x más rápido).
    """
    img = Image.fromarray(arr)

    # 1. Reducir primero a tamaño Duelo / IA (1600x1600)
    img.thumbnail(THUMB_DUEL_SIZE, Image.BILINEAR)

    # Duelo WebP
    buf_duel = io.BytesIO()
    img.save(buf_duel, format="WEBP", quality=80)
    thumb_duel_bytes = buf_duel.getvalue()

    # IA array numpy
    thumb_ai_arr = np.array(img)

    # pHash calculado sobre imagen ya reducida
    try:
        phash_str = str(imagehash.phash(img))
    except Exception:
        phash_str = ""

    # 2. Reducir a UI Grid (320x240) en cascada
    img.thumbnail(THUMB_UI_SIZE, Image.BILINEAR)
    buf_ui = io.BytesIO()
    img.save(buf_ui, format="WEBP", quality=85)
    thumb_ui_bytes = buf_ui.getvalue()

    return thumb_ui_bytes, thumb_duel_bytes, thumb_ai_arr, phash_str


def _get_exif_metadata(path: Path) -> tuple[str, int]:
    """Extrae la fecha/hora de captura y el ISO desde los metadatos EXIF."""
    dt_str = ""
    iso_val = 100
    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False)
        dt = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
        dt_str = str(dt) if dt else ""
        
        iso_tag = tags.get("EXIF ISOSpeedRatings")
        if iso_tag and iso_tag.values:
            try:
                iso_val = int(iso_tag.values[0])
            except ValueError:
                pass
    except Exception:
        pass
    return dt_str, iso_val


def _compute_phash(arr: np.ndarray) -> str:
    """Calcula el Perceptual Hash (pHash) de la imagen."""
    try:
        img = Image.fromarray(arr)
        img.thumbnail(THUMB_UI_SIZE, Image.BILINEAR)
        return str(imagehash.phash(img))
    except Exception:
        return ""


def process_single_image(path: Path, linked_raw_path: str | None = None) -> ImageRecord:
    """
    Procesa una única imagen: extrae el array de píxeles, genera thumbnails,
    calcula pHash y extrae metadatos EXIF.
    """
    record = ImageRecord(
        path=str(path),
        filename=path.name,
        is_raw=path.suffix.lower() in RAW_EXTENSIONS,
        linked_raw_path=linked_raw_path,
    )

    # 1. Cargar píxeles
    arr = _extract_raw_preview(path) if record.is_raw else _load_jpg(path)
    if arr is None:
        record.error = "No se pudo cargar la imagen"
        return record

    record.width = arr.shape[1]
    record.height = arr.shape[0]

    # 2. Generar thumbnails y pHash en cascada
    try:
        t_ui, t_duel, t_ai, p_hash = _make_thumbnails(arr)
        record.thumb_ui = t_ui
        record.thumb_duel = t_duel
        record.thumb_ai = t_ai
        record.phash = p_hash
        
        # Guardar en disco cache
        from services.thumbnail_store import save_thumbnail_to_disk
        save_thumbnail_to_disk(record.path, t_ui, t_duel)
    except Exception as e:
        logger.error(f"Error procesando thumbnails {path.name}: {e}")
        record.error = "Error al redimensionar"
        return record

    # 3. Extraer metadatos EXIF (fecha e ISO)
    dt_str, iso_val = _get_exif_metadata(path)
    record.exif_datetime = dt_str
    record.iso = iso_val

    return record


def get_ingest_tasks(directory: str) -> list[tuple[Path, str | None]]:
    """
    Descubre todos los archivos de imagen en un directorio y los agrupa por
    nombre base para emparejar RAW + JPG, devolviendo una lista de tareas (ruta, linked_raw).
    """
    paths = discover_images(directory)
    if not paths:
        return []

    groups: dict[str, list[Path]] = {}
    for p in paths:
        groups.setdefault(p.stem, []).append(p)
    
    tasks = []
    for stem, group_paths in groups.items():
        if len(group_paths) > 1:
            jpgs = [p for p in group_paths if p.suffix.lower() in JPG_EXTENSIONS]
            raws = [p for p in group_paths if p.suffix.lower() in RAW_EXTENSIONS]
            if jpgs and raws:
                # Si hay ambos, solo procesamos el JPG y enlazamos el RAW
                tasks.append((jpgs[0], str(raws[0])))
                continue
        for p in group_paths:
            tasks.append((p, None))
    return tasks


def _get_optimal_workers(max_workers: int | None = None) -> int:
    """Calcula el número óptimo de workers dejando 1 core libre para la UI y el sistema."""
    if max_workers is not None and max_workers > 0:
        return max_workers
    cpu = os.cpu_count() or 4
    return max(1, cpu - 1)


def ingest_directory(
    directory: str,
    max_workers: int | None = None,
    progress_callback=None,
) -> tuple[list[ImageRecord], dict]:
    """
    Ingesta todos los archivos de imagen en un directorio de forma concurrente
    utilizando ProcessPoolExecutor para eludir el GIL durante el procesamiento.

    Args:
        directory: Ruta al directorio de imágenes.
        max_workers: Hilos/procesos de procesamiento paralelo (None = auto).
        progress_callback: Función opcional que recibe (procesadas, total).

    Returns:
        (records, stats) — Lista de ImageRecord y estadísticas de procesamiento.
    """
    paths = discover_images(directory)
    if not paths:
        return [], {"total": 0, "success": 0, "errors": 0, "elapsed_seconds": 0}

    # Agrupar por nombre base para emparejar RAW + JPG
    groups: dict[str, list[Path]] = {}
    for p in paths:
        groups.setdefault(p.stem, []).append(p)
    
    tasks = []
    for stem, group_paths in groups.items():
        if len(group_paths) > 1:
            jpgs = [p for p in group_paths if p.suffix.lower() in JPG_EXTENSIONS]
            raws = [p for p in group_paths if p.suffix.lower() in RAW_EXTENSIONS]
            if jpgs and raws:
                # Si hay ambos, solo procesamos el JPG y enlazamos el RAW
                tasks.append((jpgs[0], str(raws[0])))
                # Si sobran archivos con el mismo stem, los ignoramos para no duplicar.
                continue
        for p in group_paths:
            tasks.append((p, None))

    total = len(tasks)
    records: list[ImageRecord] = []
    errors = 0
    start = time.perf_counter()
    workers = _get_optimal_workers(max_workers)

    try:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(process_single_image, path, linked_raw): path for path, linked_raw in tasks}
            for i, future in enumerate(as_completed(futures), 1):
                record = future.result()
                records.append(record)
                if record.error:
                    errors += 1
                if progress_callback:
                    progress_callback(i, total)
    except Exception as e:
        logger.warning(f"ProcessPoolExecutor fallback a ThreadPoolExecutor ({e})")
        records = []
        errors = 0
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(process_single_image, path, linked_raw): path for path, linked_raw in tasks}
            for i, future in enumerate(as_completed(futures), 1):
                record = future.result()
                records.append(record)
                if record.error:
                    errors += 1
                if progress_callback:
                    progress_callback(i, total)

    elapsed = time.perf_counter() - start
    stats = {
        "total": total,
        "success": total - errors,
        "errors": errors,
        "elapsed_seconds": round(elapsed, 2),
        "images_per_second": round(total / max(elapsed, 0.001), 1),
    }
    logger.info(
        f"Ingesta completa: {stats['success']}/{total} imágenes en "
        f"{stats['elapsed_seconds']}s ({stats['images_per_second']} img/s)"
    )
    return records, stats
