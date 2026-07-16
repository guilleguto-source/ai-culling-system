# Diseño: Calibración y atributos faciales (Fase G)

**Fecha**: 2026-07-16
**Estado**: Borrador para aprobación

## Problema

El detector actual (`eye_state.onnx`) es inservible sobre las fotos del
usuario. Medido:

- 97% de las fotos tendrían "ojos cerrados" con el criterio absoluto.
- El mismo ojo da 0.00 u 0.87 según cómo se recorte el parche.
- A 30-50px entre ojos: 75% dictaminadas "cerrado", mediana de prob_abierto
  0.01 (confiadamente equivocado).
- Subir la resolución a 4000px (109px entre ojos) NO lo arregla.
- Contradice la verdad de campo del usuario (IMG_8375: ojos abiertos).

Causa: el modelo no distingue "no mira a cámara" de "ojos cerrados", y es
errático fuera de caras grandes y frontales.

Además no existe forma de MEDIR si un detector funciona: cada juicio depende
de que el usuario señale fotos sueltas.

## Principio rector

**Comparación para lo subjetivo, etiqueta absoluta para lo objetivo.**

- El **duelo** (comparar 2 fotos) ya captura el gusto — incluye implícitamente
  "prefiero las que miran a cámara y sonríen". Funciona hoy con CLIP.
- La **calibración** (etiqueta absoluta) sirve para atributos verificables:
  ojos cerrados, mirada, sonrisa. Preguntar "¿cuánta alegría hay?" en escala
  absoluta daría datos inconsistentes con el propio usuario a lo largo de la
  sesión.

Corolario: **la calibración NO reemplaza al duelo**. No se etiqueta "buena
foto" ni "momento bonito" — eso es el duelo. Se etiqueta lo que se puede
verificar mirando.

## Alcance de la calibración

Se etiquetan **recortes de cara**, no fotos enteras (un rostro pequeño dentro
de una grupal es un detalle que CLIP no capta si embebe la imagen completa).

### Atributos por cara (Tier 1 — objetivos, entran ya)

| Atributo | Valores | Por qué |
|---|---|---|
| `eyes` | abiertos / cerrados / entrecerrados | Criterio de descarte del usuario |
| `gaze` | a cámara / fuera | "Caras viradas" — su segundo criterio |
| `mouth` | sonrisa / neutra / hablando-mueca | Base de "sonrisa/alegría" |

Tres preguntas por cara. Con atajos de teclado y la predicción pre-cargada
(solo corriges lo que esté mal), ~3 s por cara.

### Tier 2 — se derivan, no se preguntan

- **Sonrisa genuina (Duchenne)**: no se pregunta aparte. Es `mouth=sonrisa` +
  arruga en los ojos; si la geometría no la separa, se resuelve en Tier 3.
- **Alegría / felicidad**: NO se etiqueta en absoluto (ver principio rector).
  Emerge del duelo: si el usuario elige sistemáticamente las alegres, el taste
  model lo aprende del embedding.

### Fuera de alcance (explícito)

- Identidad de personas (reconocimiento facial).
- Emociones en escala continua.
- Etiquetar "buena foto" (eso es el duelo).

## Arquitectura en 3 pasos

### G1 — MediaPipe FaceMesh (cero etiquetas)

468 landmarks 3D por cara → geometría medible y auditable:

- `eyes`: **EAR** (eye aspect ratio) real desde el contorno del ojo — no una
  caja negra: si falla, se ve por qué.
- `gaze`/virada: **yaw/pitch** reales en 3D. (El proxy de 5 puntos de YuNet no
  discrimina: medido, IMG_8390 mirando a cámara daba el giro MÁS alto.)
- `mouth`: ratio de comisuras — proxy de sonrisa.

Dependencia nueva (~50 MB). Degradación: sin el paquete, se conserva el
comportamiento actual (ojos desactivados).

### G2 — Vista de calibración (mide G1)

Sirve para dos cosas, en este orden:

1. **Medir**: con ~100 caras etiquetadas se obtiene la precisión REAL de G1
   sobre las fotos del usuario, y se calibran los umbrales de EAR/yaw con
   números en vez de corazonadas.
2. **Entrenar** (solo si G1 no da la talla): ver G3.

### G3 — Clasificador sobre embeddings de cara (solo si hace falta)

Misma arquitectura que el taste model: CLIP sobre el **recorte de cara** →
LogisticRegression por atributo. Reutiliza `embedding_service` y el patrón de
`taste_store`. Necesita ~150-200 etiquetas por atributo.

Se implementa **solo** para los atributos donde G2 demuestre que la geometría
falla. Probablemente: sonrisa genuina vs forzada. Improbable: ojos (el EAR es
robusto).

## Datos

`backend/models/calibration.db` (SQLite), patrón de `taste_store`:

```
face_labels(
  id, photo_path, face_index, face_bbox TEXT,
  embedding BLOB,            -- CLIP del recorte (para G3)
  attribute TEXT,            -- 'eyes' | 'gaze' | 'mouth'
  value TEXT,                -- valor elegido por el usuario
  predicted TEXT,            -- lo que dijo G1 (para medir acuerdo)
  created_at, model_version
)
```

Guardar `predicted` junto a `value` permite calcular la precisión sin
re-analizar, y detectar deriva si cambia el detector.

## Selección de caras a calibrar (importa)

No mostrar caras al azar: **muestreo por incertidumbre** (active learning).
Se priorizan las caras donde G1 está menos seguro (EAR cerca del umbral) y se
cubren todos los tamaños de cara. Así 100 etiquetas valen por 500 al azar.

## UI

Vista "Calibración" junto a Grid/Duel:

- Recorte de cara grande y centrado, con contexto (la foto de fondo atenuada).
- 3 filas de opciones con la predicción de G1 pre-marcada.
- Atajos: `1/2/3` por fila, `Enter` = confirmar todo y pasar a la siguiente,
  `Espacio` = saltar (cara ambigua o basura del detector).
- Contador de progreso y precisión de G1 en vivo ("acuerdo: 84/100").

El botón "saltar" es importante: las detecciones basura (caras en la
decoración) se descartan del set en vez de contaminarlo.

## Métricas de éxito

- G1 se considera suficiente si el acuerdo con el usuario supera el 90% en
  `eyes` y el 85% en `gaze` sobre el set de calibración.
- El criterio de descarte sigue siendo RELATIVO dentro de la ráfaga (ya
  implementado): la peor del grupo, no toda foto con un ojo cerrado.

## Testing

- G1: fixtures sintéticas de EAR (ojo abierto/cerrado geométrico); yaw en
  cara frontal vs perfil; degradación sin mediapipe.
- G2: roundtrip del store; el cálculo de precisión; que "saltar" no guarde.
- G3: separabilidad con embeddings sintéticos (patrón de test_taste_model).
