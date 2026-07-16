"""
aesthetic_assessment.py — Evaluación estética heurística (OpenCV).

ROL: FALLBACK FRÍO. El camino principal para rankear dentro de un cluster es
el taste model sobre embeddings CLIP (services/taste_model.py). Estas
heurísticas (color, contraste, composición por tercios) solo se usan cuando
el taste model aún no tiene suficientes ejemplos (< MIN_EXAMPLES) o el modelo
CLIP no está descargado. Rápidas y sin dependencias, pero limitadas: no
capturan gesto, mirada ni instante — por eso son respaldo, no el criterio.
"""
import logging
import cv2
import numpy as np

logger = logging.getLogger(__name__)


def compute_colorfulness(img_rgb: np.ndarray) -> float:
    """
    Calcula el "Colorfulness" según Hasler y Süsstrunk (2003).
    Mide cuán vivos y variados son los colores en la imagen.
    """
    # Evita dividir por cero o problemas de formato separando los canales.
    # El array viene en orden RGB (img_rgb), no BGR.
    (R, G, B) = cv2.split(img_rgb.astype("float"))

    # rg = R - G
    rg = np.absolute(R - G)
    # yb = 0.5 * (R + G) - B
    yb = np.absolute(0.5 * (R + G) - B)

    # Desviación estándar y media de rg y yb
    stdRoot = np.sqrt((np.std(rg) ** 2) + (np.std(yb) ** 2))
    meanRoot = np.sqrt((np.mean(rg) ** 2) + (np.mean(yb) ** 2))

    # Colorfulness
    colorfulness = stdRoot + (0.3 * meanRoot)
    return colorfulness


def compute_contrast(img_gray: np.ndarray) -> float:
    """
    Calcula el contraste dinámico usando la desviación estándar RMS.
    Imágenes con bajo contraste (lavadas) tendrán un valor bajo.
    """
    return np.std(img_gray)


def compute_rule_of_thirds_score(img_gray: np.ndarray) -> float:
    """
    Evalúa de forma aproximada si las áreas de alto contraste caen en los 
    puntos fuertes de la regla de los tercios.
    """
    h, w = img_gray.shape
    if h < 3 or w < 3:
        return 0.5
        
    # Calcular gradiente/saliencia básica (magnitud Sobel)
    grad_x = cv2.Sobel(img_gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(img_gray, cv2.CV_32F, 0, 1, ksize=3)
    saliency = cv2.magnitude(grad_x, grad_y)
    
    # Crear máscara de tercios (matriz de pesos espaciales)
    weight_mask = np.ones((h, w), dtype=np.float32) * 0.5
    
    # Coordenadas de los tercios
    x1, x2 = w // 3, 2 * w // 3
    y1, y2 = h // 3, 2 * h // 3
    
    # Aumentar peso en las 4 intersecciones (radius ~ 15% del ancho)
    r = int(min(h, w) * 0.15)
    for cx, cy in [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]:
        # Dibujar círculos gaussianos o sólidos para las intersecciones
        cv2.circle(weight_mask, (cx, cy), r, 1.0, -1)
        
    # Calcular el score ponderado
    total_saliency = np.sum(saliency)
    if total_saliency == 0:
        return 0.5
        
    weighted_saliency = np.sum(saliency * weight_mask)
    score = weighted_saliency / total_saliency
    # Normalizamos (score típicamente va de 0.5 a 1.0)
    return min(1.0, max(0.0, (score - 0.5) * 2.0))


def evaluate_aesthetics_fast(img_rgb: np.ndarray, return_features: bool = False) -> float | tuple[float, float, float]:
    """
    Calcula un score estético global [0.0 - 1.0] combinando heurísticas.
    Si return_features=True, devuelve (colorfulness, contrast, rule_of_thirds).
    Ideal para desempatar fotos de una misma ráfaga.
    """
    if img_rgb.size == 0:
        return (0.0, 0.0, 0.5) if return_features else 0.5

    # Reducir imagen para procesamiento ultrarrápido
    h, w = img_rgb.shape[:2]
    max_dim = 256
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img_small = cv2.resize(img_rgb, (int(w * scale), int(h * scale)))
    else:
        img_small = img_rgb
        
    img_gray = cv2.cvtColor(img_small, cv2.COLOR_RGB2GRAY)

    # 1. Colorfulness (típicamente de 0 a 100+, saturamos en 80)
    c_score = compute_colorfulness(img_small)
    c_norm = min(1.0, c_score / 80.0)
    
    # 2. Contraste (típicamente de 10 a 80, saturamos en 60)
    contr_score = compute_contrast(img_gray)
    contr_norm = min(1.0, contr_score / 60.0)
    
    # 3. Composición (Regla de los Tercios proxy)
    comp_norm = compute_rule_of_thirds_score(img_gray)
    
    # Combinación ponderada predeterminada
    # (El contraste y la composición son más importantes que la saturación pura)
    final_score = (0.4 * contr_norm) + (0.4 * comp_norm) + (0.2 * c_norm)
    
    if return_features:
        return (float(c_norm), float(contr_norm), float(comp_norm))
    return float(np.clip(final_score, 0.0, 1.0))
