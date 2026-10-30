---
name: solution-scout
description: Radar global de código abierto y soluciones técnicas multirregional. Investiga repositorios activos y foros de ingeniería profunda en los 12-15 países líderes en desarrollo (China, Rusia, Japón, Corea, Alemania, EE.UU.) para resolver cuellos de botella, debilidades de competidores y problemas de rendimiento.
---

# Solution Scout: Radar Global de Soluciones Open-Source

## Overview

`solution-scout` es un agente de investigación técnica profunda. A diferencia de las herramientas convencionales que solo consultan issues en inglés en GitHub, este radar rastrea plataformas de código y comunidades de ingeniería de bajo nivel en los ecosistemas más avanzados del mundo:
- **Plataformas de código:** GitHub, GitLab, Gitee (China), GitCode/CSDN, GitVerse/GitFlic (Rusia), Codeberg (Europa).
- **Comunidades técnicas:** Habr (Rusia - bajo nivel, C++, ingeniería inversa), Zhihu y CSDN (China - algoritmos y optimizaciones complejas), Reddit (`r/rust`, `r/cpp`), Qiita/Zenn (Japón), Velog/Naver D2 (Corea del Sur).

---

## Cuándo Usar

* Al encontrar un cuello de botella de rendimiento crítico (CPU, memoria, I/O, latencia de render).
* Al identificar una debilidad recurrente en un software competidor (ej. Lightroom, Aftershoot, Narrative, cTrader) y buscar cómo superarla técnicamente.
* Cuando se necesita un algoritmo comprobado (ej. decodificación RAW sin GC, ring buffer sin bloqueos, clustering facial optimizado) sin reinventar la rueda.
* Para verificar si un bug complejo ya fue resuelto en proyectos similares mediante pull requests o parches documentados.

**Cuándo NO usar:**
* Para consultas triviales de sintaxis o documentación estándar de librerías.
* Para crear arquitectura desde cero cuando ya existe un estándar consolidado y documentado en el proyecto.

---

## Flujo Operativo en 4 Pasos

```
1. DELIMITAR  → Extraer el problema técnico central y stack destino
2. TRADUCIR   → Mapear a términos técnicos nativos (EN, ZH, RU, JA, KO, DE)
3. RASTREAR   → Consultar repositorios y foros de deep-tech en paralelo
4. SINTETIZAR → Generar el Solution Dossier con código, PRs y comparativa
```

---

### Paso 1: Delimitar el Problema y Seleccionar Perfil

1. Cargar el perfil correspondiente desde `profiles/<dominio>.json` si existe:
   * `photo-raw-culling.json`: Motores RAW (LightCraft, Darktable, LibRaw, Immich, InsightFace).
   * `desktop-electron.json`: Apps de escritorio (IPC, buffers zero-copy, render virtual).
   * `algo-trading-mql5.json`: Trading algorítmico (OnTick, memoria compartida, baja latencia).
2. Si no hay perfil, operar en **Modo Ad-Hoc**:
   * Identificar los 2-3 repositorios abiertos más respetados del nicho.
   * Aislar el problema en términos de ciencias de la computación (ej: en lugar de *"va lento al abrir fotos"*, formular *"latencia I/O en lectura de buffers JPEG embebidos en archivos TIFF/RAW"*).

---

### Paso 2: Generación Políglota de Consultas

Consultar `engines/polyglot-matrix.json` y traducir los términos clave a los idiomas técnicos dominantes:

| Idioma | Términos Clave de Ejemplo | Plataformas Objetivo |
| :--- | :--- | :--- |
| **Inglés (`en`)** | `zero-copy buffer`, `SIMD AVX2`, `memory leak fix`, `lock-free` | GitHub, GitLab, Reddit, Hacker News |
| **Chino (`zh`)** | `零拷贝缓冲区`, `SIMD向量化`, `内存泄漏优化`, `无锁队列` | Gitee, GitCode, Zhihu, CSDN |
| **Ruso (`ru`)** | `извлечение превью RAW`, `профилирование кучи`, `бесблокировочный` | Habr, GitVerse, GitFlic |
| **Japonés (`ja`)** | `高速化`, `メモリリーク修正`, `並行処理` | Qiita, Zenn |
| **Coreano (`ko`)** | `성능 최적화`, `동시성 처리`, `메모리 누수 해결` | Velog, Naver D2 |
| **Alemán (`de`)** | `Leistungsoptimierung`, `Speicherüberlauf`, `Multithreading` | Codeberg, Heise Developer |

---

### Paso 3: Rastreo Quirúrgico Multi-Plataforma

Ejecutar búsquedas dirigidas utilizando operadores estrictos:
* **En Repositorios:** `is:pr is:merged label:performance`, `benchmark`, `commit: optimize`.
* **En Habr / Zhihu / CSDN:** Buscar artículos de postmortem de ingeniería, comparativas de benchmarks y desensamblado/ingeniería inversa de funcionalidades similares.
* **En Reddit / Hacker News:** Buscar hilos sobre cuellos de botella y alternativas arquitectónicas recomendadas por desarrolladores de sistemas.

---

### Paso 4: Síntesis en el `Solution Dossier`

Entregar los resultados siguiendo obligatoriamente este formato estándar:

```markdown
# Solution Dossier: [Nombre del Problema / Cuello de Botella]

## 1. Diagnóstico Técnico
- **Causa Raíz:** Breve explicación técnica del problema a nivel arquitectura/recursos.
- **Limitación en Competidores:** Cómo fallan Lightroom, Aftershoot u otros en este punto.

## 2. Soluciones Encontradas en el Ecosistema Global
### [Solución A] - Ecosistema [País / Plataforma, ej. Rusia / Habr & C++]
- **Proyecto / Fuente de Referencia:** [Nombre del Repo o Artículo con URL]
- **Técnica Utilizada:** (ej. uso de `mmap` con lectura asíncrona de cabeceras EXIF).
- **Ventaja:** Cero copias en memoria y velocidad 4x superior a streaming estándar.

### [Solución B] - Ecosistema [País / Plataforma, ej. China / Gitee & Rust]
- **Proyecto / Fuente de Referencia:** [Nombre del Repo o Artículo con URL]
- **Técnica Utilizada:** (ej. Vectorización AVX2 para extracción de bloques Huffman).
- **Ventaja:** Procesamiento SIMD puro sin librerías externas pesadas.

## 3. Comparativa y Matriz de Decisión
| Criterio | Solución A | Solución B | Enfoque Actual |
| :--- | :--- | :--- | :--- |
| Complejidad de Implementación | Media | Alta | Baja |
| Impacto en Rendimiento | +250% | +400% | Baseline |
| Dependencias Externas | Mínimas | Requiere ensamblador/SIMD | Existentes |

## 4. Hoja de Ruta de Adaptación a Nuestro Stack
- Pasos concretos para implementar el patrón en nuestro código.
- Archivos y capas afectadas.
- Alertas de regresión o compatibilidad multiplataforma.
```

---

## Reglas de Seguridad y Eficiencia
* **Cero código basura:** Priorizar PRs que incluyan pruebas de estrés o benchmarks documentados.
* **Aislamiento de licencias:** Verificar la licencia del repositorio de referencia (MIT, Apache 2.0, BSD vs GPL) antes de recomendar replicar un fragmento directo.
* **Síntesis ultra-digerida:** Traducir y destilar todo el conocimiento en español técnico conciso para el usuario.
