# models/ — Directorio para modelos ONNX locales
# Coloca aquí los archivos .onnx descargados:
#   - yunet.onnx                  (YuNet face detector de OpenCV)
#   - eye_state.onnx              (clasificador de ojos abiertos/cerrados)
#   - clip_vit_b32_visual.onnx    (encoder visual CLIP ViT-B/32, embeddings 512-d)
#   - person_yolov8n.onnx         (detector de personas/cuerpos, protege el auto-crop)
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
