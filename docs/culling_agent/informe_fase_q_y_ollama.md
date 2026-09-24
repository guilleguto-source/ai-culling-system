# 📊 Informe Consolidado: Barrido Masivo (Fase Q) y Evaluación VLM con Ollama

---

## 1. 📌 Resumen Ejecutivo del Barrido Masivo
El análisis masivo sobre todo el archivo histórico desde febrero de 2025 ha concluido exitosamente al **100%**.

| Métrica | Valor Absoluto | Porcentaje / Observaciones |
| :--- | :--- | :--- |
| **Total de Archivos en Ámbito** | **85,689** | 100% del catálogo analizado |
| **Fotos de Imagen Procesadas** | **61,250** | Análisis facial, nitidez local y vectores CLIP |
| **Archivos Omitidos / Sidecars** | **24,439** | Videos, sidecars RAW (.xmp/.thm) y corruptos |
| **Bases de Datos SQLite Creadas** | **112 carpetas** | Mantenimiento local en red NAS sin bloqueo |
| **Vectores CLIP (ViT-B/32) en Caché** | **67,907 .npy** | 512 dimensiones por foto para búsqueda semántica |
| **Pares de Ráfaga Reconstruidos** | **18,763 pares** | Evaluación comparativa `Winner` vs `Loser` |

---

## 2. 🔬 Resultados del Experimento A/B (Fase Q)
Evaluación con **GroupKFold Cross-Validation (5-Fold por evento/carpeta)** sobre los **18,763 pares reales** de ráfaga:

| Modelo / Set de Características | Descripción de Métricas | Tasa de Acierto en Ráfaga | Desviación Estándar |
| :--- | :--- | :---: | :---: |
| **Set A: Binarizado (Producción)** | Contar ojos cerrados (`closed_eyes > 0`), miradas desviadas (`looking_away > 0`) y sonrisas | **58.1%** | $\pm 2.0\%$ |
| **Set B: Continuo (Fase Q)** | Puntuaciones continuas agregando "la peor cara" (`min_ear`, `max_blink`, `mean_smile`, `max_abs_yaw`) | **59.5%** | $\pm 0.7\%$ |
| **Set C: Combinado Completo** | Set A + Set B + Vectores Visuales CLIP (512 dims) | **59.7%** | $\pm 1.5\%$ |

> [!NOTE]
> **Conclusión del Experimento:** La representación continua (Set B) ofrece una ligera mejora de **+1.4 puntos porcentuales** en acierto y mayor estabilidad ($\pm 0.7\%$ vs $\pm 2.0\%$). Sin embargo, estadísticamente con $N=18,763$ pares, ambas representaciones se desempeñan de forma equivalente. Se recomienda mantener las métricas continuas como base rica para el motor.

---

## 3. 🦙 Desempeño e Integración de Ollama (`llama3.2-vision`)

### Arquitectura de Evaluación Híbrida
Para optimizar el tiempo de cómputo y la carga del procesador:
1. **Filtro de Descarte Masivo (Backend Local):**
   - Procesa a **1.4 fotos/segundo** usando OpenCV, MediaPipe y PyTorch (ONNX).
   - Elimina automáticamente fotos desenfocadas, con ojos cerrados masivos o sin rostros.
2. **Refinador Visual de Desempate (Ollama Streaming):**
   - **Modelo:** `llama3.2-vision` (7.8 GB).
   - **Rol:** Recibe los tríos o parejas de candidatos finalistas de ráfagas muy competidas.
   - **Criterios de Evaluación VLM:** Revisa la naturalidad de la sonrisa, la dirección exacta de la mirada y la conexión emocional del grupo que las métricas heurísticas numéricas no capturan.

---

## 4. 🚀 Estado del Sistema y Próximos Pasos

1. **Búsqueda Semántica:** La base de datos vectorial ChromaDB y la caché de 67,907 embeddings CLIP permiten búsquedas instantáneas por texto en lenguaje natural en la barra del visor (ej: *"retrato sonriente al aire libre"*).
2. **Código Depurado:** Se eliminaron las redundancias del backend (`_bad_faces` y dependencias rígidas de VIP) y se reforzó la thread-safety de SQLite con transacciones WAL.
