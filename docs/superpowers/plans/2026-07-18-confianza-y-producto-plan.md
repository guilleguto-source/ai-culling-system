# Plan de implementación: confianza, seguridad y producto

**Fecha**: 2026-07-18
**Contexto**: tres revisiones externas de UX/producto sobre Guto Flow. Este plan
recoge **solo lo que se sostiene con datos reales del sistema** y descarta
explícitamente lo que exigiría inventar métricas. Ver el estado del sistema en
`docs/GutoFlow-estado-actual.md`.

## Diagnóstico que comparten las tres revisiones (y es correcto)

El motor está muy por delante de la interfaz. El usuario **no ve** el 80% de la
inteligencia construida, **no entiende** por qué la IA decide lo que decide, y
**teme** que le arruine sus archivos. Eso frena la adopción más que un AUC
imperfecto.

## Qué se EXCLUYE de este plan (y por qué)

Las tres revisiones proponen widgets con números que **no existen**:
- "Confianza 87% / Estilo aprendido 96% / Coincidencia 95.4%" → el número real
  del gusto es **AUC 0,69**. Mostrar un 96% inventado destruye la confianza el
  día que la IA falle.
- "418 personas conocidas" → ArcFace **no está cableado** (Fase P lo arregla).
- "Niño con varita", "Cluster #42 — Grupo de niños en exterior" → requieren un
  modelo de descripción de imágenes que **no tenemos**.
- "Explain AI: Nitidez 25%, Ojos 20%, Sonrisa 18%…" → nuestra decisión son
  *gates binarios* + un score de embedding de 512 dims; **no es descomponible**
  en esos porcentajes. Se reemplaza por la Fase N, que sí es verdad.

**Regla del plan: ninguna cifra en pantalla que no salga de una medición real.**

## Principio de orden

**N y O primero** (honestidad y seguridad): hoy la UI afirma algo falso y el
export puede pisar el trabajo del usuario sin vuelta atrás. Ningún rediseño
tiene sentido encima de eso. Después **P** (valor ya construido sin usar) y
**Q** (calidad del modelo). El rediseño visual (**T**) va después, porque
hereda de N.

---

## Fase N — Explicabilidad: "por qué ganó" (y arreglar el cartel que miente)

**Problema**: el duelo dice *"Elegida por la IA (mejor score)"*, pero cuando la
decisión la toma un **gate técnico** la elegida puede tener *menor* score que
una alternativa. Está observado en pantalla (elegida 0.66 vs alternativa 0.75).
La UI afirma algo falso, y encima no explica nada.

**Diseño**:
- `cluster_gates.apply_technical_gates` pasa a devolver también **por qué**
  cayó cada descartada (`ojos_cerrados`, `rostro_blando`), no solo la lista de
  supervivientes.
- `decision.apply_decision_logic` emite por foto un campo `reasons: list[str]`
  con hechos comparativos reales: qué gate la sacó, nitidez de rostro vs la
  ganadora, conteo de ojos cerrados / miradas fuera, y **quién decidió**
  (gate técnico vs score vs modelo de gusto).
- El texto del duelo pasa a reflejar el motivo real: *"Elegida por la IA"* +
  el criterio (`mejor score` / `única sin ojos cerrados` / `rostro más nítido`).
- UI: bullets en la tarjeta ganadora ("✔ ojos abiertos · ✔ rostro más nítido")
  y en las perdedoras ("✖ ojo izquierdo cerrado").

**Riesgo**: bajo, es aditivo. No cambia ninguna decisión, solo la explica.

**Tests**: `test_explicabilidad.py` — un cluster donde el gate decide produce
`reasons` con el gate y **no** dice "mejor score"; un cluster donde gana por
score lo indica así; sin gates ni datos, `reasons` queda vacío sin romper.

---

## Fase O — Seguridad: snapshot previo + Deshacer

**Problema**: el export **escribe en los archivos reales** del usuario (XMP
embebido en JPG, sidecars de RAW) y **no guardamos el estado anterior**. Un
culling mal configurado pisa ratings de horas de trabajo sin vuelta atrás. Es
la barrera de entrada más seria para un profesional.

**Diseño**:
- Antes de escribir, leer el estado previo de cada archivo con
  `read_xmp(path, full=True)` (rating, color, banderín, revelado, recorte) y
  guardarlo en el snapshot del evento bajo `previous_state`.
- `POST /undo_export {directory}`: restaura el estado previo de cada archivo
  del último export. Idempotente y con reporte de cuántos restauró.
- Los archivos que **no tenían** XMP se registran como tales y se limpian al
  deshacer (no se les inventa un rating).
- UI: botón "Deshacer último culling" visible tras el export, con confirmación
  que diga exactamente cuántos archivos va a revertir.

**Riesgo**: medio — toca escritura de archivos. Mitigación: el snapshot previo
se escribe **antes** de tocar nada; si falla su captura, se aborta el export.

**Tests**: `test_undo_export.py` — roundtrip (estado previo → export → undo →
estado idéntico); archivo sin XMP previo queda sin XMP tras el undo; undo sin
export previo devuelve error claro.

---

## Fase P — Cablear ArcFace: identidad y cobertura por persona

**Problema**: el módulo de identidad, la alineación de 5 puntos, el
agrupamiento y la política de cobertura están **construidos y validados**
(misma persona 0,90–0,95; distintas <0,30) pero **no se ejecutan**. Es la
función más diferenciadora y hoy vale cero.

**Diseño**:
- `analyze_photo`: calcular el embedding de identidad por cara detectada
  (guardado por `face_identity.is_available()` + preferencia). Se guarda en
  `PhotoAnalysis` (en memoria; no se persiste en el caché de análisis).
- Tras la decisión, agrupar identidades del evento
  (`group_event_identities`) y aplicar `decision.photos_for_coverage` para
  **promover** la mejor foto de cada persona que quedó sin ninguna
  seleccionada. Solo suma, nunca baja nada.
- UI: panel "Personas detectadas" con **miniatura de cara + contador de fotos**
  por identidad. **Sin nombres inventados** — el usuario puede nombrarlas él.
- Preferencia para excluir una identidad de la garantía de cobertura
  (invitados de fondo, personal del salón).

**Riesgo**: coste por rostro durante el análisis; degradación a no-op si falta
el modelo. En corridas con análisis cacheado no habrá identidades → la
cobertura simplemente no actúa (seguro).

**Tests**: los de agrupamiento y cobertura ya existen; añadir el cableado —
evento con N identidades selecciona ≥1 por identidad; identidad excluida no
fuerza promoción.

---

## Fase Q — Gusto por pares dentro de la ráfaga

**Problema**: el gusto absoluto ("elegida vs descarte") da **AUC 0,69**, apenas
sobre el baseline. Estructural: las 1★ son fotos que el fotógrafo editó y
después bajó — visualmente casi idénticas a las que conservó. Y muchos rechazos
son por **redundancia dentro de la ráfaga**, no por una propiedad visual
absoluta.

**Diseño**:
- Reconstruir ráfagas del historial (agrupamiento existente por phash+tiempo)
  y usar **solo las revisadas** (que contienen al menos una 2★+).
- Dentro de cada una: ganadoras (2-3★) vs perdedoras (0-1★/negro) → pares a
  `taste_model.learn_preference`. Balanceado por construcción y comparando
  alternativas parecidas, que es la tarea real.
- **Medir honestamente**: AUC antes vs después, con validación cruzada. Si no
  sube, se documenta y se conserva el modelo anterior.
- **"Aprobar IA"** en el duelo: hoy solo aprendemos cuando el usuario
  *corrige*; el acuerdo se descarta. Un botón de confirmación genera el par
  positivo (elegida > mejor alternativa).

**Riesgo**: la mejora es una hipótesis razonable, **no una garantía**. El plan
es medir, no prometer 0,80.

**Tests**: `test_taste_pairwise.py` — ráfaga sin 2★ no genera pares; ganadora
vs perdedora genera el par correcto; idempotencia.

### RESULTADO MEDIDO (2026-07-18) — la hipótesis NO se confirmó

Medido sobre **2.235 pares de 1.712 ráfagas** del historial, evaluando la tarea
real ("dado un par de la misma ráfaga, ¿pone arriba a la que el fotógrafo
eligió?") con validación cruzada agrupada por ráfaga:

| Enfoque | Acierto |
|---|---|
| Azar | 50,0% |
| Producción, fórmula en frío (`0.6·nitidez + 0.4·estética`) | 61,2% |
| Producción, taste_model *(con fuga: cota alta)* | 62,7% |
| Rasgos técnicos (ojos, nitidez de rostro, sonrisa, blur) | 62,0% (±1,7) |
| **CLIP entrenado en pares** | **64,2%** (±2,0) |

**Conclusiones:**

1. **El enfoque por pares no mejora al absoluto** (63,9% vs 64,2% en una
   medición previa sobre los mismos datos). No se aplicó ningún cambio de
   modelo.
2. **Producción no está rota.** La sospecha de que el taste_model "pisaba la
   señal buena" al reemplazar la fórmula en frío **no se sostiene**: queda a
   mitad de tabla, no último.
3. **Todo cae en una banda de 61–64% con ±2 de error.** El techo con las
   señales actuales es ~64%: el problema no es qué modelo se elige, es que la
   tarea es intrínsecamente difícil. Ningún cambio de forma del modelo va a
   mover esto de forma significativa.
4. **Lección de método**: una medición previa sobre 300 pares dio el orden
   INVERSO (rasgos técnicos 62,3% vs CLIP 56,3%) y llevó a recomendar un cambio
   de ranking que resultó equivocado. Era ruido de muestra chica. **No sacar
   conclusiones de <1.000 pares.**

**Lo que sí podría mover la aguja** (no intentado):
- Embeber las ~79.775 fotos en 0★ (~17 h) para obtener los pares *elegida vs
  sus hermanas en cero*, que son los informativos y hoy faltan por completo:
  todos los pares medidos fueron positiva-vs-negativa.
- Señales de **detalle facial fino** (nitidez del ojo, apertura exacta,
  micro-expresión) en vez de representaciones globales. Es lo que distingue dos
  fotos casi idénticas, y ni CLIP ni los rasgos actuales lo capturan.

**Estado del código**: la infraestructura de pares (`build_burst_pairs`,
`/history/feed-taste-pairs`) queda construida y testeada pero **sin alimentar
el modelo**. Destapó un bug real de producción (fechas del catálogo con y sin
zona horaria que reventaban al ordenarlas).

---

## Fase R — Detectar cambios del catálogo (sync proactivo)

**Problema**: el sync depende de que el usuario haga *Guardar metadatos al
archivo* en Lightroom. Si no lo hace, leemos archivos sin cambios y no hay
aprendizaje. Hoy solo lo avisamos **después** de un sync vacío.

**Diseño**:
- Reusar `lr_catalog` (ya existe): comparar el rating/pick del catálogo contra
  el XMP en disco para las fotos del evento.
- Si difieren: avisar de forma accionable — *"Lightroom tiene N cambios que no
  están en los archivos. Exportá los metadatos (Ctrl+S) y volvé a sincronizar."*
- Integrarlo en el recordatorio de sync existente.

**Riesgo**: bajo. Solo lectura del catálogo, ya probado.

**Tests**: `test_catalog_diff.py` — catálogo con rating distinto al XMP detecta
la diferencia; iguales no reportan nada; sin catálogo, no-op.

---

## Fase S — Modo repaso por incertidumbre

**Problema**: revisar 182 clusters es inviable. El usuario necesita revisar
solo donde el sistema dudó.

**Diseño**:
- Reusar el patrón que ya usa la calibración (muestreo por incertidumbre):
  ordenar los clusters por cuán reñida fue la decisión (diferencia de score
  entre la ganadora y la segunda, o gates que casi no se aplicaron).
- Vista "Repaso": solo los N clusters más dudosos.
- Las decisiones del repaso alimentan el gusto (Fase Q).

**Tests**: ordenamiento por margen de decisión; cluster con ganadora clara
queda al final.

---

## Fase T — Rediseño cluster-céntrico

**Problema**: hoy hay dos modos separados (Grid de todo + Duelo) y el usuario
no tiene progreso, filtros ni contexto.

**Diseño** (lo mejor del mockup, sin los datos inventados):
- **Flujo cluster por cluster**: ganadora + alternativas juntas, navegación
  Anterior/Siguiente, contador "42 de 182" y barra de progreso.
- **Filtros**: Todas / Por revisar / Seleccionadas / Descartes / Ojos cerrados.
- **Scores visuales** (barra) en vez de números crudos; "Blur 416" →
  **nitidez normalizada**.
- `aspect-ratio` fijo con recorte en las miniaturas (elimina las barras negras).
- **Atajos de teclado**: 1-5 elegir, → siguiente, D descartar.
- **Idioma unificado en español** — solo el *display*; las claves internas
  (`selected`, `duplicates`…) están cableadas al mapeo de estrellas y al XMP y
  **no se tocan**.
- Panel lateral: reemplazar "Backend engine / Online" por **"Tu estilo"** con
  números **reales**: fotos aprendidas, decisiones registradas, escenas
  descubiertas, recorte habitual, receta de revelado, último sync. Lo técnico
  (hardware, modelos) baja a una barra de estado discreta.

**Riesgo**: es el cambio más grande de UI. Hacerlo **después de N** para no
rediseñar sobre una afirmación falsa.

---

## Fase U — EXIF y previsualización de la pre-edición

- Leer lente, apertura, ISO y velocidad (hoy solo leemos la fecha) y mostrarlos
  en el panel lateral. Plomería nueva pero barata.
- **Preview de la pre-edición**: aplicar exposición/WB/recorte sobre el thumb
  para que el usuario vea el resultado **antes** de escribir. Hoy "Aplicar
  edición" trabaja a ciegas.

---

## Fase V — Settings reestructurado

- Pestañas (IA / Workflow / Pre-edición / Lightroom / Aprendizaje /
  Rendimiento / Avanzado) y modo **Simple vs Avanzado**.
- **Los parámetros ya existen** (selectividad, blur, ojos, crop, exposure bias,
  preset): es re-empaquetado, no desarrollo.
- **Perfiles de workflow** (Bodas / Infantil / Corporativo…): bundles con
  nombre de esos mismos ajustes.
- Ayuda contextual por opción.
- Simulación: reusar `/reselect` (**ya existe**) para previsualizar el efecto de
  un cambio de ajustes sin re-analizar.

---

## Fase W — Entorno aislado

Mover el backend de la Python del sistema a `backend/.venv` (instalando ahí
mediapipe, insightface y onnxruntime). Ya rompió una vez: instalar insightface
subió numpy y rompió scikit-learn. Volverá a pasar.

---

## Recomendación de ejecución

Si se hace **una sola cosa**: la **Fase N** — hoy la interfaz afirma algo falso,
y eso contamina la confianza en todo lo demás.

Si se hacen **dos**: **N + O** (honestidad y seguridad). Son las que convierten
el producto en algo que un profesional se anima a usar con su archivo real.

Después: **P** (valor ya construido, sin usar), **Q + R** (calidad del modelo y
del sync), y recién ahí **T** (el rediseño), que hereda de N.
