# Spec: Photo Selector — Proyecto 2: Edición con tu Estilo (Perfiles IA)

> Estado: borrador exploratorio · Fecha: 2026-06-26
> **Depende de:** Proyecto 1 (motor de selección) funcionando. Este proyecto NO se
> empieza hasta validar el Proyecto 1.

## Objective

Aprender el **estilo de revelado** del fotógrafo a partir de fotos que él ya editó, y
predecir los ajustes de revelado para fotos nuevas, escribiéndolos como **XMP de develop**
para que aparezcan ya editadas (no destructivo) al abrir Lightroom.

- **Usuario:** el mismo fotógrafo, después de seleccionar (Proyecto 1).
- **Problema:** tras seleccionar las keepers, editarlas una por una sigue siendo lento.
- **Éxito:** sobre fotos nuevas del mismo tipo de evento, las predicciones acercan la foto
  a "casi terminada" (exposición, balance de blancos y color en el rango correcto), de modo
  que el retoque manual final sea mínimo.

> **Realismo:** esto es bastante más difícil que la selección. La selección usa modelos
> pre-entrenados; el estilo de edición hay que **entrenarlo con tus ediciones**, y la
> calidad depende de cuántas fotos editadas tengamos. Es un proyecto de I+D, no un clon directo.

## Por qué NO un plugin de Lightroom

El SDK de Lightroom (Lua) no puede ejecutar modelos de ML pesados. Pero Lightroom guarda
todo el revelado como **develop settings en XMP** (namespace `crs:`). Por eso el patrón
es el mismo que la selección: el músculo vive en un proceso Python externo que **escribe
XMP de revelado**; Lightroom solo lee el resultado. Un plugin Lua fino (botón
"enviar al motor / traer resultado") es opcional, nunca el motor.

## Tech Stack (propuesto)

- **Python 3.11**, comparte utilidades de I/O con el Proyecto 1.
- **Extracción de features:** estadísticos de imagen (histogramas por canal, temperatura
  estimada, luminancia media/percentiles, contraste, saturación, detección de piel/cielo).
- **Modelo:** regresión por parámetro (gradient boosting `lightgbm` o MLP pequeño) que
  mapea features → ajustes de revelado. Un modelo por grupo de parámetros del panel básico.
- **Parámetros objetivo (panel básico CRS):** `Exposure2012`, `Contrast2012`,
  `Highlights2012`, `Shadows2012`, `Whites2012`, `Blacks2012`, `Temperature`, `Tint`,
  `Vibrance`, `Saturation`. (Curva de tono y HSL como fase posterior.)
- **Lectura de datos de entrenamiento:** parsear los XMP / catálogo de fotos ya editadas
  para obtener (imagen original → ajustes de revelado del usuario).

## Commands (propuesto)

```bash
# Entrenar un perfil a partir de fotos editadas del usuario
photostyle train ./fotos-editadas --profile escolar-v1

# Aplicar el perfil a fotos nuevas (escribe XMP de revelado)
photostyle apply ./evento-nuevo --profile escolar-v1

# Evaluar: error medio de cada parámetro contra un set de validación
photostyle eval ./validacion --profile escolar-v1
```

## Project Structure (propuesto)

```
photostyle/
  cli.py
  features.py        → extrae features de imagen
  dataset.py         → empareja (imagen → develop settings) desde XMP/catálogo
  model.py           → entrena/predice por parámetro
  xmp_develop.py     → escribe ajustes crs: al sidecar
  profiles/          → modelos entrenados serializados
```

## Data Flow

```
Entrenamiento:  fotos editadas → dataset(imagen, develop_settings)
                → features → model.fit por parámetro → profile

Aplicación:     foto nueva → features → model.predict
                → xmp_develop (crs:) → Lightroom muestra la foto editada
```

## Testing Strategy

- **Dataset:** verificar que el parseo de XMP recupera correctamente los develop settings
  conocidos de un XMP de referencia.
- **Modelo:** hold-out; reportar MAE por parámetro en unidades de Lightroom (p. ej.
  Exposure en stops). Definir umbrales de "suficientemente bueno" por parámetro.
- **XMP develop:** escribir/releer; abrir en Lightroom y confirmar que los valores
  aplican sin corromper el archivo.

## Boundaries

- **Siempre:** no destructivo (solo XMP); preservar el original; versionar perfiles.
- **Preguntar primero:** qué set de fotos usar para entrenar; añadir parámetros de revelado
  al alcance (HSL, curva, máscaras).
- **Nunca:** sobrescribir ediciones existentes sin confirmación; entrenar con fotos que no
  sean del usuario.

## Success Criteria (a refinar tras Proyecto 1)

1. Con N fotos editadas (N a determinar; orientativo ≥ 300–500), el MAE de exposición y
   temperatura cae por debajo de un umbral que el usuario considere "retoque mínimo".
2. Sobre fotos nuevas del mismo tipo de evento, el usuario reporta que la edición predicha
   ahorra tiempo real frente a editar desde cero.
3. Los XMP de revelado se abren correctamente en Lightroom.

## Open Questions

1. **Volumen de datos de entrenamiento disponible:** ¿cuántas fotos ya editadas (con sus
   XMP/catálogo) tienes para arrancar? Es el factor limitante #1.
2. **¿Un perfil global o por tipo de evento** (escolar, social, exterior)? La luz cambia mucho.
3. **Alcance del revelado:** ¿basta el panel básico (exposición/WB/tono/color) o necesitas
   también curva, HSL, máscaras de IA? Propuesta: empezar por el panel básico.
4. **Origen de los datos:** ¿XMP sidecars, o hay que leer el catálogo `.lrcat` (SQLite)?
```
