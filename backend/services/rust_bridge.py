"""
rust_bridge.py — Wrapper con fallback automático para el núcleo Rust.

Si `rust_core` está compilado (maturin develop --release), usa las
implementaciones nativas. Si no, usa el pipeline Python existente
sin ningún error visible ni cambio de comportamiento.

Uso:
    from services.rust_bridge import get_embedded_jpeg, compute_phash_batch, get_focus_point
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Detección del módulo Rust
# ---------------------------------------------------------------------------

try:
    import rust_core as _rc  # type: ignore[import]
    RUST_AVAILABLE = True
    logger.info("rust_core disponible — usando pipeline nativo (Rust/Rayon)")
except ImportError:
    _rc = None
    RUST_AVAILABLE = False
    logger.debug(
        "rust_core no compilado — usando pipeline Python como fallback. "
        "Para compilar: cd backend/rust_core && maturin develop --release"
    )


# ---------------------------------------------------------------------------
# 1. Extracción de thumbnail incrustado
# ---------------------------------------------------------------------------

def get_embedded_jpeg(path: str) -> bytes | None:
    """
    Extrae el JPEG incrustado de mayor resolución de un archivo RAW.
    Rust: ~2-4 ms/foto. Python fallback: ~40-60 ms/foto.
    """
    if RUST_AVAILABLE:
        try:
            return _rc.extract_thumb(path)
        except Exception as e:
            logger.debug(f"rust_core.extract_thumb falló para {path!r}: {e}")

    # Fallback Python: rawpy
    return _extract_thumb_python(path)


def _extract_thumb_python(path: str) -> bytes | None:
    """Fallback: extrae el thumbnail via rawpy (pipeline existente)."""
    try:
        import rawpy  # type: ignore[import]
        with rawpy.imread(path) as raw:
            thumb = raw.extract_thumb()
            if thumb.format == rawpy.ThumbFormat.JPEG:
                return bytes(thumb.data)
            # Si es bitmap, lo re-codificamos en JPEG en memoria
            import io
            from PIL import Image  # type: ignore[import]
            img = Image.fromarray(thumb.data)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            return buf.getvalue()
    except Exception as e:
        logger.debug(f"_extract_thumb_python falló para {path!r}: {e}")
        return None


# ---------------------------------------------------------------------------
# 2. pHash masivo paralelo
# ---------------------------------------------------------------------------

def compute_phash_batch(paths: list[str]) -> dict[str, int]:
    """
    Calcula pHash de 64 bits para un lote de rutas.
    Rust: procesamiento paralelo con Rayon (todos los núcleos, sin GIL).
    Python fallback: secuencial con imagehash.
    """
    if RUST_AVAILABLE:
        try:
            results = _rc.phash_batch_py(paths)
            return {path: h for path, h in results}
        except Exception as e:
            logger.debug(f"rust_core.phash_batch_py falló: {e}")

    return _phash_python_batch(paths)


def _phash_python_batch(paths: list[str]) -> dict[str, int]:
    """Fallback Python: usa imagehash secuencialmente."""
    try:
        import imagehash  # type: ignore[import]
        from PIL import Image  # type: ignore[import]
    except ImportError:
        logger.warning("imagehash no disponible — pHash fallback desactivado")
        return {}

    result: dict[str, int] = {}
    for path in paths:
        try:
            h = imagehash.phash(Image.open(path))
            result[path] = int(str(h), 16)
        except Exception as e:
            logger.debug(f"phash falló para {path!r}: {e}")
    return result


def hamming_distance(a: int, b: int) -> int:
    """Distancia Hamming entre dos pHashes (POPCNT nativo si Rust disponible)."""
    if RUST_AVAILABLE:
        return _rc.phash_hamming(a, b)
    return bin(a ^ b).count("1")


def cluster_by_phash(
    path_hash_map: dict[str, int],
    threshold: int = 10,
) -> list[list[str]]:
    """
    Agrupa rutas en clusters de fotos visualmente similares (Hamming <= threshold).
    Retorna lista de grupos (cada grupo es una lista de rutas).
    """
    items = list(path_hash_map.items())  # [(path, hash), ...]
    paths = [p for p, _ in items]

    if RUST_AVAILABLE:
        try:
            hashes_tuples = [(p, h) for p, h in items]
            clusters_idx = _rc.phash_cluster(hashes_tuples, threshold)
            return [[paths[i] for i in group] for group in clusters_idx]
        except Exception as e:
            logger.debug(f"rust_core.phash_cluster falló: {e}")

    # Fallback Python: clustering union-find simple
    parent = list(range(len(paths)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        parent[find(x)] = find(y)

    hashes = [h for _, h in items]
    for i in range(len(hashes)):
        for j in range(i + 1, len(hashes)):
            if hamming_distance(hashes[i], hashes[j]) <= threshold:
                union(i, j)

    groups: dict[int, list[str]] = {}
    for i, path in enumerate(paths):
        root = find(i)
        groups.setdefault(root, []).append(path)
    return list(groups.values())


# ---------------------------------------------------------------------------
# 3. Focus point & Burst ID (MakerNotes)
# ---------------------------------------------------------------------------

def get_focus_point(raw_path: str) -> tuple[float, float, bool] | None:
    """
    Extrae el punto de enfoque activo de las MakerNotes de la cámara.
    Retorna (x_norm, y_norm, is_focused) o None si no hay datos disponibles.
    Soporta: Nikon, Sony, Canon.
    """
    if RUST_AVAILABLE:
        try:
            return _rc.focus_point(raw_path)
        except Exception as e:
            logger.debug(f"rust_core.focus_point falló para {raw_path!r}: {e}")

    # Sin Rust y sin exiftool: no disponible
    logger.debug(f"focus_point no disponible sin rust_core para {raw_path!r}")
    return None

def get_burst_id(raw_path: str) -> int | None:
    """
    Extrae el Sequence Number o Burst ID de las MakerNotes.
    Retorna un entero identificando la ráfaga, o None si no hay.
    """
    if RUST_AVAILABLE:
        try:
            return _rc.burst_id(raw_path)
        except Exception as e:
            logger.debug(f"rust_core.burst_id falló para {raw_path!r}: {e}")

    return None
