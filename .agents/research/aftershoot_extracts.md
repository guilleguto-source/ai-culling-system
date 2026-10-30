# Aftershoot: Arquitectura Interna, Modelos de IA e Ingeniería Inversa de Culling

Documento de extracción técnica profunda derivado de la ingeniería inversa sobre el instalador oficial de Aftershoot (`installer.exe` v2.20.4, 663 MB).

---

## 1. Arquitectura del Sistema y Componentes Binarios

El ecosistema de Aftershoot opera como un sistema distribuido local en tres capas:

```
+-------------------------------------------------------------+
|  Frontend: Electron (Webpack Bundle en app.asar)            |
|  - UI / Gestión de Catálogos / Preferencias de Culling       |
+-------------------------------------------------------------+
                              │
               ┌──────────────┴──────────────┐
               ▼                             ▼
+─────────────────────────────+ +─────────────────────────────+
|  rs.win32-x64-msvc.node     | |  aftershoot-backend.exe     |
|  (Node.js N-API Native)     | |  (Rust Standalone, 237 MB)  |
|  - LibRaw / RawSpeed3       | |  - Servidor Axum (REST API) |
|  - Adobe DNG SDK            | |  - Rayon (Paralelismo CPU)  |
|  - libheif / libjxl         | |  - ONNX Runtime / DirectML  |
|  - OpenCV Rust bindings     | |  - OpenVINO NPU/GPU Plugin  |
|  (Decodificación RAW ultra  | |  (Inferencia AI de Culling, |
|   rápida multihilo a RGB)   | |   Clustering y Retoque)     |
+─────────────────────────────+ +─────────────────────────────+
```

### Protocolo de Comunicación Local (Axum REST API)
Electron arranca `aftershoot-backend.exe` pasando variables de entorno (`AFTERSHOOT_DEVICE_ID`, `AFTERSHOOT_INSTANCE_ID`) y se comunica mediante endpoints REST locales:
- `POST /culling/start` y `POST /culling/start2`: Inicia el flujo de selección asistida o automática.
- `POST /culling/stop`: Cancela el análisis en ejecución.
- `POST /album/project_info`: Metadatos del catálogo o carpeta importada.
- `POST /buckets/by_images`: Obtiene los clusters de ráfagas/duplicados calculados.
- `POST /edit_metadata/write/file`: Escritura de XMP en disco.
- `POST /edit_metadata/write/db`: Modificación directa de la base de datos SQLite de Lightroom Classic (`.lrcat`).
- `POST /retouching/start`: Dispara el pipeline de retoque neuronal (acné, piel, dientes).

---

## 2. Protección y Descifrado de Modelos: "El Ofuscado"

Aftershoot almacena 23 grafos de inferencia en `backend_assets/*.jumbled`, ofuscados para prevenir su extracción directa.

### Crate `crates/el-ofuscado/src/lib.rs`
- **Algoritmo de Cifrado**: Cifrador de flujo (`StreamCipher` vía `cipher-0.4.4`) acelerado por hardware x86_64 con extensiones **AES-NI** (`aeskeygenassist`, `aeskeygenassist`).
- **Longitud de Clave**: Clave simétrica de 256 bits (`0x20` bytes).
- **Proceso de Carga**: `crates\culler\modelling\src\cradles\mod.rs` invoca `el_ofuscado::decrypt(slice, key)` directamente en memoria RAM antes de transferir el buffer a `onnxruntime::Session` u `openvino::Core`.
- **Estructura Interna del Grafo**: Una vez descifrado, cada archivo `.jumbled` es un grafo estándar **ONNX IR v7/v8** o representación intermedia **OpenVINO (IR XML + BIN)**.

---

## 3. Catálogo de Redes Neuronales de Culling (`crates/culler/modelling2`)

Aftershoot asigna a sus modelos nombres en clave inspirados en jefes de *Elden Ring / Dark Souls / Cyberpunk 2077*:

| Nombre Clave (`.jumbled`) | Tamaño | Tarea / Módulo Rust (`children/`) | Entrada / Resolución | Salidas & Métricas |
|---|---|---|---|---|
| **`rykard.jumbled`** | 7.2 MB | `face_detection\portrait.rs` | RGB completo / 4 cuadrantes (*Quartering*) | BBoxes $[x, y, w, h]$, conf, 5 landmarks faciales |
| **`fire_giant.jumbled`** | 7.2 MB | `face_detection\landscape.rs` | RGB completo horizontal | BBoxes para tomas grupales y fotos de paisaje |
| **`adam_smasher.jumbled`** | 13.1 MB | `face_pose.rs` | Crop facial 112x112 | Matriz afín 3D, ángulos [Yaw, Pitch, Roll] |
| **`micolash.jumbled`** | ~4 MB | `face_landmark.rs` | Crop facial 112x112 | Puntos clave anatómicos detallados (ojos, labios, nariz) |
| **`cloudy.jumbled`** | ~5 MB | `face_blur_classifier.rs` | **192 x 192** RGB crop + resolution vector | Probabilidades: sharp, soft, blur + score |
| **`the_four_kings.jumbled`** | 4.1 MB | `image_blur.rs` | **256 x 256** imagen global | Probabilidad de trepidación / desenfoque óptico global |
| **`cant_see.jumbled`** | ~6 MB | `closed_eyes.rs` | **256 x 256** crop de tercio ocular | 5 probabilidades (open, partial, closed, unknown, not_visible) |
| **`mimic_tear.jumbled`** | 8.9 MB | `eyegaze.rs` | Crop de región ocular | Vector de dirección de mirada respecto a la lente |
| **`rennala.jumbled`** | 4.1 MB | `emotion.rs` | Crop facial 112x112 | Sonrisa abierta, sonrisa cerrada, neutro, disgusto |
| **`ranni_the_witch.jumbled`**| 14.2 MB | `kiss.rs` | Pares de rostros cercanos | Capa densa `dense_3` detectora de beso en bodas |
| **`the_kindling_maiden_2`** (`melina`)| 12.6 MB | `saliency.rs` | 256 x 256 imagen global | Mapa de saliencia y pesos de tercios composicionales |
| **`gwyn_2.jumbled`** | 23.9 MB | `face_embedding.rs` | Crop facial 112x112 normalizado | Vector ArcFace 512D para clusterización por persona |
| **`promised_consort_radahn`**| 12.8 MB | `image_embedding_improved.rs`| 224 x 224 RGB global | Vector semántico global 512D (tipo MobileCLIP) |
| **`godrick_the_grafted.jumbled`**| **78.1 MB** | `selection.rs` | **224 x 224** RGB global | **Master Culling Head**: Score latente de estética y calidad |

---

## 4. Métricas Matemáticas y Calificación Detallada de Cada Red

### 4.1 Evaluación de Nitidez Facial (`FaceBlurClassifier`)
1. **Preprocesamiento del Crop**:
   - Se toma el bounding box $[x, y, w, h]$ del rostro.
   - Centro del crop: $C_x = x + w/2$, $C_y = y + h/2$.
   - Escala: $S = \max(w, h) \times 1.4$.
   - Se redimensiona con interpolación bilinear a **192 x 192 x 3**.
2. **Vector de Resolución (`resolution_features_input`)**:
   - Relación entre el área facial y la resolución total del sensor: $r_{\text{face}} = (w \cdot h) / (W_{\text{img}} \cdot H_{\text{img}})$.
   - Evita penalizar como "desenfocado" un rostro diminuto en una foto de cuerpo entero o paisaje.
3. **Cálculo del Score de Nitidez**:
   $$S_{\text{sharpness}} = p(\text{sharp}) - 0.5 \cdot p(\text{soft}) - 1.5 \cdot p(\text{blur})$$
4. **Descarte Inmediato (*Opt-out por Blur*)**:
   - `Lenient`: $p(\text{blur}) > 0.85 \implies$ Etiqueta **Roja**, **1 Estrella**, Flag `QuickFilter::Blur`.
   - `Moderate`: $p(\text{blur}) > 0.65 \implies$ Etiqueta **Roja**, **1 Estrella**, Flag `QuickFilter::Blur`.
   - `Strict`: $p(\text{blur}) > 0.45 \implies$ Etiqueta **Roja**, **1 Estrella**, Flag `QuickFilter::Blur`.

---

### 4.2 Evaluación de Ojos y Parpadeo (`ClosedEyes`)
1. **Preprocesamiento**:
   - Crop centrado en la línea de los ojos mediante landmarks de `micolash.jumbled`.
   - Redimensionado a **256 x 256 x 3** RGB normalizado.
2. **Las 5 Probabilidades de Salida**:
   - $p_{\text{open}}$, $p_{\text{partial}}$, $p_{\text{closed}}$, $p_{\text{unknown}}$, $p_{\text{not\_visible}}$.
3. **Calibración Exacta Extraída del Desensamblador**:
   $$\text{Confianza} = \text{clamp}\left(\frac{(p_{\text{open}} \cdot 5.0 + 1.0) \cdot 10.0}{12.0}, 0.0, 1.0\right)$$
4. **Descarte Inmediato (*Opt-out por Ojos Cerrados*)**:
   - Si $p_{\text{closed}} > 0.60$ en cualquiera de los sujetos principales:
     - Etiqueta: **Morada** (`ConcreteColor::Purple`).
     - Calificación: **1 Estrella** (`Rating::One`).
     - Flag: `QuickFilter::ClosedEyes`.
   - **Regla de Excepción de Boda**: Si `kiss.rs` (`ranni_the_witch.jumbled`) se activa, el descarte ocular se suprime (es natural cerrar los ojos al besarse).

---

### 4.3 Pose, Mirada y Emoción
- **Pose (`adam_smasher.jumbled`)**:
  - Si $|\text{Yaw}| > 45^\circ$, el rostro se clasifica como *perfil*. Se ignora la penalización de mirada si la persona no mira a la cámara.
- **Mirada (`mimic_tear.jumbled`)**:
  - Calcula el ángulo de desvío pupilar $\theta_{\text{gaze}}$. Si $|\theta_{\text{gaze}}| < 12^\circ$ y el rostro está de frente, se otorga un bonus de conexión visual $+0.15$.
- **Emoción (`rennala.jumbled`)**:
  - Sonrisa genuina abierta: Bonus $+0.20$.
  - Expresión incómoda/tensa: Penalización $-0.10$.

---

### 4.4 Detección de Ráfagas y Duplicados (`fuxx` & `kmeans.rs`)
1. **Vector Híbrido de Similitud**:
   $$\text{Sim}(A, B) = 0.55 \cdot \cos(\mathbf{v}_{\text{image}}^A, \mathbf{v}_{\text{image}}^B) + 0.35 \cdot \text{Match}(\mathbf{f}_A, \mathbf{f}_B) + 0.10 \cdot \exp\left(-\frac{\Delta t}{2.0}\right)$$
2. **Clustering vía `linfa-nn`**:
   - Divide la sesión fotográfica en grupos conexos de tomas similares para competir entre sí por la estrella de selección.

---

### 4.5 Puntuación Maestra y Asignación de Estrellas (`coloring2\src\selection.rs`)
Cada foto que supera los filtros de descarte recibe un Score Compuesto Total (almacenado en el struct en el offset `0x13b8`):

$$S_{\text{total}} = 0.35 \cdot S_{\text{sharpness}} + 0.25 \cdot S_{\text{eyes}} + 0.15 \cdot S_{\text{emotion}} + 0.10 \cdot S_{\text{saliency}} + 0.15 \cdot S_{\text{godrick}}$$

Donde $S_{\text{godrick}}$ es la predicción del modelo maestro de 78.1 MB (`godrick_the_grafted.jumbled`) sobre la imagen de 224x224.

#### Asignación de Calificaciones dentro del Cluster:
- **Foto con $\max(S_{\text{total}})$ del cluster**:
  - **Calificación**: **5 Estrellas** (`Rating::Five`).
  - **Color**: **Verde** (`ConcreteColor::Green`) — *Key Photo / Pick*.
- **Alternativas directas con $S_{\text{total}} \ge 0.88 \cdot \max(S_{\text{total}})$**:
  - **Calificación**: **4 Estrellas** (`Rating::Four`).
  - **Color**: **Amarillo** (`ConcreteColor::Yellow`) — *Top Alternate*.
- **Alternativas válidas con $S_{\text{total}} \ge 0.75 \cdot \max(S_{\text{total}})$**:
  - **Calificación**: **3 Estrellas** (`Rating::Three`).
  - **Color**: Sin etiqueta de color.
- **Duplicados redundantes inferiores ($S_{\text{total}} < 0.75 \cdot \max$)**:
  - **Calificación**: **0 Estrellas** (`Rating::Zero`).
  - **Color**: Sin color o marcado para descarte.
