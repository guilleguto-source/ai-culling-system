# Revisión de Arquitectura: Migración a UniFace

He revisado en detalle tu propuesta de migración hacia **UniFace** y he analizado cómo impactaría a la arquitectura actual (`backend/services/`). 

Mi veredicto es **SÍ, vale totalmente la pena implementarlo**. Además, tras revisar el código real, el plan original tenía un detalle equivocado que aquí corrijo.

## 🔍 Lo que ya tienes (revisión del código real)

Antes de planificar, revisé los archivos reales:
- **`face_identity.py`** ya usa `arcface_r50.onnx` internamente — el modelo ArcFace de 512-d ya está en el sistema.
- **`face_assessment.py`** usa YuNet (para bounding boxes) + un modelo ONNX propio para detectar ojos cerrados (vía EAR / Eye Aspect Ratio).
- **`blink_classifier.py`** es el modelo custom de ojos que UniFace reemplazaría directamente con `face.attributes.eyes_open`.

**Conclusión real:** Ya no es una migración de ArcFace a ArcFace. Es eliminar la capa de "plomería" (YuNet → MediaPipe → blink ONNX) y reemplazarla por UniFace que hace todo eso en un solo pipeline optimizado.

## 🎯 Por qué sigue valiendo la pena
1. **Rendimiento masivo**: Actualmente el sistema encadena múltiples modelos (YuNet para bounding boxes → MediaPipe para landmarks → Modelo ONNX propio para ojos → Modelo propio/CLIP para identidad). UniFace condensa todo esto en un solo paso optimizado. Menos transferencia en RAM, menos tiempos de carga.
2. **Nuevas Métricas Deterministas**: Poder tener `face.quality` (eDifFIQA), `pose` (pitch, yaw, roll) y `gaze` de caja es el "santo grial" del culling. Actualmente tenemos heurísticas complejas, pero poder hacer algo como `if face.pose.yaw > 30` para descartar a alguien que no mira a cámara limpiará muchísimo el código en `culling.py`.
3. **Identidad Sólida**: ArcFace es el estándar de la industria para reconocimiento facial. Sus embeddings (512-d) agruparán a las personas con mucha más precisión que lo que tenemos ahora.

---

> [!WARNING]
> ## 🚨 Corrección Crítica: El Modelo de Gustos (`taste_model.py`)
>
> En tu plan sugieres reentrenar el `taste_model.py` usando los embeddings de ArcFace (512-d) en lugar de los actuales (CLIP 768-d). **No debemos hacer esto.**
> 
> - **ArcFace** está diseñado explícitamente para filtrar TODO excepto la identidad. Ignora la iluminación, la composición e incluso *la expresión facial* (para que una persona seria y sonriendo tengan el mismo vector).
> - **El Taste Model** actualmente rankea fotos completas aprendiendo tus gustos estéticos (color, luces, encuadres, etc.).
> 
> **La solución correcta:** 
> Debemos mantener una arquitectura de "doble vía". 
> 1. Usar **CLIP (768-d)** para el análisis global de la foto y el `taste_model.py`.
> 2. Usar **UniFace (ArcFace 512-d)** única y exclusivamente para el clustering de personas (`clustering.py` y `face_identity.py`) y la evaluación de sus expresiones/ojos.

---

## 🛠️ Plan de Implementación Ajustado

Si estás de acuerdo con proceder, este será mi orden de ejecución estricto:

### Fase 1: Preparación Segura (No-Regresión)
- [ ] Mover los archivos actuales (`face_detector.py`, `face_landmarks.py`, `blink_classifier.py`) a una carpeta `legacy/` para tener un punto de rollback.
- [ ] Instalar dependencias de UniFace (o integrar su binario ONNX local si ya lo provees).

### Fase 2: Integración Core (Reemplazo de Detección)
- [ ] Modificar `face_assessment.py` e `ingester.py` para llamar a `UniFace.detect()` en lugar de YuNet.
- [ ] Eliminar `blink_classifier.py` (reemplazado por `face.attributes.eyes_open` nativo).
- [ ] Eliminar dependencia de MediaPipe en `face_mesh.py` (reemplazada por landmarks 5-pt de UniFace).
- [ ] Incorporar los nuevos scores (`face.quality`, `pose`, `gaze`) en los diccionarios de resultados que guarda `analysis_store.py`.

### Fase 3: Identidad y Culling
- [ ] Simplificar `face_identity.py`: en vez de cargar `arcface_r50.onnx` manualmente con alineación propia, delegar la extracción del embedding a `face.embedding` de UniFace (que ya hace alineación internamente). Mismo output, menos código.
- [ ] Ajustar threshold en `face_identity.py`: actualmente `IDENTITY_THRESHOLD = 0.38`, recalibrar hacia `0.45-0.55` si el pipeline de alineación de UniFace resulta en una distribución ligeramente diferente.
- [ ] Modificar `culling.py` para aprovechar las nuevas métricas (penalizar perfiles con `|face.pose.yaw| > 30°`, favorecer calidad con `face.quality`).

### Fase 4: Pruebas de Estrés
- [ ] Correr un test de ingestión sobre un par de fotos.
- [ ] Validar que la UI en el "Inspector" siga mostrando las caras correctamente recortadas y evaluadas.

## ❓ Preguntas Abiertas
Antes de empezar a programar:
1. ¿Ya tienes la librería `uniface` disponible localmente o instalada en el entorno actual de Python para poder importarla (ej. `import uniface`)?
2. ¿Aprobado mantener CLIP para la estética global y usar ArcFace solo para identidad?
