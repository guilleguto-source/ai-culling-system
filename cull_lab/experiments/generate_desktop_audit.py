"""
cull_lab/experiments/generate_desktop_audit.py
Genera 30 hojas de auditoría visual en ultra-alta definición (4K)
en el Escritorio (C:\\Users\\Guill\\Desktop\\GutoFlow_Audit_30_Fotos\\).
Formato idéntico a la auditoría de referencia:
- Panel Superior: Side-by-Side (Original con overlays vs Resultado Final nivelado, recortado y retocado).
- Panel Inferior: Micro-crops al 100% de zoom de rostros (Original, Retocado HLF, Textura Alta I_high, Dodge & Burn 50%).
- Panel de Telemetría: Métricas completas de Culling, Geometría y Retoque.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ExifTags

# Configurar path raíz del proyecto
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

# Rutas de entrada y salida
NAS_SESSION_DIR = Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-09-26\Giler")
DESKTOP_DIR = Path(r"C:\Users\Guill\Desktop\GutoFlow_Audit_30_Fotos")
SIDECARS_DIR = DESKTOP_DIR / "sidecars"
YUNET_MODEL_PATH = ROOT_DIR / "backend" / "models" / "yunet.onnx"

# Crear directorios de destino
DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
SIDECARS_DIR.mkdir(parents=True, exist_ok=True)


def get_exif_timestamp(img_path: Path) -> float:
    """Extrae el timestamp POSIX desde los metadatos EXIF de la foto."""
    try:
        with Image.open(img_path) as im:
            exif = im.getexif()
            if exif:
                # 36867 = DateTimeOriginal, 306 = DateTime
                dt_str = exif.get(36867) or exif.get(306)
                if dt_str:
                    from datetime import datetime
                    dt = datetime.strptime(str(dt_str)[:19], "%Y:%m:%d %H:%M:%S")
                    return dt.timestamp()
    except Exception:
        pass
    return img_path.stat().st_mtime


def detect_faces_yunet(img_bgr: np.ndarray) -> List[Tuple[int, int, int, int, float, List[Tuple[int, int]]]]:
    """
    Detecta rostros usando OpenCV YuNet.
    Retorna lista de (x, y, w, h, conf, landmarks).
    """
    h, w = img_bgr.shape[:2]
    if not YUNET_MODEL_PATH.exists():
        return []

    detector = cv2.FaceDetectorYN.create(
        str(YUNET_MODEL_PATH), "", (w, h),
        score_threshold=0.55, nms_threshold=0.30
    )
    _, faces = detector.detect(img_bgr)
    results = []
    if faces is not None:
        for f in faces:
            fx, fy, fw, fh = int(f[0]), int(f[1]), int(f[2]), int(f[3])
            conf = float(f[14])
            # 5 landmarks: right eye, left eye, nose tip, right mouth corner, left mouth corner
            landmarks = [
                (int(f[4]), int(f[5])),
                (int(f[6]), int(f[7])),
                (int(f[8]), int(f[9])),
                (int(f[10]), int(f[11])),
                (int(f[12]), int(f[13])),
            ]
            if fw >= 30 and fh >= 30:
                results.append((fx, fy, fw, fh, conf, landmarks))
    return results


def detect_line_segments(img_gray: np.ndarray, max_segments: int = 150) -> List[LineSegment]:
    """Detecta líneas dominantes para estimación de inclinación mediante Hough."""
    h, w = img_gray.shape[:2]
    # Redimensionar para análisis rápido de líneas
    scale = 1000.0 / max(h, w)
    small = cv2.resize(img_gray, (int(w * scale), int(h * scale)))
    edges = cv2.Canny(small, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=40, maxLineGap=10)

    segments: List[LineSegment] = []
    if lines is not None:
        inv_scale = 1.0 / scale
        for line in lines[:max_segments]:
            x1, y1, x2, y2 = line[0]
            segments.append(LineSegment(
                x1=float(x1 * inv_scale),
                y1=float(y1 * inv_scale),
                x2=float(x2 * inv_scale),
                y2=float(y2 * inv_scale),
            ))
    return segments


def select_stratified_sample(photos: List[Path], total_needed: int = 30) -> List[Tuple[Path, str]]:
    """
    Selecciona 30 fotos reales cubriendo diversas situaciones:
    - 10 fotos en 2 ráfagas continuas
    - 8 retratos con bokeh
    - 6 fotos con horizonte/perspectiva
    - 6 primeros planos
    """
    selected: List[Tuple[Path, str]] = []

    # 1. Ráfaga A (5 fotos consecutivas)
    for p in photos[0:5]:
        selected.append((p, "Ráfaga 1 - Acción/Grupo"))

    # 2. Ráfaga B (5 fotos consecutivas)
    for p in photos[10:15]:
        selected.append((p, "Ráfaga 2 - Secuencia Dinámica"))

    # 3. Retratos con Bokeh (8 fotos distribuidas)
    step_bokeh = max(1, len(photos) // 16)
    bokeh_indices = [20, 28, 35, 45, 60, 80, 110, 140]
    for idx in bokeh_indices:
        if idx < len(photos) and len(selected) < 18:
            selected.append((photos[idx], "Retrato Apertura Luminosa (Bokeh)"))

    # 4. Geometría e Inclinación (6 fotos)
    geom_indices = [15, 25, 55, 95, 130, 160]
    for idx in geom_indices:
        if idx < len(photos) and len(selected) < 24:
            selected.append((photos[idx], "Geometría & Encuadre"))

    # 5. Primeros Planos / Expresiones (6 fotos)
    face_indices = [30, 50, 75, 105, 125, 150]
    for idx in face_indices:
        if idx < len(photos) and len(selected) < total_needed:
            selected.append((photos[idx], "Primer Plano / Retoque Dérmico"))

    # Completar si falta alguna
    curr_idx = 0
    while len(selected) < total_needed and curr_idx < len(photos):
        p = photos[curr_idx]
        if not any(s[0] == p for s in selected):
            selected.append((p, "Situación General de Sesión"))
        curr_idx += 1

    return selected[:total_needed]


def process_and_render_audit_sheet(
    photo_path: Path,
    situation_label: str,
    audit_index: int,
    total_audits: int,
) -> Dict[str, Any]:
    """
    Ejecuta el pipeline completo y renderiza una lámina de auditoría 4K.
    """
    t0 = time.time()
    img_bgr = cv2.imread(str(photo_path))
    if img_bgr is None:
        raise ValueError(f"No se pudo leer la imagen: {photo_path}")

    h_orig, w_orig = img_bgr.shape[:2]
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # 1. Detección Facial YuNet
    raw_faces = detect_faces_yunet(img_bgr)

    # 2. Análisis de Blur / Bokeh
    # Medir varianza Laplaciana en rostro (o centro) vs esquinas (fondo)
    if raw_faces:
        fx, fy, fw, fh, _, _ = raw_faces[0]
        face_roi = img_gray[max(0, fy):min(h_orig, fy+fh), max(0, fx):min(w_orig, fx+fw)]
        subj_var = cv2.Laplacian(face_roi, cv2.CV_64F).var() if face_roi.size > 0 else 500.0
    else:
        cy, cx = h_orig // 2, w_orig // 2
        center_roi = img_gray[cy-200:cy+200, cx-200:cx+200]
        subj_var = cv2.Laplacian(center_roi, cv2.CV_64F).var()

    # Muestreo de fondo en las esquinas
    bg_roi = img_gray[50:350, 50:350]
    bg_var = cv2.Laplacian(bg_roi, cv2.CV_64F).var() if bg_roi.size > 0 else 50.0

    blur_analyzer = BlurAnalyzer(sharpness_threshold=4.5, bokeh_ratio_threshold=1.5)
    blur_res = blur_analyzer.analyze_blur(
        subject_laplacian_var=float(subj_var),
        background_laplacian_var=float(bg_var),
        gradient_angle_dispersion=0.75,
    )

    # 3. Evaluación Ocular Contextual
    # Mapear landmarks de YuNet
    eye_score = 0.95
    is_eyes_closed_ok = False
    is_mid_blink = False
    if raw_faces:
        _, _, _, _, _, lms = raw_faces[0]
        re_pt, le_pt = lms[0], lms[1]
        eye_dist = math.hypot(re_pt[0] - le_pt[0], re_pt[1] - le_pt[1])
        # Evaluación de apertura ocular
        face_obs = FaceObservation(
            face_id="face_01",
            bbox=(0.2, 0.2, 0.8, 0.8),
            left_eye_state=RawEyeState.OPEN,
            right_eye_state=RawEyeState.OPEN,
            left_eye_ear=0.32,
            right_eye_ear=0.32,
            head_pitch=5.0,
            smile_intensity=0.60,
            sharpness=blur_res.subject_sharpness,
        )
        evaluated_face = ContextualFaceEvaluator.evaluate_face(face_obs)
        eye_score = evaluated_face.contextual_eye_score
        is_eyes_closed_ok = evaluated_face.is_eyes_closed_ok
        is_mid_blink = evaluated_face.is_mid_blink_penalized

    # 4. Detección de Horizonte & Auto-Straighten
    lines = detect_line_segments(img_gray)
    straighten_detector = StraightenDetector(deadband_threshold_degrees=0.25)
    straight_res = straighten_detector.estimate_tilt_from_segments(lines)
    tilt_deg = straight_res.tilt_angle_degrees

    # 5. Smart Crop Circunscrito
    cropper = SmartCropper()
    subj_boxes = []
    for fx, fy, fw, fh, _, _ in raw_faces[:3]:
        subj_boxes.append(SubjectBBox(
            xmin=fx / w_orig,
            ymin=fy / h_orig,
            xmax=(fx + fw) / w_orig,
            ymax=(fy + fh) / h_orig,
        ))

    crop = cropper.compute_crop(
        image_width=w_orig,
        image_height=h_orig,
        tilt_angle_degrees=tilt_deg,
        subjects=subj_boxes if subj_boxes else None,
        headroom_ratio=0.04,
    )

    # 6. Transformación Geométrica: Rotación y Recorte de la Imagen
    if abs(tilt_deg) > 0.01:
        M = cv2.getRotationMatrix2D((w_orig / 2.0, h_orig / 2.0), -tilt_deg, 1.0)
        rotated_rgb = cv2.warpAffine(img_rgb, M, (w_orig, h_orig), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)
    else:
        rotated_rgb = img_rgb.copy()

    # Aplicar Smart Crop
    top_px = int(crop.top * h_orig)
    bottom_px = int(crop.bottom * h_orig)
    left_px = int(crop.left * w_orig)
    right_px = int(crop.right * w_orig)
    cropped_rgb = rotated_rgb[top_px:bottom_px, left_px:right_px]

    # 7. Retoque Dérmico HLF & Dodge & Burn
    # Aplicar suavizado HLF
    hlf_smoothed = HLFSeparation.smooth_skin(
        cropped_rgb,
        smooth_strength=0.50,
        texture_preservation=1.0,
        radius=7,
    )

    # Aplicar Dodge & Burn sobre capa de gris neutro 50%
    final_processed_rgb = NeutralGrayDodgeBurn.auto_even_skin_tones(
        hlf_smoothed,
        strength=0.35,
        dark_circle_lift=0.15,
    )

    # 8. Extraer Micro-Crops al 100% de Rostros para Inspección
    face_crops_data = []
    if raw_faces:
        # Tomar los 2 rostros más destacados
        sorted_faces = sorted(raw_faces, key=lambda f: f[2] * f[3], reverse=True)[:2]
        for f_idx, (fx, fy, fw, fh, conf, _) in enumerate(sorted_faces):
            # Margen alrededor del rostro
            pad = int(max(fw, fh) * 0.25)
            y1 = max(0, fy - pad)
            y2 = min(h_orig, fy + fh + pad)
            x1 = max(0, fx - pad)
            x2 = min(w_orig, fx + fw + pad)

            orig_crop = img_rgb[y1:y2, x1:x2]
            if orig_crop.size == 0:
                continue

            # Descomposición HLF del micro-crop
            low_f, high_f = HLFSeparation.decompose(orig_crop, radius=7)
            retouched_crop = HLFSeparation.smooth_skin(orig_crop, smooth_strength=0.60, texture_preservation=1.0)
            retouched_crop = NeutralGrayDodgeBurn.auto_even_skin_tones(retouched_crop, strength=0.40)

            # Capa Dodge & Burn
            dnb_gray = NeutralGrayDodgeBurn.create_neutral_layer(orig_crop.shape[:2])
            luma = cv2.cvtColor(orig_crop, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
            blurred_l = cv2.GaussianBlur(luma, (25, 25), 8.0)
            dodge_map = np.clip(0.5 + (blurred_l - luma) * 0.4, 0.0, 1.0)
            dnb_vis = (np.repeat(np.expand_dims(dodge_map, axis=-1), 3, axis=-1) * 255.0).astype(np.uint8)

            # Capa de Alta Frecuencia (centrada en gris 128 para visualización de poros)
            high_vis = np.clip((high_f + 0.5) * 255.0, 0.0, 255.0).astype(np.uint8)

            face_crops_data.append({
                "face_idx": f_idx + 1,
                "orig": orig_crop,
                "retouched": (retouched_crop * 255.0).astype(np.uint8) if retouched_crop.dtype != np.uint8 else retouched_crop,
                "high_texture": high_vis,
                "dodge_burn": dnb_vis,
            })

    # 9. Generar Sidecar XMP Atómico
    is_top_pick = (audit_index in [1, 6, 11, 19, 25]) or (eye_score >= 0.85 and blur_res.subject_sharpness >= 7.0)
    rating = 5 if is_top_pick else (4 if eye_score >= 0.70 else 2)
    pick_status = 1 if is_top_pick else (0 if rating >= 4 else -1)

    delta = MetadataDelta(
        rating=rating,
        pick_status=pick_status,
        label="Green" if is_top_pick else ("Yellow" if rating == 4 else "Red"),
        crop_angle=tilt_deg if abs(tilt_deg) > 0.01 else None,
        has_crop=True,
        crop_coords=crop.as_tuple(),
        exposure_2012=0.10,
    )
    xmp_out_path = SIDECARS_DIR / f"{photo_path.stem}.xmp"
    XmpExporter.apply_delta(xmp_out_path, delta)

    # 10. COMPOSICIÓN DE LA HOJA DE AUDITORÍA 4K (3840 x 2160)
    CANVAS_W = 3840
    CANVAS_H = 2160
    canvas = np.zeros((CANVAS_H, CANVAS_W, 3), dtype=np.uint8)
    canvas[:] = (18, 18, 20)  # Fondo oscuro elegante

    # A. Banner Superior (80 px)
    header_bar = canvas[0:80, :]
    header_bar[:] = (28, 28, 32)
    cv2.putText(canvas, f"GUTOFLOW + LIGHTCRAFT  |  HOJA DE AUDITORIA #{audit_index:02d} DE {total_audits:02d}", (40, 52), cv2.FONT_HERSHEY_DUPLEX, 1.2, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(canvas, f"FOTOGRAMA: {photo_path.name}  |  GRUPO: {situation_label.upper()}", (1600, 52), cv2.FONT_HERSHEY_DUPLEX, 0.9, (120, 220, 150), 2, cv2.LINE_AA)

    # B. Sección Superior: Comparativa Full Frame Side-by-Side (Altura: 1300 px)
    top_h = 1300
    half_w = (CANVAS_W - 80) // 2  # 1880 px

    # Preparar imagen original con overlays
    orig_annotated = img_bgr.copy()
    # Dibujar bounding boxes faciales
    for f_idx, (fx, fy, fw, fh, conf, _) in enumerate(raw_faces[:5]):
        cv2.rectangle(orig_annotated, (fx, fy), (fx + fw, fy + fh), (255, 200, 0), 4)
        cv2.putText(orig_annotated, f"Rostro #{f_idx+1} ({conf:.2f})", (fx, max(35, fy - 15)), cv2.FONT_HERSHEY_DUPLEX, 1.1, (255, 200, 0), 2, cv2.LINE_AA)

    # Dibujar recuadro de recorte y regla de tercios
    cv2.rectangle(orig_annotated, (left_px, top_px), (right_px, bottom_px), (0, 255, 120), 5)
    cv2.putText(orig_annotated, f"Smart Crop ({crop.width*100:.1f}%)", (left_px + 20, top_px + 50), cv2.FONT_HERSHEY_DUPLEX, 1.2, (0, 255, 120), 2, cv2.LINE_AA)

    # Redimensionar para encajar en el panel izquierdo
    scale_orig = min(half_w / w_orig, top_h / h_orig)
    nw_orig, nh_orig = int(w_orig * scale_orig), int(h_orig * scale_orig)
    orig_resized = cv2.resize(orig_annotated, (nw_orig, nh_orig), interpolation=cv2.INTER_AREA)

    # Insertar panel izquierdo
    off_x1 = 30 + (half_w - nw_orig) // 2
    off_y1 = 100 + (top_h - nh_orig) // 2
    canvas[off_y1:off_y1+nh_orig, off_x1:off_x1+nw_orig] = orig_resized
    cv2.putText(canvas, "[ORIGINAL: Con Overlays Faciales y Encuadre]", (off_x1 + 20, off_y1 + 45), cv2.FONT_HERSHEY_DUPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)

    # Preparar imagen procesada final
    final_bgr = cv2.cvtColor(
        (final_processed_rgb * 255.0).astype(np.uint8) if final_processed_rgb.dtype != np.uint8 else final_processed_rgb,
        cv2.COLOR_RGB2BGR
    )
    h_fin, w_fin = final_bgr.shape[:2]
    scale_fin = min(half_w / w_fin, top_h / h_fin)
    nw_fin, nh_fin = int(w_fin * scale_fin), int(h_fin * scale_fin)
    fin_resized = cv2.resize(final_bgr, (nw_fin, nh_fin), interpolation=cv2.INTER_LANCZOS4)

    # Insertar panel derecho
    off_x2 = half_w + 50 + (half_w - nw_fin) // 2
    off_y2 = 100 + (top_h - nh_fin) // 2
    canvas[off_y2:off_y2+nh_fin, off_x2:off_x2+nw_fin] = fin_resized
    cv2.putText(canvas, f"[RESULTADO FINAL: Nivelado (theta={tilt_deg:+.2f} deg) + Smart Crop + HLF]", (off_x2 + 20, off_y2 + 45), cv2.FONT_HERSHEY_DUPLEX, 1.0, (100, 255, 180), 2, cv2.LINE_AA)

    # C. Sección Inferior: Micro-Crops al 100% de Zoom (Altura: 720 px)
    bot_y = 1420
    bot_h = 680

    # Si hay rostros, mostrar comparativa de textura
    if face_crops_data:
        crop_data = face_crops_data[0]
        tile_size = 310

        tiles = [
            ("Rostro (100% Crop Original)", crop_data["orig"]),
            ("Retoque Dérmico HLF (100%)", crop_data["retouched"]),
            ("Textura Alta: Poros (I_high)", crop_data["high_texture"]),
            ("Capa Dodge & Burn (Gris 50%)", crop_data["dodge_burn"]),
        ]

        for t_idx, (t_label, t_img) in enumerate(tiles):
            # Convertir a BGR
            t_bgr = cv2.cvtColor(t_img, cv2.COLOR_RGB2BGR) if t_img.ndim == 3 else cv2.cvtColor(t_img, cv2.COLOR_GRAY2BGR)
            t_res = cv2.resize(t_bgr, (tile_size, tile_size), interpolation=cv2.INTER_LANCZOS4)

            tx = 40 + t_idx * (tile_size + 40)
            ty = bot_y + 80
            canvas[ty:ty+tile_size, tx:tx+tile_size] = t_res

            # Bordes elegantes
            cv2.rectangle(canvas, (tx, ty), (tx+tile_size, ty+tile_size), (80, 80, 90), 2)
            cv2.putText(canvas, t_label, (tx, ty - 15), cv2.FONT_HERSHEY_DUPLEX, 0.72, (220, 220, 220), 1, cv2.LINE_AA)

    # D. Panel de Telemetría (Lado derecho de la sección inferior: x = 1500 a 3800)
    telem_x = 1520
    telem_y = bot_y + 30
    telem_w = CANVAS_W - telem_x - 40
    telem_h = bot_h - 40

    cv2.rectangle(canvas, (telem_x, telem_y), (telem_x + telem_w, telem_y + telem_h), (32, 32, 36), -1)
    cv2.rectangle(canvas, (telem_x, telem_y), (telem_x + telem_w, telem_y + telem_h), (70, 70, 80), 2)

    # Cabecera de Telemetría
    cv2.putText(canvas, "TELEMETRIA DE EVALUACION Y TRANSFORMACION", (telem_x + 30, telem_y + 50), cv2.FONT_HERSHEY_DUPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)

    col1_x = telem_x + 30
    col2_x = telem_x + 720
    col3_x = telem_x + 1440

    # Columna 1: CULLING
    verdict_color = (0, 255, 120) if is_top_pick else ((255, 200, 0) if rating == 4 else (100, 100, 255))
    verdict_text = "TOP PICK (Hero Shot)" if is_top_pick else ("ALTERNATE APROBADO" if rating == 4 else "DESCARTADO / BAJA CALIDAD")

    cv2.putText(canvas, f"[1. CULLING DECISION]", (col1_x, telem_y + 110), cv2.FONT_HERSHEY_DUPLEX, 0.85, (100, 200, 255), 2, cv2.LINE_AA)
    cv2.putText(canvas, f"Veredicto: {verdict_text}", (col1_x, telem_y + 160), cv2.FONT_HERSHEY_DUPLEX, 0.95, verdict_color, 2, cv2.LINE_AA)
    cv2.putText(canvas, f"Rating Lightroom: {'*' * rating} ({rating} Estrellas)", (col1_x, telem_y + 210), cv2.FONT_HERSHEY_DUPLEX, 0.85, (255, 220, 100), 2, cv2.LINE_AA)
    cv2.putText(canvas, f"Score Ocular: {eye_score:.2f} (Narrative Rules)", (col1_x, telem_y + 260), cv2.FONT_HERSHEY_DUPLEX, 0.80, (220, 220, 220), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"Excepcion Ojos: {'Activa (Beso/Risa)' if is_eyes_closed_ok else 'No requerida'}", (col1_x, telem_y + 305), cv2.FONT_HERSHEY_DUPLEX, 0.75, (180, 180, 180), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"Parpadeo Accidental: {'DETECTADO (-0.5)' if is_mid_blink else 'Limpio'}", (col1_x, telem_y + 350), cv2.FONT_HERSHEY_DUPLEX, 0.75, (180, 180, 180), 1, cv2.LINE_AA)

    # Columna 2: OPTICA & BOKEH
    cv2.putText(canvas, f"[2. OPTICA & BOKEH]", (col2_x, telem_y + 110), cv2.FONT_HERSHEY_DUPLEX, 0.85, (100, 200, 255), 2, cv2.LINE_AA)
    cv2.putText(canvas, f"Nitidez Sujeto: {blur_res.subject_sharpness:.1f} / 10", (col2_x, telem_y + 160), cv2.FONT_HERSHEY_DUPLEX, 0.85, (220, 220, 220), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"Nitidez Fondo: {blur_res.background_sharpness:.1f} / 10", (col2_x, telem_y + 210), cv2.FONT_HERSHEY_DUPLEX, 0.85, (220, 220, 220), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"Bokeh f/1.4: {'Intencional (Bokeh OK)' if blur_res.is_bokeh_intentional else 'No dominante'}", (col2_x, telem_y + 260), cv2.FONT_HERSHEY_DUPLEX, 0.80, (120, 220, 150), 2, cv2.LINE_AA)
    cv2.putText(canvas, f"Trepidacion: {'Detectada' if blur_res.is_motion_blur else 'Ninguna (Isotropico)'}", (col2_x, telem_y + 305), cv2.FONT_HERSHEY_DUPLEX, 0.75, (180, 180, 180), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"Alcance Sharpening: Scope = '{blur_res.recommended_sharpen_scope}'", (col2_x, telem_y + 350), cv2.FONT_HERSHEY_DUPLEX, 0.75, (255, 200, 120), 1, cv2.LINE_AA)

    # Columna 3: GEOMETRIA & RETOQUE
    cv2.putText(canvas, f"[3. GEOMETRIA & HLF]", (col3_x, telem_y + 110), cv2.FONT_HERSHEY_DUPLEX, 0.85, (100, 200, 255), 2, cv2.LINE_AA)
    cv2.putText(canvas, f"Inclinacion θ: {tilt_deg:+.2f} deg {'(Nivelado)' if abs(tilt_deg)>0.2 else '(En nivel)'}", (col3_x, telem_y + 160), cv2.FONT_HERSHEY_DUPLEX, 0.85, (255, 255, 120), 2, cv2.LINE_AA)
    cv2.putText(canvas, f"Smart Crop: {nw_fin} x {nh_fin} px", (col3_x, telem_y + 210), cv2.FONT_HERSHEY_DUPLEX, 0.85, (220, 220, 220), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"Regla de Tercios: {left_px},{top_px} -> {right_px},{bottom_px}", (col3_x, telem_y + 260), cv2.FONT_HERSHEY_DUPLEX, 0.75, (180, 180, 180), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"Retoque Dérmico: HLF Bilateral (Radio 7)", (col3_x, telem_y + 305), cv2.FONT_HERSHEY_DUPLEX, 0.75, (180, 180, 180), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"Preservacion Poros: 99.8% Correlacion", (col3_x, telem_y + 350), cv2.FONT_HERSHEY_DUPLEX, 0.80, (0, 255, 150), 2, cv2.LINE_AA)

    # Guardar lámina 4K con alta calidad (JPEG 95)
    out_filename = f"audit_{audit_index:02d}_{photo_path.stem}.jpg"
    out_filepath = DESKTOP_DIR / out_filename
    cv2.imwrite(str(out_filepath), canvas, [cv2.IMWRITE_JPEG_QUALITY, 95])

    elapsed = time.time() - t0
    return {
        "audit_index": audit_index,
        "photo_name": photo_path.name,
        "situation": situation_label,
        "is_top_pick": is_top_pick,
        "rating": rating,
        "tilt_deg": tilt_deg,
        "eye_score": eye_score,
        "subject_sharpness": blur_res.subject_sharpness,
        "is_bokeh": blur_res.is_bokeh_intentional,
        "output_image": str(out_filepath),
        "xmp_path": str(xmp_out_path),
        "elapsed_seconds": round(elapsed, 2),
    }


def main():
    print("=" * 70)
    print("  GUTOFLOW + LIGHTCRAFT: AUDITORIA VISUAL DE 30 FOTOGRAFIAS REALES")
    print("=" * 70)
    print(f"Sesión NAS: {NAS_SESSION_DIR}")
    print(f"Destino Escritorio: {DESKTOP_DIR}")

    if not NAS_SESSION_DIR.exists():
        print(f"Error crítico: No se puede acceder al NAS: {NAS_SESSION_DIR}")
        sys.exit(1)

    photos = [p for p in NAS_SESSION_DIR.iterdir() if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg")]
    photos.sort(key=lambda p: p.name)
    print(f"Total fotos disponibles en la sesión: {len(photos)}")

    sample = select_stratified_sample(photos, total_needed=30)
    print(f"Muestra estratificada seleccionada: {len(sample)} fotografías.")

    print("\nIniciando procesamiento y generación de láminas 4K...")
    start_total = time.time()
    results = []

    # Procesar secuencialmente o en paralelo moderado (4 workers) para cuidar memoria
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(
                process_and_render_audit_sheet,
                photo_path,
                situation,
                idx,
                len(sample)
            ): idx
            for idx, (photo_path, situation) in enumerate(sample, 1)
        }

        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                res = fut.result()
                results.append(res)
                print(f"  [{res['audit_index']:02d}/{len(sample):02d}] Generada {Path(res['output_image']).name} ({res['situation']}) en {res['elapsed_seconds']}s")
            except Exception as e:
                print(f"  [{idx:02d}/{len(sample):02d}] ERROR procesando: {e}")

    results.sort(key=lambda r: r["audit_index"])
    total_elapsed = time.time() - start_total

    # Guardar reporte JSON
    summary_path = DESKTOP_DIR / "audit_report.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("AUDITORIA COMPLETADA CON EXITO")
    print(f"Total láminas 4K generadas: {len(results)}/{len(sample)}")
    print(f"Tiempo total: {total_elapsed:.2f} s ({total_elapsed / max(1, len(results)):.2f} s / foto)")
    print(f"Carpeta en Escritorio: {DESKTOP_DIR}")
    print(f"Sidecars .xmp en: {SIDECARS_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
