# Diseño: Mejora de selección — gates técnicos + embeddings + feedback Lightroom

**Fecha**: 2026-07-15
**Estado**: Aprobado

## Problema

El score estético actual (`aesthetic_assessment.py`) usa 3 heurísticas genéricas
(colorfulness, contraste RMS, proxy de tercios por Sobel) que ignoran dónde están
las personas. El usuario fotografía eventos con prioridad: **grupos > momentos >
retratos > detalles**. En grupos, lo que decide la mejor foto es que todos salgan
bien (ojos abiertos, caras nítidas), no los tercios. El taste model actual solo
puede aprender pesos sobre 3 features programadas: nunca capturará gesto,
instante o mirada.

Presupuesto de cómputo: puede tardar más (~0.5-2 s extra por foto aceptable).

## Solución: 3 capas dentro de cada cluster

### Capa 1 — Gates técnicos (extiende `face_assessment.py`)

- **Nitidez por rostro**: varianza del Laplaciano calculada en el crop de cada
  cara detectada por YuNet (no en la imagen completa). Se agrega al resultado
  por rostro.
- **Ojos cerrados**: ya existe (EAR rápido + OCEC ONNX).
- **Regla de descarte relativa, nunca absoluta**: una foto queda fuera del
  ranking solo si otra foto *del mismo cluster* no tiene ese defecto
  (p.ej. hay alternativa con todos los ojos abiertos, o con la cara principal
  nítida). Si todas las fotos del cluster tienen el defecto, ninguna se
  descarta — no se pierde el único registro de un momento.
- Los gates eliminan candidatas ANTES del ranking por gusto: técnica ≠ gusto.

### Capa 2 — Embeddings (`backend/services/embedding_service.py`, nuevo)

- Modelo: **CLIP ViT-B/32 image encoder, ONNX**, ejecución local con
  onnxruntime (ya en el stack). ~150 MB, descarga única a `backend/models/`
  (mismo patrón que los modelos YuNet/OCEC existentes; instrucciones en
  `backend/models/README.md`).
- Entrada: `thumb_ai` (lado largo 1600 px, se redimensiona a 224×224 con el
  preprocesado estándar CLIP). Salida: vector float32 de 512 dims, normalizado L2.
- Coste estimado: ~0.1-0.3 s/foto en CPU.
- **Caché en disco**: keyed por `(path, mtime)`. Re-correr un evento no
  re-embebe fotos sin cambios.

### Capa 3 — Gusto (reescribe el interior de `taste_model.py`, misma interfaz pública)

- **Almacén de ejemplos**: SQLite en `backend/models/taste_examples.db`.
  Esquema: `id, embedding BLOB, label INTEGER (+1/-1), source TEXT
  ('duel'|'lightroom'), event_dir TEXT, created_at TEXT, embedding_dim INTEGER,
  model_version TEXT`.
- **Scorer**: regresión logística (scikit-learn, ya en el stack) entrenada
  sobre los embeddings almacenados. Re-entrena al agregar ejemplos (barato:
  cientos de vectores de 512 dims).
- **Fallback frío**: con < 50 ejemplos, el ranking usa las heurísticas actuales
  (`evaluate_aesthetics_fast`) + ratio de ojos abiertos como desempate. La
  interfaz `predict_score` / `learn_preference` / `is_trained` se conserva para
  no romper `main.py`.
- El pickle SGD actual (`user_taste_model.pkl`) queda obsoleto; se ignora si
  existe (los ejemplos nuevos parten de cero — el historial previo son 3
  features, incompatible).

## Fuentes de entrenamiento

1. **Duelos (existente, mejorado)**: "Elegir esta" → ganadora = ejemplo +1,
   perdedora = ejemplo −1, guardando embeddings. El re-export XMP inmediato
   (ya implementado) se mantiene.
2. **Sync Lightroom (nuevo)**: endpoint `POST /reimport_xmp {directory}` +
   botón "Sincronizar desde Lightroom" en la UI.
   - Relee los XMP (sidecar para RAW, embebido para JPEG) del directorio ya
     exportado.
   - Compara el label actual contra lo que el sistema exportó (según
     `ratings_mapping` de settings, labels en español: Roja/Verde/Azul…).
   - Foto que el usuario **subió** de categoría → ejemplo +1; que **bajó** →
     ejemplo −1. Sin cambio → no genera ejemplo.
   - Respuesta: conteo de correcciones detectadas e incorporadas.

## Ranking final dentro del cluster

```
candidatas = cluster
supervivientes = gates_técnicos(candidatas)      # relativo al cluster
si taste_model.is_trained (≥50 ejemplos):
    representative = argmax(score_embeddings(supervivientes))
si no:
    representative = argmax(heurísticas + desempate ojos abiertos)
```

## Degradación y errores

- **ONNX de CLIP ausente/corrupto**: `embedding_service` reporta no disponible;
  el pipeline corre solo con Capa 1 + heurísticas. Log WARNING claro, sin crash.
- **Versionado**: cada ejemplo guarda `embedding_dim` y `model_version`. Si se
  cambia el modelo de embeddings en el futuro, los ejemplos incompatibles se
  excluyen del entrenamiento (no se borran).
- **SQLite corrupto**: se renombra a `.bak` y se recrea vacío; log ERROR.

## Testing

- Gates: fixtures sintéticas (cara nítida vs desenfocada por blur gaussiano;
  cluster donde todas son borrosas → ninguna descartada).
- Reimport XMP: sidecars de ejemplo con labels modificados → verifica signo de
  los ejemplos generados.
- Embeddings: smoke test (shape 512, norma L2 ≈ 1, determinismo entre corridas,
  caché hit por mtime).
- Fallback: sin ONNX → pipeline completo termina y usa heurísticas.

## Fuera de alcance (YAGNI)

- Reconocimiento de personas específicas (face recognition/identidad).
- Scoring por API externa o VLM en la nube.
- UI de explicabilidad del score.
- Migración del historial del SGD anterior.
