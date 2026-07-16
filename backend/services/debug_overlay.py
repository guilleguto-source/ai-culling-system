import cv2
import numpy as np
import json
from pathlib import Path
from PIL import Image
import io
from services.analysis import PhotoAnalysis

def get_max_focus_block(img_rgb: np.ndarray, grid: int = 5) -> tuple[int, int, int, int]:
    """Retorna el bounding box (x, y, w, h) del bloque 5x5 más nítido."""
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    h, w = lap.shape
    best_var = -1.0
    best_bbox = (0, 0, w, h)
    for i in range(grid):
        for j in range(grid):
            x1 = j * w // grid
            y1 = i * h // grid
            x2 = (j + 1) * w // grid
            y2 = (i + 1) * h // grid
            block = lap[y1:y2, x1:x2]
            if block.size:
                v = float(block.var())
                if v > best_var:
                    best_var = v
                    best_bbox = (x1, y1, x2 - x1, y2 - y1)
    return best_bbox

def draw_debug_overlay(img_rgb: np.ndarray, analysis: PhotoAnalysis) -> np.ndarray:
    """Dibuja los recuadros de depuración sobre la imagen en OpenCV."""
    # Hacer una copia para no alterar el original
    img = img_rgb.copy()
    h, w = img.shape[:2]

    # 1. Obtener bloque de enfoque máximo
    focus_bbox = get_max_focus_block(img)
    fx, fy, fw, fh = focus_bbox

    # Lógica de coincidencia de enfoque
    has_faces = len(analysis.face_bboxes) > 0
    is_intentional = False
    
    # Verificar si el centro del bloque de enfoque cae dentro de alguna cara
    fcx, fcy = fx + fw // 2, fy + fh // 2
    for bbox in analysis.face_bboxes:
        # En el análisis, bboxes están relativos a thumb_ai (usualmente 1600px).
        # Aseguramos coordenadas absolutas relativas a las dimensiones de img
        # (ya que img es 1600px, pero escalamos por si acaso)
        rx, ry, rw, rh = bbox
        if rx <= fcx <= rx + rw and ry <= fcy <= ry + rh:
            is_intentional = True
            break

    # Determinar color del recuadro de enfoque (BGR)
    if has_faces:
        focus_color = (0, 255, 0) if is_intentional else (0, 140, 255) # Verde si coincide, Naranja si no
        focus_label = "Max Focus (OK)" if is_intentional else "Max Focus (Shifted!)"
    else:
        # Detalle sin caras
        focus_color = (0, 255, 255) # Amarillo
        focus_label = "Max Focus (Detail)"

    # Dibujar recuadro de enfoque (discontinuo simulado con OpenCV)
    # Dibujamos líneas discontinuas
    draw_dashed_rect(img, (fx, fy), (fx + fw, fy + fh), focus_color, thickness=3, label=focus_label)

    # 2. Dibujar caras detectadas
    for i, bbox in enumerate(analysis.face_bboxes):
        rx, ry, rw, rh = bbox
        # Recuadro verde continuo para rostros
        cv2.rectangle(img, (rx, ry), (rx + rw, ry + rh), (0, 200, 0), 3)
        
        # Puntuación de nitidez
        sharp = analysis.face_sharpness[i] if i < len(analysis.face_sharpness) else 0.0
        closed_text = " (CLOSED)" if analysis.any_closed_eyes and i == 0 else "" # OCEC simple
        text = f"Face {i}: {sharp:.1f}{closed_text}"
        cv2.putText(img, text, (rx, ry - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    # 3. Dibujar crop propuesto (azul)
    # Si tenemos propuesta de crop en el snapshot, pero aquí solo tenemos el análisis.
    # El crop se calcula en decision.py, pero podemos emular la zona de crop si se requiere.
    # Si el crop no está pre-calculado, no lo pintamos o si lo pintamos si se provee.
    # Pero el crop depende del crop_dict en los resultados finales.
    # Para hacerlo dinámico, si no hay crop_dict, podemos estimarlo o simplemente omitirlo si no aplica.

    # 4. Dibujar región de saliencia (amarillo)
    if analysis.saliency_region:
        sx, sy, sw, sh = analysis.saliency_region
        cv2.rectangle(img, (sx, sy), (sx + sw, sy + sh), (0, 255, 255), 2)
        cv2.putText(img, "Saliency", (sx, sy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

    # 5. Escribir texto informativo de exposición
    exp_text = f"Scene: {analysis.scene_type} | Blur: {analysis.blur_score:.1f}"
    exp_text_2 = f"Skin: {analysis.pre_skin_lum} | Global: {analysis.pre_global_lum:.2f} | Clip: {analysis.pre_clip_frac:.2%}"
    
    cv2.putText(img, exp_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 3)
    cv2.putText(img, exp_text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 1)
    
    cv2.putText(img, exp_text_2, (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(img, exp_text_2, (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 1)

    return img

def draw_dashed_rect(img, pt1, pt2, color, thickness=1, style='dashed', gap=10, label=""):
    """Dibuja un rectángulo con bordes discontinuos en OpenCV."""
    x1, y1 = pt1
    x2, y2 = pt2
    
    # Dibujar líneas discontinuas arriba y abajo
    for x in range(x1, x2, gap * 2):
        cv2.line(img, (x, y1), (min(x + gap, x2), y1), color, thickness)
        cv2.line(img, (x, y2), (min(x + gap, x2), y2), color, thickness)
        
    # Dibujar líneas discontinuas izquierda y derecha
    for y in range(y1, y2, gap * 2):
        cv2.line(img, (x1, y), (x1, min(y + gap, y2)), color, thickness)
        cv2.line(img, (x2, y), (x2, min(y + gap, y2)), color, thickness)
        
    if label:
        cv2.putText(img, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, thickness)
