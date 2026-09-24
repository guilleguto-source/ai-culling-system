# Resumen de Cambios: Unificación RAW+JPG en Culling Inicial

Se ha implementado el soporte integral para que cada disparo en formato dual (**RAW + JPEG**) sea tratado como una sola entidad fotográfica en todas las fases del sistema.

## Cambios Realizados

1. **Estimación inicial (`backend/routers/culling.py`)**:
   - `get_culling_estimate`: Ahora agrupa los archivos por su directorio y nombre base (`stem`), contabilizando únicamente las tomas únicas reales antes de iniciar el trabajo.

2. **Decisión y Selección (`backend/services/decision.py`)**:
   - Se eliminó la inyección sintética de elementos duplicados para el RAW vinculado (`results.append(raw_res)`).
   - Ahora cada fotografía en `results` contiene la propiedad `linked_raw_path`. La lista de resultados para la UI (`GridView`, contadores, filtros) refleja exactamente el número de disparos únicos (1.225 fotos en vez de 1.821).

3. **Exportación XMP Dual (`backend/services/xmp_exporter.py`)**:
   - `export_results_to_xmp` y `export_results_to_xmp_generator`: Al exportar calificaciones, si la foto tiene un `linked_raw_path`, escribe automáticamente los metadatos (sidecar `.xmp`) tanto para el JPG como para el RAW de forma transparente en segundo plano.

4. **Persistencia de Snapshot (`backend/services/export_snapshot.py`)**:
   - `save_snapshot`: Registra tanto el archivo principal como el `linked_raw_path` en el snapshot de sesión para que la sincronización bidireccional desde Lightroom reconozca correcciones hechas sobre cualquiera de los dos formatos.

## Verificación Realizada

- **Tests Automatizados**:
  - Se creó `backend/tests/test_raw_jpg_pairing.py` verificando:
    1. Que `apply_decision_logic` no duplica elementos ante parejas RAW+JPG.
    2. Que `export_results_to_xmp` escribe los sidecars XMP tanto para el JPG como para el RAW con sus respectivas calificaciones.
  - Resultado: **2/2 passed**.
  - Batería de regresión (`test_selection_v2.py`, `test_xmp.py`, `test_pre_edit_xmp.py`, `test_lightroom_sync.py`): **30/30 passed**.
- **Estimación en Vivo**:
  - Verificado `get_culling_estimate` sobre carpeta con RAW+JPG, confirmando que devuelve el número de disparos únicos y no el conteo bruto de archivos.
