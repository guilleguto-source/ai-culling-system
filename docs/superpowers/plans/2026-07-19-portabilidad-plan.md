# Plan de portabilidad: Guto Flow en otra PC Windows y en MacBook Pro

**Fecha**: 2026-07-19
**Estado**: PLANIFICADO — ejecutar cuando termine la mejora de Fase Q en curso
(stage2 corriendo hasta ~21/07; NO copiar bases de datos ni cachés antes de eso).

**Hechos verificados sobre el repo (no suposiciones):**
- `npm run build` ya encadena: `vite build` → `tsc` → PyInstaller (`--onedir`,
  `backend/run.py` → `dist/backend`) → `electron-builder`.
- `src/main/backend.ts` ya contempla ambos SO: en dev usa
  `backend/.venv/Scripts/python.exe` (win) o `backend/.venv/bin/python` (mac);
  empaquetado usa `resources/backend/backend.exe` (win) o `backend` (mac).
- Puerto hardcodeado: `BACKEND_PORT = 8000` en `backend.ts`; los componentes
  React también hardcodean `http://127.0.0.1:8000`. Coherente entre sí — no tocar.
- **Sin dependencias de binarios externos**: el XMP se embebe en Python puro
  (`xmp_exporter.py`), no usa exiftool.
- `backend/requirements.txt` existe.
- `assets/icon.ico` existe (win). NO existe `icon.icns` (mac) — hay que generarlo.

---

## Inventario de qué llevar (común a ambos destinos)

### 1. Modelos de IA — `backend/models/` (~522 MB, portables tal cual)
| Archivo | Tamaño |
|---|---|
| `clip_vit_b32_visual.onnx` | 336 MB |
| `arcface_r50.onnx` | 167 MB |
| `person_yolov8n.onnx` | 13 MB |
| `face_landmarker.task` | 4 MB |
| `yunet.onnx` | 1 MB |
| `eye_state.onnx` | 1 MB |

### 2. Estado aprendido — portable SIEMPRE (guarda embeddings, no rutas)
| Archivo | Contenido |
|---|---|
| `backend/models/taste_examples.db` (100 MB) | ejemplos de gusto ±1 |
| `backend/models/calibration.db` (0,7 MB) | etiquetas de calibración facial |
| `backend/models/crop_style.json` | estilo de recorte aprendido |
| `backend/models/develop_recipes.json` | receta de revelado por escena |
| `backend/models/scene_centroids.npy` | centroides de las 12 escenas |

### 3. Estado ligado a RUTAS ABSOLUTAS — portable solo entre máquinas con las mismas rutas
| Qué | Condición |
|---|---|
| `backend/models/history.db` (46 MB) | las fotos deben verse en las MISMAS rutas (mismo mapeo de NAS / letra de unidad). Si no: re-correr `/history/bootstrap` en destino |
| `backend/models/cache/` (thumbnails, 2,5 GB) | clave = md5(ruta en minúsculas). Rutas distintas → omitir, se regenera |
| `backend/models/emb_cache/` (177 MB) | idem (clave ruta+mtime) |
| `backend/models/face_emb_cache/` | idem |
| `backend/models/analysis/` (32 MB) | idem — bases SQLite por carpeta hasheada |
| `backend/models/exports/*.json` | snapshots de export con rutas absolutas |

**Regla práctica**: a la otra PC Windows con el NAS mapeado igual → llevar todo.
Al Mac → llevar solo los grupos 1 y 2; el grupo 3 se regenera o se re-bootstrapea.

### 4. Configuración
- Windows: `%APPDATA%/ai_culling_system/settings.json`
- Mac (destino): `~/Library/Application Support/ai_culling_system/settings.json`
- Revisar adentro: rutas de presets del usuario (si apuntan a carpetas locales,
  llevar también esas carpetas y corregir las rutas).

### 5. Precondición dura
**Esperar a que stage2 de Fase Q termine** antes de copiar `emb_cache/`,
`analysis/` o cualquier `.db` — copiar una SQLite a mitad de escritura la corrompe.
Verificación: el log `backend/scripts/out/stage2.log` termina con "Listo." y
`ps` no muestra el proceso python del experimento.

---

## PLAN A — Portátil para otra PC Windows

### Fase A0 — Preparación (en esta PC, 15 min)
1. Commit del estado actual del repo (los cambios de Loupe + fase_q_experiment
   están sin commitear — commitearlos primero).
2. `pip freeze` desde `backend/.venv` y comparar contra `backend/requirements.txt`;
   actualizar el requirements si faltan paquetes (mediapipe se instaló después).
3. Anotar la versión exacta de Python del venv (`python --version`) — la otra
   PC debe usar la misma major.minor para PyInstaller sin sorpresas.

### Fase A1 — Configurar target portable (5 min)
En `package.json`, dentro de `build.win`:
```json
"win": {
  "icon": "assets/icon.ico",
  "target": ["portable"]
}
```
Alternativa si se prefiere carpeta en vez de exe único: `"target": ["zip"]`
(el exe portable único arranca más lento porque se auto-extrae en cada apertura;
con 522 MB de modelos, **zip/carpeta es la opción recomendada**).

### Fase A2 — Resolver el ÚNICO riesgo conocido: los modelos en el paquete (30 min)
PyInstaller empaqueta código, no datos. El código resuelve los modelos con
`Path(__file__).parent.parent / "models"`, que dentro del onedir apunta a
`dist/backend/_internal/../models` = `dist/backend/models` (o similar según
layout). Verificación y arreglo:
1. Correr solo `npm run build:backend`.
2. Inspeccionar `dist/backend/` — ¿dónde queda `run.py`'s `__file__`?
3. Copiar `backend/models/*.onnx` + `face_landmarker.task` a la carpeta que el
   código resuelve (probar arrancando `dist/backend/backend.exe` a mano y
   pegándole a `http://127.0.0.1:8000/health` y `/hardware`).
4. Automatizarlo: agregar los modelos a `extraResources` de electron-builder
   O un paso `copy` en el script `build` — decisión al ejecutar, según el
   layout real que produzca PyInstaller.
5. **NO empaquetar** en ese copy: `*.db`, `cache/`, `emb_cache/`,
   `face_emb_cache/`, `analysis/`, `exports/` (el paquete quedaría de 3+ GB y
   con datos personales; el estado se lleva aparte — ver Fase A4).

### Fase A3 — Build completo y prueba local (1 h)
1. `npm run build` completo.
2. Copiar el resultado (`release/` o `dist/` según electron-builder) a una
   carpeta FUERA del repo, p. ej. `C:\Temp\GutoFlowPortable\`.
3. Prueba de humo en esta misma PC:
   - Arranca sin venv ni Node instalados a la vista (simula la otra PC).
   - `/health` responde; panel "Tu estilo" carga.
   - Culling de una carpeta chica de prueba (~30 fotos con caras).
   - Verificar en el log del backend que cargaron: YuNet, MediaPipe, CLIP,
     ArcFace (si falta un modelo, degrada silencioso — revisar el log, no
     asumir por que "no crashea").
   - Export XMP + Deshacer funcionan.

### Fase A4 — Migración del estado a la otra PC (30 min)
1. En la PC destino, arrancar la app UNA vez (crea `%APPDATA%/ai_culling_system/`).
2. Cerrarla y copiar encima:
   - `settings.json` → `%APPDATA%/ai_culling_system/`
   - Grupo 2 completo (estado aprendido) → carpeta `models/` del paquete.
   - Grupo 3 SOLO si el NAS/discos están mapeados con las mismas letras y rutas.
3. Verificación de estado migrado:
   - Panel "Tu estilo" muestra los números reales (24k+ decisiones, 12 escenas).
   - `/calibration/stats` muestra las precisiones conocidas.
   - Un culling sobre una ráfaga conocida elige parecido a esta PC.

### Fase A5 — Actualizaciones futuras
Documentar el procedimiento: re-correr `npm run build`, reemplazar la carpeta
del paquete, NO tocar `%APPDATA%` ni la carpeta `models/` con el estado.
El estado aprendido nuevo viaja copiando los archivos del grupo 2.

---

## PLAN B — MacBook Pro

### Fase B0 — Transporte del repo (30 min)
Opción recomendada: remoto git privado (GitHub) — `git push` desde esta PC,
`git clone` en el Mac. Añadir antes un `.gitignore` que excluya (si no está):
`backend/.venv/`, `node_modules/`, `dist/`, `backend/models/*.onnx`,
`backend/models/*.task`, `backend/models/*.db`, `backend/models/cache/`,
`backend/models/emb_cache/`, `backend/models/face_emb_cache/`,
`backend/models/analysis/`.
Los modelos y el estado viajan por disco externo / red, no por git.

### Fase B1 — Entorno de desarrollo en el Mac (1-2 h)
1. Instalar: Node LTS, Python 3.12 (arm64, python.org o pyenv — la MISMA
   major.minor que el venv de Windows).
2. `cd repo && npm install`
3. `python3.12 -m venv backend/.venv && backend/.venv/bin/pip install -r backend/requirements.txt`
   - Todas las dependencias clave (mediapipe, onnxruntime, opencv-python,
     rawpy, scikit-learn, fastapi) publican wheels macOS arm64 — no se espera
     compilación. Si `rawpy` diera problemas en arm64: `pip install rawpy --only-binary :all:`
     y verificar versión con wheel disponible.
4. Copiar los 6 modelos a `backend/models/`.
5. **Hito 1**: `npm run dev` — la app abre, backend arranca desde el venv
   (backend.ts ya usa `bin/python` en darwin), `/health` responde.
6. Prueba de humo igual que A3 (culling chico, verificar en log que cargan los
   4 modelos, export XMP a archivos de prueba).

### Fase B2 — Estado aprendido en el Mac (30 min)
1. Copiar grupo 2 (taste, calibration, crop_style, develop_recipes,
   scene_centroids) a `backend/models/`.
2. `history.db`: las rutas Windows adentro no existen en el Mac. Dos opciones:
   - Si el catálogo `.lrcat` y las fotos son accesibles desde el Mac (NAS
     montado): re-correr `/history/bootstrap` + `/history/embed` allá (crea un
     history nuevo con rutas mac). El embed re-usa fuerza bruta — puede tardar.
   - Si no: omitir history.db. El gusto YA vive en `taste_examples.db`
     (portable); solo se pierde la posibilidad de re-alimentar desde historial.
3. `settings.json` → `~/Library/Application Support/ai_culling_system/`
   revisando rutas internas (presets).

### Fase B3 — App empaquetada .app (2-3 h, opcional — dev mode ya es usable)
1. Generar `assets/icon.icns` desde el logo (iconutil o herramienta online).
2. En `package.json`:
```json
"mac": {
  "icon": "assets/icon.icns",
  "target": ["dir"],
  "identity": null
}
```
   (`identity: null` = sin firma; `dir` = .app en carpeta, sin dmg).
3. `npm run build` EN EL MAC (PyInstaller y electron-builder no cross-compilan;
   el build de Windows no sirve para Mac ni viceversa).
4. Riesgo conocido: **mediapipe + PyInstaller en macOS** a veces necesita
   `--collect-data mediapipe` o hooks extra para sus binarios internos. Si el
   backend empaquetado no arranca, agregar al script `build:backend`:
   `--collect-all mediapipe --collect-all onnxruntime`.
5. Repetir la verificación de modelos de A2 sobre el layout que produzca
   PyInstaller en mac.
6. Gatekeeper: app sin firmar → primera apertura con clic derecho → Abrir.
   (Firmarla requiere Apple Developer Program, $99/año — no necesario para
   uso propio.)
7. Prueba de humo completa (igual A3).

### Fase B4 — Diferencias de plataforma a vigilar (checklist de QA en Mac)
- [ ] Rutas del NAS: en Mac los montajes son `/Volumes/...` — el picker de
  carpetas debe poder navegarlos; los cachés se regeneran con esas rutas.
- [ ] `thumbnail_store` / `analysis_store` hashean rutas en minúsculas —
  consistente en APFS (case-insensitive por defecto); sin acción salvo que el
  volumen sea case-sensitive (raro).
- [ ] Lightroom Classic en Mac: el flujo XMP (Ctrl+S → Cmd+S) es idéntico;
  verificar un roundtrip completo de sync.
- [ ] Rendimiento: en Apple Silicon, onnxruntime CPU es rápido pero se puede
  evaluar `onnxruntime-silicon`/CoreML EP más adelante (NO en la primera
  migración — primero que funcione igual que en Windows).

---

## Orden de ejecución sugerido (cuando termine Fase Q)

1. Commit de todo lo pendiente (Loupe, fase_q_experiment, resultados).
2. Plan A completo (misma plataforma = menos riesgo, valida el empaquetado).
3. Plan B fases B0-B2 (dev mode en Mac = ya usable para trabajar).
4. Plan B fase B3 (.app) solo si el dev mode resulta incómodo en el día a día.

**Esfuerzo total estimado**: Plan A ~2-3 h · Plan B ~4-6 h (mitad es espera de
descargas/instalaciones).
