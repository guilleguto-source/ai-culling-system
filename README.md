# AI Culling System

Sistema de escritorio offline de selección inteligente de fotografías (culling) asistido por IA. Electron + React/TypeScript (frontend) comunicándose con un backend local en Python + FastAPI + ONNX Runtime.

## Requisitos

### Backend (Python 3.10+)
```bash
cd backend
pip install -r requirements.txt
```

### Frontend (Node.js 18+)
```bash
npm install
```

## Ejecución en Desarrollo

```bash
npm run dev
```

Esto inicia simultáneamente:
- **Vite** (frontend React) en `http://localhost:5173`
- **Electron** (proceso principal) que lanza el backend Python automáticamente en `http://127.0.0.1:8000`

También puedes usar la interfaz directamente desde el navegador en `http://localhost:5173`.

## Cómo Funciona

1. Selecciona una carpeta con fotos (JPG, CR2, NEF, ARW, etc.).
2. El motor analiza cada foto: detecta rostros, evalúa nitidez, agrupa ráfagas similares.
3. Asigna calificaciones automáticas:
   - **Verde (3★)** — Mejor foto de cada grupo (Selected).
   - **Violeta (0★)** — Duplicados aceptables para revisión manual.
   - **Rojo (0★)** — Borrosas o peores de cada ráfaga (candidatas a eliminar).
4. Escribe los metadatos directamente en los archivos (JPEG embebido, RAW sidecar `.xmp`).

---

## Guía de Sincronización con Adobe Lightroom

### 1. Configurar el Conjunto de Etiquetas de Color

Los nombres de los colores escritos por la IA deben coincidir **exactamente** con el conjunto de etiquetas configurado en Lightroom.

**En Lightroom Classic:**
1. Ve a **Metadatos → Conjunto de etiquetas de color → Editar…**
2. Verifica que los nombres de las etiquetas sean:
   - Rojo: `Red` (o `Rojo` si usas LR en español)
   - Verde: `Green` (o `Verde`)
   - Azul: `Blue` (o `Azul`)
   - Púrpura: `Purple` (o `Púrpura`)

3. Si tu Lightroom está en español, edita el archivo `settings.json` en `%APPDATA%\ai_culling_system\` y cambia los valores de `color` para que coincidan:
```json
{
  "ratings_mapping": {
    "selected":    { "stars": 3, "color": "Verde" },
    "highlighted": { "stars": 3, "color": "Azul" },
    "blurry":      { "stars": 0, "color": "Rojo" },
    "closed_eyes": { "stars": 0, "color": "Púrpura" },
    "duplicates":  { "stars": 0, "color": "Púrpura" }
  }
}
```

### 2. Leer Metadatos Tras el Culling

Después de ejecutar el culling:

1. Abre la carpeta en Lightroom.
2. Selecciona todas las fotos (`Ctrl+A`).
3. Ve a **Metadatos → Leer metadatos de archivos** (o `Ctrl+Shift+R` en Windows).
4. Lightroom actualizará las estrellas, etiquetas de color y flags de selección.

> **Nota:** Si tienes activado "Escribir cambios automáticamente en XMP" en las preferencias de Lightroom, puede haber un conflicto de escritura. Recomendamos desactivar esa opción mientras usas el sistema de culling.

### 3. Filtrar Rápidamente en Lightroom

Tras la lectura de metadatos, puedes usar la barra de filtros de Lightroom:

- **Ver solo las seleccionadas:** Filtrar por ★★★ (3 estrellas) o color Verde.
- **Ver candidatas a eliminar:** Filtrar por color Rojo → revisar → eliminar las que confirmes.
- **Ver duplicados para decidir:** Filtrar por color Púrpura.

---

## Compatibilidad de Hardware

- **GPU dedicada (NVIDIA/AMD):** Usa ONNX Runtime con `CUDAExecutionProvider` o `DirectMLExecutionProvider` automáticamente.
- **Sin GPU:** Fallback automático a `CPUExecutionProvider` con optimización de hilos (75% de los núcleos físicos).

## Estructura del Proyecto

```
ai_culling_system/
├── backend/
│   ├── main.py                     # FastAPI — orquestador del pipeline
│   ├── models/                     # Modelos ONNX (YuNet, etc.)
│   ├── services/
│   │   ├── ingester.py             # Lectura JPG/RAW + thumbnails
│   │   ├── scene_classifier.py     # Detección de rostros (YuNet)
│   │   ├── technical_quality.py    # Nitidez (Laplaciano) + saliencia
│   │   ├── clustering.py           # pHash + DBSCAN
│   │   ├── xmp_exporter.py         # Escritura XMP (embebido + sidecar)
│   │   └── settings_manager.py     # Configuración persistente
│   ├── utils/
│   │   └── hardware.py             # Detección GPU/CPU
│   └── requirements.txt
├── src/
│   ├── main/                       # Electron main process
│   ├── preload/                    # IPC bridge
│   └── renderer/src/               # React UI (App, Sidebar, Grid, Duel)
├── package.json
└── README.md
```
