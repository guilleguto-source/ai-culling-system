# Plan de Corrección: Segmentación de Cuerpo Completo en Grupos Masivos (Paridad Sujeto Lightroom)

## 1. Causa Raíz Identificada
- En `IMG_0257` (30+ niños en plano general), `selfie_segmenter.tflite` solo cubre el 3.4% de la imagen porque está optimizado para 1-2 personas en plano medio/primer plano.
- En el collage de auditoría (`IMG_0257_audit.jpg`), solo se observaba tinte en los rostros porque correspondía a la capa `facial_skin` (YuNet + FaceMesh), mientras que `person.png` (Sujeto Pop) estaba casi vacía.

---

## 2. Arquitectura Propuesta: Tiled Hybrid Subject Segmentation
Para igualar la selección de "Sujeto" de Lightroom en grupos masivos:
1. **Detección Global de Personas:** Ejecutar `person_yolov8n.onnx` (`detect_persons`) para localizar todos los cuerpos de la escena (en `IMG_0257` detecta 20 cuerpos completos).
2. **Segmentación por Recorte (Tiled Segmentation):**
   - Para cada persona detectada, extraer el crop con 10% de margen.
   - Enviar cada crop individual a `selfie_segmenter` (donde cada niño ocupa el 100% del frame, permitiendo que el modelo opere en su rango óptimo de confianza con mean > 0.45 y max 1.0).
3. **Anatomical Face Fallback:** Para cualquier rostro YuNet no englobado en una caja de persona, proyectar la extensión anatómica del torso y segmentar el recorte.
4. **Fusión Máxima:** Combinar la máscara global con todos los recortes segmentados (`np.maximum`), preservando alpha continuo y bordes limpios sin invadir el césped.

---

## 3. Archivos Afectados
- `backend/services/mask_generator.py`: Lógica de `person.png` con soporte híbrido global + recortes YOLOv8/YuNet.
- `backend/scripts/run_mask_suite.py`: Re-generación del collage de auditoría `IMG_0257_audit.jpg`.
- `docs/audit_mattes/IMG_0257_audit.jpg`: Actualización del registro visual.

---

## 4. Checklist de Validación
- [ ] Implementar función de segmentación por baldosas en `mask_generator.py`.
- [ ] Ejecutar prueba de verificación en `IMG_0257.JPG`.
- [ ] Generar nuevo collage de auditoría `IMG_0257_audit.jpg` con cuerpos y ropa tintados en rojo/naranja.
- [ ] Re-procesar sidecars XMP de la sesión `Giler` en el NAS.
