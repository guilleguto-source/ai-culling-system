import asyncio
import json
import logging
import os
import queue
import time
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.job_manager import job_manager
from services.settings_manager import load_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Culling"])

_job_state = job_manager

# Lazy singleton model instances
_face_detector = None
_gaze_estimator = None


def _get_face_detector():
    global _face_detector
    if _face_detector is None:
        try:
            from uniface import FaceAnalyzer
            _face_detector = FaceAnalyzer()
            logger.info("UniFace FaceAnalyzer cargado exitosamente.")
        except Exception as e:
            logger.error(f"Error inicializando UniFace FaceAnalyzer: {e}")
            _face_detector = None
    return _face_detector


def _get_gaze_estimator():
    global _gaze_estimator
    if _gaze_estimator is None:
        try:
            import urllib3
            import requests
            from uniface.gaze import MobileGaze
            urllib3.disable_warnings()
            _original_get = requests.get

            def _bypass_get(*args, **kwargs):
                kwargs['verify'] = False
                return _original_get(*args, **kwargs)

            requests.get = _bypass_get
            _gaze_estimator = MobileGaze()
            logger.info("MobileGaze cargado exitosamente.")
        except Exception as e:
            logger.error(f"Error inicializando MobileGaze: {e}")
            _gaze_estimator = None
    return _gaze_estimator


def _safe_getmtime(path) -> float:
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


# --- Schemas ---

class IngestRequest(BaseModel):
    directory: str
    mode: str = "cull_edit"   # "cull" (solo selección) | "cull_edit" (selección + edición)


# --- Helpers de inicio de trabajo ---

def _start_pipeline_job(data: IngestRequest, background_tasks: BackgroundTasks, mode: str):
    if not Path(data.directory).is_dir():
        raise HTTPException(status_code=400, detail=f"Directorio no válido: {data.directory}")

    job_id = f"job_{int(time.time())}"
    if not job_manager.start_job(job_id=job_id, mode=mode):
        raise HTTPException(status_code=400, detail="Ya hay un proceso de culling en curso")

    background_tasks.add_task(_run_culling_pipeline, data.directory, job_id, mode)
    return {"job_id": job_id, "status": "started", "mode": mode}


# --- Endpoints ---

@router.post("/cull")
def start_culling(request: IngestRequest, background_tasks: BackgroundTasks):
    """Inicia un trabajo de culling en segundo plano."""
    return _start_pipeline_job(request, background_tasks, "cull")


@router.post("/reselect")
def start_reselect(request: IngestRequest, background_tasks: BackgroundTasks):
    """Re-evalúa selectividad (Fase C) usando la caché de análisis (instantáneo)."""
    return _start_pipeline_job(request, background_tasks, "cull")


@router.post("/ingest")
def start_ingest(data: IngestRequest, background_tasks: BackgroundTasks):
    """Inicia el proceso de culling sobre un directorio de imágenes."""
    return _start_pipeline_job(data, background_tasks, data.mode)


@router.get("/status")
def get_status():
    """Retorna el estado actual del job de culling en progreso."""
    return job_manager.get_status()


@router.get("/events")
async def stream_events():
    """
    Transmite eventos de progreso y cambios de fase en tiempo real usando Server-Sent Events (SSE).
    """
    async def event_generator():
        q = job_manager.subscribe()
        try:
            while True:
                try:
                    event = q.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.1)
                    continue

                sanitized = _sanitize_for_json(event)
                payload = json.dumps(sanitized)
                yield f"data: {payload}\n\n"

                if event.get("type") in ("completed", "error"):
                    break
        except asyncio.CancelledError:
            pass
        finally:
            job_manager.unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


from utils.json_utils import safe_dumps

def _sanitize_for_json(obj: Any) -> Any:
    if obj is None:
        return None
    return json.loads(safe_dumps(obj))


@router.get("/results")
def get_results():
    """Retorna los resultados completos del último job completado."""
    status, results, stats = job_manager.get_results()
    if status not in ("completed", "error"):
        raise HTTPException(status_code=400, detail="No hay resultados disponibles aún")
    return {
        "results": _sanitize_for_json(results),
        "stats": _sanitize_for_json(stats),
    }



# --- Pipeline de Culling (Background Task) ---

def _run_culling_pipeline(directory: str, job_id: str, mode: str = "cull_edit"):
    """
    Ejecuta el pipeline completo de culling en segundo plano.
    Fases: Ingesta → Escena → Clustering → Calidad Técnica → Biométrica → Estética → Resultados
    """
    try:
        settings = load_settings()
        prefs = settings["selection_preferences"]

        from services.ingester import ingest_directory
        from services.scene_classifier import classify_scene, compute_saliency_region, SceneType
        from services.clustering import cluster_images, assign_cluster_representatives
        from services.cluster_gates import apply_technical_gates_explained
        from services.auto_crop import propose_crop, detect_horizon_angle, LEVEL_LIMITS
        from services import pre_edit
        from services.preset_manager import load_preset
        from services.technical_quality import evaluate_technical_quality, max_region_sharpness
        from services.aesthetic_assessment import evaluate_aesthetics_fast
        from services.taste_model import taste_model
        from services.settings_manager import get_blur_threshold, get_dbscan_epsilon
        import cv2

        blur_threshold = get_blur_threshold(settings)
        dbscan_epsilon = get_dbscan_epsilon(settings)

        # FASE 1: Ingesta y Miniaturas (NAS I/O)
        from services.ingester import get_ingest_tasks, process_single_image, ImageRecord, RAW_EXTENSIONS
        from services.analysis import analyze_photo, PhotoAnalysis
        from services.analysis_store import init_store, load_analysis, save_analysis
        from services.thumbnail_store import get_thumbnail_cache_paths, read_thumbnail_from_disk
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import concurrent.futures
        import io
        from PIL import Image

        t0_ingest = time.time()
        tasks = get_ingest_tasks(directory)
        total = len(tasks)
        
        job_manager.set_phase("Descargando y generando miniaturas...")

        pre_edit_prefs = prefs.get("pre_edit", {})
        pre_edit_enabled = pre_edit_prefs.get("enabled", True)

        records = []
        conn = init_store(directory)

        BATCH_SIZE = 200
        errors = 0

        # === FASE 1: INGESTA (Leer NAS -> Guardar Local) ===
        for batch_start in range(0, total, BATCH_SIZE):
            batch_tasks = tasks[batch_start:batch_start + BATCH_SIZE]
            to_process = []
            
            for path, linked_raw in batch_tasks:
                current_mtime = _safe_getmtime(path)
                ans = load_analysis(conn, str(path), current_mtime)
                ui_path, duel_path = get_thumbnail_cache_paths(str(path))
                
                # Check cache for both DB and thumbnails
                if ans and ui_path.exists() and duel_path.exists():
                    rec = ImageRecord(
                        path=str(path),
                        filename=path.name,
                        is_raw=path.suffix.lower() in RAW_EXTENSIONS,
                        linked_raw_path=linked_raw,
                        phash=ans.phash,
                        exif_datetime=ans.exif_datetime
                    )
                    records.append(rec)
                else:
                    to_process.append((path, linked_raw))

            if to_process:
                # max_workers=4 limits concurrent NAS reads
                with ThreadPoolExecutor(max_workers=4) as executor:
                    futures = {executor.submit(process_single_image, p, lr): p for p, lr in to_process}
                    for future in as_completed(futures):
                        try:
                            rec = future.result(timeout=60)
                        except Exception as e:
                            logger.error(f"Error ingesting file: {e}")
                            continue
                        records.append(rec)
                        if rec.error:
                            errors += 1

            job_manager.update_phase_progress("thumbnails", len(records), total)
            job_manager.update_progress(
                processed=len(records),
                total=total,
                progress=(len(records) / max(1, total)) * 30.0,
            )

        job_manager.complete_phase("thumbnails")

        # Sort records by path to ensure consistent order
        records.sort(key=lambda r: r.path)
        
        elapsed_ingest = time.time() - t0_ingest
        job_manager.set_stat("ingest", {
            "total": total,
            "success": total - errors,
            "errors": errors,
            "elapsed_seconds": round(elapsed_ingest, 1),
            "images_per_second": round(total / max(elapsed_ingest, 0.001), 1),
        })

        # === FASE 2: ANÁLISIS IA (Leer SSD Local) ===
        job_manager.set_phase("Analizando gestos, enfoque y composición...")
        t0_analysis = time.time()
        analyses: list[PhotoAnalysis] = []
        face_detector = _get_face_detector()
        gaze_estimator = _get_gaze_estimator()
        eye_session = None
        
        for global_idx, record in enumerate(records):
            current_mtime = _safe_getmtime(record.path) if not record.error else 0.0
            ans = load_analysis(conn, record.path, current_mtime)
            
            if record.error:
                ans = PhotoAnalysis(path=record.path, index=global_idx, is_raw=record.is_raw, error=record.error)
            elif not ans:
                # Cargar imagen desde caché local en SSD
                try:
                    duel_bytes = read_thumbnail_from_disk(record.path, "duel")
                    if duel_bytes:
                        img = Image.open(io.BytesIO(duel_bytes)).convert("RGB")
                        arr = np.array(img)
                        record.thumb_ai = arr
                    else:
                        logger.warning(f"No duel thumbnail found for {record.path}, analysis may fail.")
                except Exception as e:
                    logger.error(f"Error loading local thumbnail for {record.path}: {e}")

                exe = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                f = exe.submit(
                    analyze_photo,
                    index=global_idx,
                    record=record,
                    face_detector=face_detector,
                    gaze_estimator=gaze_estimator,
                    eye_session=eye_session,
                    blur_threshold=blur_threshold,
                    detect_closed_eyes=prefs.get("detect_closed_eyes", True),
                    pre_edit_enabled=pre_edit_enabled,
                )
                try:
                    ans = f.result(timeout=45)
                except concurrent.futures.TimeoutError:
                    logger.error(f"Timeout analyzing {record.path}")
                    ans = PhotoAnalysis(path=record.path, index=global_idx, is_raw=record.is_raw, error=True, sharpness=0.0)
                finally:
                    exe.shutdown(wait=False, cancel_futures=True)
                    
                if not ans.error:
                    save_analysis(conn, ans, current_mtime)
            else:
                ans.index = global_idx

            record.thumb_ai = None  # Free memory
            analyses.append(ans)

            job_manager.update_phase_progress("analysis", global_idx + 1, total)
            job_manager.update_progress(
                processed=global_idx + 1,
                total=total,
                progress=30.0 + ((global_idx + 1) / max(1, total)) * 40.0,
            )

        job_manager.complete_phase("analysis")

        # G3: Clasificador aprendido
        # UniFace v10: los conteos de faces ya vienen refinados desde analyze_photo
        portrait_count = sum(1 for a in analyses if a.scene_type in ('portrait', 'multi_portrait'))
        if portrait_count:
            # IMPORTANTE: NO guardar objetos PhotoAnalysis en set_stat - causaría error 500 en /status
            job_manager.set_stat("face_learned", {"fotos_con_rostros": portrait_count})
            logger.info(f"G3: {portrait_count} fotos con rostros detectados.")

        # FASE 3: Clustering y Detección de Duplicados Exactos
        job_manager.set_phase("Agrupando fotos por ráfaga y similitud...")
        job_manager.update_phase_progress("clustering", 0, 100)
        exact_duplicates_map = {}
        if prefs.get("detect_duplicates", True):
            from services.clustering import find_exact_duplicates
            exact_duplicates_map = find_exact_duplicates(
                [r.phash for r in records],
                [r.exif_datetime for r in records],
            )
            job_manager.set_stat("exact_duplicates", {"count": len(exact_duplicates_map)})

            clusters = cluster_images(
                [r.phash for r in records],
                [r.exif_datetime for r in records],
                [a.scene_type for a in analyses],
                epsilon_hash=dbscan_epsilon,
            )
            clusters = assign_cluster_representatives(clusters, [a.blur_score for a in analyses], [a.aesthetic_score for a in analyses])
        else:
            from services.clustering import ImageCluster
            clusters = [
                ImageCluster(i, analyses[i].scene_type, [i], i)
                for i in range(len(records))
            ]

        # FASE 3b: Embeddings visuales
        # FASE 3b: Embeddings CLIP (solo ráfagas multi-foto en lotes vectorizados)
        from services import embedding_service
        if embedding_service.is_available():
            job_manager.set_phase("Extrayendo vectores de estilo visual (CLIP)...")
            multi_indices = [
                idx for c in clusters if len(c.image_indices) > 1
                for idx in c.image_indices
            ]
            embedded = 0
            from services.thumbnail_store import read_thumbnail_from_disk
            from PIL import Image
            import io

            BATCH_SIZE = 16
            for chunk_start in range(0, len(multi_indices), BATCH_SIZE):
                chunk_indices = multi_indices[chunk_start:chunk_start + BATCH_SIZE]
                batch_items = []
                for idx in chunk_indices:
                    rec = records[idx]
                    if rec.error:
                        continue
                    thumb_ai = None
                    try:
                        duel_bytes = read_thumbnail_from_disk(rec.path, "duel")
                        if duel_bytes:
                            img = Image.open(io.BytesIO(duel_bytes)).convert("RGB")
                            thumb_ai = np.array(img)
                        else:
                            from services.ingester import _extract_raw_preview, _load_jpg, THUMB_AI_SIZE
                            p = Path(rec.path)
                            arr = _extract_raw_preview(p) if rec.is_raw else _load_jpg(p)
                            if arr is not None:
                                img = Image.fromarray(arr)
                                img.thumbnail(THUMB_AI_SIZE, Image.BILINEAR)
                                thumb_ai = np.array(img)
                    except Exception as e:
                        logger.error(f"Error cargando thumbnail para batch embedding: {e}")

                    batch_items.append((rec.path, thumb_ai))

                if batch_items:
                    res = embedding_service.embed_paths_batch(batch_items, batch_size=BATCH_SIZE)
                    embedded += sum(1 for vec in res if vec is not None)

                job_manager.update_progress(progress=80.0 + (min(len(multi_indices), chunk_start + BATCH_SIZE) / max(1, len(multi_indices))) * 10.0)

            job_manager.set_stat("embeddings", {"computed": embedded, "candidates": len(multi_indices)})
            logger.info(f"Embeddings listos: {embedded}/{len(multi_indices)} fotos en clusters.")

        job_manager.update_progress(progress=90.0)

        # FASE 3c: Pre-edición
        develop_by_idx: dict[int, dict] = {}
        preset_data = None
        if pre_edit_enabled:
            job_manager.set_phase("Aplicando filtros y pre revelados...")
            preset_path = pre_edit_prefs.get("preset_path") or ""
            if preset_path and Path(preset_path).exists():
                preset_data = load_preset(preset_path)
            order = sorted(range(len(records)),
                           key=lambda i: (records[i].exif_datetime or "~", i))
            signatures = [
                pre_edit.PhotoSignature(
                    index=i,
                    has_people=bool(analyses[i].face_bboxes),
                    wb=analyses[i].pre_wb,
                    skin_lum=analyses[i].pre_skin_lum,
                    global_lum=analyses[i].pre_global_lum,
                    clip_frac=analyses[i].pre_clip_frac,
                ) for i in order
            ]
            develop_by_idx = pre_edit.compute_pre_edits(
                signatures,
                bias=float(pre_edit_prefs.get("exposure_bias", 0.0)),
                preset_wb_bias=preset_data.wb_bias if preset_data else (0.0, 0.0),
                exposure_deadband=float(pre_edit_prefs.get("exposure_deadband", 0.15)),
                auto_wb=pre_edit_prefs.get("auto_wb", False),
            )
            job_manager.set_stat("pre_edit", {
                "preset": preset_data.name if preset_data else None,
                "photos": len(develop_by_idx),
            })

            from services.neural_lut import compute_lut_adjustments
            from services.tonal_rescue import suggest_tonal_adjustments, TonalReport
            from services import embedding_service as _emb_svc

            lut_cfg = pre_edit_prefs.get("neural_lut", {})
            lut_enabled = lut_cfg.get("enabled", True)
            lut_strength = float(lut_cfg.get("strength", 0.8))
            fallback_lut = lut_cfg.get("fallback_lut", "warm_golden")

            rescue_cfg = pre_edit_prefs.get("tonal_rescue", {})
            rescue_enabled = rescue_cfg.get("enabled", True)
            hi_thresh = float(rescue_cfg.get("highlights_threshold", 0.05))
            sh_thresh = float(rescue_cfg.get("shadows_threshold", 0.10))

            lut_applied_count = 0
            tonal_count = 0

            for i in develop_by_idx:
                emb = _emb_svc.embed_path(records[i].path, None) if _emb_svc.is_available() else None
                scene = analyses[i].scene_type if i < len(analyses) else None
                
                # 1. Neural 3D-LUT / Look aprendido (o fallback curado)
                if lut_enabled:
                    lut_adj = compute_lut_adjustments(
                        scene=scene,
                        embedding=emb,
                        strength=lut_strength,
                        fallback_lut=fallback_lut,
                    )
                    if lut_adj:
                        lut_applied_count += 1
                        for k, v in lut_adj.items():
                            develop_by_idx[i][k] = v

                # 2. Rescate Tonal automático en pre-revelado
                if rescue_enabled and i < len(analyses):
                    a = analyses[i]
                    clip_val = getattr(a, "pre_clip_frac", 0.0) or 0.0
                    glob_lum = getattr(a, "pre_global_lum", 0.18) or 0.18
                    report = TonalReport(
                        highlights_clip=clip_val,
                        shadows_clip=0.0,
                        midtone_lum=glob_lum,
                        has_faces=bool(getattr(a, "face_bboxes", None)),
                    )
                    tonal = suggest_tonal_adjustments(report, highlights_threshold=hi_thresh, shadows_threshold=sh_thresh)
                    if tonal:
                        tonal_count += 1
                        for k, v in tonal.items():
                            cur = develop_by_idx[i].get(k, 0)
                            try:
                                develop_by_idx[i][k] = max(-100, min(100, int(round(float(cur) + float(v)))))
                            except (ValueError, TypeError):
                                develop_by_idx[i][k] = v

            job_manager.set_stat("neural_lut", {"enabled": lut_enabled, "photos_applied": lut_applied_count})
            if tonal_count > 0:
                job_manager.set_stat("tonal_rescue", {"rescued_photos": tonal_count})

            # ARMONIZACIÓN POR CLUSTER
            for cluster in clusters:
                if len(cluster.image_indices) > 1:
                    c_exps, c_temps, c_tints = [], [], []
                    for idx in cluster.image_indices:
                        if idx in develop_by_idx:
                            c_exps.append(develop_by_idx[idx].get("Exposure2012", 0.0))
                            c_temps.append(develop_by_idx[idx].get("IncrementalTemperature", 0.0))
                            c_tints.append(develop_by_idx[idx].get("IncrementalTint", 0.0))
                    
                    if c_exps:
                        med_exp = float(np.median(c_exps))
                        med_temp = float(np.median(c_temps))
                        med_tint = float(np.median(c_tints))
                        
                        for idx in cluster.image_indices:
                            if idx in develop_by_idx:
                                develop_by_idx[idx]["Exposure2012"] = round(med_exp, 2)
                                develop_by_idx[idx]["IncrementalTemperature"] = round(med_temp, 1)
                                develop_by_idx[idx]["IncrementalTint"] = round(med_tint, 1)

        job_manager.complete_phase("clustering")

        # FASE 4a: Representative por cluster y score
        job_manager.set_phase("Seleccionando las mejores fotos y aplicando reglas...")
        job_manager.update_phase_progress("selection", 0, 100)
        ratings_map = settings["ratings_mapping"]
        results = []

        SHARP_REF = 500.0
        use_taste = taste_model.is_trained and embedding_service.is_available()
        rep_scores: dict[int, float] = {}
        all_scores: dict[int, float] = {}
        gate_reasons: dict[int, str] = {}
        decidido_por: dict[int, str] = {}
        margenes: dict[int, float] = {}

        for cluster in clusters:
            if not cluster.image_indices:
                continue

            candidates, motivos_gate = apply_technical_gates_explained(
                cluster.image_indices,
                [a.face_attrs for a in analyses],
                [a.face_sharpness for a in analyses],
                [a.face_bboxes for a in analyses],
            )
            gate_reasons.update(motivos_gate)

            for idx in cluster.image_indices:
                a = analyses[idx]
                blur_norm = min(1.0, a.blur_score / SHARP_REF)
                score = 0.6 * blur_norm + 0.4 * a.aesthetic_score
                if use_taste and len(cluster.image_indices) > 1:
                    emb = embedding_service.embed_path(records[idx].path, records[idx].thumb_ai)
                    if emb is not None:
                        score = taste_model.predict_score(emb)
                all_scores[idx] = score

            best_idx = max(candidates, key=lambda i: all_scores[i])
            
            if len(candidates) > 1:
                cands_sorted = sorted(candidates, key=lambda i: all_scores[i], reverse=True)
                margen = round(all_scores[cands_sorted[0]] - all_scores[cands_sorted[1]], 4)
                
                # FASE S: Refinamiento VLM
                if prefs.get("use_vlm_refinement", False) and margen < 0.05:
                    job_manager.set_phase("La IA está desempatando algunas ráfagas...")
                    from services.vlm_refiner import decide_winner
                    top_paths = [records[i].path for i in cands_sorted[:3]]
                    vlm_winner_idx = decide_winner(top_paths)
                    if vlm_winner_idx is not None:
                        best_idx = cands_sorted[vlm_winner_idx]
                        decidido_por[best_idx] = "vlm"

                # FASE 3.4: Desempate ELO
                if best_idx not in decidido_por and margen <= 0.02:
                    from services.elo_ranking import rank_burst_elo
                    ranked_elo, _, _ = rank_burst_elo(candidates, analyses, all_scores)
                    if ranked_elo:
                        best_idx = ranked_elo[0]
                        decidido_por[best_idx] = "elo"
            else:
                margen = 1.0
                
            cluster.representative_index = best_idx
            rep_scores[best_idx] = all_scores[best_idx]
            
            for idx in cluster.image_indices:
                margenes[idx] = margen

            if len(cluster.image_indices) > 1:
                if best_idx in decidido_por:
                    pass
                elif len(candidates) == 1 and motivos_gate:
                    decidido_por[best_idx] = "gate"
                elif use_taste:
                    decidido_por[best_idx] = "gusto"
                else:
                    decidido_por[best_idx] = "score"

        SEVERE_BLUR_FACTOR = 0.35
        trash_flags = [
            (a.blur_flag
             and a.blur_score < blur_threshold * SEVERE_BLUR_FACTOR
             and a.sharp_anywhere < blur_threshold)
            or pre_edit.is_trash_exposure(a.pre_global_lum, a.pre_clip_frac)
            for a in analyses
        ]

        # FASE 4b & 4c: Selectividad y Calificaciones
        from services.decision import apply_decision_logic
        results, demoted, final_selected, highlights = apply_decision_logic(
            records=records,
            analyses=analyses,
            clusters=clusters,
            rep_scores=rep_scores,
            all_scores=all_scores,
            gate_reasons=gate_reasons,
            decided_by=decidido_por,
            margins=margenes,
            trash_flags=trash_flags,
            prefs=prefs,
            settings=settings,
            develop_by_idx=develop_by_idx,
            exact_duplicates=exact_duplicates_map,
        )

        job_manager.set_stat("selectivity", {
            "mode": prefs.get("selectivity_target", "standard"),
            "singletons_demoted": len(demoted),
            "selected": len(final_selected),
            "highlighted": len(highlights),
        })

        # FASE 4d: Cobertura por persona
        if prefs.get("ensure_person_coverage", True):
            from services.face_identity import group_event_identities
            from services.decision import photos_for_group_coverage

            embs_por_foto = {
                a.index: a.face_identities for a in analyses if a.face_identities
            }
            if embs_por_foto:
                identidades = group_event_identities(embs_por_foto)
                promovidas = photos_for_group_coverage(
                    identidades, set(final_selected), all_scores)
                por_path = {r["path"]: r for r in results}
                target_frac = {"few": 0.30, "standard": 0.40, "more": 0.50}.get(prefs.get("selectivity_target", "standard"), 0.40)
                max_count = int(round(len(records) * (target_frac + 0.05)))
                
                # Contamos cuántas hay elegidas actualmente (ignorando las vinculadas en crudo añadidas al final de decision)
                current_selected = len(final_selected)
                aplicadas = 0
                
                for idx in promovidas:
                    if idx >= len(records):
                        continue
                    r = por_path.get(records[idx].path)
                    if r and r["label"] not in ("selected", "highlighted"):
                        r["label"] = "recommended"
                        r["stars"] = ratings_map.get("recommended", {}).get("stars", 1)
                        r["color"] = ratings_map.get("recommended", {}).get("color", "Amarillo")
                        r["reasons"] = ["✔ Cobertura (aparece poco en la selección)"]
                        aplicadas += 1
                        # Al ser "recomendada" no cuenta contra el techo máximo de "Elegidas"
                        # current_selected += 1
                        
                job_manager.set_stat("person_coverage", {
                    "identidades": len({i for ids in identidades.values() for i in ids}),
                    "promovidas": aplicadas,
                })

        # FASE 5: Exportar metadatos a XMP
        from services.undo_export import capture_previous_state
        backup_stats = capture_previous_state(
            directory, [r["path"] for r in results if not r.get("error")])
        job_manager.set_stat("backup", backup_stats)

        job_manager.complete_phase("selection")
        
        from services.xmp_exporter import export_results_to_xmp, export_results_to_xmp_generator
        job_manager.set_phase("Dando los toques finales...")
        overwrite_xmp = prefs.get("overwrite_xmp_ratings", False)
        
        # Uso del generador para poder actualizar el progreso de la fase de export
        xmp_gen = export_results_to_xmp_generator(
            [{**r, "crop": None, "develop": None} for r in results] if mode == "cull" else results,
            ratings_map,
            overwrite=overwrite_xmp,
            preset=None if mode == "cull" else preset_data
        )
        
        xmp_stats = {"written": 0, "skipped": 0, "errors": 0, "total": len(results)}
        for i, stat_update in enumerate(xmp_gen):
            if stat_update == "written":
                xmp_stats["written"] += 1
            elif stat_update == "skipped":
                xmp_stats["skipped"] += 1
            elif stat_update == "error":
                xmp_stats["errors"] += 1
            job_manager.update_phase_progress("export", i + 1, len(results))
        
        job_manager.complete_phase("export")
        job_manager.set_stat("xmp", xmp_stats)
        job_manager.set_stat("edits_applied", (mode != "cull"))

        from services.analysis_store import refresh_mtimes
        resellados = refresh_mtimes(conn, [r["path"] for r in results])
        logger.info(f"Análisis re-sellado tras el export XMP: {resellados} fotos.")

        from services.export_snapshot import save_snapshot
        save_snapshot(directory, results,
                      preset_path=preset_data.path if preset_data else "",
                      edits_applied=(mode != "cull"))

        job_manager.set_results(
            results=results,
            stats={
                "total_clusters": len(clusters),
                "total_images": len(records),
            }
        )

        logger.info(f"Job {job_id} completado: {len(results)} imágenes procesadas. XMP: {xmp_stats}")

    except Exception as e:
        logger.exception(f"Error en pipeline de culling: {e}")
        job_manager.set_error(str(e))
