"""
CullLab End-to-End Real-World Simulation & Latency Benchmark.
Simula una boda completa de 1,000 fotografías divididas en 120 ráfagas.
Ejecuta la tubería completa: discriminación de blur -> evaluación ocular -> clustering -> persistencia XMP.
"""

from __future__ import annotations

import os
import random
import sys
import tempfile
import time
from pathlib import Path

# Asegurar que el raíz de GUTOFLOW esté en sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from cull_lab.core.xmp_exporter import MetadataDelta, XmpDeltaAccumulator, XmpExporter
from cull_lab.culling.blur_analyzer import BlurAnalyzer
from cull_lab.culling.clustering import BurstClusterer, PhotoMetadata
from cull_lab.culling.evaluator import (
    ContextualFaceEvaluator,
    FaceObservation,
    RawEyeState,
)


def run_benchmark():
    print("=" * 70)
    print("  CULL-LAB: SIMULACIÓN DE CASO DE USO REAL (1,000 FOTOGRAFÍAS)")
    print("=" * 70)

    num_photos = 1000
    num_bursts = 120
    random.seed(42)

    # 1. Generar ráfagas simuladas realistas
    raw_photos_data = []
    base_time = 1700000000.0

    cur_time = base_time
    photo_idx = 1
    for burst_i in range(num_bursts):
        burst_len = random.randint(4, 15)
        # Contexto de ráfaga: ¿es beso? ¿es retrato f/1.4? ¿es risa?
        burst_is_kiss = (random.random() < 0.15)
        burst_is_f14 = (random.random() < 0.30)
        burst_is_laugh = (random.random() < 0.20)

        for b_j in range(burst_len):
            cur_time += random.uniform(0.10, 0.25)  # 4 a 10 fps
            photo_id = f"_DSC{photo_idx:04d}"
            raw_photos_data.append({
                "id": photo_id,
                "timestamp": cur_time,
                "is_kiss": burst_is_kiss,
                "is_f14": burst_is_f14,
                "is_laugh": burst_is_laugh,
            })
            photo_idx += 1
            if len(raw_photos_data) >= num_photos:
                break
        cur_time += random.uniform(5.0, 30.0)  # Pausa entre escenas
        if len(raw_photos_data) >= num_photos:
            break

    print(f"[1/4] Fotos simuladas preparadas: {len(raw_photos_data)} fotogramas.")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        blur_analyzer = BlurAnalyzer()
        clusterer = BurstClusterer()
        accumulator = XmpDeltaAccumulator(debounce_seconds=0.05)

        start_time = time.perf_counter()

        # 2. Análisis de Blur y Evaluación Facial
        cull_inputs: list[PhotoMetadata] = []
        for p in raw_photos_data:
            # Simular métricas ópticas
            if p["is_f14"]:
                s_var = random.uniform(900.0, 1800.0)
                bg_var = random.uniform(15.0, 45.0)  # Bokeh
            else:
                s_var = random.uniform(300.0, 1200.0)
                bg_var = s_var * random.uniform(0.7, 1.1)

            dispersion = random.uniform(0.6, 0.85)
            blur_diag = blur_analyzer.analyze_blur(s_var, bg_var, dispersion)

            # Simular ojos
            if p["is_kiss"]:
                eye_st = RawEyeState.CLOSED
            elif p["is_laugh"]:
                eye_st = RawEyeState.CLOSED
            elif random.random() < 0.08:
                eye_st = RawEyeState.MID_BLINK
            elif random.random() < 0.12:
                eye_st = RawEyeState.PARTIALLY_OPEN
            else:
                eye_st = RawEyeState.OPEN

            face_obs = FaceObservation(
                face_id=f"f_{p['id']}",
                bbox=(0.2, 0.2, 0.4, 0.5),
                left_eye_state=eye_st,
                right_eye_state=eye_st,
                is_kissing_context=p["is_kiss"],
                smile_intensity=0.85 if p["is_laugh"] else 0.2,
                mouth_open=0.6 if p["is_laugh"] else 0.1,
                sharpness=blur_diag.subject_sharpness,
            )
            eval_face = ContextualFaceEvaluator.evaluate_face(face_obs)

            cull_inputs.append(PhotoMetadata(
                id=p["id"],
                file_path=str(tmp_path / f"{p['id']}.ARW"),
                timestamp=p["timestamp"],
                focus_score=eval_face.focus_score,
                eye_score=eval_face.contextual_eye_score,
                aesthetic_score=random.uniform(4.0, 9.0),
            ))

        eval_done = time.perf_counter()
        print(f"[2/4] Análisis óptico y facial completado en {(eval_done - start_time)*1000:.2f} ms "
              f"({len(cull_inputs)/ (eval_done - start_time):.1f} fotos/segundo).")

        # 3. Clusterización de ráfagas y selección de Top Picks
        clusters = clusterer.cluster_photos(cull_inputs)
        cluster_done = time.perf_counter()
        print(f"[3/4] Agrupadas {len(clusters)} ráfagas con selección de Top Pick en "
              f"{(cluster_done - eval_done)*1000:.2f} ms.")

        # 4. Emisión atómica de deltas XMP
        total_top_picks = 0
        total_rejected = 0
        for cluster in clusters:
            for photo in cluster.photos:
                classification = cluster.classifications[photo.id]
                rating = 0
                label = None
                pick_status = 0

                if classification.is_top_pick:
                    rating = 5
                    label = "Green"
                    pick_status = 1
                    total_top_picks += 1
                elif classification.is_alternate:
                    rating = 4
                    label = "Yellow"
                    pick_status = 1
                elif classification.is_rejected:
                    rating = 1
                    label = "Red"
                    pick_status = -1
                    total_rejected += 1
                else:
                    # Duplicado no rechazado
                    rating = 2

                accumulator.record_delta(
                    photo.file_path,
                    MetadataDelta(rating=rating, label=label, pick_status=pick_status),
                )

        accumulator.flush_sync()
        accumulator.shutdown()

        total_done = time.perf_counter()
        total_elapsed = total_done - start_time
        ms_per_photo = (total_elapsed / len(cull_inputs)) * 1000

        print(f"[4/4] Persistencia atómica XMP completada.")
        print("-" * 70)
        print("RESULTADOS DE RENDIMIENTO Y PRECISIÓN:")
        print(f"  • Fotos procesadas:       {len(cull_inputs)}")
        print(f"  • Ráfagas detectadas:     {len(clusters)}")
        print(f"  • Top Picks elegidos:     {total_top_picks}")
        print(f"  • Fotos descartadas:      {total_rejected}")
        print(f"  • Tiempo total:           {total_elapsed:.3f} s")
        print(f"  • Latencia por foto:      {ms_per_photo:.2f} ms / foto  (Objetivo: < 10.0 ms)")
        print(f"  • Throughput global:      {len(cull_inputs)/total_elapsed:.1f} fotos / segundo")
        print("=" * 70)

        # Verificación de integridad: comprobar que se crearon los archivos XMP en disco
        xmp_count = len(list(tmp_path.glob("*.xmp")))
        assert xmp_count == len(cull_inputs), f"Se esperaban {len(cull_inputs)} XMPs, se encontraron {xmp_count}"
        print(f"VERIFICACIÓN: {xmp_count}/{len(cull_inputs)} archivos .xmp generados y validados con éxito.")


if __name__ == "__main__":
    run_benchmark()
