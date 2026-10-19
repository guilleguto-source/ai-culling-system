"""
mask_generator.py — Generador neural de máscaras anatómicas y de sujeto (Paridad Lightroom).
Exporta 5 planos alpha de 8 bits:
  1. person.png        (Sujeto / Pop: silueta de cuerpo completo con selfie_segmenter)
  2. facial_skin.png   (Piel facial sin ojos, pestañas, cejas ni labios)
  3. eye_sclera.png    (Esclera de los ojos con feather en lagrimal)
  4. iris_pupil.png    (Iris circular recortado estrictamente por párpados)
  5. teeth.png         (Dientes reales dentro de apertura bucal)
"""
import sys
import os
import json
import argparse
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENCV_NUM_THREADS", "1")

import cv2
import numpy as np
from PIL import Image, ImageOps

from services.app_paths import get_models_dir
from services.person_detector import detect_persons

MODELS_DIR = get_models_dir()
YUNET_PATH = MODELS_DIR / "yunet.onnx"
LANDMARKER_PATH = MODELS_DIR / "face_landmarker.task"
SEGMENTER_PATH = MODELS_DIR / "selfie_segmenter.tflite"

# MediaPipe FaceMesh Landmarks (478 puntos)
LEFT_IRIS_CENTER = 468
LEFT_IRIS_BOUNDARY = [469, 470, 471, 472]
RIGHT_IRIS_CENTER = 473
RIGHT_IRIS_BOUNDARY = [474, 475, 476, 477]

LEFT_EYE_CONTOUR = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
RIGHT_EYE_CONTOUR = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]

LEFT_EYEBROW = [70, 63, 105, 66, 107, 55, 65, 52, 53, 46]
RIGHT_EYEBROW = [300, 293, 334, 296, 336, 285, 295, 282, 283, 276]

INNER_LIPS = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191]
OUTER_LIPS = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 61, 185, 40, 39, 37, 0, 267, 269, 270, 409]

FACE_OVAL = [
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378,
    400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21,
    54, 103, 67, 109
]

TARGET_SIZE = 512


def load_image(path: Path) -> np.ndarray:
    """Carga imagen preservando orientación EXIF."""
    raw_exts = {".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2"}
    if path.suffix.lower() in raw_exts:
        try:
            import rawpy
            with rawpy.imread(str(path)) as raw:
                try:
                    thumb = raw.extract_thumb()
                    if thumb.format == rawpy.ThumbFormat.JPEG:
                        import io
                        img = Image.open(io.BytesIO(thumb.data))
                        img = ImageOps.exif_transpose(img).convert("RGB")
                        return np.array(img)
                except Exception:
                    pass
                arr = raw.postprocess(use_camera_wb=True, half_size=True)
                return arr
        except Exception:
            pass

    pil_img = Image.open(path)
    pil_img = ImageOps.exif_transpose(pil_img).convert("RGB")
    return np.array(pil_img)


def calculate_iou(boxA, boxB):
    """Calcula Intersección sobre Unión entre dos bboxes [x, y, w, h]."""
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[0] + boxA[2], boxB[0] + boxB[2])
    yB = min(boxA[1] + boxA[3], boxB[1] + boxB[3])
    interW = max(0, xB - xA)
    interH = max(0, yB - yA)
    interArea = interW * interH
    boxAArea = boxA[2] * boxA[3]
    boxBArea = boxB[2] * boxB[3]
    iou = interArea / float(boxAArea + boxBArea - interArea + 1e-6)
    return iou


def nms_boxes(boxes, scores, iou_thresh=0.35):
    """Aplica Non-Maximum Suppression estricto."""
    if len(boxes) == 0:
        return []
    indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    keep = []
    while indices:
        current = indices.pop(0)
        keep.append(current)
        indices = [i for i in indices if calculate_iou(boxes[current], boxes[i]) < iou_thresh]
    return keep


def generate_all_masks(img_path: str, output_dir: str):
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    img_rgb = load_image(Path(img_path))
    h0, w0 = img_rgb.shape[:2]

    person_full = np.zeros((h0, w0), dtype=np.uint8)
    skin_full = np.zeros((h0, w0), dtype=np.uint8)
    sclera_full = np.zeros((h0, w0), dtype=np.uint8)
    iris_full = np.zeros((h0, w0), dtype=np.uint8)
    teeth_full = np.zeros((h0, w0), dtype=np.uint8)

    # -------------------------------------------------------------
    # 1. Sujeto / Pop: Segmentación precisa con Selfie Segmenter
    # -------------------------------------------------------------
    person_segmented = False
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
                    # Rescalar a tamaño completo con bordes suaves
                    conf_u8 = (np.clip(conf, 0.0, 1.0) * 255.0).astype(np.uint8)
                    person_full = cv2.resize(conf_u8, (w0, h0), interpolation=cv2.INTER_LINEAR)
                    person_segmented = True
        except Exception as e:
            sys.stderr.write(f"Warning: selfie segmenter failed: {e}\n")

    if not person_segmented:
        # Fallback YOLOv8 bounding boxes
        person_boxes = detect_persons(img_rgb)
        if person_boxes:
            for (bx, by, bw, bh) in person_boxes:
                x0, y0 = max(0, bx), max(0, by)
                x1, y1 = min(w0, bx + bw), min(h0, by + bh)
                if x1 <= x0 or y1 <= y0:
                    continue
                sub_w, sub_h = x1 - x0, y1 - y0
                cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
                p_layer = np.zeros((h0, w0), dtype=np.uint8)
                cv2.ellipse(p_layer, (cx, cy), (sub_w // 2, sub_h // 2), 0, 0, 360, 255, -1)
                ksize = max(5, int(min(sub_w, sub_h) * 0.08) | 1)
                p_layer = cv2.GaussianBlur(p_layer, (ksize, ksize), 0)
                person_full = np.maximum(person_full, p_layer)

    # -------------------------------------------------------------
    # 2. Detección Facial con YuNet y Filtro NMS
    # -------------------------------------------------------------
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

    # -------------------------------------------------------------
    # 3. MediaPipe FaceLandmarker (478 landmarks)
    # -------------------------------------------------------------
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
        except Exception as e:
            sys.stderr.write(f"Warning: MediaPipe landmarker init failed: {e}\n")

    CROP_MARGIN = 0.60
    CROP_SIZE = 384
    import mediapipe as mp

    # Precalcular espacio HSV para discriminación de dientes
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

        # Si MediaPipe NO confirma landmarks, DESCARTAR. Cero fallback cartoon.
        if not res.face_landmarks or len(res.face_landmarks) == 0:
            continue

        lms = res.face_landmarks[0]

        def to_full_px(idx):
            lm = lms[idx]
            px = cx0 + int(round(lm.x * cw))
            py = cy0 + int(round(lm.y * ch))
            return np.array([np.clip(px, 0, w0 - 1), np.clip(py, 0, h0 - 1)], dtype=np.int32)

        # ---------------------------------------------------------
        # A. Contornos Palpebrales de Ojos
        # ---------------------------------------------------------
        l_eye_pts = np.array([to_full_px(i) for i in LEFT_EYE_CONTOUR], dtype=np.int32)
        r_eye_pts = np.array([to_full_px(i) for i in RIGHT_EYE_CONTOUR], dtype=np.int32)

        l_eye_mask = np.zeros((h0, w0), dtype=np.uint8)
        r_eye_mask = np.zeros((h0, w0), dtype=np.uint8)
        cv2.fillPoly(l_eye_mask, [l_eye_pts], 255)
        cv2.fillPoly(r_eye_mask, [r_eye_pts], 255)

        # ---------------------------------------------------------
        # B. Iris & Pupila (Circunferencia exacta recortada por párpados)
        # ---------------------------------------------------------
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

        # ---------------------------------------------------------
        # C. Esclera (Palpebral menos Iris dilatado, con feather subpíxel)
        # ---------------------------------------------------------
        k_iris = np.ones((3, 3), np.uint8)
        l_iris_dil = cv2.dilate(l_iris, k_iris, iterations=1)
        r_iris_dil = cv2.dilate(r_iris, k_iris, iterations=1)

        l_sclera = cv2.bitwise_and(l_eye_mask, cv2.bitwise_not(l_iris_dil))
        r_sclera = cv2.bitwise_and(r_eye_mask, cv2.bitwise_not(r_iris_dil))
        face_sclera = cv2.bitwise_or(l_sclera, r_sclera)
        # Feather sutil en el lagrimal
        face_sclera = cv2.GaussianBlur(face_sclera, (3, 3), 0)
        sclera_full = np.maximum(sclera_full, face_sclera)

        # ---------------------------------------------------------
        # D. Dientes (Apertura bucal + Umbral HSV reflectivo)
        # ---------------------------------------------------------
        p13 = to_full_px(13)   # Labio superior interno centro
        p14 = to_full_px(14)   # Labio inferior interno centro
        p10 = to_full_px(10)   # Frente
        p152 = to_full_px(152) # Mentón

        lip_gap = float(np.linalg.norm(p13 - p14))
        face_h = float(np.linalg.norm(p10 - p152))
        gap_ratio = lip_gap / max(1.0, face_h)

        if gap_ratio >= 0.025:
            # Boca abierta: aislar dientes dentro del polígono INNER_LIPS
            inner_lip_pts = np.array([to_full_px(i) for i in INNER_LIPS], dtype=np.int32)
            mouth_poly = np.zeros((h0, w0), dtype=np.uint8)
            cv2.fillPoly(mouth_poly, [inner_lip_pts], 255)
            # Erosión ligera para no tocar el borde del labio
            mouth_poly = cv2.erode(mouth_poly, np.ones((3, 3), np.uint8), iterations=1)

            # Extraer píxeles de alta claridad y baja saturación (esmalte dental)
            sat = img_hsv[:, :, 1]
            val = img_hsv[:, :, 2]
            teeth_bin = (mouth_poly > 0) & (sat < 85) & (val > 80)

            face_teeth = np.zeros((h0, w0), dtype=np.uint8)
            face_teeth[teeth_bin] = 255
            # Antialiasing subpíxel
            face_teeth = cv2.GaussianBlur(face_teeth, (3, 3), 0)
            teeth_full = np.maximum(teeth_full, face_teeth)

        # ---------------------------------------------------------
        # E. Piel Facial (Óvalo facial menos ojos, cejas y labios externos)
        # ---------------------------------------------------------
        skin_layer = np.zeros((h0, w0), dtype=np.uint8)
        oval_pts = np.array([to_full_px(i) for i in FACE_OVAL], dtype=np.int32)
        cv2.fillPoly(skin_layer, [oval_pts], 255)

        # Sustracción de cavidades oculares (dilatadas 3 px para proteger pestañas)
        k_eye = np.ones((5, 5), np.uint8)
        l_eye_dil = cv2.dilate(l_eye_mask, k_eye, iterations=1)
        r_eye_dil = cv2.dilate(r_eye_mask, k_eye, iterations=1)
        skin_layer = cv2.bitwise_and(skin_layer, cv2.bitwise_not(l_eye_dil))
        skin_layer = cv2.bitwise_and(skin_layer, cv2.bitwise_not(r_eye_dil))

        # Sustracción de cejas
        l_brow_pts = np.array([to_full_px(i) for i in LEFT_EYEBROW], dtype=np.int32)
        r_brow_pts = np.array([to_full_px(i) for i in RIGHT_EYEBROW], dtype=np.int32)
        brow_mask = np.zeros((h0, w0), dtype=np.uint8)
        cv2.fillPoly(brow_mask, [l_brow_pts], 255)
        cv2.fillPoly(brow_mask, [r_brow_pts], 255)
        brow_mask = cv2.dilate(brow_mask, np.ones((3, 3), np.uint8), iterations=1)
        skin_layer = cv2.bitwise_and(skin_layer, cv2.bitwise_not(brow_mask))

        # Sustracción de labios externos completos
        outer_lip_pts = np.array([to_full_px(i) for i in OUTER_LIPS], dtype=np.int32)
        lip_mask = np.zeros((h0, w0), dtype=np.uint8)
        cv2.fillPoly(lip_mask, [outer_lip_pts], 255)
        lip_mask = cv2.dilate(lip_mask, np.ones((3, 3), np.uint8), iterations=1)
        skin_layer = cv2.bitwise_and(skin_layer, cv2.bitwise_not(lip_mask))

        # Excluir cabello muy oscuro, gafas o viseras negras que caigan dentro del óvalo
        dark_occlusions = (img_hsv[:, :, 2] < 35) & (skin_layer > 0)
        skin_layer[dark_occlusions] = 0

        # Suavizado de bordes para transición natural de mandíbula
        skin_layer = cv2.GaussianBlur(skin_layer, (5, 5), 0)
        skin_full = np.maximum(skin_full, skin_layer)

    # -------------------------------------------------------------
    # 4. Exportación a TARGET_SIZE (512x512) en PNG y Raw BIN
    # -------------------------------------------------------------
    def save_layer(img_layer, name):
        resized = cv2.resize(img_layer, (TARGET_SIZE, TARGET_SIZE), interpolation=cv2.INTER_AREA)
        png_path = out_path / f"{name}.png"
        cv2.imwrite(str(png_path), resized)
        bin_path = out_path / f"{name}.bin"
        with open(bin_path, "wb") as f:
            f.write(resized.tobytes())
        return str(png_path)

    p_saved = save_layer(person_full, "person")
    sk_saved = save_layer(skin_full, "facial_skin")
    sc_saved = save_layer(sclera_full, "eye_sclera")
    ir_saved = save_layer(iris_full, "iris_pupil")
    t_saved = save_layer(teeth_full, "teeth")

    result = {
        "ok": True,
        "input": str(img_path),
        "output_dir": str(out_path),
        "faces_detected": len(confirmed_faces),
        "masks": {
            "person": p_saved,
            "facial_skin": sk_saved,
            "eye_sclera": sc_saved,
            "iris_pupil": ir_saved,
            "teeth": t_saved,
        }
    }
    print(json.dumps(result))
    return result


def main():
    parser = argparse.ArgumentParser(description="Generador neural de máscaras de segmentación")
    parser.add_argument("--input", required=True, help="Ruta de la imagen de entrada")
    parser.add_argument("--output-dir", required=True, help="Directorio donde guardar las máscaras")
    args = parser.parse_args()

    generate_all_masks(args.input, args.output_dir)


if __name__ == "__main__":
    main()
