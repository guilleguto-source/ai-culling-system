# AI Culling System

Sistema de culling (preselección) de fotos de eventos con IA local: detección de
rostros (YuNet), ojos cerrados (OCEC), nitidez/exposición consciente de escena,
agrupado de duplicados (DBSCAN + pHash) y escritura de calificaciones a Adobe Lightroom.

Arquitectura: **Electron + React (Vite/TS)** + backend **FastAPI** (Python).

## Cómo se escriben las calificaciones (XMP)

- **JPEG** → los metadatos XMP (estrellas + etiqueta de color + pick/reject) se
  **insertan dentro del archivo** (segmento APP1), en Python puro (sin `exiftool`).
  Lightroom **no lee** sidecars `.xmp` para JPEG, por eso deben ir embebidos.
- **RAW** → se escribe un **sidecar `.xmp`** junto al archivo (Lightroom sí lo lee para RAW).
- Solo se toca la sección de metadatos; **nunca** se recodifica el píxel.

## Sincronizar con Adobe Lightroom Classic

### 1. Conjunto de etiquetas de color
Las etiquetas de color solo se ven con color si su **texto** coincide con el conjunto
activo en Lightroom. Los nombres se toman de tu configuración (`settings.json` →
`ratings_mapping`), así que **deben ser idénticos** a tu conjunto en LR.

- En Lightroom: **Metadatos → Conjunto de etiquetas de color → Editar…**
- Asegúrate de que los nombres coincidan exactamente (mayúsculas/acentos incluidos).
  Ejemplos por idioma:
  - Inglés (por defecto LR): `Red, Yellow, Green, Blue, Purple`
  - Español (por defecto LR): `Rojo, Amarillo, Verde, Azul, Morado`
- Configura los mismos nombres en el panel de estrellas/colores de la app.
  Si no coinciden, la etiqueta existe pero se muestra **en blanco**.

### 2. Forzar la lectura de metadatos
Si la carpeta **ya estaba importada** en tu catálogo, Lightroom no relee el disco solo:

1. En la cuadrícula (G), **quita cualquier filtro** (abajo debe decir "N de N").
2. **Ctrl+A** para seleccionar todas.
3. **Metadatos → Leer metadatos del archivo** → confirma.

> Si tienes activado *"Escribir cambios automáticamente en XMP"* en
> **Edición → Configuración del catálogo → Metadatos**, desactívalo mientras culleas
> para que Lightroom no sobrescriba los archivos con su catálogo (vacío).

## Modelos

Coloca en `backend/models/`:
- `yunet.onnx` — detector de rostros (OpenCV Zoo).
- `eye_state.onnx` — clasificador de ojos abiertos/cerrados (OCEC, salida `prob_open`).
- `expression.onnx` — clasificador de sonrisa (opcional, HSC).
- `aesthetic.onnx` — modelo estético (opcional; mientras no esté, se usa un placeholder).

## Desarrollo

```bash
# Backend
cd backend && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pytest tests        # tests

# App completa (frontend + electron + backend)
npm install && npm run dev
```
