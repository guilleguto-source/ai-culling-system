# Guto Flow — AI Photo Culling & Auto-Editing System (v2.1)

[![Build & Tests](https://img.shields.io/badge/Tests-335%20passed%20%E2%9C%85-brightgreen)](#)
[![License](https://img.shields.io/badge/License-Proprietary-blue)](#)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Electron%20%7C%20Python-orange)](#)

**Guto Flow** es un sistema de escritorio profesional e inteligente para la selección (**culling**), organización y pre-edición automática de fotografías en volumen para fotógrafos de bodas, eventos y retratos. 

Funciona de forma **100% offline y local**, combinando un frontend moderno en Electron + React/TypeScript con un motor backend modular en Python + FastAPI y modelos optimizados en ONNX Runtime.

---

## 🌟 Características Principales (v2.1)

### 🤖 1. Motor de Análisis e Inteligencia Artificial
* **Calidad Técnica & Nitidez**: Evaluación por filtro Laplaciano de varianza, análisis de saliencia y nitidez facial focalizada.
* **Motor Estético 7-Ejes**: Ponderación inteligente de composición, rango dinámico, exposición, colorimetría, expresión y prioridad de personas VIP.
* **Detección & Landmarks Faciales**: Integración de **UniFace (SCRFD)** de alto rendimiento y análisis fino de micro-expresiones (parpadeo, sonrisa y dirección de mirada).
* **Reconocimiento de Personas**: **UniFace (ArcFace)** para clustering persona-a-persona, garantizando cobertura equitativa de todos los protagonistas.
* **Auto-Encuadre (YOLOv8)**: Detección de personas de espaldas y encuadre basado en la regla de tercios y espacio de mirada.
* **Búsqueda Semántica Offline (SigLIP)**: Consulta en lenguaje natural (ej: *"niños riendo"*, *"primer plano novia"*) sin conexión a internet ni llamadas a APIs externas.

### 🧠 2. Aprendizaje Adaptativo de Estilo
* **Gusto Visual (Duelo & Lightroom Sync)**: Aprende continuamente de los duelos 1v1 y de las correcciones del fotógrafo en Lightroom.
* **Revelado por Escena (Neural LUT & Recetas CRS)**: Aprende la firma de tono, contraste y color por tipo de iluminación (interior cálido, atardecer, luz dura).
* **Pre-edición Inteligente**: Balance de blancos neutro, rescate tonal de altas luces/sombras y retoque suave de piel (frecuencia dividida).

### 🛡️ 3. Resiliencia, Seguridad & Deshacer
* **Respaldo Atómico de XMP (`undo_export.py`)**: Guarda los bytes crudos del XMP antes de escribir. Permite **Deshacer el Culling en 1-Clic** exactamente al estado original.
* **Rescatabilidad de Proyectos**: Re-lectura de XMPs para sincronización bidireccional desde Lightroom Classic.
* **Manejo de Errores Granular**: Si un RAW individual está dañado, el sistema lo aísla y continúa procesando el lote sin detenerse.

### 📦 4. Infraestructura de Empaquetado & Asistente de Primera Ejecución
* **Asistente de Descarga SSE (`ModelDownloadWizard.tsx`)**: Descargador atómico de modelos IA con reporte de progreso en tiempo real mediante Server-Sent Events.
* **Resolutor Central de Rutas (`app_paths.py`)**: Desacoplamiento total para producción. En Windows empaquetado opera en `%APPDATA%/GutoFlow/`.
* **Pipeline Integrado (`scripts/build.ps1`)**: Script de automatización de compilación de frontend, bundle de PyInstaller con `hiddenimports`, verificador de salud (`verify_build.py`) e instalador standalone NSIS (~100 MB).

---

## 📜 Historial de Versiones, Mejoras y Correcciones

Para consultar la bitácora histórica completa y granular, revisa [CHANGELOG.md](CHANGELOG.md).

### 🚀 [v2.1.0] - 2026-09-11
* **✨ Nuevas Características & Mejoras**:
  * **Motor de Selección V2**: Algoritmo con supervivencia obligatoria para momentos clave, control de cadencia temporal (*pacing*), poda estricta a cuota objetivo (*trim to target*) y bonificación VIP (+20% de score para sujetos prioritarios).
  * **Unificación Nativa RAW + JPEG**: Tratamiento integral del par dual como 1 solo disparo fotográfico en estimación inicial, visualización en cuadrícula, contadores de biblioteca y exportación.
  * **Herramientas de Cliente & UI Renovada**:
    * `ClientToolsModal.tsx`: Herramientas auxiliares de filtrado y control de catálogo.
    * `PreCullingModal.tsx`: Configuración de parámetros y criterios antes de iniciar el procesamiento.
    * `VIPBar.tsx`: Barra interactiva en la interfaz para seleccionar y priorizar identidades clave del evento.
    * `SleepCountdownModal.tsx`: Temporizador interactivo para apagar o suspender el equipo tras finalizar lotes pesados.
  * **Adapters y Resiliencia**:
    * `FaceEngineAdapter`: Desacoplamiento modular del motor facial para intercambio transparente de modelos.
    * `DiscrepancyFilter`: Detección y auditoría de discrepancias en calificaciones de ráfaga.
    * `session_history_store.py`: Persistencia estructurada de sesiones y estadísticas en SQLite.
  * **Documentación & Benchmarks de Culling Agent**: Integración de planes de migración, auditorías faciales y 21 scripts de prueba/benchmark en `docs/culling_agent/` y `scripts/scratch/`.
* **🐛 Correcciones & Bugs Resueltos**:
  * *Bug de Duplicidad RAW/JPG*: Resuelto el problema donde carpetas con parejas RAW+JPG duplicaban el conteo (ej. 1.821 archivos reportados frente a 1.225 tomas reales).
  * *Exportación XMP Asimétrica*: Corregido el fallo donde solo se generaba sidecar para el archivo JPEG; ahora se escriben metadatos sincronizados tanto para el RAW como para el JPG de forma atómica.
  * *Rutas Inválidas en Limpieza de Biblioteca*: Corregida excepción en `media.py` (`cleanup_library`) ante rutas relativas, directorios nulos o carpetas de pruebas huérfanas.
  * *Sincronización Incompleta de Snapshot*: Añadido el campo `linked_raw_path` en las sesiones persistidas para garantizar la sincronización bidireccional desde Lightroom Classic.

---

### 🚀 [v2.0.0] - 2026-08-25
* **✨ Nuevas Características & Mejoras**:
  * **Migración Integral a UniFace**: Sustitución de MediaPipe e InsightFace por un pipeline unificado de detección facial y embeddings (SCRFD + ArcFace) sobre ONNX Runtime, compatible con DirectML, CUDA y CPU.
  * **Búsqueda Semántica con SigLIP**: Migración de CLIP clásico hacia Google SigLIP (ViT-B/16), logrando una precisión semántica significativamente mayor en lenguaje natural sin requerir conexión externa.
  * **Lazy Loading de Modelos IA**: Carga bajo demanda y patrón Singleton para redes neuronales pesadas (`FaceAnalyzer`, `MobileGaze`), reduciendo el cold start del backend de ~4.5s a ~0.8s.
  * **Arquitectura Limpia & Reducción de Huella**:
    * Eliminación total de dependencias obsoletas (`mediapipe` en `requirements.txt`), reduciendo ~200MB de tamaño del instalador.
    * Centralización del 100% de peticiones de red del frontend a través de `apiClient`.
    * Purgado de código muerto: canales IPC en desuso (`backend:undo:*`), vistas huérfanas y reestructuración en `backend/services/legacy/`.
* **🐛 Correcciones & Bugs Resueltos**:
  * *Fugas de Memoria en GPU/CPU*: Liberación explícita de tensores de imagen y contextos de sesión en ONNX Runtime tras procesar cada ráfaga.
  * *Deadlock en JobManager*: Corrección de condiciones de carrera en el pool de hilos al cancelar trabajos batch masivos.
  * *URLs Hardcodeadas*: Erradicación de cadenas fijas `127.0.0.1:8000` en componentes React que causaban fallos cuando el puerto dinámico cambiaba.

---

### ✨ [v1.3.0] - 2026-08-08
* **✨ Nuevas Características & Mejoras**:
  * **Storyline 2.0 Foundation**: Segmentación automática temporal y semántica que organiza el evento fotográfico en capítulos lógicos (preparativos, ceremonia, sesión nupcial, fiesta).
  * **Event Library & Autocompletado**: Biblioteca de eventos para categorizar y recuperar rápidamente sesiones previas.
  * **Selección Múltiple en Cuadrícula**: Soporte completo de operaciones por lote con `Shift + Click`, `Ctrl + Click` y `Ctrl + A`.
  * **Streaming de Progreso en Tiempo Real (SSE)**: Implementación de Server-Sent Events en FastAPI para reportar métricas granulares y avances sin sobrecarga de polling continuo.
  * **Reglas de Ráfagas Mejoradas**: Balanceo de orientación horizontal/vertical (H/V) y selección óptima de hasta 2 fotos representativas por ráfaga.
* **🐛 Correcciones & Bugs Resueltos**:
  * *Desalineación Temporal por Zonas Horarias*: Corregido el parseo de metadatos EXIF cuando las cámaras tenían desfases entre hora local y UTC.
  * *Penalización Indebida de Fotos Verticales*: Solucionado un sesgo en el algoritmo de composición que degradaba injustamente planos verticales en ráfagas mixtas.

---

### ✨ [v1.2.0] - 2026-07-27
* **✨ Nuevas Características & Mejoras**:
  * **Búsqueda Semántica Offline**: Consulta en lenguaje natural (ej. *"beso novios"*, *"pastel de bodas"*) ejecutada íntegramente de manera local.
  * **Refinamiento Visual VLM**: Desempate de sonrisas forzadas y micro-gestos mediante modelos de lenguaje visual.
  * **Wizard de Descarga de Modelos**: Asistente interactivo en frontend con reporte de avance y verificación de integridad criptográfica (SHA-256).
  * **Inspector de Fotos y Lupa**: Panel con histograma en tiempo real, metadatos EXIF profundos y herramienta de zoom de alta fidelidad.
  * **Empaquetado de Producción**: Pipeline automatizado con PyInstaller y Electron Builder para generar instaladores NSIS ligeros y reproducibles.
* **🐛 Correcciones & Bugs Resueltos**:
  * *Corrupción en Descargas de Modelos*: Implementada escritura en archivos temporales `.tmp` antes de confirmar la sustitución definitiva de los pesos.
  * *Lentitud en Carga de RAWs*: Integración de `rawpy` con fallback ultra-rápido a vistas previas JPEG embebidas.

---

### ✨ [v1.1.0] - 2026-07-20
* **✨ Nuevas Características & Mejoras**:
  * **Aprendizaje Continuo desde Lightroom**: Sincronización bidireccional mediante reimportación de XMP para aprender las preferencias de calificación y recorte del fotógrafo.
  * **Garantía de Cobertura de Personas**: Reglas de balance para asegurar que cada persona detectada tenga al menos un número proporcional de fotografías de calidad seleccionadas.
  * **Modo Duelo (Duel View)**: Comparador lado a lado optimizado para atajos de teclado rápidos (`1` vs `2`).
  * **Deshacer Atómico (Undo Export)**: Respaldo previo de archivos de metadatos permitiendo revertir la sesión de culling al estado original con 1 solo clic.
* **🐛 Correcciones & Bugs Resueltos**:
  * *Sobrescritura Destructiva de Metadatos*: Corrección para preservar etiquetas preexistentes en archivos XMP durante la exportación.
  * *Falsos Positivos de Ojos Cerrados*: Ajuste de umbrales en el clasificador facial ante sombras intensas o uso de gafas de sol.

---

### 📦 [v1.0.0] - 2026-07-01
* **✨ Nuevas Características**:
  * Primera versión funcional de **Guto Flow**: plataforma de escritorio híbrida Electron + FastAPI.
  * Motor de nitidez por varianza Laplaciana y saliencia visual.
  * Motor estético multi-criterio de 7 ejes (composición, exposición, contraste, color, personas VIP, nitidez y expresión).
  * Agrupación automática por ráfagas temporales y visuales.
  * Exportación estándar de etiquetas de estrellas y colores en sidecars XMP compatibles con Lightroom y Camera Raw.

---

## 📊 Estado de Pruebas & Calidad de Código

* **Pruebas de Backend (`pytest`)**: **335 / 335 pruebas aprobadas (100% en verde)** cubriendo modelos, routers, cálculo estético y servicios de exportación.
* **Validación TypeScript**: `npx tsc --noEmit` superado sin errores de sintaxis o tipos.

---

## 🚀 Guía de Desarrollo Local

### Requisitos Previos
* **Node.js** 18+
* **Python** 3.10 o 3.12 (Virtualenv aislado en `backend/.venv`)

### 1. Clonar e Instalar Dependencias

```bash
# Frontend
npm install

# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cd ..
```

### 2. Ejecutar en Modo Desarrollo

```bash
npm run dev
```

Esto arranca automáticamente:
1. **Vite Dev Server** (React UI) en `http://localhost:5173`.
2. **Electron Main Process**, lanzando el backend FastAPI en `http://127.0.0.1:8000`.

---

## 🛠️ Estructura del Proyecto

```
ai_culling_system/
├── backend/
│   ├── core/                      # Singleton JobManager y orquestación
│   ├── models/                    # Modelos ONNX y LUTs predeterminados
│   ├── routers/                   # Router FastAPI (culling, setup, calibration, media, export, etc.)
│   ├── services/                  # Servicios de IA, aprendizaje, XMP y app_paths
│   ├── tests/                     # Suite de 327 tests unitarios con pytest
│   └── main.py                    # Servidor FastAPI
├── scripts/
│   ├── build.ps1                  # Automated build pipeline script
│   ├── verify_build.py            # Executable health check smoke test
│   └── installer.nsh              # Personalización del instalador NSIS
├── src/
│   ├── main/                      # Proceso principal de Electron
│   ├── preload/                   # IPC Bridge seguro
│   └── renderer/src/              # Frontend React + TypeScript
│       ├── api/                   # Cliente API centralizado
│       └── components/            # UI Components (Grid, Duel, Wizard, Inspector)
├── backend.spec                   # Especificación PyInstaller
└── package.json                   # Configuración Electron-builder y NSIS
```

---

## 📄 Guía de Sincronización con Adobe Lightroom Classic

1. En Lightroom Classic, ve a **Metadatos → Conjunto de etiquetas de color → Editar…**
2. Configura los nombres de los colores (`Red`, `Green`, `Blue`, `Purple`).
3. Tras ejecutar el culling en Guto Flow, abre Lightroom, selecciona las fotos (`Ctrl+A`) y presiona **Ctrl+Shift+R** (*Metadatos → Leer metadatos de archivos*).

---

## 📜 Historial de Versiones y Evolución del Motor

Para consultar el análisis técnico detallado, los benchmarks completos y la arquitectura interna de cada versión, revisa el [CHANGELOG.md](CHANGELOG.md).

### Tabla de Evolución Tecnológica e IA

| Componente / Tarea | Enfoque Anterior | Enfoque Actual (`v2.3`) | Motivo & Beneficio Clave |
| :--- | :--- | :--- | :--- |
| **Detección Facial** | MediaPipe FaceMesh | **UniFace (SCRFD ONNX)** | Eliminación de dependencias pesadas (-200MB) y +40% FPS en CPU. |
| **Reconocimiento Facial** | InsightFace | **ArcFace (UniFace 512D)** | Integración limpia en ONNX Runtime sin dependencias C++ conflictivas. |
| **Búsqueda Semántica** | CLIP ViT-B/32 | **SigLIP Local** | -25% falsos positivos en descripciones complejas de eventos y bodas. |
| **Detección de Ráfagas** | pHash visual + $\Delta t$ fijo | **Rust MakerNotes + Adaptive DBSCAN** | 100% de fiabilidad en ráfagas de cámara; tolerante a grano ISO alto. |
| **Selección de Candidatas**| Score estático | **Hero Shot (Yaw $< 15^\circ$) + Pacing** | Prioriza mirada frontal directa y evita huecos narrativos en el evento. |
| **Storyline & Ritmo** | Línea de tiempo plana | **Storyline 2.0 con Escisión B-Roll** | Aísla tomas de detalles/decoración para no alterar el ritmo cronológico. |
| **Interfaz & Renderizado** | DOM estándar | **Digital Darkroom + `react-virtuoso`** | Interfaz oscura profesional con renderizado a 60 FPS en 15,000+ fotos. |

### Resumen de Versiones

* **v2.3.0 (Actual):** Extracción nativa de MakerNotes en Rust (Sony/Nikon/Canon), DBSCAN adaptativo, Hero Shot por ángulo *Yaw*, Storyline 2.0 con B-Roll y rediseño UI "Digital Darkroom".
* **v2.1.0:** Motor de Selección V2 con supervivencia por capítulo, soporte unificado para pares RAW+JPEG, suite de herramientas de cliente y persistencia histórica en SQLite.
* **v2.0.0:** Re-arquitectura limpia con migración integral a UniFace (SCRFD + ArcFace), SigLIP semántico, Lazy Loading de modelos (-73% cold start) y 325 pruebas unitarias.
* **v1.3.0:** Storyline 1.0, streaming de progreso en tiempo real con SSE, multi-selección avanzada (`Ctrl+A`, `Shift+Click`) y reglas de orientación H/V.
* **v1.2.0:** Búsqueda semántica offline, refinamiento con modelos de visión (VLM), lupa de inspección al 100% y pipeline de empaquetado de producción para Windows.
* **v1.1.0:** Sincronización y aprendizaje bidireccional desde Lightroom Classic, Modo Duelo (Duel View) y calibración de preferencias de usuario.
* **v1.0.0:** MVP inicial con motor de culling automático (blur, parpadeo, clustering), pre-edición tonal y auto-crop no destructivo inyectado en `.XMP`.

---

© 2026 Guto Flow. Todos los derechos reservados.
