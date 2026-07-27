# Calibración del pre-revelado contra el historial real (2026-07-27)

**Contexto**: se midieron las tres correcciones automáticas del pre-revelado
(exposición, enderezado, reencuadre) y el WB contra el historial de Lightroom
del fotógrafo (105.557 fotos, análisis local cacheado + develop/crop reales del
catálogo). Mismo método que Fase Q: medir antes de cambiar una regla por otra.

## Resultado por corrección

### Exposición — el bias fijo es la peor opción
Dataset: 54.321 fotos con `Exposure2012` real y firma de luz medida.

| Regla | MAE | Acierta "¿corregir o no?" |
|---|---|---|
| No tocar nada (0) | 0.093 EV | 79% |
| Bias fijo +0.3 (default viejo) | 0.296 EV | 21% |
| Modelo aprendido (Ridge / GBM, GroupKFold) | 0.140 EV | ~30% |

El usuario deja el **78% de sus fotos en exposición 0**. El bias fijo empuja el
histograma de fotos que jamás tocaría. Ni un modelo aprendido sobre la firma de
luz global le gana a "no tocar": sus correcciones dependen de señales que no
medimos (sujeto puntual, flash fallido, intención).

**Cambio**: `exposure_bias` default 0.3 → **0.0**; banda muerta **±0.15 EV**
(correcciones menores se anulan). El p90 de corrección real del usuario es +0.4,
así que lo chico es ruido.

### Enderezado — activamente dañino
Dataset: 7.709 fotos (4.679 que el usuario rotó + 3.030 control que dejó derechas).

| Métrica | Valor |
|---|---|
| Rotación típica del usuario | mediana 1.29°, media 1.77° |
| Error del detector donde opina (n=2.082) | MAE **4.80°** |
| Baseline "no rotar" en esas mismas fotos | MAE 1.77° |
| Falsas correcciones (>1° en fotos derechas) | **79.8%** |

El detector de horizonte (Hough) se engancha con mesas, marcos y guirnaldas en
fotos de evento. Erra 2.7x más que ignorar el problema y torcería 4 de cada 5
fotos ya derechas.

**Cambio**: `auto_straighten` default **False**, desacoplado del crop (antes el
enderezado venía acoplado dentro de `propose_crop`).

### Reencuadre — casi neutro pero inútil
Dataset: 7.642 fotos con recorte real.

| Métrica | Valor |
|---|---|
| Fotos que el usuario recorta (de todo el archivo) | 12% |
| Área retenida cuando recorta | mediana 76% |
| Acuerdo binario recortar/no | 19% |
| IoU propuesta vs real | 0.739 |
| IoU "marco completo" vs real | 0.746 |

El auto-crop no acierta la intención compositiva — es un pelín peor que no hacer
nada. No es dañino como el enderezado, pero su valor es ≈ 0.

**Cambio**: `auto_crop` default **"off"** (queda como sugerencia manual opt-in).

### WB — no calibrable, y el usuario aplica una firma fija
Dataset: 15.743 fotos con `Temperature` real.

**Todas son RAW, en Kelvin absoluto** (mediana 5100K, p10 4150, p90 5700).
**Cero JPG.** El estimador actual (`estimate_wb`) produce valores
**incrementales** para JPEG — un espacio de WB que el usuario nunca usa. No hay
ground truth para calibrarlo. Y su WB real es una firma tenue y constante
(≈5100K, tint mediana +9 magenta, spread apretado), no corrección por foto.

**Cambio**: `auto_wb` default **False** — la corrección adaptativa por piel se
apaga; sobrevive el sesgo del preset y el consenso por sesión (evita saltos
bruscos dentro de una ráfaga).

## Hilo común

Las tres correcciones geométricas/tonales dan el mismo resultado: la edición del
usuario es **mínima, consistente e intencional**, y su intención no es predecible
desde las señales medidas. El valor del sistema está en el **culling** (real) y
en **quitarse del medio** en la edición. Todo queda disponible como opt-in; solo
cambió el default a "no estorbar".

## Bancos de prueba guardados (backend/scripts/out/)
- `enderezado_benchmark.json` — 7.709 casos ángulo detectado vs real.
- `reencuadre_benchmark.json` — 7.642 casos IoU propuesta vs recorte real.
- (exposición y WB se re-derivan de history.db + análisis cacheado.)

## Pendiente
- Migrar el `settings.json` del usuario: tiene guardado `auto_crop: medio` y
  `exposure_bias: 0.4` (el merge conserva lo guardado sobre los nuevos defaults).
- WB por escena con las 15.743 muestras de Temperature: condicionar por los 12
  clusters de escena (p.ej. no auto-corregir WB en pista de baile con LEDs).
  No intentado — requiere mapear el espacio absoluto RAW al incremental.
