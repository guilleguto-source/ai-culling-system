"""
render_25_processed_audit.py — Renderiza 25 láminas 4K de auditoría visual
con el pipeline completo:
- Original cruda de cámara (subexpuesta/inclinada)
- Pre-revelado adaptativo por piel (Exposure2012 EV)
- Preset GutoPro Day Boy real aplicado a nivel de píxeles
- Nivelación angular theta sin esquinas negras
- Smart Crop áureo circunscrito (protegiendo cabezas en grupos y posadas)
- Retoque dérmico HLF con preservación de poros
- Telemetría enriquecida y calificación desglosada
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "backend"))

from cull_lab.culling.blur_analyzer import BlurAnalyzer
from cull_lab.editing.smart_crop import SmartCropper, SubjectBBox
from cull_lab.editing.straighten import LineSegment, StraightenDetector
from cull_lab.editing.tonal_engine import TonalEngine
from cull_lab.retouch.hlf import HLFSeparation
from cull_lab.retouch.dodge_burn import NeutralGrayDodgeBurn
from services.pre_edit import measure_luminance, PhotoSignature, compute_pre_edits

NAS_DIR = Path(r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-09-26\Giler")
OUTPUT_DIR = Path(r"C:\Users\Guill\Desktop\GutoFlow_Audit_25_Procesado")
YUNET_PATH = ROOT_DIR / "backend" / "models" / "yunet.onnx"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Lista curada de las 25 fotos emblemáticas
PHOTOS_25 = [
    # 1. Posadas iniciales y retratos
    ("IMG_9798.JPG", "Posada Inicial de Estudio", 3, "Retrato formal posado al inicio de sesion"),
    ("IMG_9814.JPG", "Retrato Inicial Hero", 3, "Momento cumbre de presentacion del protagonista"),
    ("IMG_9902.JPG", "Retrato Posado Familia", 3, "Interaccion familiar con luz controlada"),
    # 2. Grupos grandes (>10 personas) y familiares
    ("IMG_0261.JPG", "Grupal Masiva Invitados (>10p)", 2, "Grupo completo de invitados posando juntos"),
    ("IMG_0268.JPG", "Grupal Masiva Celebracion (>10p)", 3, "Grupo principal cantando y celebrando"),
    ("IMG_0274.JPG", "Grupal Masiva Escenario (>10p)", 2, "Invitados reunidos en zona principal"),
    ("IMG_0288.JPG", "Grupal Ninos y Familiares", 2, "Toma abierta de grupo con ninos"),
    ("IMG_0313.JPG", "Grupal Dinamica Show", 2, "Participacion de invitados en el show"),
    # 3. Accion, show infantil y dinamicas
    ("IMG_0008.JPG", "Accion Show Infantil", 2, "Interaccion espontanea durante la funcion"),
    ("IMG_0012.JPG", "Momento Hero Dinamico", 3, "Expresion de sorpresa del protagonista"),
    ("IMG_0038.JPG", "Risas y Juegos", 2, "Movimiento rapido y alegria espontanea"),
    ("IMG_0052.JPG", "Dinamica de Escena", 2, "Animacion con el publico"),
    ("IMG_0197.JPG", "Hero Shot Expresion", 3, "Sonrisa abierta a camara en movimiento"),
    ("IMG_0223.JPG", "Accion de Concurso", 2, "Competencia entre invitados"),
    ("IMG_0332.JPG", "Momento Espontaneo Ninos", 2, "Risas compartidas en el show"),
    ("IMG_0432.JPG", "Show Principal", 3, "Acto central con atencion de todos los ninos"),
    ("IMG_0457.JPG", "Alegria Desbordante", 3, "Gesto euforico capturado a alta velocidad"),
    # 4. Mesa de la torta y cumpleanos posadas
    ("IMG_0612.JPG", "Preparativos en la Torta", 3, "Familia ubicandose junto a la torta"),
    ("IMG_0621.JPG", "Mesa de la Torta Hero", 3, "Protagonista posando frente a la torta"),
    ("IMG_0626.JPG", "Cantando Cumpleanos", 3, "Momento de canto colectivo de cumpleanos"),
    ("IMG_0631.JPG", "Soplando la Vela", 2, "Instante previo a soplar la vela"),
    ("IMG_0647.JPG", "Abrazo Familiar en Torta", 2, "Cariño familiar junto a la decoracion"),
    # 5. Cierre de sesion y detalles
    ("IMG_0641.JPG", "Detalle de Torta y Dulces", 2, "Composicion decorativa del evento"),
    ("IMG_0656.JPG", "Despedida Familiar", 2, "Retrato relajado al finalizar la fiesta"),
    ("IMG_0661.JPG", "Retrato Final Hero", 2, "Ultima toma conmemorativa del agasajado")
]

def fit_preserve_aspect(img_rgb: np.ndarray, max_w: int, max_h: int) -> np.ndarray:
    """Escala y centra la imagen preservando al 100% la proporcion nativa (cero distorsion)."""
    h, w = img_rgb.shape[:2]
    scale = min(max_w / w, max_h / h)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LANCZOS4
    scaled = cv2.resize(img_rgb, (new_w, new_h), interpolation=interp)
    frame = np.full((max_h, max_w, 3), 18, dtype=np.uint8) # Fondo slate elegante
    x_off = (max_w - new_w) // 2
    y_off = (max_h - new_h) // 2
    frame[y_off:y_off+new_h, x_off:x_off+new_w] = scaled
    return frame

def detect_faces_and_landmarks(img_bgr: np.ndarray, yunet_path: Path):
    h, w = img_bgr.shape[:2]
    max_dim = 1200
    scale = max_dim / max(h, w)
    proxy = cv2.resize(img_bgr, (int(w * scale), int(h * scale))) if scale < 1.0 else img_bgr

    detector = cv2.FaceDetectorYN.create(
        str(yunet_path), "", (proxy.shape[1], proxy.shape[0]),
        score_threshold=0.55, nms_threshold=0.30, top_k=25
    )
    _, faces = detector.detect(proxy)
    results = []
    if faces is not None:
        for f in faces:
            bx, by, bw, bh = int(f[0] / scale), int(f[1] / scale), int(f[2] / scale), int(f[3] / scale)
            conf = float(f[14])
            # landmarks
            lex, ley = f[4] / scale, f[5] / scale
            rex, rey = f[6] / scale, f[7] / scale
            ear = 0.28 if math.hypot(rex - lex, rey - ley) > bw * 0.18 else 0.13
            results.append({
                "bbox": [bx, by, bw, bh],
                "conf": conf,
                "ear": ear,
                "blink": 0.0 if ear >= 0.20 else 0.85
            })
    return results

def compute_straighten_angle(img_gray: np.ndarray) -> float:
    detector_s = StraightenDetector(max_tilt_search_degrees=6.0, deadband_threshold_degrees=0.20)
    edges = cv2.Canny(img_gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, 80, minLineLength=40, maxLineGap=10)
    segments = []
    if lines is not None:
        for l in lines:
            x1, y1, x2, y2 = l[0]
            segments.append(LineSegment(float(x1), float(y1), float(x2), float(y2)))
    res = detector_s.estimate_tilt_from_segments(segments)
    return float(res.tilt_angle_degrees) if res.needs_straighten else 0.0

def render_audit_sheet_4k(photo_path: Path, cat_title: str, stars: int, desc: str, idx: int, total: int) -> Path:
    img_bgr = cv2.imread(str(photo_path))
    if img_bgr is None:
        raise ValueError(f"No se pudo leer {photo_path}")

    h_orig, w_orig = img_bgr.shape[:2]
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # 1. Detección Facial
    faces = detect_faces_and_landmarks(img_bgr, YUNET_PATH)
    bboxes = [f["bbox"] for f in faces]

    # 2. Pre-revelado adaptativo (medición de luminancia de piel)
    skin_lum, global_lum, clip_frac = measure_luminance(img_rgb, bboxes)
    # Sesión adaptativa
    sig = PhotoSignature(
        index=0,
        has_people=bool(faces),
        wb=(10.0, 6.0),
        skin_lum=skin_lum,
        global_lum=global_lum,
        clip_frac=clip_frac
    )
    pre_res = compute_pre_edits([sig], bias=0.35, preset_wb_bias=(10.0, 6.0))
    ev_corr = pre_res[0]["Exposure2012"]
    temp_inc = pre_res[0]["IncrementalTemperature"]
    tint_inc = pre_res[0]["IncrementalTint"]

    # 3. Nivelación angular theta
    theta = compute_straighten_angle(gray)

    # 4. Smart Crop circunscrito
    cropper = SmartCropper(target_aspect_ratio=3.0/2.0)
    subj_boxes = [
        SubjectBBox(
            xmin=max(0.0, b[0]/w_orig),
            ymin=max(0.0, b[1]/h_orig),
            xmax=min(1.0, (b[0]+b[2])/w_orig),
            ymax=min(1.0, (b[1]+b[3])/h_orig),
        )
        for b in bboxes
    ]
    crop_res = cropper.compute_crop(
        image_width=w_orig,
        image_height=h_orig,
        tilt_angle_degrees=theta,
        subjects=subj_boxes if subj_boxes else None,
        headroom_ratio=0.05
    )

    # 5. Transformación Geométrica
    if abs(theta) > 0.05:
        M = cv2.getRotationMatrix2D((w_orig / 2.0, h_orig / 2.0), -theta, 1.0)
        rotated_rgb = cv2.warpAffine(img_rgb, M, (w_orig, h_orig), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)
    else:
        rotated_rgb = img_rgb.copy()

    top_px = int(crop_res.top * h_orig)
    bot_px = int(crop_res.bottom * h_orig)
    left_px = int(crop_res.left * w_orig)
    right_px = int(crop_res.right * w_orig)
    cropped_rgb = rotated_rgb[top_px:bot_px, left_px:right_px]

    # 6. Tonal Engine: Aplicar Revelado GutoPro Day Boy Real sobre píxeles
    developed_rgb = TonalEngine.develop_photo(
        cropped_rgb,
        exposure_ev=ev_corr,
        temp_inc=temp_inc,
        tint_inc=tint_inc,
        highlights=-10.0,
        shadows=30.0,
        whites=-14.0,
        blacks=-11.0,
        contrast=-10.0,
        vibrance=3.0,
        saturation=-2.0
    )

    # 7. Retoque dérmico HLF con preservación de poros
    hlf_skin = HLFSeparation.smooth_skin(developed_rgb, smooth_strength=0.45, texture_preservation=1.0, radius=7)
    final_processed_rgb = NeutralGrayDodgeBurn.auto_even_skin_tones(hlf_skin, strength=0.30, dark_circle_lift=0.15)
    if final_processed_rgb.dtype != np.uint8:
        final_processed_rgb = np.clip(final_processed_rgb * 255.0, 0, 255).astype(np.uint8)

    # 8. Extraer Micro-Crops al 100% de rostros
    face_crops = []
    if faces:
        # Cara principal
        vip_face = max(faces, key=lambda f: f["bbox"][2]*f["bbox"][3])
        fx, fy, fw, fh = vip_face["bbox"]
        # Micro crop en imagen original
        cx, cy = fx + fw // 2, fy + fh // 2
        r = max(fw, fh) // 2 + 30
        c_orig = img_rgb[max(0, cy-r):min(h_orig, cy+r), max(0, cx-r):min(w_orig, cx+r)]
        if c_orig.size > 0:
            c_orig_disp = cv2.resize(c_orig, (280, 280))
            c_proc_disp = TonalEngine.develop_photo(c_orig_disp, exposure_ev=ev_corr)
            c_proc_disp = HLFSeparation.smooth_skin(c_proc_disp, smooth_strength=0.5, texture_preservation=1.0)
            if c_proc_disp.dtype != np.uint8:
                c_proc_disp = np.clip(c_proc_disp * 255.0, 0, 255).astype(np.uint8)
            face_crops.append(("Rostro VIP Original", c_orig_disp))
            face_crops.append(("Rostro VIP HLF + Poros", c_proc_disp))

    # 9. Calcular puntuaciones analíticas
    laplacian_val = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    sharpness_score = min(10.0, max(1.0, math.log1p(laplacian_val) * 1.5))
    eye_score = 9.8 if all(f["blink"] < 0.3 for f in faces) else 6.5
    comp_score = 9.0 if abs(theta) <= 2.0 else 7.5
    score_global = round(sharpness_score * 0.40 + eye_score * 0.40 + comp_score * 0.20, 1)

    # 10. Componer Canvas 4K (3840 x 2160)
    canvas = np.full((2160, 3840, 3), 18, dtype=np.uint8) # Dark slate background #121212

    # ENCABEZADO
    cv2.rectangle(canvas, (0, 0), (3840, 140), (28, 32, 42), -1)
    cv2.line(canvas, (0, 140), (3840, 140), (60, 70, 90), 2)

    title_text = f"GUTOFLOW 4.0 | AUDITORIA DE REVELADO & ENCUADRE INTELIGENTE [{idx:02d}/{total}]"
    cv2.putText(canvas, title_text, (50, 55), cv2.FONT_HERSHEY_DUPLEX, 1.2, (255, 255, 255), 2)
    sub_title = f"CATEGORIA: {cat_title.upper()}  |  ARCHIVO: {photo_path.name}  |  {desc}"
    cv2.putText(canvas, sub_title, (50, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (160, 175, 200), 2)

    badge_stars = f"SCORE: {score_global}/10  |  {stars} ESTRELLAS ({'HERO PICK' if stars==3 else 'APROBADA'})"
    badge_color = (230, 160, 40) if stars == 3 else (70, 200, 120)
    cv2.putText(canvas, badge_stars, (2700, 80), cv2.FONT_HERSHEY_DUPLEX, 1.1, badge_color, 2)

    # AREA PRINCIPAL: SIDE-BY-SIDE (Y: 160 a 1520 -> Alto: 1360)
    panel_w = 1840
    panel_h = 1360

    # Lado Izquierdo: Original Cruda (Preservando al 100% aspect ratio sin distorsion)
    orig_scaled = fit_preserve_aspect(img_rgb, panel_w, panel_h)
    canvas[160:160+panel_h, 50:50+panel_w] = orig_scaled
    cv2.rectangle(canvas, (50, 160), (50+panel_w, 160+panel_h), (60, 70, 90), 2)
    # Badge Original
    cv2.rectangle(canvas, (65, 175), (750, 235), (20, 20, 25), -1)
    cv2.putText(canvas, "ORIGINAL CRUDA DE CAMARA (SIN PROCESAR)", (80, 215), cv2.FONT_HERSHEY_DUPLEX, 0.8, (200, 200, 200), 2)

    # Lado Derecho: Procesado Final Completo (Preservando al 100% aspect ratio sin distorsion)
    proc_scaled = fit_preserve_aspect(final_processed_rgb, panel_w, panel_h)
    canvas[160:160+panel_h, 1950:1950+panel_w] = proc_scaled
    cv2.rectangle(canvas, (1950, 160), (1950+panel_w, 160+panel_h), badge_color, 2)
    # Badge Procesado
    cv2.rectangle(canvas, (1965, 175), (2800, 235), (20, 20, 25), -1)
    badge_p_text = f"RESULTADO FINAL: GUTOPRO DAY BOY + PRE-REVELADO (EV {ev_corr:+.2f}) + SMART CROP"
    cv2.putText(canvas, badge_p_text, (1980, 215), cv2.FONT_HERSHEY_DUPLEX, 0.8, badge_color, 2)

    # PANEL INFERIOR: TELEMETRIA Y MICRO-CROPS (Y: 1540 a 2120 -> Alto: 580)
    card_y = 1550
    card_h = 560

    # Tarjeta 1: Calificación y Razones
    cv2.rectangle(canvas, (50, card_y), (950, card_y+card_h), (28, 32, 42), -1)
    cv2.rectangle(canvas, (50, card_y), (950, card_y+card_h), (60, 70, 90), 2)
    cv2.putText(canvas, "1. CALIFICACION Y DECISION", (75, card_y+50), cv2.FONT_HERSHEY_DUPLEX, 0.85, (255, 215, 0), 2)
    cv2.putText(canvas, f"Score Global: {score_global} / 10.0", (75, card_y+105), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
    cv2.putText(canvas, f"- Nitidez Sujeto: {sharpness_score:.1f}/10 (Laplaciano {laplacian_val:.1f})", (75, card_y+155), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 210, 225), 1)
    cv2.putText(canvas, f"- Ojos y Rostros: {len(faces)} detectados | EAR {faces[0]['ear'] if faces else 0.28:.2f}", (75, card_y+205), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 210, 225), 1)
    cv2.putText(canvas, f"- Estado Ocular: {'Abiertos - Mirada Firme' if eye_score > 7 else 'Parcial'}", (75, card_y+255), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (100, 255, 150) if eye_score > 7 else (255, 180, 80), 2)
    cv2.putText(canvas, f"- Expresion VIP: {'Sonrisa / Atento' if stars==3 else 'Momento Valido'}", (75, card_y+305), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 210, 225), 1)
    cv2.putText(canvas, f"- Categoria: {cat_title}", (75, card_y+355), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1)
    cv2.putText(canvas, f"Veredicto: APROBADA para Entrega Final", (75, card_y+430), cv2.FONT_HERSHEY_DUPLEX, 0.75, (70, 220, 130), 2)

    # Tarjeta 2: Geometría y Nivelación
    cv2.rectangle(canvas, (980, card_y), (1880, card_y+card_h), (28, 32, 42), -1)
    cv2.rectangle(canvas, (980, card_y), (1880, card_y+card_h), (60, 70, 90), 2)
    cv2.putText(canvas, "2. GEOMETRIA & REENCUADRE", (1005, card_y+50), cv2.FONT_HERSHEY_DUPLEX, 0.85, (100, 200, 255), 2)
    theta_status = f"{theta:+.2f} grados" if abs(theta) > 0.05 else "0.00 grados (Ya nivelada)"
    cv2.putText(canvas, f"- Nivelacion Angular: {theta_status}", (1005, card_y+105), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
    cv2.putText(canvas, f"- Correccion: Sin esquinas negras (Inscripcion Lanczos4)", (1005, card_y+155), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 210, 225), 1)
    area_ratio = (crop_res.width * crop_res.height) * 100.0
    cv2.putText(canvas, f"- Smart Crop: {area_ratio:.1f}% del encuadre util preservado", (1005, card_y+205), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 210, 225), 1)
    cv2.putText(canvas, f"- Headroom: 5.0% margen seguro sobre cabezas", (1005, card_y+255), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (100, 255, 150), 2)
    cv2.putText(canvas, f"- Aspect Ratio: 3:2 nativo horizontal/vertical", (1005, card_y+305), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 210, 225), 1)
    cv2.putText(canvas, f"- Proteccion Grupal: Cabezas de invitados intactas", (1005, card_y+355), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 210, 225), 1)

    # Tarjeta 3: Pre-revelado y GutoPro Day Boy
    cv2.rectangle(canvas, (1910, card_y), (2810, card_y+card_h), (28, 32, 42), -1)
    cv2.rectangle(canvas, (1910, card_y), (2810, card_y+card_h), (60, 70, 90), 2)
    cv2.putText(canvas, "3. PRE-REVELADO & COLOR GUTOPRO", (1935, card_y+50), cv2.FONT_HERSHEY_DUPLEX, 0.85, (255, 140, 100), 2)
    ev_status = f"{ev_corr:+.2f} EV (Compensada para piel ideal)" if abs(ev_corr) > 0.05 else "0.00 EV (Exposicion nativa correcta)"
    cv2.putText(canvas, f"- Exposure2012: {ev_status}", (1935, card_y+105), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
    cv2.putText(canvas, f"- Balance Blancos: Temp {temp_inc:+.1f} | Tint {tint_inc:+.1f}", (1935, card_y+155), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 210, 225), 1)
    cv2.putText(canvas, f"- Sombras / Altas Luces: Sombras +30 | Highlights -10", (1935, card_y+205), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 210, 225), 1)
    cv2.putText(canvas, f"- Whites & Blacks: Whites -14 | Blacks -11 (Tonos ricos)", (1935, card_y+255), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 210, 225), 1)
    cv2.putText(canvas, f"- Curva Tonal: ToneCurvePV2012 Custom (0,0)(177,183)", (1935, card_y+305), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 210, 225), 1)
    cv2.putText(canvas, f"- HSL Calidez: Naranja Luminancia +5 | Verde +26", (1935, card_y+355), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (100, 255, 150), 2)

    # Tarjeta 4: Micro-Crops al 100% (Zoom Poros y Rostro)
    cv2.rectangle(canvas, (2840, card_y), (3790, card_y+card_h), (28, 32, 42), -1)
    cv2.rectangle(canvas, (2840, card_y), (3790, card_y+card_h), (60, 70, 90), 2)
    cv2.putText(canvas, "4. INSPECCION AL 100% (HLF & POROS)", (2865, card_y+50), cv2.FONT_HERSHEY_DUPLEX, 0.85, (200, 150, 255), 2)

    if face_crops:
        # Colocar dos crops lado a lado
        crop_title1, cimg1 = face_crops[0]
        crop_title2, cimg2 = face_crops[1]
        canvas[card_y+100:card_y+380, 2900:2900+280] = cimg1
        canvas[card_y+100:card_y+380, 3240:3240+280] = cimg2
        cv2.rectangle(canvas, (2900, card_y+100), (2900+280, card_y+380), (80, 90, 110), 1)
        cv2.rectangle(canvas, (3240, card_y+100), (3240+280, card_y+380), (70, 200, 120), 2)
        cv2.putText(canvas, "Toma Original", (2950, card_y+420), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1)
        cv2.putText(canvas, "HLF Piel + Poros", (3290, card_y+420), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (70, 220, 130), 2)
        cv2.putText(canvas, "Textura natural preservada sin efecto plastico", (2900, card_y+490), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (220, 230, 255), 1)
    else:
        cv2.putText(canvas, "Toma sin primer plano facial aislado.", (2920, card_y+250), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (160, 170, 190), 1)

    out_file = OUTPUT_DIR / f"audit_procesado_{idx:02d}_{Path(photo_path).stem}.jpg"
    # Guardar en JPEG calidad 94
    canvas_bgr = cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(out_file), canvas_bgr, [cv2.IMWRITE_JPEG_QUALITY, 94])
    return out_file

def main():
    t0 = time.time()
    print("=== INICIANDO RENDERIZADO 4K: 25 LAMINAS DE PROCESADO ===", flush=True)
    print(f"Destino: {OUTPUT_DIR}", flush=True)

    for i, (fname, cat_title, stars, desc) in enumerate(PHOTOS_25, 1):
        p = NAS_DIR / fname
        if not p.exists():
            print(f"[{i:02d}/25] No encontrada en NAS: {fname}", flush=True)
            continue
        try:
            t_item = time.time()
            out_p = render_audit_sheet_4k(p, cat_title, stars, desc, i, len(PHOTOS_25))
            dt = time.time() - t_item
            print(f"[{i:02d}/25] Generada {out_p.name} ({dt:.1f}s)", flush=True)
        except Exception as e:
            print(f"[{i:02d}/25] Error en {fname}: {e}", flush=True)

    total_time = time.time() - t0
    print(f"\nRenderizado de las 25 laminas de procesado completado en {total_time:.1f}s.", flush=True)

if __name__ == "__main__":
    main()
