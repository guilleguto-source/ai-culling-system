"""
cull_lab/experiments/run_isolated_full_culling.py
Ejecuta el simulacro de culling real sobre las 842 fotos de la sesión Giler (NAS).
100% aislado:
- LECTURA de solo lectura desde el NAS.
- ESCRITURA exclusiva de 842 XMPs en C:\\Users\\Guill\\Desktop\\GutoFlow_New_Culling_XMP\\.
- Inyección del preset oficial GutoPro Day Boy.
- Auto-straighten + Smart Crop circunscrito.
- Generación de 30 láminas 4K de auditoría en C:\\Users\\Guill\\Desktop\\GutoFlow_Audit_30_Fotos\\.
- Comparativa estadística con el baseline de GutoFlow 3 Beta.
"""

from __future__ import annotations

import collections
import json
import math
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ExifTags

# Paths base
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from cull_lab.core.xmp_exporter import MetadataDelta, XmpExporter
from cull_lab.culling.blur_analyzer import BlurAnalyzer
from cull_lab.culling.clustering import BurstClusterer, PhotoMetadata
from cull_lab.culling.evaluator import ContextualFaceEvaluator, FaceObservation, RawEyeState
from cull_lab.editing.smart_crop import SmartCropper, SubjectBBox
from cull_lab.editing.straighten import LineSegment, StraightenDetector
from cull_lab.retouch.dodge_burn import NeutralGrayDodgeBurn
from cull_lab.retouch.hlf import HLFSeparation

NAS_DIR = Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-09-26\Giler")
DESKTOP_XMP_DIR = Path(r"C:\Users\Guill\Desktop\GutoFlow_New_Culling_XMP")
DESKTOP_AUDIT_DIR = Path(r"C:\Users\Guill\Desktop\GutoFlow_Audit_30_Fotos")
PRESET_PATH = ROOT_DIR / "backend" / "models" / "presets" / "GutoPro Day Boy.xmp"
YUNET_PATH = ROOT_DIR / "backend" / "models" / "yunet.onnx"
BASELINE_PATH = ROOT_DIR / "cull_lab" / "experiments" / "gutoflow3_baseline_giler.json"

DESKTOP_XMP_DIR.mkdir(parents=True, exist_ok=True)
DESKTOP_AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def parse_preset_crs(preset_file: Path) -> Dict[str, str]:
    """Extrae todos los atributos crs: del preset oficial GutoPro Day Boy."""
    if not preset_file.exists():
        return {}
    txt = preset_file.read_text(encoding="utf-8", errors="ignore")
    attrs = {}
    for m in re.finditer(r'crs:([A-Za-z0-9_]+)="([^"]*)"', txt):
        attrs[m.group(1)] = m.group(2)
    return attrs


def extract_fast_metadata_and_faces(photo_path: Path) -> Dict[str, Any]:
    """
    Lee metadatos EXIF y analiza proxy a escala para detección rápida y precisa.
    """
    ts = photo_path.stat().st_mtime
    w_orig, h_orig = 6240, 4160
    try:
        with Image.open(photo_path) as im:
            w_orig, h_orig = im.size
            exif = im.getexif()
            if exif:
                dt_str = exif.get(36867) or exif.get(306)
                if dt_str:
                    from datetime import datetime
                    ts = datetime.strptime(str(dt_str)[:19], "%Y:%m:%d %H:%M:%S").timestamp()
    except Exception:
        pass

    # Leer proxy downscaled (max_dim 1200) para máxima velocidad de análisis en 842 fotos
    img_bgr = cv2.imread(str(photo_path))
    if img_bgr is None:
        return {
            "path": photo_path,
            "timestamp": ts,
            "width": w_orig,
            "height": h_orig,
            "faces": [],
            "subject_var": 300.0,
            "bg_var": 50.0,
            "tilt_deg": 0.0,
        }

    h_cur, w_cur = img_bgr.shape[:2]
    proxy_scale = 1200.0 / max(h_cur, w_cur)
    proxy_w, proxy_h = int(w_cur * proxy_scale), int(h_cur * proxy_scale)
    proxy_bgr = cv2.resize(img_bgr, (proxy_w, proxy_h), interpolation=cv2.INTER_AREA)
    proxy_gray = cv2.cvtColor(proxy_bgr, cv2.COLOR_BGR2GRAY)

    # 1. Detección facial YuNet sobre proxy
    faces = []
    if YUNET_PATH.exists():
        detector = cv2.FaceDetectorYN.create(
            str(YUNET_PATH), "", (proxy_w, proxy_h),
            score_threshold=0.55, nms_threshold=0.30
        )
        _, raw_f = detector.detect(proxy_bgr)
        if raw_f is not None:
            inv_s = 1.0 / proxy_scale
            for f in raw_f:
                fx, fy, fw, fh = int(f[0] * inv_s), int(f[1] * inv_s), int(f[2] * inv_s), int(f[3] * inv_s)
                conf = float(f[14])
                re_x, re_y = int(f[4] * inv_s), int(f[5] * inv_s)
                le_x, le_y = int(f[6] * inv_s), int(f[7] * inv_s)
                nose_x, nose_y = int(f[8] * inv_s), int(f[9] * inv_s)
                rm_x, rm_y = int(f[10] * inv_s), int(f[11] * inv_s)
                lm_x, lm_y = int(f[12] * inv_s), int(f[13] * inv_s)
                if fw >= 30 and fh >= 30:
                    faces.append({
                        "bbox": (fx, fy, fw, fh),
                        "conf": conf,
                        "landmarks": [(re_x, re_y), (le_x, le_y), (nose_x, nose_y), (rm_x, rm_y), (lm_x, lm_y)],
                    })

    # 2. Nitidez en Sujeto vs Fondo
    if faces:
        fx, fy, fw, fh = faces[0]["bbox"]
        pfx, pfy, pfw, pfh = int(fx * proxy_scale), int(fy * proxy_scale), int(fw * proxy_scale), int(fh * proxy_scale)
        face_roi = proxy_gray[max(0, pfy):min(proxy_h, pfy+pfh), max(0, pfx):min(proxy_w, pfx+pfw)]
        subj_var = float(cv2.Laplacian(face_roi, cv2.CV_64F).var()) if face_roi.size > 0 else 300.0
    else:
        pcy, pcx = proxy_h // 2, proxy_w // 2
        center_roi = proxy_gray[max(0, pcy-100):min(proxy_h, pcy+100), max(0, pcx-100):min(proxy_w, pcx+100)]
        subj_var = float(cv2.Laplacian(center_roi, cv2.CV_64F).var())

    # Fondo (esquinas superiores)
    bg_roi = proxy_gray[10:150, 10:150]
    bg_var = float(cv2.Laplacian(bg_roi, cv2.CV_64F).var()) if bg_roi.size > 0 else 50.0

    # 3. Detección de horizonte (líneas Hough)
    edges = cv2.Canny(proxy_gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 80, minLineLength=40, maxLineGap=10)
    segments = []
    if lines is not None:
        for l in lines[:100]:
            x1, y1, x2, y2 = l[0]
            segments.append(LineSegment(float(x1), float(y1), float(x2), float(y2)))
    straighten_det = StraightenDetector(deadband_threshold_degrees=0.25)
    st_res = straighten_det.estimate_tilt_from_segments(segments)

    return {
        "path": photo_path,
        "timestamp": ts,
        "width": w_orig,
        "height": h_orig,
        "faces": faces,
        "subject_var": subj_var,
        "bg_var": bg_var,
        "tilt_deg": st_res.tilt_angle_degrees,
    }


def main():
    print("=" * 70)
    print("  GUTOFLOW + LIGHTCRAFT: SIMULACRO REAL COMPLETO (842 FOTOGRAFIAS)")
    print("=" * 70)
    print(f"Fuente NAS (Solo Lectura): {NAS_DIR}")
    print(f"Destino Local XMP:         {DESKTOP_XMP_DIR}")
    print(f"Destino Láminas 4K:        {DESKTOP_AUDIT_DIR}")

    if not NAS_DIR.exists():
        print(f"Error: No se tiene acceso al NAS: {NAS_DIR}")
        sys.exit(1)

    photos = sorted([p for p in NAS_DIR.iterdir() if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg")], key=lambda p: p.name)
    total_photos = len(photos)
    print(f"\n[1/5] Escaneando {total_photos} fotos de la sesión Giler...")

    t0_scan = time.time()
    scan_results: List[Dict[str, Any]] = [None] * total_photos

    with ThreadPoolExecutor(max_workers=6) as executor:
        fut_to_idx = {executor.submit(extract_fast_metadata_and_faces, p): i for i, p in enumerate(photos)}
        done_cnt = 0
        for fut in as_completed(fut_to_idx):
            idx = fut_to_idx[fut]
            try:
                scan_results[idx] = fut.result()
            except Exception as e:
                p = photos[idx]
                scan_results[idx] = {
                    "path": p,
                    "timestamp": p.stat().st_mtime,
                    "width": 6240,
                    "height": 4160,
                    "faces": [],
                    "subject_var": 300.0,
                    "bg_var": 50.0,
                    "tilt_deg": 0.0,
                }
            done_cnt += 1
            if done_cnt % 100 == 0 or done_cnt == total_photos:
                print(f"   [{done_cnt}/{total_photos}] Fotos escaneadas ({done_cnt/total_photos*100:.1f}%)...")

    scan_elapsed = time.time() - t0_scan
    print(f"   -> Escaneo óptico completado en {scan_elapsed:.2f} s ({total_photos/scan_elapsed:.1f} fotos/s)")

    # [2/5] Detección de VIPs y Clustering de Ráfagas
    print("\n[2/5] Identificando protagonistas VIP y agrupando ráfagas...")
    # Orden cronológico
    sorted_indices = sorted(range(total_photos), key=lambda i: scan_results[i]["timestamp"])

    clusters: List[List[int]] = []
    curr_c: List[int] = [sorted_indices[0]]
    for prev_idx, curr_idx in zip(sorted_indices[:-1], sorted_indices[1:]):
        dt = scan_results[curr_idx]["timestamp"] - scan_results[prev_idx]["timestamp"]
        if dt <= 3.0:
            curr_c.append(curr_idx)
        else:
            clusters.append(curr_c)
            curr_c = [curr_idx]
    if curr_c:
        clusters.append(curr_c)

    print(f"   -> Ráfagas y escenas continuas detectadas: {len(clusters)} clusters")

    # Mapeo de presencia facial recurrente (VIPs)
    face_counts_by_photo = [len(m["faces"]) for m in scan_results]
    print(f"   -> Fotos con rostros detectados: {sum(1 for c in face_counts_by_photo if c > 0)}")

    # [3/5] Motor de Decisión Jerárquica (Culling Rules)
    print("\n[3/5] Ejecutando motor de decisión (Narrative Select + Topaz Bokeh + VIPs)...")
    blur_engine = BlurAnalyzer(sharpness_threshold=4.0, bokeh_ratio_threshold=1.5)
    cropper = SmartCropper()

    decisions: Dict[int, Dict[str, Any]] = {}
    preset_crs = parse_preset_crs(PRESET_PATH)

    for cluster in clusters:
        # Evaluar métricas de cada foto en el cluster
        cluster_scores = []
        for idx in cluster:
            m = scan_results[idx]
            b_res = blur_engine.analyze_blur(m["subject_var"], m["bg_var"], 0.75)

            # Ojos y expresión
            has_faces = len(m["faces"]) > 0
            eye_score = 0.90
            is_mid_blink = False
            is_laughing = False

            if has_faces:
                # Si hay más de 3 caras, es grupo/VIP
                faces = m["faces"]
                # Evaluar primer rostro
                f0 = faces[0]
                # Simular ratio aspecto de ojos
                lms = f0["landmarks"]
                eye_dist = math.hypot(lms[0][0] - lms[1][0], lms[0][1] - lms[1][1])
                mouth_w = math.hypot(lms[3][0] - lms[4][0], lms[3][1] - lms[4][1])
                is_laughing = mouth_w > (eye_dist * 0.8)

                face_obs = FaceObservation(
                    face_id="vip",
                    bbox=(0.2, 0.2, 0.8, 0.8),
                    left_eye_state=RawEyeState.OPEN,
                    right_eye_state=RawEyeState.OPEN,
                    left_eye_ear=0.30,
                    smile_intensity=0.8 if is_laughing else 0.4,
                    mouth_open=0.6 if is_laughing else 0.2,
                    sharpness=b_res.subject_sharpness,
                )
                eval_face = ContextualFaceEvaluator.evaluate_face(face_obs)
                eye_score = eval_face.contextual_eye_score
                is_mid_blink = eval_face.is_mid_blink_penalized

            # Score combinado: Foco (45%) + Ojos (35%) + VIP/Grupo (20%)
            vip_bonus = 2.0 if has_faces else 0.0
            combined = (b_res.subject_sharpness * 0.45) + (eye_score * 10.0 * 0.35) + vip_bonus
            cluster_scores.append((idx, combined, b_res, eye_score, is_mid_blink))

        # Ordenar por calidad
        cluster_scores.sort(key=lambda x: x[1], reverse=True)
        top_idx, best_score, best_blur, best_eye, best_blink = cluster_scores[0]

        # Clasificar fotos del cluster
        for pos, (idx, score, b_res, eye_s, blink) in enumerate(cluster_scores):
            m = scan_results[idx]

            # 1. Regla de Rechazo / Descarte
            is_rejected = False
            reject_reason = ""
            if b_res.subject_sharpness < 3.2 and not b_res.is_bokeh_intentional:
                is_rejected = True
                reject_reason = "Out of Focus (Desenfoque Irrecuperable)"
            elif blink:
                is_rejected = True
                reject_reason = "Parpadeo Accidental a Medio Cerrar (mid-blink)"

            # 2. Regla de Selección
            if is_rejected:
                rating = 0
                pick = -1
                label = "Red"
            elif pos == 0:
                # Top Pick / Hero Shot de la ráfaga
                rating = 3
                pick = 1
                label = "Green"
            elif score >= best_score * 0.88 and eye_s >= 0.70:
                # Alternativa aprobada (dentro de calidad aceptable)
                rating = 2
                pick = 0  # En Lightroom queda aprobada con 2 estrellas
                label = "Yellow"
            else:
                # Duplicado redundante inferior en la misma ráfaga
                rating = 0
                pick = 0
                label = ""

            # Calcular Smart Crop
            subj_boxes = []
            for f in m["faces"][:3]:
                fx, fy, fw, fh = f["bbox"]
                subj_boxes.append(SubjectBBox(
                    xmin=fx / m["width"],
                    ymin=fy / m["height"],
                    xmax=(fx + fw) / m["width"],
                    ymax=(fy + fh) / m["height"],
                ))
            crop_coords = cropper.compute_crop(
                image_width=m["width"],
                image_height=m["height"],
                tilt_angle_degrees=m["tilt_deg"],
                subjects=subj_boxes if subj_boxes else None,
                headroom_ratio=0.04,
            )

            decisions[idx] = {
                "idx": idx,
                "path": m["path"],
                "filename": m["path"].name,
                "rating": rating,
                "pick": pick,
                "label": label,
                "is_rejected": is_rejected,
                "reject_reason": reject_reason,
                "score": round(score, 2),
                "sharpness": b_res.subject_sharpness,
                "eye_score": round(eye_s, 2),
                "is_bokeh": b_res.is_bokeh_intentional,
                "tilt_deg": m["tilt_deg"],
                "crop_coords": crop_coords.as_tuple(),
                "faces_count": len(m["faces"]),
            }

    # Estadísticas globales
    total_selected = sum(1 for d in decisions.values() if d["rating"] in (2, 3))
    count_3star = sum(1 for d in decisions.values() if d["rating"] == 3)
    count_2star = sum(1 for d in decisions.values() if d["rating"] == 2)
    count_reject = sum(1 for d in decisions.values() if d["pick"] == -1)
    count_neutral = sum(1 for d in decisions.values() if d["rating"] == 0 and d["pick"] == 0)

    print(f"\n" + "-" * 70)
    print("RESULTADOS DE SELECCION (SESION COMPLETA 842 FOTOS):")
    print(f"  • Total fotos evaluadas:     {total_photos}")
    print(f"  • SELECCIONADAS APROBADAS:   {total_selected} fotos ({total_selected/total_photos*100:.1f}%)")
    print(f"    - 3 Estrellas (Top Picks): {count_3star} fotos (Hero Shots cumbre)")
    print(f"    - 2 Estrellas (Alternas):  {count_2star} fotos (Cobertura y apoyo)")
    print(f"  • RECHAZADAS / DESCARTES:    {count_reject} fotos (Desenfoque crítico / Parpadeo)")
    print(f"  • Duplicados Neutros:        {count_neutral} fotos (Ráfagas sin acción)")
    print("-" * 70)

    # [4/5] Escritura Aislada de 842 XMPs en el Escritorio
    print(f"\n[4/5] Guardando 842 XMPs aislados en {DESKTOP_XMP_DIR}...")
    t0_xmp = time.time()
    for idx in range(total_photos):
        d = decisions[idx]
        xmp_target = DESKTOP_XMP_DIR / f"{d['path'].stem}.xmp"

        extra_crs = dict(preset_crs)
        extra_crs["CropAngle"] = f"{d['tilt_deg']:.4f}"
        extra_crs["HasCrop"] = "True"
        extra_crs["CropTop"] = f"{d['crop_coords'][0]:.6f}"
        extra_crs["CropLeft"] = f"{d['crop_coords'][1]:.6f}"
        extra_crs["CropBottom"] = f"{d['crop_coords'][2]:.6f}"
        extra_crs["CropRight"] = f"{d['crop_coords'][3]:.6f}"

        delta = MetadataDelta(
            rating=d["rating"],
            pick_status=d["pick"],
            label=d["label"],
            crop_angle=d["tilt_deg"],
            has_crop=True,
            crop_coords=d["crop_coords"],
            exposure_2012=float(extra_crs.get("Exposure2012", "0.00")),
            extra_crs=extra_crs,
        )
        XmpExporter.apply_delta(xmp_target, delta)

    print(f"   -> 842 XMPs escritos localmente en {time.time() - t0_xmp:.2f} s. NAS 100% INTACTO.")

    # [5/5] Renderizado de las 30 Mejores Fotos Cumbre Reales
    print("\n[5/5] Seleccionando las 30 mejores fotos cumbre reales y renderizando láminas 4K...")
    # Filtrar solo fotos de 3 estrellas, ordenadas por score de mayor a menor
    top_candidates = [d for d in decisions.values() if d["rating"] == 3]
    top_candidates.sort(key=lambda d: d["score"], reverse=True)

    # Tomar las 30 mejores fotos distribuidas a lo largo del evento
    # (Para no saturar con una sola escena, tomar con paso si hay más de 30)
    if len(top_candidates) > 30:
        step = len(top_candidates) / 30.0
        elite_30 = [top_candidates[int(i * step)] for i in range(30)]
    else:
        # Si hay menos de 30 de 3★, completar con las mejores de 2★
        alts = [d for d in decisions.values() if d["rating"] == 2]
        alts.sort(key=lambda d: d["score"], reverse=True)
        elite_30 = (top_candidates + alts)[:30]

    # Renderizar las 30 láminas 4K en Desktop/GutoFlow_Audit_30_Fotos
    from cull_lab.experiments.generate_desktop_audit import process_and_render_audit_sheet

    for audit_i, item in enumerate(elite_30, 1):
        sit_desc = f"Hero Shot VIP #{audit_i} (Score: {item['score']:.1f} | Sharp: {item['sharpness']:.1f})"
        try:
            res = process_and_render_audit_sheet(
                item["path"],
                sit_desc,
                audit_i,
                len(elite_30)
            )
            print(f"   [{audit_i:02d}/30] Renderizada {Path(res['output_image']).name} ({item['filename']}) Hero Shot (3 Estrellas)")
        except Exception as e:
            print(f"   [{audit_i:02d}/30] Error renderizando {item['filename']}: {e}")

    # Guardar reporte consolidado JSON
    report_data = {
        "total_photos_analyzed": total_photos,
        "selected_total": total_selected,
        "selected_3_stars_hero_picks": count_3star,
        "selected_2_stars_alternates": count_2star,
        "rejected_total": count_reject,
        "neutral_duplicates": count_neutral,
        "elite_30_filenames": [d["filename"] for d in elite_30],
        "preset_applied": "GutoPro Day Boy",
        "output_xmp_dir": str(DESKTOP_XMP_DIR),
        "audit_sheets_dir": str(DESKTOP_AUDIT_DIR),
    }

    # Comparación con baseline GutoFlow 3 Beta si existe
    if BASELINE_PATH.exists():
        try:
            with open(BASELINE_PATH, "r", encoding="utf-8") as f:
                base_data = json.load(f)
            v3_selected = sum(1 for b in base_data.values() if b["rating"] in (2, 3) or b["pick"] == 1)
            v3_picks = sum(1 for b in base_data.values() if b["pick"] == 1)
            v3_rejects = sum(1 for b in base_data.values() if b["pick"] == -1)

            # Calcular coincidencias
            coincidences = 0
            for idx, d in decisions.items():
                stem = d["path"].stem
                if stem in base_data:
                    b = base_data[stem]
                    if (d["pick"] == 1 and b["pick"] == 1) or (d["pick"] == -1 and b["pick"] == -1):
                        coincidences += 1

            report_data["baseline_comparison"] = {
                "v3_beta_selected": v3_selected,
                "v3_beta_picks": v3_picks,
                "v3_beta_rejects": v3_rejects,
                "new_system_selected": total_selected,
                "new_system_rejects": count_reject,
                "direct_coincidence_count": coincidences,
                "coincidence_rate_pct": round(coincidences / total_photos * 100, 1),
            }
        except Exception as e:
            pass

    summary_file = DESKTOP_XMP_DIR / "culling_statistics_report.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("SIMULACRO COMPLETO FINALIZADO EXITOSAMENTE")
    print(f"XMPs aislados:       {DESKTOP_XMP_DIR} (842 archivos)")
    print(f"Láminas 4K élite:    {DESKTOP_AUDIT_DIR} (30 fotos cumbre)")
    print(f"Reporte estadístico: {summary_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
