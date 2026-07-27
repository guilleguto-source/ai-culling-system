# Plan de corrección: bugs de la revisión completa (2026-07-26)

**Contexto**: revisión sistemática post-commit de las 3 fases (`8c592e3`, `6450aef`,
`9b26f74`) encontró 4 bugs reales y 3 inconsistencias menores, concentrados en las
features nuevas sin tests (storyline, búsqueda semántica server-side, VLM, blink).
Decisiones del usuario: **arreglar la integración del blink ya** (no descablear) y
**probar el VLM end-to-end contra su Ollama local** (tiene llama3.2-vision).

**Regla del plan**: cada fix entra con el test que lo habría atrapado. Un solo
commit `fix:` al final con todo verificado.

---

## Fase 1 — Revivir `/storyline` (NameError: current_directory)

**Bug**: `main.py` lee `current_directory` que **nunca se asigna** → 500 en toda
llamada. `StorylineTimeline.tsx` lo llama al montar → la feature está muerta.

**Diseño**: endpoint stateless, igual que `/search/semantic`:
- `GET /storyline?directory=...&gap=30` — `directory` obligatorio (422 si falta).
- Eliminar toda referencia a `current_directory`.
- `MainContent.tsx` ya tiene `directory`: pasarlo como prop a `StorylineTimeline`
  y que este lo incluya en el fetch (y re-fetchee si cambia).

**Tests** (`test_storyline_api.py`):
- `/storyline` sin `directory` → 422.
- Con directorio sin análisis → `{"storyline": []}` sin crash.
- `build_storyline` con fotos sintéticas cacheadas → capítulos por hueco temporal
  y `medoid_thumb` con `size=ui` y ruta URL-encodeada (espacios/tildes).

---

## Fase 2 — Thumb malformado en `/search/semantic`

**Bug**: `main.py:254` arma `"/thumbnail?path={path}&type=ui"` — parámetro
inexistente (`type` en vez de `size`) y ruta sin encodear. Mismo bug que ya se
arregló en storyline_builder pero quedó duplicado acá.

**Diseño**: helper único `thumb_url(path, size="ui")` (en `thumbnail_store` o
util pequeño) usado por `main.py` y `storyline_builder.py` — una sola fuente del
formato de URL, se acabó el bug duplicado.

**Tests**: unit del helper (encodea espacios/tildes, usa `size=`); test del
endpoint con `search_photos` monkeypatcheado verificando el `thumb` devuelto.

---

## Fase 3 — Integración del blink classifier (AttributeError latente)

**Bug**: `analysis.py:135` hace `a.eyes_closed = bool(...)` pero `eyes_closed`
es `@property` sin setter en `FaceAttributes` → `AttributeError` apenas exista
`blink_detector.onnx`. Nunca se probó con modelo. Además el comentario dice
"persistir la decisión híbrida" pero `face_attrs` ya se serializó antes del loop
(no persiste nada).

**Diseño** (arreglar en serio, decisión del usuario):
- No mutar `FaceAttributes`. Calcular la decisión híbrida en variables locales:
  `closed_eyes_count` desde el score compuesto SIN tocar los objetos.
- Persistir la decisión por cara agregando la clave `"closed_hybrid": bool` al
  dict de `face_attrs` (post `to_dict`), para que calibración/UI puedan verla.
- Serializar `face_attrs` DESPUÉS del bloque híbrido, no antes.
- Guard de longitud: `predict_eyes_open` devuelve por cara de `face_bboxes`;
  indexar con cuidado cuando `eye_landmarks` viene corto (ya lo hace, verificar).
- Documentar en el bloque: **cuando se consiga un blink_detector.onnx real hay
  que subir ANALYSIS_VERSION** (cambia QUÉ se mide; el caché no distingue).

**Tests** (`test_blink_integration.py`):
- Con `blink_classifier` monkeypatcheado (disponible, probs conocidas):
  `analyze_photo` no tira AttributeError y los conteos reflejan el score
  compuesto; `face_attrs` incluye `closed_hybrid`.
- Sin modelo (is_available=False): fallback MediaPipe intacto (conteos = suma
  de `eyes_closed` de válidas).

---

## Fase 4 — VLM refiner: mandar thumbnails, no originales (+ prueba real)

**Bug**: `main.py` pasa `records[i].path` (archivo ORIGINAL) y `_encode_image`
lo base64-ea crudo: un RAW es indecodificable para el VLM y un JPG de 20-40MB
revienta el timeout de 15s.

**Diseño**:
- `vlm_refiner`: nueva `_load_thumb_b64(path)` — lee el thumb "duel" (1600px
  WebP) de `thumbnail_store`; `cv2.imdecode` → `imencode('.jpg')` → base64
  (JPEG porque es lo que la tubería de visión de Ollama digiere seguro).
- Si NO hay thumb cacheado para alguna candidata → `return None` (no enviar
  originales jamás; el culling sigue con el score frío).
- Timeout 15s → 45s (modelo de visión en CPU local; es opt-in y solo en empates).
- `except (URLError, TimeoutError, Exception)` → excepciones concretas
  (`URLError`, `TimeoutError`, `json.JSONDecodeError`, `KeyError`) + un
  `except Exception` separado con log de stacktrace (no silencioso).
- **Riesgo conocido a validar en vivo**: llama3.2-vision maneja UNA imagen por
  mensaje de forma confiable; con 3 puede degradar. Si la prueba real muestra
  respuestas incoherentes → plan B en esta misma fase: componer UN collage
  lado-a-lado con etiquetas "0", "1", "2" y mandar una sola imagen.

**Prueba end-to-end (Ollama del usuario corriendo)**:
1. `GET http://localhost:11434/api/tags` → confirmar llama3.2-vision.
2. Tomar una ráfaga real ya analizada (thumbs duel en caché), llamar
   `decide_winner` con 2-3 candidatas casi idénticas.
3. Verificar: responde índice válido, latencia aceptable, y repetir 3 veces
   para ver estabilidad (temperature 0.1).
4. Si incoherente → implementar collage y repetir.

**Tests offline** (sin Ollama, monkeypatch de urlopen): parseo de respuesta
("2", "La mejor es 1", basura → None), candidata sin thumb → None, timeout →
None sin excepción.

---

## Fase 5 — Menores

- `SemanticSearchBar.tsx`: agregar `directory` a las deps del `useEffect`
  (closure stale al cambiar de carpeta con búsqueda activa).
- `run.py`: respetar `--port` (hoy ignora el argumento que le pasa el Electron
  empaquetado y hardcodea 8000 — funciona por coincidencia).
- `exif_info.py:43`: `except (OSError, Exception)` → `except OSError` + log.

---

## Fase 6 — Verificación y cierre

1. `pytest backend/tests` completo (257 + los nuevos, 0 fallos).
2. `tsc --noEmit` limpio.
3. Prueba manual con la app: storyline renderiza capítulos con miniaturas en
   una carpeta real (con espacios en el nombre), búsqueda semántica muestra
   thumbs, VLM decide en un empate real.
4. Un commit: `fix: storyline sin estado global, thumbs encodeados, blink sin
   AttributeError y VLM sobre thumbnails` (+ tests nuevos).

**Orden**: 1 → 2 → 3 → 5 → 4 (el VLM al final porque depende de Ollama activo
y puede requerir la iteración del collage).
