"""
ingester.py — Motor de ingesta de imágenes JPG y RAW.
Extrae previews JPEG embebidos de archivos RAW para evitar decodificación completa.
Genera thumbnails para la UI y para los modelos de IA.
"""
import io
import logging
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

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


def _make_thumbnails(arr: np.ndarray) -> tuple[bytes, bytes, np.ndarray]:
    """
    Genera tres thumbnails a partir de un array RGB:
    - thumb_ui: bytes WebP para mostrar en la galería (grid).
    - thumb_duel: bytes WebP en alta resolución para el Duelo A/B.
    - thumb_ai: array numpy redimensionado para modelos de IA.
    """
    img = Image.fromarray(arr)

    # Thumbnail para UI (mantiene aspecto)
    img_ui = img.copy()
    img_ui.thumbnail(THUMB_UI_SIZE, Image.LANCZOS)
    buf_ui = io.BytesIO()
    img_ui.save(buf_ui, format="WEBP", quality=85)
    thumb_ui_bytes = buf_ui.getvalue()

    # Thumbnail para Duelos en alta resolución
    img_duel = img.copy()
    img_duel.thumbnail(THUMB_DUEL_SIZE, Image.LANCZOS)
    buf_duel = io.BytesIO()
    img_duel.save(buf_duel, format="WEBP", quality=80)
    thumb_duel_bytes = buf_duel.getvalue()

    # Thumbnail para IA — aspecto preservado (NO cuadrado, no deforma rostros)
    img_ai = img.copy()
    img_ai.thumbnail(THUMB_AI_SIZE, Image.LANCZOS)
    thumb_ai_arr = np.array(img_ai)

    return thumb_ui_bytes, thumb_duel_bytes, thumb_ai_arr


def _get_exif_datetime(path: Path) -> str:
    """Extrae la fecha/hora de captura desde los metadatos EXIF."""
    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(f, stop_tag="EXIF DateTimeOriginal", details=False)
        dt = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
        return str(dt) if dt else ""
    except Exception:
        return ""


def _compute_phash(arr: np.ndarray) -> str:
    """Calcula el Perceptual Hash (pHash) de la imagen para detección de duplicados."""
    try:
        img = Image.fromarray(arr)
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

    # 2. Generar thumbnails
    try:
        t_ui, t_duel, t_ai = _make_thumbnails(arr)
        record.thumb_ui = t_ui
        record.thumb_duel = t_duel
        record.thumb_ai = t_ai
        
        # Guardar en disco cache
        from services.thumbnail_store import save_thumbnail_to_disk
        save_thumbnail_to_disk(record.path, t_ui, t_duel)
    except Exception as e:
        logger.error(f"Error procesando thumbnails {path.name}: {e}")
        record.error = "Error al redimensionar"
        return record
        
    # 3. Calcular pHash para detección de duplicados
    record.phash = _compute_phash(arr)

    # 4. Extraer fecha EXIF
    record.exif_datetime = _get_exif_datetime(path)

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


def ingest_directory(
    directory: str,
    max_workers: int = 4,
    progress_callback=None,
) -> tuple[list[ImageRecord], dict]:
    """
    Ingesta todos los archivos de imagen en un directorio de forma concurrente.

    Args:
        directory: Ruta al directorio de imágenes.
        max_workers: Hilos de procesamiento paralelo.
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

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
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
        "images_per_second": round(total / elapsed, 1) if elapsed > 0 else 0,
    }
    logger.info(
        f"Ingesta completa: {stats['success']}/{total} imágenes en "
        f"{stats['elapsed_seconds']}s ({stats['images_per_second']} img/s)"
    )
    return records, stats
