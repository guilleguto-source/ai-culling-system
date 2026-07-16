# Diseño: Pre-edición no destructiva — preset + WB por sesión + exposición por rostros (Fase 6)

**Fecha**: 2026-07-15
**Estado**: Aprobado
**Specs previas**: selección (fases 1-4), auto-crop (fase 5) — implementadas.

## Problema

Tras el culling, el usuario aplica a mano un preset, corrige WB y exposición
foto por foto. Automatizarlo como pre-edición: el look sale del preset del
usuario, el WB se uniformiza por bloques de luz y la exposición se mide sobre
las personas. Todo vía crs:* en el XMP existente — reversible, píxeles intactos.

## Arquitectura: segundo paso post-selección

El análisis usa TODAS las fotos (incluidas duplicadas/descartadas — más
muestras, medianas más robustas), pero solo se escribe en las `selected`.

Orden de capas en el paquete XMP: **preset (look) → WB de sesión → exposición
por foto → crop (fase 5)**. Los campos calculados pisan a los del preset.

## 1. Preset del usuario

- Formato: preset moderno `.xmp` de Lightroom (PV ≥ 11). Verificado con
  "GutoPro Day.xmp" del usuario.
- **Merge**: los atributos/elementos crs del preset se copian al paquete XMP
  de cada foto selected, EXCEPTO:
  - Metadatos de preset: `PresetType, UUID, Cluster, Supports*, ShowIn*,
    Name, ShortName, SortName, Group, Description, CameraModelRestriction,
    Copyright, ContactInfo, CompatibleVersion, Table_*, CompressedSettings,
    FilterList` (basura de catálogo).
  - `AutoTone` — pelearía contra nuestra exposición calculada.
  - `WhiteBalance, IncrementalTemperature, IncrementalTint` — el WB lo
    calculamos nosotros; los incrementos del preset (+5/+5) se conservan como
    SESGO sumado al WB calculado (es el look del usuario).
  - `Exposure2012` si existiera — la calculamos nosotros.
  - `Crop*` — fase 5 manda.
- **Máscaras IA** (`MaskGroupBasedCorrections` con MaskSubType=3: piel,
  esclerótica, iris, dientes, sujeto): se copian tal cual. Limitación Adobe:
  LR puede pedir "actualizar ajustes de IA" para recomputar la segmentación
  al abrir la foto. Documentar en UI (tooltip).
- **Gestión**: los presets usados se copian a `backend/models/presets/`;
  settings guarda los últimos 5 (ruta + nombre) y el activo. "Ninguno" válido.

## 2. Exposición — prioridad personas, sesgo +0.3 siempre

- Con rostros: luminancia mediana de la piel (región central de cada bbox,
  40-70% del alto para evitar pelo/frente quemada); entre rostros, la mediana.
  `stops = log2(target_skin / medida)` en luminancia lineal
  (sRGB→lineal). `target_skin` constante nombrada (calibrar en campo, inicial
  0.42).
- Sin rostros: mediana global del cuadro a tono medio (`target_mid = 0.18`).
- `Exposure2012 = clamp(stops, ±1.5) + bias` donde `bias` es configurable
  (slider −0.5..+0.5, default **+0.3, se aplica siempre**).
- **Acotado por consenso**: la corrección final no puede alejarse más de
  ±0.7 EV de la mediana de correcciones de su sesión de luz (calculada con
  todas las fotos de la sesión). Redondeo a pasos de 0.05.

## 3. WB — consenso por sesión de luz

### Estimación por foto
- Con personas: **prioridad piel** — pixeles de piel de los rostros; la
  desviación del tono de piel esperado da la dominante de color.
- Sin personas: **prioridad blancos** — pixeles luminosos (top ~10%) y de
  baja saturación; su desviación del neutro da la dominante.
- La dominante RGB se convierte a `IncrementalTemperature` (eje azul-ámbar)
  e `IncrementalTint` (eje verde-magenta), escala −100..100.

### Prioridad de personas (regla del usuario)
- La mediana de una sesión se calcula SOLO con las estimaciones de piel
  (fotos con personas) cuando la sesión tiene ≥3 de ellas; las estimaciones
  por blancos no votan en sesiones con gente — las pieles mandan siempre.
- Fotos de detalle/sin personas dentro de una sesión con gente: reciben por
  defecto el WB de la sesión (continuidad), SALVO que su propia estimación
  por blancos se desvíe fuerte de la mediana (> `DETAIL_OVERRIDE_DELTA`,
  inicial 10 unidades) — luz genuinamente distinta (ventana, flash) → se
  editan aparte con su estimación propia, clamp ±15.
- Sesiones enteras sin personas: mediana por blancos, como estaba.

### Sesiones de luz (histéresis)
- Firma por foto: (temp_est, tint_est, luminancia mediana), orden por hora
  EXIF (sin EXIF: orden de archivo).
- Una sesión SOLO se rompe cuando **≥4 fotos consecutivas** se desvían de la
  mediana móvil de la sesión más que el umbral (`SESSION_BREAK_DELTA`,
  inicial: 12 unidades incremental o 1.0 EV de luminancia). Fotos sueltas
  distintas (detalles, close-ups) permanecen en la sesión: reciben el WB de
  la sesión y sus estimaciones se excluyen de la mediana (rechazo por MAD).
- Sesiones con <5 estimaciones válidas heredan el WB de la sesión vecina más
  cercana en el tiempo.
- Aplicación: cada selected recibe la MEDIANA de su sesión (uniformidad
  total dentro del bloque) + el sesgo del preset, clamp final ±15.

### Limitación RAW
`IncrementalTemperature/Tint` solo aplica a no-RAW. En RAW (sidecar) el WB
se omite en esta fase (v2 requeriría Kelvin + As Shot); exposición y preset
sí se escriben (son absolutos).

## 4. Configuración y UI

- `selection_preferences.pre_edit`: `{enabled: bool (default true),
  preset_path: str | "", exposure_bias: float (-0.5..0.5, default 0.3),
  recent_presets: [hasta 5]}`.
- SettingsModal, sección "Pre-edición": toggle; zona drag&drop / botón buscar
  `.xmp`; dropdown de últimos 5; slider de sesgo −0.5..+0.5 (paso 0.05);
  nota de máscaras IA.
- Endpoints: `GET /presets` (recientes + activo), `POST /presets/use`
  (ruta → valida, copia, activa).

## 5. Salvaguardas

- Preset ilegible/incompatible → log WARNING, pre-edición sigue sin preset.
- Estimación WB sin pixeles útiles (ni piel ni blancos) → foto sin voto;
  recibe la mediana de sesión igualmente.
- `pre_edit.enabled=false` → fase completa omitida (XMP como hoy).
- El sync de Lightroom (fase 4) sigue comparando solo estrellas — las
  ediciones del usuario sobre sliders no generan ejemplos de gusto.

## 6. Testing

- Preset: merge excluye la lista negra completa; conserva curva/HSL/máscaras;
  sesgo WB del preset extraído (+5/+5).
- Exposición: cara sintética oscura → stops positivos; clamp ±1.5; bias
  sumado; acotado a mediana de sesión ±0.7.
- Sesiones: escenario del usuario — 50 fotos de 6 grupos con 3 detalles y un
  close-up intercalados → UNA sesión; 4+ fotos consecutivas distintas →
  corte; sesión chica hereda de vecina.
- WB: imagen con dominante cálida conocida → incrementos que la neutralizan
  (signo correcto); clamp ±15.
- XMP: paquete completo (preset+WB+exposición+crop) parsea y `xmp_reader`
  sigue leyendo Rating/Label.

## Fuera de alcance (YAGNI)

- WB Kelvin para RAW (v2).
- Ediciones locales generadas por nosotros (dodge/burn, máscaras propias).
- Aprender el estilo de edición del usuario.
- Presets `.lrtemplate` antiguos.
