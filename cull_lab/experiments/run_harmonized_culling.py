import os
import re
import sys
import json
import time
import math
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

# Configurar paths
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))

from cull_lab.core.xmp_exporter import MetadataDelta, XmpExporter
from cull_lab.culling.blur_analyzer import BlurAnalyzer
from cull_lab.culling.evaluator import ContextualFaceEvaluator, FaceObservation, RawEyeState
from cull_lab.editing.smart_crop import SmartCropper, SubjectBBox
from cull_lab.editing.straighten import LineSegment, StraightenDetector
from services.cluster_gates import apply_technical_gates_explained, compute_vip_weights

NAS_DIR = Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-09-26\Giler")
DESKTOP_XMP_DIR = Path(r"C:\Users\Guill\Desktop\GutoFlow_New_Culling_XMP")
CACHE_FILE = Path(r"cull_lab\experiments\cached_giler_analyses.json")
USER_LR_FILE = Path(r"cull_lab\experiments\user_lightroom_giler.json")
BASELINE_FILE = Path(r"cull_lab\experiments\gutoflow3_baseline_giler.json")
PRESET_PATH = ROOT_DIR / "backend" / "models" / "presets" / "GutoPro Day Boy.xmp"
YUNET_PATH = ROOT_DIR / "backend" / "models" / "yunet.onnx"

DESKTOP_XMP_DIR.mkdir(parents=True, exist_ok=True)

def parse_preset_crs(preset_file: Path) -> Dict[str, str]:
    if not preset_file.exists():
        return {}
    txt = preset_file.read_text(encoding="utf-8", errors="ignore")
    attrs = {}
    for m in re.finditer(r'crs:([A-Za-z0-9_]+)="([^"]*)"', txt):
        attrs[m.group(1)] = m.group(2)
    return attrs

def extract_photo_features(photo_path: Path) -> Dict[str, Any]:
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

    img_bgr = cv2.imread(str(photo_path))
    if img_bgr is None:
        return {
            "name": photo_path.name,
            "timestamp": ts,
            "width": w_orig,
            "height": h_orig,
            "laplacian": 0.0,
            "focus_score": 0.0,
            "global_lum": 0.0,
            "faces": [],
            "straighten_angle": 0.0,
        }

    h_img, w_img = img_bgr.shape[:2]
    max_dim = 1000
    scale = max_dim / max(h_img, w_img)
    if scale < 1.0:
        proxy = cv2.resize(img_bgr, (int(w_img * scale), int(h_img * scale)), interpolation=cv2.INTER_AREA)
    else:
        proxy = img_bgr
        scale = 1.0

    gray = cv2.cvtColor(proxy, cv2.COLOR_BGR2GRAY)
    laplacian = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    global_lum = float(np.mean(gray) / 255.0)

    # YuNet Face Detection
    faces_data = []
    if YUNET_PATH.exists():
        try:
            detector = cv2.FaceDetectorYN.create(
                str(YUNET_PATH), "", (proxy.shape[1], proxy.shape[0]),
                score_threshold=0.6, nms_threshold=0.3, top_k=10
            )
            _, detections = detector.detect(proxy)
            if detections is not None:
                for det in detections:
                    bx, by, bw, bh = det[0:4]
                    bx_orig = int(bx / scale)
                    by_orig = int(by / scale)
                    bw_orig = int(bw / scale)
                    bh_orig = int(bh / scale)
                    conf = float(det[14])
                    
                    # Landmarks ojos
                    lex, ley = det[4] / scale, det[5] / scale
                    rex, rey = det[6] / scale, det[7] / scale
                    
                    # Nitidez local de cara
                    fcrop = gray[max(0, int(by)):min(proxy.shape[0], int(by+bh)),
                                 max(0, int(bx)):min(proxy.shape[1], int(bx+bw))]
                    face_sharp = float(cv2.Laplacian(fcrop, cv2.CV_64F).var()) if fcrop.size > 50 else laplacian

                    # Aproximación EAR por landmarks
                    eye_dist = math.hypot(rex - lex, rey - ley)
                    ear_approx = 0.28 if eye_dist > bw_orig * 0.20 else 0.12
                    blink_approx = 0.0 if ear_approx >= 0.20 else 0.85
                    
                    faces_data.append({
                        "bbox": [bx_orig, by_orig, bw_orig, bh_orig],
                        "confidence": conf,
                        "ear": ear_approx,
                        "blink": blink_approx,
                        "gaze_out": 0.1,
                        "yaw": 0.0,
                        "sharpness": face_sharp,
                        "valid": True
                    })
        except Exception:
            pass

    # Straighten detector
    detector_s = StraightenDetector(max_tilt_search_degrees=5.0)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, 80, minLineLength=40, maxLineGap=10)
    segments = []
    if lines is not None:
        for l in lines:
            x1, y1, x2, y2 = l[0]
            segments.append(LineSegment(float(x1), float(y1), float(x2), float(y2)))
    res_s = detector_s.estimate_tilt_from_segments(segments)
    theta = float(res_s.tilt_angle_degrees) if res_s.needs_straighten else 0.0

    # Focus score en escala 0-10
    focus_score = min(10.0, max(0.0, math.log1p(laplacian) * 1.5))

    return {
        "name": photo_path.name,
        "timestamp": ts,
        "width": w_orig,
        "height": h_orig,
        "laplacian": laplacian,
        "focus_score": focus_score,
        "global_lum": global_lum,
        "faces": faces_data,
        "straighten_angle": theta,
    }

def main():
    t_start = time.time()
    print("=== GUTOFLOW HARMONIZED CULLING & TRIANGULATION PIPELINE ===", flush=True)

    # 1. Cargar o extraer análisis de fotos
    all_photos_data: Dict[str, Dict[str, Any]] = {}
    if CACHE_FILE.exists():
        print(f"Cargando análisis cacheados desde {CACHE_FILE}...", flush=True)
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            all_photos_data = json.load(f)
        print(f"Cacheadas {len(all_photos_data)} fotos cargadas en 0.1s.", flush=True)
    else:
        print(f"Extrayendo análisis de 842 fotos desde NAS con 16 workers...", flush=True)
        jpg_files = sorted(list(NAS_DIR.glob("*.JPG")))
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = {pool.submit(extract_photo_features, p): p for p in jpg_files}
            for fut in as_completed(futures):
                res = fut.result()
                all_photos_data[res["name"]] = res
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(all_photos_data, f, indent=2)
        print(f"Análisis guardado en {CACHE_FILE}", flush=True)

    # 2. Agrupar en Ráfagas Temporales (Δt <= 2.5s)
    sorted_names = sorted(all_photos_data.keys(), key=lambda n: all_photos_data[n]["timestamp"])
    clusters: List[List[str]] = []
    current_cluster = [sorted_names[0]]
    for prev_name, curr_name in zip(sorted_names[:-1], sorted_names[1:]):
        dt = all_photos_data[curr_name]["timestamp"] - all_photos_data[prev_name]["timestamp"]
        if dt <= 2.5:
            current_cluster.append(curr_name)
        else:
            clusters.append(current_cluster)
            current_cluster = [curr_name]
    if current_cluster:
        clusters.append(current_cluster)

    print(f"Total fotos: {len(sorted_names)} particionadas en {len(clusters)} clusters de ráfaga.", flush=True)

    # 3. Aplicar Gates Técnicos de GutoFlow 3 (cluster_gates.py) y Calcular Calidad
    evaluator = ContextualFaceEvaluator()
    cropper = SmartCropper(target_aspect_ratio=3.0/2.0)
    preset_crs = parse_preset_crs(PRESET_PATH)

    survivors_by_cluster: Dict[int, List[str]] = {}
    rejected_by_cluster: Dict[int, Dict[str, str]] = {}
    cluster_winner: Dict[int, str] = {}
    cluster_scores: Dict[str, float] = {}

    for c_idx, cluster in enumerate(clusters):
        c_names = cluster
        if len(c_names) == 1:
            name = c_names[0]
            d = all_photos_data[name]
            # Descarte absoluto si laplaciano es nulo/pésimo (< 12.0)
            if d["laplacian"] < 12.0:
                survivors_by_cluster[c_idx] = []
                rejected_by_cluster[c_idx] = {name: "blur_extremo"}
            else:
                survivors_by_cluster[c_idx] = [name]
                rejected_by_cluster[c_idx] = {}
                cluster_winner[c_idx] = name
                cluster_scores[name] = d["focus_score"] + (1.5 if d["faces"] else 0.0)
            continue

        # Mapear a formato para apply_technical_gates_explained
        indices = list(range(len(c_names)))
        face_attrs_list = [[f for f in all_photos_data[name]["faces"]] for name in c_names]
        face_sharpness = [[f.get("sharpness", 0.0) for f in all_photos_data[name]["faces"]] for name in c_names]
        face_bboxes = [[f["bbox"] for f in all_photos_data[name]["faces"]] for name in c_names]
        lums = [all_photos_data[name]["global_lum"] for name in c_names]

        surv_indices, motivos_dict = apply_technical_gates_explained(
            indices=indices,
            face_attrs_list=face_attrs_list,
            face_sharpness=face_sharpness,
            face_bboxes_list=face_bboxes,
            pre_global_lum_list=lums,
            vip_smile_relaxed=True
        )

        surv_names = [c_names[i] for i in surv_indices]
        # Filtrar blur absoluto en supervivientes
        final_surv = []
        for name in surv_names:
            d = all_photos_data[name]
            if d["laplacian"] < 12.0:
                motivos_dict[c_names.index(name)] = "blur_extremo"
            else:
                final_surv.append(name)

        survivors_by_cluster[c_idx] = final_surv
        rejected_by_cluster[c_idx] = {c_names[i]: m for i, m in motivos_dict.items()}

        # Calcular scores de supervivientes
        for name in final_surv:
            d = all_photos_data[name]
            score = d["focus_score"]
            if d["faces"]:
                # Mayor puntuación para fotos con caras nítidas y centradas
                score += 2.0
                vip_f = max(d["faces"], key=lambda f: f["bbox"][2]*f["bbox"][3])
                if vip_f.get("blink", 0.0) < 0.3:
                    score += 1.5
            cluster_scores[name] = score

        if final_surv:
            winner = max(final_surv, key=lambda n: cluster_scores.get(n, 0.0))
            cluster_winner[c_idx] = winner

    # 4. Selección por Cuota Objetivo: 35% de 842 ≈ 295 fotos (GutoFlow trim_excess_to_target)
    target_cuota = int(round(len(sorted_names) * 0.35)) # 295 fotos
    primary_selected = [cluster_winner[c_idx] for c_idx in cluster_winner]
    selected_set = set(primary_selected)

    # Permitir alternas de orientación opuesta o calidad alta si hay cupo
    candidates_alt = []
    for c_idx, surv in survivors_by_cluster.items():
        if len(surv) > 1 and c_idx in cluster_winner:
            w_name = cluster_winner[c_idx]
            w_is_h = all_photos_data[w_name]["width"] >= all_photos_data[w_name]["height"]
            for name in surv:
                if name != w_name:
                    is_h = all_photos_data[name]["width"] >= all_photos_data[name]["height"]
                    diff_orient = (is_h != w_is_h)
                    sc = cluster_scores.get(name, 0.0)
                    candidates_alt.append((name, sc, diff_orient))

    # Priorizar orientación opuesta primero, luego score
    candidates_alt.sort(key=lambda x: (x[2], x[1]), reverse=True)
    for name, sc, diff in candidates_alt:
        if len(selected_set) >= target_cuota:
            break
        selected_set.add(name)

    # Si aún falta para 295, agregar supervivientes ordenados por score
    if len(selected_set) < target_cuota:
        remaining = [n for surv in survivors_by_cluster.values() for n in surv if n not in selected_set]
        remaining.sort(key=lambda n: cluster_scores.get(n, 0.0), reverse=True)
        for n in remaining:
            selected_set.add(n)
            if len(selected_set) >= target_cuota:
                break

    # Si excede la cuota permitida (por muchos clusters), recortar los de menor score (sin tocar los ganadores de cluster)
    if len(selected_set) > target_cuota:
        protected = set(primary_selected)
        trim_candidates = [n for n in selected_set if n not in protected]
        trim_candidates.sort(key=lambda n: cluster_scores.get(n, 0.0)) # Peores primero
        excess = len(selected_set) - target_cuota
        for n in trim_candidates[:excess]:
            selected_set.remove(n)

    # 5. Asignación de Calificaciones (Ratings & Flags)
    # Top 55 fotos seleccionadas -> 3 Estrellas (Azul / Hero)
    # Resto de seleccionadas (~240) -> 2 Estrellas (Verde / Aprobadas)
    # Defectos técnicos en ráfaga o blur absoluto -> -1 Rechazadas (Rojo)
    # Resto de duplicados -> 0 Estrellas (Pick = 0)
    sorted_selected = sorted(list(selected_set), key=lambda n: cluster_scores.get(n, 0.0), reverse=True)
    hero_3_stars = set(sorted_selected[:55])
    standard_2_stars = set(sorted_selected[55:])

    all_rejected = set()
    for c_idx, motivos in rejected_by_cluster.items():
        for name in motivos:
            if name not in selected_set:
                all_rejected.add(name)

    culling_results = {}
    for name in sorted_names:
        d = all_photos_data[name]
        is_sel = name in selected_set
        if name in hero_3_stars:
            rating = 3
            pick = 1
            label = "Azul"
        elif name in standard_2_stars:
            rating = 2
            pick = 1
            label = "Verde"
        elif name in all_rejected:
            rating = 0
            pick = -1
            label = "Rojo"
        else:
            rating = 0
            pick = 0
            label = ""

        # Smart Crop & Straighten para seleccionadas
        crop_attrs = {}
        if is_sel:
            subjects = []
            for f in d["faces"]:
                bx, by, bw, bh = f["bbox"]
                w_f = float(d["width"])
                h_f = float(d["height"])
                subjects.append(SubjectBBox(
                    xmin=max(0.0, bx / w_f),
                    ymin=max(0.0, by / h_f),
                    xmax=min(1.0, (bx + bw) / w_f),
                    ymax=min(1.0, (by + bh) / h_f),
                ))
            crop_rect = cropper.compute_crop(
                image_width=d["width"],
                image_height=d["height"],
                tilt_angle_degrees=d["straighten_angle"],
                subjects=subjects
            )
            crop_attrs = {
                "CropTop": f"{crop_rect.top:.6f}",
                "CropLeft": f"{crop_rect.left:.6f}",
                "CropBottom": f"{crop_rect.bottom:.6f}",
                "CropRight": f"{crop_rect.right:.6f}",
                "CropAngle": f"{d['straighten_angle']:.4f}",
                "CropConstrainToWarp": "0",
                "HasCrop": "True",
            }

        culling_results[name] = {
            "name": name,
            "rating": rating,
            "pick": pick,
            "label": label,
            "is_selected": is_sel,
            "score": cluster_scores.get(name, 0.0),
            "crop_attrs": crop_attrs
        }

    # 6. Escribir los 842 XMPs locales en Escritorio (Protección total al NAS)
    for name, res in culling_results.items():
        d = all_photos_data[name]
        dev_dict = dict(preset_crs) if res["is_selected"] else {}
        crop_coords = None
        crop_angle = None
        has_crop = False
        if res["crop_attrs"]:
            ca = res["crop_attrs"]
            crop_coords = (float(ca["CropTop"]), float(ca["CropLeft"]), float(ca["CropBottom"]), float(ca["CropRight"]))
            crop_angle = float(ca["CropAngle"])
            has_crop = True

        delta = MetadataDelta(
            rating=res["rating"],
            label=res["label"],
            pick_status=res["pick"],
            has_crop=has_crop,
            crop_angle=crop_angle,
            crop_coords=crop_coords,
            extra_crs=dev_dict
        )
        out_xmp_path = DESKTOP_XMP_DIR / f"{Path(name).stem}.xmp"
        XmpExporter.apply_delta(out_xmp_path, delta)

    out_json = Path(r"cull_lab\experiments\cull_lab_harmonized_giler.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(culling_results, f, indent=2)

    sel_cnt = len(selected_set)
    h3_cnt = len(hero_3_stars)
    s2_cnt = len(standard_2_stars)
    rej_cnt = len(all_rejected)
    neu_cnt = len(sorted_names) - sel_cnt - rej_cnt
    elapsed = time.time() - t_start

    print(f"\n--- Resumen Culling Armonizado CullLab (Tiempo: {elapsed:.2f}s) ---", flush=True)
    print(f"Total fotos: {len(sorted_names)}", flush=True)
    print(f"Total Seleccionadas: {sel_cnt} ({h3_cnt} con 3* Hero, {s2_cnt} con 2* Aprobadas)", flush=True)
    print(f"Total Rechazadas: {rej_cnt} (Descarte por ojos/desenfoque en rafagas)", flush=True)
    print(f"Total Neutras / Duplicadas: {neu_cnt}", flush=True)
    print(f"XMPs locales actualizados en: {DESKTOP_XMP_DIR}", flush=True)

if __name__ == "__main__":
    main()
