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
# CLIP ViT-B/32 (encoder visual, ONNX):
#   Opción A — export directo con Python (recomendado, ~350 MB de deps temporales):
#     pip install torch transformers onnx
#     python - <<'EOF'
#     import torch
#     from transformers import CLIPVisionModelWithProjection
#     m = CLIPVisionModelWithProjection.from_pretrained("openai/clip-vit-base-patch32")
#     m.eval()
#     x = torch.randn(1, 3, 224, 224)
#     torch.onnx.export(
#         m, x, "clip_vit_b32_visual.onnx",
#         input_names=["pixel_values"], output_names=["image_embeds"],
#         dynamic_axes={"pixel_values": {0: "batch"}}, opset_version=17,
#     )
#     EOF
#   Opción B — descargar un export ONNX ya hecho (p.ej. Xenova/clip-vit-base-patch32
#   en HuggingFace, archivo onnx/vision_model.onnx) y renombrarlo.
#
#   La salida debe ser el vector de 512 dims (image_embeds). El servicio lo
#   normaliza L2 automáticamente. Sin este archivo, la app funciona igual pero
#   el ranking usa solo heurísticas (embedding_service.is_available() == False).
#
# emb_cache/ — caché de embeddings (.npy) generado automáticamente; se puede
# borrar sin riesgo (se regenera).
