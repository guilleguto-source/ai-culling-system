"""
reindex_siglip_thumbnails.py — Indexador masivo de embeddings SigLIP (768d).
Recorre todas las miniaturas en caché (.webp) e inyecta embeddings SigLIP
L2-normalizados a máxima velocidad en lotes vectorizados. Omitiendo
imágenes previamente procesadas.
"""
import sys
import os
from pathlib import Path
import time
import logging
import cv2
import numpy as np

# A Toda Máquina: maximizar hilos en CPU si PyTorch corre en CPU
try:
    import torch
    num_cores = os.cpu_count() or 4
    torch.set_num_threads(num_cores)
except Exception:
    pass

# Agregar backend al sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.thumbnail_store import CACHE_ROOT
from services import siglip_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("siglip_reindexer")


def run_reindexing(max_samples: int | None = None, batch_size: int = 128):
    print("=" * 65)
    print("  INICIANDO RE-INDEXACIÓN MASIVA A TODA MÁQUINA CON SIGLIP (768-dim)")
    print("=" * 65)

    if not CACHE_ROOT.exists():
        logger.error(f"No se encontró el directorio de miniaturas: {CACHE_ROOT}")
        return

    # Buscar todas las miniaturas webp
    logger.info(f"Buscando miniaturas en: {CACHE_ROOT}...")
    all_webp = list(CACHE_ROOT.rglob("*.webp"))
    total_found = len(all_webp)
    logger.info(f"Total de miniaturas en el disco: {total_found}")

    if max_samples:
        all_webp = all_webp[:max_samples]
        logger.info(f"Limitando a {max_samples} miniaturas.")

    # Filtrar aquellas que ya estén en caché para reanudar sin duplicar trabajo
    logger.info("Verificando trabajo previo en caché...")
    pending_items = []
    already_cached = 0

    for p in all_webp:
        try:
            mtime = p.stat().st_mtime
            if siglip_service.load_cached_embedding(str(p), mtime) is not None:
                already_cached += 1
            else:
                pending_items.append((p, mtime))
        except Exception:
            pending_items.append((p, 0.0))

    logger.info(f"Imágenes ya procesadas previamente: {already_cached}")
    logger.info(f"Imágenes pendientes por procesar: {len(pending_items)}")

    if not pending_items:
        print("=" * 65)
        print("  ¡TODAS LAS IMÁGENES YA TIENEN EMBEDDINGS SIGLIP EN CACHÉ!")
        print("=" * 65)
        return

    start_time = time.time()
    processed_count = 0
    total_pending = len(pending_items)

    for i in range(0, total_pending, batch_size):
        chunk = pending_items[i:i + batch_size]
        chunk_paths = [item[0] for item in chunk]
        chunk_mtimes = [item[1] for item in chunk]
        images_rgb = []

        for p, _ in chunk:
            try:
                img_bgr = cv2.imread(str(p))
                if img_bgr is not None:
                    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                    images_rgb.append(img_rgb)
                else:
                    images_rgb.append(None)
            except Exception as e:
                images_rgb.append(None)

        # Inferencia vectorizada en batch
        embeddings = siglip_service.embed_batch(images_rgb, batch_size=batch_size)

        # Guardar resultados en caché
        for (p, mtime), emb in zip(chunk, embeddings):
            if emb is not None:
                siglip_service.save_cached_embedding(str(p), mtime, emb)
                processed_count += 1

        elapsed = time.time() - start_time
        speed = processed_count / elapsed if elapsed > 0 else 0
        remaining = total_pending - processed_count
        eta_sec = remaining / speed if speed > 0 else 0
        eta_min = eta_sec / 60.0

        total_done = already_cached + processed_count
        pct = (total_done / total_found) * 100.0 if total_found > 0 else 100.0

        if (i // batch_size) % 2 == 0 or (i + batch_size) >= total_pending:
            print(
                f"Progreso: {total_done}/{total_found} ({pct:.1f}%) | "
                f"Nuevas: {processed_count}/{total_pending} | "
                f"Velocidad: {speed:.1f} imgs/sec | ETA: {eta_min:.1f} min",
                flush=True,
            )

    total_time = time.time() - start_time
    print("=" * 65)
    print(f"  RE-INDEXACIÓN COMPLETADA EXITOSAMENTE")
    print(f"  Total procesadas en este lote: {processed_count}")
    print(f"  Tiempo transcurrido: {total_time / 60.0:.2f} minutos ({processed_count / total_time:.1f} imgs/sec)")
    print("=" * 65)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Re-indexar miniaturas con SigLIP")
    parser.add_argument("--limit", type=int, default=None, help="Límite de imágenes para test")
    parser.add_argument("--batch", type=int, default=128, help="Tamaño de lote")
    args = parser.parse_args()

    run_reindexing(max_samples=args.limit, batch_size=args.batch)
