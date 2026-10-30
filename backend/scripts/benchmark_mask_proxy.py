"""
benchmark_mask_proxy.py — Comparativa rigurosa A/B:
Método A: Lienzo Original (24 MP, 6000x4000)
Método B: Lienzo Proxy (2048 px)
Evalúa sobre las 4 fotos clave de C:/Users/Guill/Desktop/Pruebas MAscaras.
Calcula IoU, coincidencia de píxeles, tiempos y ahorro de memoria RAM.
"""
import sys
import os
import time
import json
import gc
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
from PIL import Image, ImageOps

from services.mask_generator import (
    YUNET_PATH, LANDMARKER_PATH, SEGMENTER_PATH,
    LEFT_IRIS_CENTER, LEFT_IRIS_BOUNDARY,
    RIGHT_IRIS_CENTER, RIGHT_IRIS_BOUNDARY,
    LEFT_EYE_CONTOUR, RIGHT_EYE_CONTOUR,
    LEFT_EYEBROW, RIGHT_EYEBROW,
    INNER_LIPS, OUTER_LIPS, FACE_OVAL,
    nms_boxes, TARGET_SIZE, detect_persons
)

TEST_DIR = Path("C:/Users/Guill/Desktop/Pruebas MAscaras")
TEST_IMAGES = ["IMG_4821.jpg", "IMG_0341.JPG", "IMG_0308.JPG", "IMG_0257.JPG"]
OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "models" / "cache" / "mattes" / "benchmark_proxy"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

LAYERS = ["person", "facial_skin", "eye_sclera", "iris_pupil", "teeth"]


def load_image_controlled(path: Path, max_dim: int | None = None) -> np.ndarray:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    if max_dim is not None and max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.BILINEAR)
    return np.array(img)


def run_pipeline(img_rgb: np.ndarray) -> dict[str, np.ndarray]:
    """Ejecuta la segmentación completa de 5 capas sobre img_rgb y retorna {layer: mask_512}."""
    h0, w0 = img_rgb.shape[:2]

    person_full = np.zeros((h0, w0), dtype=np.uint8)
    skin_full = np.zeros((h0, w0), dtype=np.uint8)
    sclera_full = np.zeros((h0, w0), dtype=np.uint8)
    iris_full = np.zeros((h0, w0), dtype=np.uint8)
    teeth_full = np.zeros((h0, w0), dtype=np.uint8)

    # 1. YuNet
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    confirmed_faces = []
    if YUNET_PATH.exists():
        detector = cv2.FaceDetectorYN.create(
            str(YUNET_PATH), "", (w0, h0),
            score_threshold=0.55, nms_threshold=0.30
        )
        _, raw_faces = detector.detect(img_bgr)
        if raw_faces is not None and len(raw_faces) > 0:
            boxes = [[int(f[0]), int(f[1]), int(f[2]), int(f[3])] for f in raw_faces]
            scores = [float(f[14]) for f in raw_faces]
            keep_idx = nms_boxes(boxes, scores, iou_thresh=0.35)
            confirmed_faces = [raw_faces[i] for i in keep_idx]

    # 2. Sujeto Pop (Segmenter + YOLOv8 + Torso)
    if SEGMENTER_PATH.exists():
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision

            base_opts = mp_python.BaseOptions(model_asset_path=str(SEGMENTER_PATH))
            opts = vision.ImageSegmenterOptions(
                base_options=base_opts,
                running_mode=vision.RunningMode.IMAGE,
                output_confidence_masks=True
            )
            with vision.ImageSegmenter.create_from_options(opts) as segmenter:
                scale = 1024.0 / max(h0, w0)
                sw, sh = int(round(w0 * scale)), int(round(h0 * scale))
                small = cv2.resize(img_rgb, (sw, sh), interpolation=cv2.INTER_AREA)
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=small)
                res = segmenter.segment(mp_img)
                if res.confidence_masks:
                    conf = res.confidence_masks[0].numpy_view()
                    conf_u8 = (np.clip(conf, 0.0, 1.0) * 255.0).astype(np.uint8)
                    person_full = cv2.resize(conf_u8, (w0, h0), interpolation=cv2.INTER_LINEAR)

                # YOLOv8 Person Crops
                person_boxes = detect_persons(img_rgb)
                for bx, by, bw, bh in person_boxes:
                    mx, my = int(bw * 0.10), int(bh * 0.10)
                    x0 = max(0, bx - mx)
                    y0 = max(0, by - my)
                    x1 = min(w0, bx + bw + mx)
                    y1 = min(h0, by + bh + my)
                    crop = img_rgb[y0:y1, x0:x1]
                    if crop.size == 0:
                        continue
                    ch, cw = crop.shape[:2]
                    cscale = 512.0 / max(ch, cw)
                    c_small = cv2.resize(crop, (max(1, int(round(cw * cscale))), max(1, int(round(ch * cscale)))), interpolation=cv2.INTER_AREA)
                    mp_crop = mp.Image(image_format=mp.ImageFormat.SRGB, data=c_small)
                    res_crop = segmenter.segment(mp_crop)
                    if res_crop.confidence_masks:
                        cmask = res_crop.confidence_masks[0].numpy_view()
                        cmask_u8 = (np.clip(cmask, 0.0, 1.0) * 255.0).astype(np.uint8)
                        cmask_full = cv2.resize(cmask_u8, (cw, ch), interpolation=cv2.INTER_LINEAR)
                        person_full[y0:y1, x0:x1] = np.maximum(person_full[y0:y1, x0:x1], cmask_full)

                # Torso YuNet
                for f in confirmed_faces:
                    fx, fy, fw, fh = int(f[0]), int(f[1]), int(f[2]), int(f[3])
                    fcx, fcy = int(fx + fw / 2), int(fy + fh / 2)
                    if person_full[min(h0 - 1, max(0, fcy)), min(w0 - 1, max(0, fcx))] < 100:
                        bx = int(max(0, fcx - fw * 1.5))
                        by = int(max(0, fy - fh * 0.5))
                        bw = int(min(w0 - bx, fw * 3.0))
                        bh = int(min(h0 - by, fh * 4.5))
                        crop = img_rgb[by:by + bh, bx:bx + bw]
                        if crop.size > 0:
                            ch, cw = crop.shape[:2]
                            cscale = 512.0 / max(ch, cw)
                            c_small = cv2.resize(crop, (max(1, int(round(cw * cscale))), max(1, int(round(ch * cscale)))), interpolation=cv2.INTER_AREA)
                            mp_crop = mp.Image(image_format=mp.ImageFormat.SRGB, data=c_small)
                            res_crop = segmenter.segment(mp_crop)
                            if res_crop.confidence_masks:
                                cmask = res_crop.confidence_masks[0].numpy_view()
                                cmask_u8 = (np.clip(cmask, 0.0, 1.0) * 255.0).astype(np.uint8)
                                cmask_full = cv2.resize(cmask_u8, (cw, ch), interpolation=cv2.INTER_LINEAR)
                                person_full[by:by + bh, bx:bx + bw] = np.maximum(person_full[by:by + bh, bx:bx + bw], cmask_full)
        except Exception as e:
            sys.stderr.write(f"Segmenter exception: {e}\n")

    # 3. MediaPipe FaceLandmarker
    landmarker = None
    if LANDMARKER_PATH.exists():
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
            opts = vision.FaceLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(LANDMARKER_PATH)),
                running_mode=vision.RunningMode.IMAGE,
                num_faces=1,
                min_face_detection_confidence=0.10,
            )
            landmarker = vision.FaceLandmarker.create_from_options(opts)
        except Exception:
            pass

    CROP_MARGIN = 0.60
    CROP_SIZE = 384
    import mediapipe as mp

    img_hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)

    for f in confirmed_faces:
        fx, fy, fw, fh = int(f[0]), int(f[1]), int(f[2]), int(f[3])
        fcx, fcy = fx + fw / 2, fy + fh / 2
        side = max(fw, fh) * (1.0 + CROP_MARGIN)
        cx0 = int(max(0, fcx - side / 2))
        cy0 = int(max(0, fcy - side / 2))
        cx1 = int(min(w0, fcx + side / 2))
        cy1 = int(min(h0, fcy + side / 2))
        crop = img_rgb[cy0:cy1, cx0:cx1]
        if crop.size == 0 or landmarker is None:
            continue

        ch, cw = crop.shape[:2]
        crop_resized = cv2.resize(crop, (CROP_SIZE, CROP_SIZE))
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=crop_resized)
        res = landmarker.detect(mp_img)

        if not res.face_landmarks or len(res.face_landmarks) == 0:
            continue

        lms = res.face_landmarks[0]

        def to_full_px(idx):
            lm = lms[idx]
            px = cx0 + int(round(lm.x * cw))
            py = cy0 + int(round(lm.y * ch))
            return np.array([np.clip(px, 0, w0 - 1), np.clip(py, 0, h0 - 1)], dtype=np.int32)

        # Ojos
        l_eye_pts = np.array([to_full_px(i) for i in LEFT_EYE_CONTOUR], dtype=np.int32)
        r_eye_pts = np.array([to_full_px(i) for i in RIGHT_EYE_CONTOUR], dtype=np.int32)
        l_eye_mask = np.zeros((h0, w0), dtype=np.uint8)
        r_eye_mask = np.zeros((h0, w0), dtype=np.uint8)
        cv2.fillPoly(l_eye_mask, [l_eye_pts], 255)
        cv2.fillPoly(r_eye_mask, [r_eye_pts], 255)

        # Iris
        l_center = to_full_px(LEFT_IRIS_CENTER)
        l_b_pts = [to_full_px(i) for i in LEFT_IRIS_BOUNDARY]
        l_radius = float(np.mean([np.linalg.norm(l_center - pt) for pt in l_b_pts])) * 1.15
        l_iris_circle = np.zeros((h0, w0), dtype=np.uint8)
        cv2.circle(l_iris_circle, (int(l_center[0]), int(l_center[1])), max(1, int(round(l_radius))), 255, -1)
        l_iris = cv2.bitwise_and(l_iris_circle, l_eye_mask)

        r_center = to_full_px(RIGHT_IRIS_CENTER)
        r_b_pts = [to_full_px(i) for i in RIGHT_IRIS_BOUNDARY]
        r_radius = float(np.mean([np.linalg.norm(r_center - pt) for pt in r_b_pts])) * 1.15
        r_iris_circle = np.zeros((h0, w0), dtype=np.uint8)
        cv2.circle(r_iris_circle, (int(r_center[0]), int(r_center[1])), max(1, int(round(r_radius))), 255, -1)
        r_iris = cv2.bitwise_and(r_iris_circle, r_eye_mask)

        face_iris = cv2.bitwise_or(l_iris, r_iris)
        iris_full = np.maximum(iris_full, face_iris)

        # Esclera
        k_iris = np.ones((3, 3), np.uint8)
        l_iris_dil = cv2.dilate(l_iris, k_iris, iterations=1)
        r_iris_dil = cv2.dilate(r_iris, k_iris, iterations=1)
        l_sclera = cv2.bitwise_and(l_eye_mask, cv2.bitwise_not(l_iris_dil))
        r_sclera = cv2.bitwise_and(r_eye_mask, cv2.bitwise_not(r_iris_dil))
        face_sclera = cv2.bitwise_or(l_sclera, r_sclera)
        face_sclera = cv2.GaussianBlur(face_sclera, (3, 3), 0)
        sclera_full = np.maximum(sclera_full, face_sclera)

        # Dientes
        p13 = to_full_px(13)
        p14 = to_full_px(14)
        p10 = to_full_px(10)
        p152 = to_full_px(152)
        lip_gap = float(np.linalg.norm(p13 - p14))
        face_h = float(np.linalg.norm(p10 - p152))
        gap_ratio = lip_gap / max(1.0, face_h)

        if gap_ratio >= 0.025:
            inner_lip_pts = np.array([to_full_px(i) for i in INNER_LIPS], dtype=np.int32)
            mouth_poly = np.zeros((h0, w0), dtype=np.uint8)
            cv2.fillPoly(mouth_poly, [inner_lip_pts], 255)
            mouth_poly = cv2.erode(mouth_poly, np.ones((3, 3), np.uint8), iterations=1)
            sat = img_hsv[:, :, 1]
            val = img_hsv[:, :, 2]
            teeth_bin = (mouth_poly > 0) & (sat < 85) & (val > 80)
            face_teeth = np.zeros((h0, w0), dtype=np.uint8)
            face_teeth[teeth_bin] = 255
            face_teeth = cv2.GaussianBlur(face_teeth, (3, 3), 0)
            teeth_full = np.maximum(teeth_full, face_teeth)

        # Piel Facial
        face_oval_pts = np.array([to_full_px(i) for i in FACE_OVAL], dtype=np.int32)
        skin_poly = np.zeros((h0, w0), dtype=np.uint8)
        cv2.fillPoly(skin_poly, [face_oval_pts], 255)

        eye_eyebrow_sub = np.zeros((h0, w0), dtype=np.uint8)
        l_brow_pts = np.array([to_full_px(i) for i in LEFT_EYEBROW], dtype=np.int32)
        r_brow_pts = np.array([to_full_px(i) for i in RIGHT_EYEBROW], dtype=np.int32)
        for poly in [l_eye_pts, r_eye_pts, l_brow_pts, r_brow_pts]:
            cv2.fillPoly(eye_eyebrow_sub, [poly], 255)
        outer_lip_pts = np.array([to_full_px(i) for i in OUTER_LIPS], dtype=np.int32)
        cv2.fillPoly(eye_eyebrow_sub, [outer_lip_pts], 255)

        k_skin = np.ones((5, 5), np.uint8)
        dilated_sub = cv2.dilate(eye_eyebrow_sub, k_skin, iterations=1)
        skin_layer = cv2.bitwise_and(skin_poly, cv2.bitwise_not(dilated_sub))
        skin_layer = cv2.GaussianBlur(skin_layer, (5, 5), 0)
        skin_full = np.maximum(skin_full, skin_layer)

    person_full = np.maximum(person_full, skin_full)

    # Redimensionar al tamaño final estandarizado (512x512)
    def to_512(m):
        return cv2.resize(m, (TARGET_SIZE, TARGET_SIZE), interpolation=cv2.INTER_AREA)

    return {
        "person": to_512(person_full),
        "facial_skin": to_512(skin_full),
        "eye_sclera": to_512(sclera_full),
        "iris_pupil": to_512(iris_full),
        "teeth": to_512(teeth_full),
    }


def compute_metrics(m_a: np.ndarray, m_b: np.ndarray) -> dict:
    """Calcula métricas de fidelidad matemática entre dos máscaras 512x512."""
    bin_a = m_a > 127
    bin_b = m_b > 127

    intersection = np.logical_and(bin_a, bin_b).sum()
    union = np.logical_or(bin_a, bin_b).sum()

    if union == 0:
        iou = 1.0
        dice = 1.0
    else:
        iou = float(intersection) / float(union)
        dice = float(2 * intersection) / float(bin_a.sum() + bin_b.sum())

    # Tolerancia: porcentaje de píxeles cuya diferencia absoluta <= 10 (sobre 255)
    diff = np.abs(m_a.astype(np.int16) - m_b.astype(np.int16))
    pixel_match = float(np.mean(diff <= 10)) * 100.0
    mae = float(np.mean(diff))

    return {
        "iou": round(iou, 4),
        "dice": round(dice, 4),
        "pixel_match_pct": round(pixel_match, 2),
        "mae": round(mae, 2),
    }


def main():
    print("=" * 80)
    print("BENCHMARK A/B: ORIGINAL (24 MP) VS PROXY (2048 PX)")
    print("=" * 80)

    summary_results = []

    for img_name in TEST_IMAGES:
        img_path = TEST_DIR / img_name
        if not img_path.exists():
            print(f"[!] Archivo no encontrado: {img_path}")
            continue

        print(f"\n---> Evaluando: {img_name}")
        out_sub_a = OUTPUT_ROOT / "A_24MP" / img_name
        out_sub_b = OUTPUT_ROOT / "B_Proxy" / img_name
        out_diff = OUTPUT_ROOT / "Diff_Heatmaps" / img_name
        out_sub_a.mkdir(parents=True, exist_ok=True)
        out_sub_b.mkdir(parents=True, exist_ok=True)
        out_diff.mkdir(parents=True, exist_ok=True)

        # -------------------------------------------------------------
        # PIPELINE A: 24 MP ORIGINAL
        # -------------------------------------------------------------
        gc.collect()
        tracemalloc.start()
        t0 = time.perf_counter()

        img_a = load_image_controlled(img_path, max_dim=None)
        h_a, w_a = img_a.shape[:2]
        masks_a = run_pipeline(img_a)

        t_a = time.perf_counter() - t0
        _, peak_a = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        del img_a
        gc.collect()

        ram_a_mb = peak_a / (1024 * 1024)

        # Guardar máscaras A
        for name, m in masks_a.items():
            cv2.imwrite(str(out_sub_a / f"{name}.png"), m)

        # -------------------------------------------------------------
        # PIPELINE B: PROXY 2048 PX
        # -------------------------------------------------------------
        gc.collect()
        tracemalloc.start()
        t0 = time.perf_counter()

        img_b = load_image_controlled(img_path, max_dim=2048)
        h_b, w_b = img_b.shape[:2]
        masks_b = run_pipeline(img_b)

        t_b = time.perf_counter() - t0
        _, peak_b = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        del img_b
        gc.collect()

        ram_b_mb = peak_b / (1024 * 1024)

        # Guardar máscaras B y mapas de diferencia
        img_result = {
            "image": img_name,
            "res_a": f"{w_a}x{h_a}",
            "res_b": f"{w_b}x{h_b}",
            "time_a_s": round(t_a, 2),
            "time_b_s": round(t_b, 2),
            "speedup": round(t_a / max(0.01, t_b), 2),
            "ram_a_mb": round(ram_a_mb, 1),
            "ram_b_mb": round(ram_b_mb, 1),
            "ram_reduction_pct": round((1.0 - ram_b_mb / max(0.1, ram_a_mb)) * 100.0, 1),
            "layers": {},
        }

        for name in LAYERS:
            ma = masks_a[name]
            mb = masks_b[name]
            cv2.imwrite(str(out_sub_b / f"{name}.png"), mb)

            # Diferencia visual amplificada 3x
            diff = np.abs(ma.astype(np.int16) - mb.astype(np.int16)).astype(np.uint8)
            heatmap = cv2.applyColorMap(diff * 3, cv2.COLORMAP_JET)
            # Collage: A | B | Heatmap Diff
            ma_bgr = cv2.cvtColor(ma, cv2.COLOR_GRAY2BGR)
            mb_bgr = cv2.cvtColor(mb, cv2.COLOR_GRAY2BGR)
            side_by_side = np.hstack([ma_bgr, mb_bgr, heatmap])
            cv2.imwrite(str(out_diff / f"{name}_comparison.png"), side_by_side)

            metrics = compute_metrics(ma, mb)
            img_result["layers"][name] = metrics

        summary_results.append(img_result)
        print(f"  A (24MP): {t_a:.2f}s | RAM peak: {ram_a_mb:.1f}MB")
        print(f"  B (Proxy): {t_b:.2f}s | RAM peak: {ram_b_mb:.1f}MB ({img_result['ram_reduction_pct']}% ahorro)")
        for l, met in img_result["layers"].items():
            print(f"    - {l:12s}: IoU={met['iou']:.4f} | Coincidencia={met['pixel_match_pct']}%")

    # Guardar reporte JSON
    report_file = OUTPUT_ROOT / "benchmark_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(summary_results, f, indent=2)

    print("\n" + "=" * 80)
    print("REPORTE FINAL GUARDADO EN:", report_file)
    print("=" * 80)


if __name__ == "__main__":
    main()
