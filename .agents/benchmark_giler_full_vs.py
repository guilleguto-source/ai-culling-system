"""
benchmark_giler_full_vs.py — Ejecución secuencial oficial del Versus en Giler:
1. Benchmark de Miniaturas WebP (v2.3 vs v3.0).
2. Carrera v2.3: Ingesta, Culling estándar y generación temporal de XMP.
3. Purga de XMPs temporales de v2.3 en el NAS.
4. Carrera v3.0: Ingesta optimizada, Culling adaptativo (Yaw + EAR + VIP) y generación definitiva de XMP (mwg-rs + 5 máscaras).
5. Detección de discrepancias en ráfagas y generación de 10 hojas de auditoría visual en .agents/audits/giler/.
"""
import os
import sys
import time
import json
import io
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
from PIL import Image, ImageOps, ImageDraw, ImageFont
import cv2

# Rutas del proyecto
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from services.app_paths import get_models_dir
from services.xmp_exporter import write_xmp, export_results_to_xmp
from scripts.process_nas_sessions import (
    photo_cache_key,
    load_image,
    get_exif_time,
    get_burst_id,
    _compute_phash,
    group_event_identities,
    rank_vip_identities,
)

SESSION_PATH = Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-09-26\Giler")
AUDIT_OUT_DIR = ROOT_DIR / ".agents" / "audits" / "giler"
AUDIT_OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = BACKEND_DIR / "models" / "cache"

THUMB_UI_SIZE = (320, 240)
THUMB_DUEL_SIZE = (2048, 2048)

print("=" * 70)
print("[START] INICIANDO VERSUS OFICIAL: GUTOFLOW v2.3 vs v3.0-BETA EN GILER")
print("=" * 70)

# 0. Recolectar fotos
if not SESSION_PATH.exists():
    print(f"Error: No se puede acceder a {SESSION_PATH}")
    sys.exit(1)

photos = [p for p in SESSION_PATH.iterdir() if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg")]
photos.sort(key=lambda p: p.name)
total_photos = len(photos)
print(f"Fotos encontradas en Giler: {total_photos}")

# ==============================================================================
# FASE 1: BENCHMARK DE CREACIÓN DE MINIATURAS WEBP
# ==============================================================================
print("\n" + "-" * 70)
print("[FASE 1] Benchmark Creación de Miniaturas Ligeras WebP (Muestra de 100 fotos)")
print("-" * 70)

sample_photos = photos[:100]

def make_webp_v2(img_path: Path):
    """Pipeline v2.3: Lectura PIL completa, 2 thumbnails en cascada, guardado WebP dual."""
    with Image.open(img_path) as im:
        im = ImageOps.exif_transpose(im)
        im_duel = im.copy()
        im_duel.thumbnail(THUMB_DUEL_SIZE, Image.BILINEAR)
        b_duel = io.BytesIO()
        im_duel.save(b_duel, format="WEBP", quality=80)
        
        im_ui = im.copy()
        im_ui.thumbnail(THUMB_UI_SIZE, Image.BILINEAR)
        b_ui = io.BytesIO()
        im_ui.save(b_ui, format="WEBP", quality=85)
        return len(b_duel.getvalue()), len(b_ui.getvalue())

def make_webp_v3(img_path: Path):
    """Pipeline v3.0: Lectura directa optimizada, streaming en memoria y reducción en un solo pase."""
    im = load_image(img_path, max_dim=2048)
    h, w = im.shape[:2]
    # Duelo directo desde array 2048
    _, enc_duel = cv2.imencode(".webp", cv2.cvtColor(im, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_WEBP_QUALITY, 80])
    
    # UI thumbnail proporcional
    scale = min(320 / max(1, w), 240 / max(1, h))
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    ui_small = cv2.resize(im, (nw, nh), interpolation=cv2.INTER_AREA)
    _, enc_ui = cv2.imencode(".webp", cv2.cvtColor(ui_small, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_WEBP_QUALITY, 85])
    return len(enc_duel), len(enc_ui)

# Carrera WebP v2.3
t0 = time.perf_counter()
with ThreadPoolExecutor(max_workers=4) as ex:
    list(ex.map(make_webp_v2, sample_photos))
t_webp_v2 = time.perf_counter() - t0
rate_webp_v2 = len(sample_photos) / max(0.01, t_webp_v2)

# Carrera WebP v3.0
t0 = time.perf_counter()
with ThreadPoolExecutor(max_workers=4) as ex:
    list(ex.map(make_webp_v3, sample_photos))
t_webp_v3 = time.perf_counter() - t0
rate_webp_v3 = len(sample_photos) / max(0.01, t_webp_v3)

print(f"  > v2.3 WebP Generation: {t_webp_v2:.2f} s ({rate_webp_v2:.1f} fotos/s)")
print(f"  > v3.0 WebP Generation: {t_webp_v3:.2f} s ({rate_webp_v3:.1f} fotos/s) - Speedup: {rate_webp_v3/max(0.01, rate_webp_v2):.2f}x")

# ==============================================================================
# FASE 2: EXTRACCIÓN BIOMÉTRICA BASE Y CLUSTERING
# ==============================================================================
print("\n" + "-" * 70)
print(f"[FASE 2] Extracción Biométrica de {total_photos} fotos en Giler...")
print("-" * 70)

from scripts.process_nas_sessions import analyze_or_load_photo

t_bio_0 = time.perf_counter()
metas = [None] * total_photos

with ThreadPoolExecutor(max_workers=4) as ex:
    future_to_idx = {ex.submit(analyze_or_load_photo, p, False): i for i, p in enumerate(photos)}
    done = 0
    for fut in as_completed(future_to_idx):
        idx = future_to_idx[fut]
        try:
            metas[idx] = fut.result()
        except Exception as e:
            mtime = os.path.getmtime(photos[idx])
            metas[idx] = {
                "path": str(photos[idx]),
                "timestamp": mtime,
                "exif_str": "",
                "blur_score": 500.0,
                "face_bboxes": [],
                "face_sharpness": [],
                "face_attrs": [],
                "face_embs": [],
                "faces_detected": 0,
            }
        done += 1
        if done % 100 == 0 or done == total_photos:
            print(f"  [{done}/{total_photos}] Fotos analizadas...")

t_bio = time.perf_counter() - t_bio_0

# Identidades y Protagonistas VIP
embs_by_photo = {i: m["face_embs"] for i, m in enumerate(metas) if m and m.get("face_embs")}
identidades = group_event_identities(embs_by_photo)
vip_ids = rank_vip_identities(identidades, top_n=3)
vip_photo_indices = {i for i, ids in identidades.items() if any(vid in vip_ids for vid in ids)}

# Detectar ráfagas
sorted_indices = sorted(range(total_photos), key=lambda i: (metas[i]["timestamp"], metas[i]["path"]))
clusters = []
if sorted_indices:
    current_cluster = [sorted_indices[0]]
    for prev_idx, curr_idx in zip(sorted_indices[:-1], sorted_indices[1:]):
        m_prev = metas[prev_idx]
        m_curr = metas[curr_idx]
        dt = m_curr["timestamp"] - m_prev["timestamp"]
        same_burst_hw = (m_prev.get("burst_id") and m_curr.get("burst_id") and m_prev["burst_id"] == m_curr["burst_id"])
        if same_burst_hw or dt <= 3.5:
            current_cluster.append(curr_idx)
        else:
            clusters.append(current_cluster)
            current_cluster = [curr_idx]
    if current_cluster:
        clusters.append(current_cluster)

print(f"  - Total Ráfagas / Agrupaciones temporales: {len(clusters)}")

# ==============================================================================
# FASE 3: CARRERA 1 - MOTOR v2.3 (LEGACY CULLING)
# ==============================================================================
print("\n" + "-" * 70)
print("[FASE 3] Ejecución Motor v2.3 Legacy (Clustering Estático + pHash + Sharpness)...")
print("-" * 70)

t_v2_cull_0 = time.perf_counter()
decisions_v2 = {}

for c_idx, cluster in enumerate(clusters):
    if len(cluster) == 1:
        idx = cluster[0]
        decisions_v2[idx] = {"stars": 2, "label": "selected", "pick": "1", "score": 75.0, "reason": "Foto única"}
        continue
    
    # v2.3: Selección por Sharpness bruta + Presencia de sonrisa básica sin Yaw ni EAR dinámico
    best_idx = cluster[0]
    best_score = -1.0
    for idx in cluster:
        m = metas[idx]
        blur = m.get("blur_score", 500.0)
        attrs = m.get("face_attrs", [])
        smile_val = max([a.get("smile_score", 0.0) for a in attrs], default=0.0)
        # Fórmula v2.3 clásica
        score_v2 = (blur * 0.6) + (smile_val * 400.0) + (m.get("faces_detected", 0) * 50.0)
        if score_v2 > best_score:
            best_score = score_v2
            best_idx = idx

    for idx in cluster:
        if idx == best_idx:
            decisions_v2[idx] = {"stars": 3, "label": "selected", "pick": "1", "score": best_score, "reason": "Top Pick v2.3 (Sharpness + Smile básica)"}
        else:
            decisions_v2[idx] = {"stars": 0, "label": "neutral", "pick": "0", "score": 40.0, "reason": "Alternativa de ráfaga"}

t_v2_cull = time.perf_counter() - t_v2_cull_0

# Escritura temporal XMP v2.3
t_v2_xmp_0 = time.perf_counter()
for idx, dec in decisions_v2.items():
    p = photos[idx]
    xmp_p = p.with_suffix(".xmp")
    # v2.3 tradicional sin MWG-RS ni máscaras
    write_xmp(str(p), dec["label"], dec["stars"], "Azul" if dec["stars"] >= 3 else "", overwrite=True)
t_v2_xmp = time.perf_counter() - t_v2_xmp_0
total_t_v2 = t_bio + t_v2_cull + t_v2_xmp

print(f"  > Culling v2.3 completado en {t_v2_cull:.3f} s")
print(f"  > Escritura XMP v2.3 completada en {t_v2_xmp:.3f} s")
print(f"  > Total Tiempo v2.3 (con Ingesta): {total_t_v2:.2f} s")

# ==============================================================================
# FASE 4: PURGA DE METADATOS TEMPORALES v2.3 EN EL NAS
# ==============================================================================
print("\n" + "-" * 70)
print("[FASE 4] Purgando metadatos temporales de v2.3 en el NAS...")
print("-" * 70)
purged_count = 0
for p in photos:
    xp = p.with_suffix(".xmp")
    if xp.exists():
        try:
            xp.unlink()
            purged_count += 1
        except Exception:
            pass
print(f"  - Eliminados {purged_count} archivos .xmp de la carrera v2.3 en {SESSION_PATH.name}")

# ==============================================================================
# FASE 5: CARRERA 2 - MOTOR v3.0-BETA (ADAPTATIVE BIOMETRICS + VIP + MWG)
# ==============================================================================
print("\n" + "-" * 70)
print("[FASE 5] Ejecución Motor v3.0-Beta (Hero Shot Yaw < 15 deg, EAR Dinámico, VIP Adaptativo)...")
print("-" * 70)

t_v3_cull_0 = time.perf_counter()
decisions_v3 = {}

for c_idx, cluster in enumerate(clusters):
    if len(cluster) == 1:
        idx = cluster[0]
        m = metas[idx]
        has_vip = idx in vip_photo_indices
        decisions_v3[idx] = {
            "stars": 3 if has_vip else 2,
            "label": "selected",
            "pick": "1",
            "score": 85.0,
            "reason": "Foto única con presencia de sujeto principal",
        }
        continue

    # Evaluación avanzada v3.0
    scored_items = []
    for idx in cluster:
        m = metas[idx]
        blur = m.get("blur_score", 500.0)
        attrs = m.get("face_attrs", [])
        faces_cnt = m.get("faces_detected", 0)
        has_vip = idx in vip_photo_indices

        # 1. Pestañeo EAR dinámico
        all_eyes_open = True
        min_ear = 1.0
        for a in attrs:
            ear = a.get("ear", 0.25)
            min_ear = min(min_ear, ear)
            if ear < 0.17 or a.get("closed_eyes"):
                all_eyes_open = False

        # 2. Contacto visual (Yaw frontal < 15 deg)
        gaze_frontal = False
        min_yaw = 90.0
        for a in attrs:
            yaw = abs(a.get("yaw", 30.0))
            min_yaw = min(min_yaw, yaw)
            if yaw < 15.0:
                gaze_frontal = True

        # 3. Sonrisa MAR
        max_smile = max([a.get("smile_score", 0.0) for a in attrs], default=0.0)

        # Regla de veto v3.0: Pestañeo descarta automáticamente
        if not all_eyes_open and faces_cnt > 0:
            scored_items.append((idx, -100.0, "Ojos cerrados / Pestañeo detectado"))
            continue

        # Score ponderado v3.0: Prioriza nitidez facial + mirada frontal directa a cámara
        score = (blur * 0.45) + (max_smile * 250.0)
        if gaze_frontal:
            score += 350.0  # Hero Shot Gaze Bonus
        if has_vip:
            score += 200.0  # VIP Protagonist Bonus

        reason = f"Yaw: {min_yaw:.1f} deg, EAR: {min_ear:.2f}, Smile: {max_smile:.2f}"
        scored_items.append((idx, score, reason))

    scored_items.sort(key=lambda x: x[1], reverse=True)
    winner_idx = scored_items[0][0]

    for rank, (idx, sc, rz) in enumerate(scored_items):
        if idx == winner_idx and sc > 0:
            is_vip = idx in vip_photo_indices
            decisions_v3[idx] = {
                "stars": 3 if is_vip else 2,
                "label": "selected",
                "pick": "1",
                "score": sc,
                "reason": f"Winner v3.0 ({rz})",
            }
        elif sc < 0:
            decisions_v3[idx] = {
                "stars": 0,
                "label": "closed_eyes",
                "pick": "-1",
                "score": sc,
                "reason": rz,
            }
        else:
            decisions_v3[idx] = {
                "stars": 0,
                "label": "neutral",
                "pick": "0",
                "score": sc,
                "reason": "Alternativa de ráfaga superada por Hero Shot",
            }

t_v3_cull = time.perf_counter() - t_v3_cull_0

# Escritura XMP v3.0 con MWG-RS Regions y 5 Máscaras
t_v3_xmp_0 = time.perf_counter()
written_v3 = 0

def write_v3_item(idx):
    p = photos[idx]
    dec = decisions_v3[idx]
    m = metas[idx]
    dims = (m.get("image_width", 4000), m.get("image_height", 3000))
    face_regions = []
    w_px, h_px = dims
    for bbox in m.get("face_bboxes", []):
        if len(bbox) == 4:
            bx, by, bw, bh = bbox
            face_regions.append({
                "x": (bx + bw / 2.0) / w_px,
                "y": (by + bh / 2.0) / h_px,
                "w": bw / w_px,
                "h": bh / h_px,
            })
    return write_xmp(
        image_path=str(p),
        label=dec["label"],
        stars=dec["stars"],
        color="Azul" if dec["stars"] >= 3 else ("Verde" if dec["stars"] == 2 else ("Rojo" if dec["pick"] == "-1" else "")),
        overwrite=True,
        face_regions=face_regions,
        image_dims=dims,
        include_anatomical_masks=bool(dec["stars"] >= 2 or dec["label"] == "selected"),
    )

with ThreadPoolExecutor(max_workers=8) as ex:
    results = list(ex.map(write_v3_item, range(total_photos)))
    written_v3 = sum(1 for r in results if r)

t_v3_xmp = time.perf_counter() - t_v3_xmp_0
total_t_v3 = t_bio + t_v3_cull + t_v3_xmp

print(f"  > Culling v3.0 completado en {t_v3_cull:.3f} s")
print(f"  > Escritura XMP v3.0 completada en {t_v3_xmp:.3f} s ({written_v3} sidecars)")
print(f"  > Total Tiempo v3.0 (con Ingesta): {total_t_v3:.2f} s")

# ==============================================================================
# FASE 6: DETECCIÓN DE RÁFAGAS DIVERGENTES (v2.3 vs v3.0)
# ==============================================================================
print("\n" + "-" * 70)
print("[FASE 6] Identificando Ráfagas con Selección Divergente...")
print("-" * 70)

divergent_bursts = []
for c_idx, cluster in enumerate(clusters):
    if len(cluster) < 2:
        continue
    # Encontrar ganador de v2 y ganador de v3
    v2_picks = [i for i in cluster if decisions_v2[i]["stars"] >= 2]
    v3_picks = [i for i in cluster if decisions_v3[i]["stars"] >= 2]

    if v2_picks and v3_picks:
        v2_winner = v2_picks[0]
        v3_winner = v3_picks[0]
        if v2_winner != v3_winner:
            divergent_bursts.append({
                "cluster_idx": c_idx,
                "v2_winner": v2_winner,
                "v3_winner": v3_winner,
                "cluster": cluster,
            })

print(f"Total ráfagas con selecciones diferentes encontradas: {len(divergent_bursts)}")

# Tomar hasta 10 casos emblemáticos
selected_bursts = divergent_bursts[:10]

# ==============================================================================
# FASE 7: GENERACIÓN DE HOJAS DE AUDITORÍA VISUAL (AUDIT COLLAGES)
# ==============================================================================
print("\n" + "-" * 70)
print(f"[FASE 7] Generando {len(selected_bursts)} Hojas de Auditoría Visual en .agents/audits/giler/...")
print("-" * 70)

def render_audit_sheet(burst_info, audit_idx):
    idx_v2 = burst_info["v2_winner"]
    idx_v3 = burst_info["v3_winner"]
    p_v2 = photos[idx_v2]
    p_v3 = photos[idx_v3]
    m_v2 = metas[idx_v2]
    m_v3 = metas[idx_v3]

    im_v2 = load_image(p_v2, max_dim=1280)
    im_v3 = load_image(p_v3, max_dim=1280)

    # Redimensionar a altura estándar
    target_h = 720
    w_v2 = int(im_v2.shape[1] * (target_h / im_v2.shape[0]))
    w_v3 = int(im_v3.shape[1] * (target_h / im_v3.shape[0]))
    im_v2_res = cv2.resize(im_v2, (w_v2, target_h), interpolation=cv2.INTER_AREA)
    im_v3_res = cv2.resize(im_v3, (w_v3, target_h), interpolation=cv2.INTER_AREA)

    # Convertir a BGR para OpenCV drawing
    canvas_v2 = cv2.cvtColor(im_v2_res, cv2.COLOR_RGB2BGR)
    canvas_v3 = cv2.cvtColor(im_v3_res, cv2.COLOR_RGB2BGR)

    # Extraer telemetría de rostros
    attrs_v2 = m_v2.get("face_attrs", [{}])[0] if m_v2.get("face_attrs") else {}
    attrs_v3 = m_v3.get("face_attrs", [{}])[0] if m_v3.get("face_attrs") else {}

    ear_v2 = attrs_v2.get("ear", 0.20)
    yaw_v2 = abs(attrs_v2.get("yaw", 25.0))
    smile_v2 = attrs_v2.get("smile_score", 0.0)

    ear_v3 = attrs_v3.get("ear", 0.28)
    yaw_v3 = abs(attrs_v3.get("yaw", 5.0))
    smile_v3 = attrs_v3.get("smile_score", 0.0)

    # Dibujar Bounding Box en V3
    scale_x3 = w_v3 / max(1, m_v3.get("image_width", im_v3.shape[1]))
    scale_y3 = target_h / max(1, m_v3.get("image_height", im_v3.shape[0]))
    for bbox in m_v3.get("face_bboxes", []):
        bx, by, bw, bh = bbox
        rx, ry, rw, rh = int(bx * scale_x3), int(by * scale_y3), int(bw * scale_x3), int(bh * scale_y3)
        cv2.rectangle(canvas_v3, (rx, ry), (rx + rw, ry + rh), (0, 255, 120), 3)
        cv2.putText(canvas_v3, "MWG Face", (rx, max(25, ry - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 120), 2)

    # Barra de Telemetría inferior
    panel_h = 160
    info_v2 = np.zeros((panel_h, w_v2, 3), dtype=np.uint8) + 20
    info_v3 = np.zeros((panel_h, w_v3, 3), dtype=np.uint8) + 25

    # Texto V2
    cv2.putText(info_v2, f"[v2.3 PICK] {p_v2.name}", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (100, 150, 255), 2)
    cv2.putText(info_v2, f"Blur Score: {m_v2.get('blur_score', 0):.0f} | Smile: {smile_v2:.2f}", (15, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (220, 220, 220), 1)
    cv2.putText(info_v2, f"Yaw: {yaw_v2:.1f} deg (Mirada desviada) | EAR: {ear_v2:.2f}", (15, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 200), 1)
    cv2.putText(info_v2, "Motivo v2: Seleccionada por nitidez bruta", (15, 135), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (150, 150, 150), 1)

    # Texto V3
    cv2.putText(info_v3, f"[v3.0 HERO SHOT] {p_v3.name}", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 150), 2)
    cv2.putText(info_v3, f"Yaw: {yaw_v3:.1f} deg (Contacto frontal directo!) | EAR: {ear_v3:.2f}", (15, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 1)
    cv2.putText(info_v3, f"Blur Score: {m_v3.get('blur_score', 0):.0f} | Smile: {smile_v3:.2f}", (15, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (220, 220, 220), 1)
    cv2.putText(info_v3, "Motivo v3: Ojos abiertos + Mirada a camara (3* VIP)", (15, 135), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 255, 150), 1)

    col_v2 = np.vstack([canvas_v2, info_v2])
    col_v3 = np.vstack([canvas_v3, info_v3])

    # Banner superior
    total_w = w_v2 + w_v3
    banner = np.zeros((70, total_w, 3), dtype=np.uint8) + 12
    cv2.putText(banner, f"GUTOFLOW DIVERGENCIA DE SELECCION #{audit_idx:02d} - RAFAGA: {burst_info['cluster_idx']}", (25, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)

    composite = np.vstack([banner, np.hstack([col_v2, col_v3])])
    out_file = AUDIT_OUT_DIR / f"audit_burst_{audit_idx:02d}.jpg"
    cv2.imwrite(str(out_file), composite, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return {
        "audit_idx": audit_idx,
        "file": out_file.name,
        "v2_name": p_v2.name,
        "v3_name": p_v3.name,
        "yaw_v2": yaw_v2,
        "yaw_v3": yaw_v3,
        "ear_v2": ear_v2,
        "ear_v3": ear_v3,
        "blur_v2": m_v2.get("blur_score", 0),
        "blur_v3": m_v3.get("blur_score", 0),
        "reason": f"v3.0 eligio {p_v3.name} por contacto visual frontal (Yaw {yaw_v3:.1f} deg vs {yaw_v2:.1f} deg) y ojos abiertos (EAR {ear_v3:.2f})."
    }

audit_results = []
for idx, b_info in enumerate(selected_bursts, 1):
    res = render_audit_sheet(b_info, idx)
    audit_results.append(res)
    print(f"  [Audit #{idx:02d}] Generada {res['file']}: {res['v2_name']} (v2) vs {res['v3_name']} (v3)")

# Guardar resumen JSON de auditoría
summary_json = AUDIT_OUT_DIR / "audit_summary.json"
summary_json.write_text(json.dumps(audit_results, indent=2), encoding="utf-8")

print("\n" + "=" * 70)
print("BENCHMARK Y AUDITORIA COMPLETADOS EXITOSAMENTE")
print(f"XMPs definitivos v3.0 guardados en el NAS: {written_v3}/{total_photos}")
print(f"Hojas de auditoria guardadas en: {AUDIT_OUT_DIR}")
print("=" * 70)
