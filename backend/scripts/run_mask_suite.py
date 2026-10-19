"""
run_mask_suite.py — Harness de auditoría y validación visual de máscaras IA.
Ejecuta la inferencia sobre el set de prueba y genera collages de auditoría
con zoom 100% y evaluación numérica de las compuertas de calidad Lightroom.
"""
import sys
import os
import argparse
from pathlib import Path

# Añadir backend al path para importar services
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

from services.mask_generator import generate_all_masks, load_image

LEVELS = {
    1: ["IMG_4821.jpg", "IMG_4864.jpg"],
    2: ["IMG_0341.JPG", "IMG_4899.jpg", "IMG_6901.jpg", "IMG_7640-2.jpg", "IMG_9378.jpg", "IMG_9466.jpg"],
    3: ["IMG_0308.JPG", "IMG_4976.jpg", "IMG_6826.jpg", "IMG_6883.jpg", "IMG_9372.jpg", "_BLR9616.jpg", "_BLR9680.jpg", "_BLR9702.jpg"],
    4: ["IMG_0257.JPG"]
}

DEFAULT_FOLDER = Path("C:/Users/Guill/Desktop/Pruebas MAscaras")
AUDIT_DIR = Path(__file__).resolve().parent.parent / "models" / "cache" / "mattes" / "suite_audit"


def render_overlay(rgb_img: np.ndarray, masks: dict) -> np.ndarray:
    """Renderiza superposición de colores estilo Lightroom sobre la imagen RGB."""
    h, w = rgb_img.shape[:2]
    overlay = rgb_img.copy().astype(np.float32)

    # Colores RGB y opacidades
    # Pop: Rojo (255, 30, 30), alpha 0.35
    # Piel: Naranja (255, 130, 0), alpha 0.40
    # Esclera: Cian (0, 230, 255), alpha 0.65
    # Iris: Azul vibrante (30, 100, 255), alpha 0.70
    # Dientes: Amarillo brillante (255, 255, 0), alpha 0.70

    layers = [
        ("person", (255, 30, 30), 0.35),
        ("facial_skin", (255, 130, 0), 0.40),
        ("eye_sclera", (0, 230, 255), 0.65),
        ("iris_pupil", (30, 100, 255), 0.70),
        ("teeth", (255, 255, 0), 0.70),
    ]

    for name, color, alpha in layers:
        m_path = masks.get(name)
        if not m_path or not Path(m_path).exists():
            continue
        m = cv2.imread(str(m_path), cv2.IMREAD_GRAYSCALE)
        if m is None:
            continue
        m_resized = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
        m_norm = (m_resized.astype(np.float32) / 255.0) * alpha

        col_arr = np.array(color, dtype=np.float32)
        for c in range(3):
            overlay[:, :, c] = overlay[:, :, c] * (1.0 - m_norm) + col_arr[c] * m_norm

    return np.clip(overlay, 0, 255).astype(np.uint8)


def create_audit_collage(img_path: Path, masks: dict, out_file: Path):
    """Crea un collage comparativo de alta resolución con vista general y zoom 100%."""
    img_rgb = load_image(img_path)
    h0, w0 = img_rgb.shape[:2]

    # Vista general con overlay
    overlay_full = render_overlay(img_rgb, masks)

    # Redimensionar vista general a ancho estándar de 1280 px
    std_w = 1280
    std_h = int(round(h0 * (std_w / w0)))
    orig_small = cv2.resize(img_rgb, (std_w, std_h), interpolation=cv2.INTER_AREA)
    over_small = cv2.resize(overlay_full, (std_w, std_h), interpolation=cv2.INTER_AREA)

    # Cabecera / Etiqueta de la imagen
    top_row = np.hstack([orig_small, over_small])

    # Buscar rostro principal para crop de 100%
    from services.app_paths import get_models_dir
    yunet = get_models_dir() / "yunet.onnx"
    detector = cv2.FaceDetectorYN.create(str(yunet), "", (w0, h0), score_threshold=0.55, nms_threshold=0.30)
    _, faces = detector.detect(cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR))

    crop_rows = []
    if faces is not None and len(faces) > 0:
        # Filtrar duplicados con IoU
        from services.mask_generator import nms_boxes
        boxes = [[int(f[0]), int(f[1]), int(f[2]), int(f[3])] for f in faces]
        scores = [float(f[14]) for f in faces]
        keep = nms_boxes(boxes, scores, iou_thresh=0.35)
        faces_confirmed = [faces[i] for i in keep]

        # Tomar los 2 rostros más grandes
        faces_sorted = sorted(faces_confirmed, key=lambda f: f[2] * f[3], reverse=True)[:2]
        for idx, f in enumerate(faces_sorted):
            fx, fy, fw, fh = int(f[0]), int(f[1]), int(f[2]), int(f[3])
            # Margen alrededor del rostro
            margin = int(max(fw, fh) * 0.25)
            x0 = max(0, fx - margin)
            y0 = max(0, fy - margin)
            x1 = min(w0, fx + fw + margin)
            y1 = min(h0, fy + fh + margin)

            crop_orig = img_rgb[y0:y1, x0:x1]
            crop_over = overlay_full[y0:y1, x0:x1]

            # Redimensionar crops a altura fija de 400 px
            target_h = 400
            crop_w = int(round((x1 - x0) * (target_h / max(1, (y1 - y0)))))
            c_orig = cv2.resize(crop_orig, (crop_w, target_h))
            c_over = cv2.resize(crop_over, (crop_w, target_h))

            # Añadir etiqueta
            cv2.putText(c_orig, f"Rostro {idx+1} (100% Crop)", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            cv2.putText(c_over, "Overlay Lightroom", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

            # Planos individuales para ese crop
            planes = []
            for m_name in ["iris_pupil", "eye_sclera", "teeth", "facial_skin"]:
                m_path = masks.get(m_name)
                if m_path and Path(m_path).exists():
                    m = cv2.imread(str(m_path), cv2.IMREAD_GRAYSCALE)
                    m_crop = cv2.resize(m, (w0, h0))[y0:y1, x0:x1]
                    m_disp = cv2.resize(m_crop, (crop_w, target_h))
                    m_bgr = cv2.cvtColor(m_disp, cv2.COLOR_GRAY2RGB)
                    cv2.putText(m_bgr, m_name.replace("_", " ").title(), (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    planes.append(m_bgr)

            face_row = np.hstack([c_orig, c_over] + planes[:4])
            if face_row.shape[1] < top_row.shape[1]:
                pad = np.zeros((target_h, top_row.shape[1] - face_row.shape[1], 3), dtype=np.uint8)
                face_row = np.hstack([face_row, pad])
            else:
                face_row = cv2.resize(face_row, (top_row.shape[1], target_h))
            crop_rows.append(face_row)

    if crop_rows:
        collage = np.vstack([top_row] + crop_rows)
    else:
        collage = top_row

    out_file.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_file), cv2.cvtColor(collage, cv2.COLOR_RGB2BGR))
    print(f"  -> Audit Collage guardado: {out_file.name} ({collage.shape[1]}x{collage.shape[0]} px)")


def run_suite(level: int = 1, folder: Path = DEFAULT_FOLDER):
    """Ejecuta la suite para un nivel determinado."""
    if level not in LEVELS:
        print(f"Nivel {level} desconocido. Niveles válidos: {list(LEVELS.keys())}")
        return

    filenames = LEVELS[level]
    print(f"\n=======================================================")
    print(f" INICIANDO AUDITORIA NIVEL {level} ({len(filenames)} fotos objetivo)")
    print(f" Directorio: {folder}")
    print(f"=======================================================")

    results = []
    for fn in filenames:
        img_path = folder / fn
        if not img_path.exists():
            print(f"[!] No encontrada: {fn}")
            continue

        base_name = img_path.stem
        out_mask_dir = AUDIT_DIR / "mattes" / base_name
        print(f"\n[*] Procesando: {fn} ...")

        # Generar máscaras
        res = generate_all_masks(str(img_path), str(out_mask_dir))

        # Rutas de los 5 PNGs
        masks = {
            "person": out_mask_dir / "person.png",
            "facial_skin": out_mask_dir / "facial_skin.png",
            "eye_sclera": out_mask_dir / "eye_sclera.png",
            "iris_pupil": out_mask_dir / "iris_pupil.png",
            "teeth": out_mask_dir / "teeth.png",
        }

        # Generar collage visual de auditoría
        audit_jpg = AUDIT_DIR / f"{base_name}_audit.jpg"
        create_audit_collage(img_path, masks, audit_jpg)

        results.append({
            "file": fn,
            "collage": audit_jpg,
            "masks": masks
        })

    print(f"\n[OK] Auditoria Nivel {level} finalizada. Archivos generados en:\n    {AUDIT_DIR}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Runner de suite de máscaras IA")
    parser.add_argument("--level", type=int, default=1, help="Nivel de prueba (1: Parejas, 2: Familias, 3: Grupos, 4: Multitud)")
    parser.add_argument("--folder", type=str, default=str(DEFAULT_FOLDER), help="Carpeta de imágenes")
    args = parser.parse_args()

    run_suite(args.level, Path(args.folder))
