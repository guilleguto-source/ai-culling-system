# Guto Flow — Estado actual del sistema

> Documento de referencia técnica. Fecha: 2026-07-18.
> Describe **lo que el sistema hace hoy**, con números reales medidos y una
> sección final honesta de lo que falta.

---

## 1. Qué es

Culler inteligente de eventos fotográficos que **aprende el criterio del
fotógrafo** en vez de imponer uno genérico. Procesa eventos de cientos o miles
de fotos: agrupa ráfagas, elige la mejor de cada una, califica, descarta,
propone una pre-edición y exporta todo a Lightroom vía XMP.

**Corre 100% local y offline.** Ninguna foto ni dato sale de la máquina.

### Stack

- **Frontend:** Electron + React + TypeScript.
- **Backend:** Python + FastAPI (uvicorn).
- **Persistencia:** SQLite (varias bases separadas por dominio) + cachés en disco.
- **Modelos:** ONNX / MediaPipe `.task`, todos locales.
- **Config:** `settings.json` en `%APPDATA%/ai_culling_system/`.

---

## 2. Motor de visión

| Modelo | Archivo | Rol |
|---|---|---|
| **YuNet** | `yunet.onnx` | Detección de rostros + 5 landmarks (2 ojos, nariz, 2 comisuras) |
| **MediaPipe FaceLandmarker** | `face_landmarker.task` | Atributos por cara: EAR (apertura ocular), blendshape de parpadeo, sonrisa, mirada, yaw. **Bonus:** si no encuentra cara dentro del recorte, la detección de YuNet era basura (decoración, muñecos) → filtro de validez gratis |
| **CLIP ViT-B/32 (visual)** | `clip_vit_b32_visual.onnx` | Embeddings de apariencia (512-d). Base del gusto y del agrupamiento por escena |
| **ArcFace r50** | `arcface_r50.onnx` | Embeddings de identidad facial (512-d) |
| **YOLOv8n** | `person_yolov8n.onnx` | Detección de **personas completas** — gente de espaldas, de perfil o sin rostro visible, para que el auto-crop nunca corte a nadie |

Todos degradan limpio: si falta un modelo, la función se desactiva y el resto
del pipeline sigue funcionando.

---

## 3. Pipeline de culling (paso a paso)

### 3.1 Ingesta
- Lee **JPG y RAW** (CR2, CR3, ARW, DNG).
- De los RAW extrae el **preview embebido** (rápido, no revela el RAW completo).
- Genera un *thumb de análisis* (lado largo 1600 px).
- **Empareja RAW+JPG** del mismo disparo por nombre base, para que las
  decisiones se apliquen al par completo.

### 3.2 Análisis por foto → objeto `PhotoAnalysis`
Un solo objeto por foto con todos los hechos medidos:

- **Escena:** retrato vs detalle.
- **Rostros:** cajas + 5 landmarks por cara.
- **Atributos faciales** (por cara): ojos abiertos/cerrados, mirada a cámara o
  fuera, sonrisa, giro de cabeza, y validez.
- **Nitidez por rostro.**
- **Conteos:** caras válidas, ojos cerrados, miradas fuera, sonrisas.
- **Saliencia** (en fotos de detalle): dónde está el foco de interés.
- **Calidad técnica:** varianza Laplaciana + "¿hay *algo* nítido en el cuadro?".
  En **retratos** se mide sobre el recorte del rostro (respeta el bokeh
  artístico); en **detalles**, sobre la región de saliencia.
- **Estética** heurística (fallback frío).
- **Firma de luz:** luminancia de piel, luminancia global, fracción de píxeles
  quemados, y estimación de balance de blancos.

### 3.3 Caché de análisis
SQLite por directorio, con clave `(ruta, mtime)` y versión de esquema
(`ANALYSIS_VERSION`). **Re-correr un evento no re-analiza** lo que no cambió.
El análisis es ~95% del tiempo de cómputo, así que esto es crítico.

### 3.4 Agrupamiento en ráfagas
**pHash + timestamps EXIF + DBSCAN.** Separa los grupos de detalles/objetos de
los grupos de retratos (criterios distintos).

### 3.5 Elección de la representativa
Dos etapas:

1. **Gates técnicos relativos** — descarta candidatas con ojos cerrados o
   rostro blando *comparado con sus hermanas*. Regla de oro: **nunca vacía el
   cluster**; si todas fallan un gate, ese gate no se aplica.
2. **Score** entre las supervivientes:
   - Con el **taste model entrenado** → score de gusto sobre el embedding CLIP.
   - En frío → `0.6 · nitidez_normalizada + 0.4 · estética`.

### 3.6 Decisión (política)
- **Selectividad:** conserva 40% / 65% / 85% (pocas / estándar / más).
- **Highlights:** top 10% de las seleccionadas.
- **Basura real:** solo desenfoque **severo** (muy por debajo del umbral *y* sin
  nada nítido en el cuadro) o exposición extrema (quemada o casi negra). El
  desenfoque leve no se marca: solo penaliza el score.
- **Descarte por rostros:** *relativo* a la ganadora de su ráfaga — se marca la
  que tiene más caras con problema que la elegida ("la peor de la grupal").
  Un criterio absoluto pintaría medio evento.
- Traduce a **estrellas / color / banderín** según un mapeo configurable.

### 3.7 Pre-edición
- **Exposición:** medida en la piel de *esa* foto, acotada a la mediana de su
  **sesión de luz** ±0.7 EV. Así la piel oscura queda correctamente oscura y la
  clara correctamente clara — uniformiza el bloque sin imponer un tono.
- **Sesiones de luz con histéresis:** solo 4 fotos consecutivas desviadas
  cortan una sesión (evita cortes por una foto rara).
- **WB:** las pieles mandan; los detalles heredan la sesión salvo luz
  genuinamente distinta.
- **Guardas:** nunca sube la exposición de una foto con altas luces quemadas.
- **"Look" aprendido por escena** (ver §6): contraste, sombras, altas luces,
  claridad, etc.

### 3.8 Auto-recorte
Propone recorte usando rostros, **personas completas** (YOLO), saliencia y
ángulo de horizonte. Niveles configurables de agresividad. Nunca corta a una
persona detectada.

### 3.9 Exportación XMP
- **JPG:** XMP embebido en el segmento APP1.
- **RAW:** sidecar `.xmp`.
- Escribe: rating, etiqueta de color, banderín (pick/reject), ajustes `crs` de
  revelado y rectángulo de recorte + ángulo.
- Aplica el **preset del usuario** (curva, HSL, color grading, máscaras IA),
  excluyendo lo que el sistema calcula por su cuenta (exposición, WB, crop).
- Guarda un **snapshot** por evento de lo que exportó — base del sync.
- Re-sella el mtime del análisis tras escribir (si no, el caché nunca acertaría).

### 3.10 Modos
- **Culling + Edición:** analiza, decide y escribe todo.
- **Solo Culling:** escribe selección/estrellas, deja el revelado y el recorte
  *propuestos* para aplicarlos después con "Aplicar edición".
- **Re-selección (`/reselect`):** vuelve a decidir con otros ajustes usando el
  análisis cacheado — **en segundos, sin re-analizar**.

---

## 4. Persistencia

| Base / caché | Contenido |
|---|---|
| `analysis/<hash-dir>.db` | Análisis por foto, por evento |
| `emb_cache/*.npy` | Embeddings CLIP (clave: ruta + mtime) |
| `face_emb_cache/*.npy` | Embeddings de recortes de cara |
| `taste_examples.db` | Ejemplos de gusto (+1/−1) con su origen |
| `calibration.db` | Etiquetas de calibración facial + embeddings + geometría |
| `history.db` | Historial completo del catálogo Lightroom etiquetado |
| `exports/*.json` | Snapshot de lo exportado por evento + estado de sync |
| `develop_recipes.json`, `crop_style.json`, `scene_centroids.npy` | Modelos aprendidos |
| Caché de thumbnails | Miniaturas para la UI |

---

## 5. Los cuatro sistemas de aprendizaje

### 5.1 Duelos
Elegís una alternativa de la ráfaga → genera un par **ganadora (+1) /
perdedora (−1)** sobre embeddings CLIP. Regresión logística re-entrenada al
vuelo. Mínimo 50 ejemplos para confiar en él.

### 5.2 Sync con Lightroom
**Bidireccional pero basado en archivos** (no hay plugin):
nosotros escribimos XMP → Lightroom los lee → vos editás → **guardás metadatos
al archivo** (Ctrl+S o auto-XMP) → los releemos.

Aprende de:
- **Cambios de estrellas** → gusto (subiste = +1, bajaste = −1). Idempotente.
- **Revelado y recorte** de las fotos que conservaste → estilo por escena.

Incluye recordatorio al abrir la app ("falta sincronizar el evento X") con
opciones de posponer 8 h o descartar, y un aviso cuando detecta 0 cambios
(síntoma típico de que Lightroom no volcó los metadatos al archivo).

### 5.3 Calibración de rostros
- **Muestreo por incertidumbre:** pregunta primero las caras donde el detector
  está en el filo del umbral o sus dos señales se contradicen. ~100 etiquetas
  rinden como ~500 al azar.
- Etiquetás: **ojos** (abiertos/cerrados/entrecerrados), **mirada**
  (a cámara/fuera), **boca** (sonrisa/neutra/hablando), **lentes**
  (sin/normales/oscuros), **sujeto** (persona/no es cara/ilegible).
- Entrena un **clasificador híbrido**: embedding CLIP del recorte de cara **+**
  las 5 señales geométricas de MediaPipe, con estandarización para que la
  geometría no se ahogue entre las 512 dimensiones.
- Mínimos: 60 ejemplos y 15 por clase. Muestra **precisión honesta** por
  validación cruzada, separada en "geometría" vs "aprendido".
- **Está cableado:** refina los conteos de rostros durante el culling. Con
  lentes oscuros, por ejemplo, no penaliza ojos ni mirada.

### 5.4 Historial del catálogo Lightroom
Ver §6.

---

## 6. Aprendizaje del historial (lo más grande)

Lector **solo-lectura** del `.lrcat` (SQLite de Lightroom). Nunca escribe en él.

**Alcance:** desde 2026-02-01 → **105.557 fotos** analizadas del catálogo.

### Convención de selección del fotógrafo
| Marca | Significado | Uso | Cantidad |
|---|---|---|---|
| 2★ | Interesante | **positiva** | 16.398 |
| 3★ | Super | **positiva** (highlight) | 2.113 |
| 1★ | Bajada al editar | **negativa** | 3.222 |
| Banderín negro | A borrar | **negativa** | 3.026 |
| 4★ / 5★ | Marcador de "por dónde quedé" | **ignorar** | 1.087 |
| 0★ | Sin revisar | ambiguo | 79.775 |

Los **colores no se usan** (uso reciente, señal no confiable). Las **ediciones
extremas** de exposición (>1 EV) se marcan y excluyen: son correcciones de
error, no estilo.

### Qué se aprendió

**Escenas (12 grupos)** — clustering de embeddings CLIP sobre las 18.294
positivas embebidas. Cada grupo con su foto **medoide** representante, para
poder bautizarlo. Tamaños entre 909 y 2.357 fotos.

**Revelado por escena** — recuperó su receta:
```
Contraste −10 · Sombras +25 · Blancos −15 · Negros −10
Altas luces −10/−15 · Claridad +4 · Dehaze +5 · Saturación 0
```
**Hallazgo importante:** es prácticamente **idéntica en las 12 escenas**. Es su
preset de importación, su firma consistente. Condicionar el revelado por escena
aporta poco *en este caso* — el sistema lo detectó solo.

**Recorte por escena** — acá sí hay variación real: conserva entre **74% y 82%**
del cuadro (recorta cerrado), con leve sesgo lateral y sin rotación
sistemática.

**Gusto** — 24.363 decisiones alimentadas al modelo.

---

## 7. Números reales medidos

| Métrica | Valor |
|---|---|
| Fotos del catálogo procesadas (feb-2025+) | 105.557 |
| Positivas embebidas (CLIP) | 18.294 |
| Negativas embebidas | 6.053 |
| Ejemplos de gusto | 24.363 |
| **Gusto — AUC** | **68,7%** |
| Gusto — balanced accuracy | 63,8% |
| Gusto — accuracy / baseline | 77,5% / 75,1% |
| Escenas descubiertas | 12 |
| Fotos con recorte en el historial | 13.634 |
| Recorte mediano (área conservada) | 74–82% |
| **ArcFace — misma persona** | **0,90–0,95** similitud coseno |
| ArcFace — personas distintas | < 0,30 |
| Velocidad de ingesta observada | ~47 img/s |
| Embedding (carga NAS + CLIP) | ~1,3–1,9 img/s |

**Lectura honesta del gusto:** AUC 0,69 es señal real pero **modesta**. El
motivo es estructural: los descartes de 1★ son fotos que le interesaron lo
suficiente para editarlas y después bajó — visualmente casi idénticas a las que
conservó. Y muchos rechazos son por **redundancia dentro de la ráfaga**, que no
es una propiedad visual absoluta.

---

## 8. Interfaz

- **Grid** — todas las fotos con su etiqueta (seleccionada / duplicada / ojos
  cerrados / descartada).
- **Duelo** — compara las alternativas de una ráfaga, ordenadas por score, con
  columnas (2/3/4) y tamaño de imagen configurables y recordados. Elegir otra
  entrena el modelo.
- **Calibración** — una cara a la vez, con recuadro sobre la cara en cuestión,
  atajos de teclado por fila y precisión en vivo por atributo.
- **Recordatorio de sync** — al abrir la app lista los eventos pendientes, con
  "Sincronizar ahora" / "Recordar en 8 h" / "Ya terminé".
- **Settings** — mapeo a estrellas/colores de Lightroom, selectividad,
  detectores activos, pre-edición y presets.
- **Visor de depuración** (`/debug/overlay`) — dibuja cajas de cara/persona,
  crop propuesto y zona de saliencia sobre la foto.

---

## 9. API (endpoints)

**Sesión y proceso**
`/health` · `/hardware` · `/settings` (GET/POST) · `/ingest` · `/cull` ·
`/reselect` · `/status` · `/results` · `/shutdown`

**Visualización**
`/thumbnail` · `/debug/overlay`

**Proyectos y caché**
`/cache/projects` · `/cache/open` · `/cache/clear`

**Aprendizaje directo**
`/learn_preference` (duelos)

**Calibración**
`/calibration/candidates` · `/calibration/face` · `/calibration/label` ·
`/calibration/stats`

**Presets y edición**
`/presets` · `/presets/use` · `/apply_edits`

**Lightroom**
`/reimport_xmp` · `/sync/pending` · `/sync/snooze` · `/sync/dismiss`

**Historial**
`/history/bootstrap` · `/history/embed` · `/history/scenes` ·
`/history/feed-taste` · `/history/develop-style` · `/history/crop-style`

---

## 10. Estado honesto — lo que NO está terminado

### Construido y probado, pero **no cableado**
- **ArcFace / identidad de personas.** El módulo, la alineación de 5 puntos, el
  agrupamiento por identidad y la política de "al menos una buena foto de cada
  persona" están construidos y **validados sobre fotos reales**, pero **no se
  ejecutan durante el culling**. Personas reconocidas hoy = **0**.

### Limitaciones del aprendizaje
- **El gusto es flojo** (AUC 0,69). Falta el enfoque de **pares dentro de la
  ráfaga** (comparar alternativas casi idénticas), que debería rendir bastante
  más que el actual "elegida vs descarte" absoluto.
- **Solo se aprende de las correcciones.** Si estás de acuerdo con la IA, esa
  señal se pierde: no hay un "Aprobar". Es la mitad del aprendizaje tirada.

### Riesgos reales
- **No hay deshacer.** El export **escribe en los archivos reales** del usuario
  (XMP embebido en los JPG, sidecars de los RAW) y **no guardamos el estado
  previo**. Un culling mal configurado pisa ratings sin vuelta atrás.
- **Fragilidad de entorno.** En desarrollo el backend corre con la **Python del
  sistema**, así que cualquier `pip install` global puede romperlo (ya pasó:
  instalar insightface subió numpy y rompió scikit-learn). Pendiente moverlo a
  un venv aislado.

### Deuda de interfaz
- **Un cartel miente:** el duelo dice "Elegida por la IA (mejor score)", pero
  cuando la decisión la toma un **gate técnico**, la elegida puede tener *menor*
  score que una alternativa. Observado en pantalla.
- **La UI no explica sus decisiones** — no muestra *por qué* ganó una foto,
  aunque el sistema tiene todos los datos para hacerlo.
- **Métricas crudas:** muestra "Blur: 416" (varianza Laplaciana) en vez de una
  nitidez normalizada legible.
- **Idioma mezclado** (inglés y español conviviendo en la misma pantalla).
- **Sin preview de la pre-edición** antes de aplicarla.
- **Sin filtros rápidos** en el Grid ni atajos de teclado en el duelo.
- El panel lateral muestra "Backend Engine / Online" — información de
  infraestructura donde debería estar el diferencial del producto (lo que la IA
  aprendió del fotógrafo).
