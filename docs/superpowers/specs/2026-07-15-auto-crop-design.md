# Diseño: Auto-crop no destructivo (Fase 5)

**Fecha**: 2026-07-15
**Estado**: Aprobado
**Spec previa**: `2026-07-15-seleccion-embeddings-design.md` (fases 1-4, implementadas)

## Problema

Además de seleccionar, el sistema puede proponer un mejor encuadre: tercios /
proporción áurea, espacio de mirada, horizonte nivelado. Debe ser reversible y
nunca destructivo.

## Solución: crop propuesto vía XMP

El recorte se escribe como metadatos de Camera Raw en el mismo XMP que ya
exportamos (sidecar RAW / APP1 JPEG):

- `crs:HasCrop=True`, `crs:CropLeft/Top/Right/Bottom` (fracciones 0..1),
  `crs:CropAngle` (grados), `crs:CropConstrainToWarp=0`.
- Lightroom muestra la foto ya reencuadrada; el usuario ajusta o quita el
  crop con un clic. Los píxeles originales nunca se tocan.
- Se mantiene SIEMPRE la proporción original de la foto.

## Niveles de recorte (configuración)

`selection_preferences.auto_crop`: `off | minimo | medio | agresivo`.
**Default: `minimo`.** Solo se procesa en fotos con label `selected`.

Límite = máximo % lineal removible por dimensión (ancho y alto por separado):

| Nivel     | Recorte máx. lineal |
|-----------|---------------------|
| off       | — (no se escribe crop) |
| minimo    | 10%                 |
| medio     | 20%                 |
| agresivo  | 35%                 |

## Reglas por tipo de escena

### Grupos (≥3 rostros)
- SOLO nivelado de horizonte. Sin recomposición, independiente del nivel.
- Ángulo máximo a corregir: ±7°. Más allá → se asume holandés intencional o
  error de detección → no se toca.
- La rotación consume recorte inevitable (≈1.5% lineal por grado). Si nivelar
  exige >8% lineal → no se nivela.

### Retratos / parejas (1-2 rostros)
- Nivelado (mismas reglas de grupos) + recomposición dentro del nivel:
  - Rostro dominante (mayor área) al punto fuerte de tercios más cercano.
    Con nivel `agresivo` se permite también proporción áurea (φ ≈ 0.618) si
    queda mejor que tercios.
  - Espacio de mirada: ~⅔ del aire horizontal hacia donde apunta la nariz
    (dirección estimada con landmarks YuNet: nariz vs centro de ojos).
- Margen de seguridad: ningún rostro a menos de 0.5× su propio tamaño del
  borde del crop propuesto.

### Detalles / sin rostros
- Nivelado + región de saliencia (ya calculada) al punto fuerte de tercios
  más cercano, dentro del nivel.

## Detección de horizonte

- Hough probabilístico sobre bordes (Canny) en la mitad superior/central de la
  imagen; candidatas = líneas largas casi horizontales (|θ| < 15°).
- Ángulo = mediana ponderada por longitud de las candidatas. Sin candidatas
  suficientemente largas (< 25% del ancho) → no se nivela.

## Salvaguardas globales

1. Cambio total propuesto < 2% lineal y |ángulo| < 0.5° → no se escribe crop.
2. Si el crop propuesto corta cualquier rostro (bbox + margen) → descartado.
3. `auto_crop=off` o foto no-`selected` → sin crop.
4. El crop se escribe junto al rating existente sin pisarlo (mismo paquete
   XMP: Rating + Label + PickStatus + crs:Crop*).
5. El sync desde Lightroom (Fase 4) ignora los campos crs — solo compara
   estrellas; un crop ajustado por el usuario no genera ejemplos de gusto.

## Componentes

- `backend/services/auto_crop.py` (nuevo): geometría pura —
  `detect_horizon_angle(img_gray) -> float | None`,
  `propose_crop(scene_type, face_bboxes, eye_landmarks, saliency_region,
  img_shape, level) -> CropProposal | None` con
  `CropProposal(left, top, right, bottom, angle)` en fracciones.
- `xmp_exporter.py`: extender `_build_xmp_packet` para incluir campos crs
  opcionales; `write_xmp(..., crop: CropProposal | None)`.
- `main.py`: en FASE 4 del pipeline, calcular propuesta para las `selected`
  y pasarla al export. Resultado incluye `has_crop` para la UI.
- `SettingsModal.tsx`: selector de nivel (off/mínimo/medio/agresivo).
- UI Grid/Duel: badge "✂" en fotos con crop propuesto (informativo).

## Testing

- Geometría: fixtures sintéticas — cara en borde → crop la respeta; cara
  descentrada → crop la acerca a tercios sin exceder el nivel; grupo → solo
  ángulo; ángulo 10° → no se nivela; recorte necesario > límite → recorte
  parcial hasta el límite o descarte.
- Horizonte: imagen sintética con línea a 3° → detecta ≈3°; sin líneas → None.
- XMP: paquete con crs:Crop* parsea y conserva Rating/Label; roundtrip con
  xmp_reader no rompe el sync.

## Fuera de alcance (YAGNI)

- Estimación de mirada con modelo dedicado (gaze estimation neural).
- Leading lines como criterio de composición.
- Aplicar el crop a los píxeles (export de JPGs recortados).
- Aprender preferencias de encuadre del usuario.
