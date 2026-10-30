# Plan: Purga de Términos Sensibles & Enriquecimiento Visual de Alto Nivel

## Contexto Digerido
El usuario solicita expresamente NO mencionar "ingeniería inversa" ni exponer detalles excesivos o códigos hexadecimales de metadatos. La presentación debe enfocarse en "diferentes algoritmos especializados", "visión por computador" y "procesamiento avanzado", manteniendo un tono profesional, general con detalles clave y altamente visual.

## Archivos Afectados
- `README.md` (eliminación de referencias a tags hexadecimales/ingeniería inversa; redacción ejecutiva de alto nivel; integración de muestras visuales).
- `CHANGELOG.md` (ajuste de redacción técnica hacia descripciones algorítmicas generales).
- `assets/showcase/` (activos visuales y comparativas gráficas antes/después).

## Checklist de Tareas
- [ ] **1. Depuración de Contenido Sensible en README y CHANGELOG:**
  - Sustituir menciones de tags EXIF hexadecimales (`0x0017`, `0x200B`, `0x001D`, etc.) por "algoritmos especializados de agrupación temporal y hardware en Rust".
  - Eliminar cualquier alusión a ingeniería inversa o desensamblado; describir como "algoritmos de visión computacional, segmentación semántica y compatibilidad estándar con metadatos XMP".
- [ ] **2. Tono General y Profesional (Sin Fuga de Secretos):**
  - Enfocar en beneficios para el fotógrafo: velocidad, precisión, 100% offline, respeto de selecciones y paridad de edición.
- [ ] **3. Galería Visual "Antes vs. Después" en README:**
  - *Culling Inteligente:* Descarte (ojos cerrados/distracción) vs. Foto seleccionada (Hero Shot).
  - *Alineación Geométrica:* Corrección angular sutil de horizonte.
  - *Segmentación Avanzada:* Muestra visual de separación por capas (piel, vestimenta, fondo) a partir de `docs/audit_mattes/`.
- [ ] **4. Vista Previa de la Experiencia de Usuario:**
  - Mockup/tarjeta gráfica representativa del entorno Digital Darkroom.
