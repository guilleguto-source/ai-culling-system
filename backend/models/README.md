# models/ — Directorio para modelos locales
# Coloca aquí los archivos descargados:
#   - yunet.onnx                  (YuNet face detector de OpenCV: ENCUENTRA las caras)
#   - face_landmarker.task        (MediaPipe: ANALIZA cada cara — ojos/mirada/sonrisa)
#   - clip_vit_b32_visual.onnx    (encoder visual CLIP ViT-B/32, embeddings 512-d)
#   - person_yolov8n.onnx         (detector de personas/cuerpos, protege el auto-crop)
#
# NOTA: eye_state.onnx quedó OBSOLETO (2026-07-16). Medido sobre el evento
# real: 97% de falsos "ojos cerrados"; el mismo ojo devolvía 0.00 u 0.87 según
# el recorte; ni a 4000px acertaba. Lo reemplaza face_landmarker.task.
#
# MediaPipe FaceLandmarker (3.6 MB) — atributos faciales:
#     pip install mediapipe
#     python -c "import truststore; truststore.inject_into_ssl(); \
#       import urllib.request; urllib.request.urlretrieve( \
#       'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task', \
#       'face_landmarker.task')"
#   Arquitectura: MediaPipe NO ve las caras chicas sobre la foto completa
#   (reescala a 192px), así que YuNet las encuentra y MediaPipe analiza cada
#   RECORTE ampliado. Bonus: si MediaPipe no halla cara en el recorte, la
#   detección de YuNet era basura (decoración) → filtro de validez gratis
#   (medido: en una foto YuNet vio 43 "caras" y solo 7 lo eran).
#   Coste: ~47 ms/foto (~1 min por evento de 1000).
#
# YOLOv8n (detector de personas, ~12 MB):
#     pip install ultralytics
#     yolo export model=yolov8n.pt format=onnx opset=12
#     → renombrar yolov8n.onnx a person_yolov8n.onnx y colocarlo aquí.
#   Sin este archivo el crop protege solo cuerpos derivados de rostros
#   detectados (gente de espaldas/perfil queda sin protección).
#
# Descarga YuNet desde:
# https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet
#
# CLIP ViT-B/32 (encoder visual, ONNX, 336 MB) — YA INSTALADO (2026-07-16).
#   Receta verificada en esta máquina:
#     pip install torch transformers onnx onnxscript truststore
#     python - <<'EOF'
#     import truststore; truststore.inject_into_ssl()   # el TLS de HuggingFace
#     # falla con el bundle de certifi (antivirus/proxy intercepta): truststore
#     # usa el almacén de certificados de Windows y resuelve. NO desactivar la
#     # verificación SSL.
#     import torch, onnx
#     from transformers import CLIPVisionModelWithProjection
#     m = CLIPVisionModelWithProjection.from_pretrained("openai/clip-vit-base-patch32").eval()
#     torch.onnx.export(
#         m, torch.randn(1, 3, 224, 224), "clip_tmp.onnx",
#         input_names=["pixel_values"], output_names=["image_embeds"],
#         dynamic_axes={"pixel_values": {0: "batch"}}, opset_version=17,
#     )
#     # OJO: torch exporta el grafo (101 KB) + los pesos aparte (.onnx.data).
#     # Consolidar en UN archivo, si no el .onnx suelto se rompe en silencio:
#     onnx.save_model(onnx.load("clip_tmp.onnx"), "clip_vit_b32_visual.onnx",
#                     save_as_external_data=False)
#     EOF
#   Verificación: dos fotos de la misma ráfaga deben dar similitud coseno
#   ~0.85+, y escenas distintas ~0.6. Si ambas dan valores similares, los
#   pesos no se cargaron.
#
#   La salida debe ser el vector de 512 dims (image_embeds). El servicio lo
#   normaliza L2 automáticamente. Sin este archivo, la app funciona igual pero
#   el ranking usa solo heurísticas (embedding_service.is_available() == False).
#
# emb_cache/ — caché de embeddings (.npy) generado automáticamente; se puede
# borrar sin riesgo (se regenera).

# arcface_r50.onnx — Reconocimiento de personas (Fase L, opcional)
#   Embedding de IDENTIDAD facial (512 dims). Habilita agrupar por persona y
#   "al menos una buena foto de cada uno". Sin este archivo, la app funciona
#   igual y face_identity.is_available() == False (la función se desactiva).
#   Descargar un ArcFace r50 (glint360k/ms1mv3) en ONNX, input 112x112 RGB
#   normalizado (x-0.5)/0.5, y guardarlo aquí como arcface_r50.onnx.
#   Verificación: dos fotos de la MISMA persona → similitud coseno ~0.5+;
#   personas distintas < 0.3. Umbral de agrupamiento en face_identity.py.
