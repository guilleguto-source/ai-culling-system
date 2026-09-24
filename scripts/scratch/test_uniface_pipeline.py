import sys
import cv2
import numpy as np

# BYPASS SSL para descargas de github en esta PC
import urllib3
urllib3.disable_warnings()
import requests
original_get = requests.get
def bypass_get(*args, **kwargs):
    kwargs['verify'] = False
    return original_get(*args, **kwargs)
requests.get = bypass_get

sys.path.insert(0, "backend")

# 1. Probar importación e inicialización de modelos
print("Inicializando modelos UniFace...")
try:
    from uniface import FaceAnalyzer
    from uniface.gaze import MobileGaze
    
    face_detector = FaceAnalyzer()
    gaze_estimator = MobileGaze()
    print("✓ Modelos UniFace inicializados correctamente.")
except Exception as e:
    print(f"❌ Error inicializando modelos: {e}")
    sys.exit(1)

# 2. Probar lectura de imagen y pipeline básico
print("Leyendo imagen de prueba...")
test_image_path = r"\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-08-09\IMG_0833.JPG"
img_bgr = cv2.imread(test_image_path)

if img_bgr is None:
    print(f"❌ No se pudo leer la imagen: {test_image_path}")
    sys.exit(1)

# Reducir a 2048px (como en la ingesta)
h, w = img_bgr.shape[:2]
if max(h, w) > 2048:
    scale = 2048 / max(h, w)
    img_bgr = cv2.resize(img_bgr, (int(w * scale), int(h * scale)))

img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
print(f"✓ Imagen leída y redimensionada: {img_bgr.shape}")

# 3. Probar classify_scene (que ahora llama a FaceAnalyzer y MobileGaze)
print("Ejecutando classify_scene...")
try:
    from services.scene_classifier import classify_scene
    scene_result = classify_scene(img_rgb, face_detector, gaze_estimator=gaze_estimator)
    print(f"✓ classify_scene finalizado. Tipo de escena: {scene_result.scene_type}")
    print(f"  Rostros encontrados: {scene_result.face_count}")
    for i in range(scene_result.face_count):
        print(f"  Rostro {i}: bbox={scene_result.face_bboxes[i]}, yaw={scene_result.face_yaws[i]:.1f}°, pitch={scene_result.face_pitches[i]:.1f}°")
except Exception as e:
    print(f"❌ Error en classify_scene: {e}")
    sys.exit(1)

# 4. Probar evaluate_eyes_fast (el parche modificado)
print("Ejecutando evaluate_eyes_fast...")
try:
    from services.face_assessment import evaluate_eyes_fast
    if scene_result.face_count > 0:
        eye_result = evaluate_eyes_fast(img_rgb, scene_result.eye_landmarks, scene_result.face_bboxes)
        print(f"✓ evaluate_eyes_fast finalizado. Algún ojo cerrado: {eye_result.any_closed_eyes}")
        for res in eye_result.face_results:
            print(f"  Rostro {res.face_index}: ojos_cerrados={res.has_closed_eyes}, ear={res.eye_aspect_ratio:.3f}")
    else:
        print("✓ No hay caras, saltando evaluación de ojos.")
except Exception as e:
    print(f"❌ Error en evaluate_eyes_fast: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n🚀 TODO OK! Los módulos de UniFace funcionan y el pipeline no se rompe.")
