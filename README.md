# Guto Flow — AI Photo Culling & Auto-Editing System (v1.5)

[![Build & Tests](https://img.shields.io/badge/Tests-327%20passed%20%E2%9C%85-brightgreen)](#)
[![License](https://img.shields.io/badge/License-Proprietary-blue)](#)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Electron%20%7C%20Python-orange)](#)

**Guto Flow** es un sistema de escritorio profesional e inteligente para la selección (**culling**), organización y pre-edición automática de fotografías en volumen para fotógrafos de bodas, eventos y retratos. 

Funciona de forma **100% offline y local**, combinando un frontend moderno en Electron + React/TypeScript con un motor backend modular en Python + FastAPI y modelos optimizados en ONNX Runtime.

---

## 🌟 Características Principales (v1.5)

### 🤖 1. Motor de Análisis e Inteligencia Artificial
* **Calidad Técnica & Nitidez**: Evaluación por filtro Laplaciano de varianza, análisis de saliencia y nitidez facial focalizada.
* **Motor Estético 7-Ejes**: Ponderación inteligente de composición, rango dinámico, exposición, colorimetría, expresión y prioridad de personas VIP.
* **Landmarks & Micro-expresiones**: Integración de **YuNet** (detección facial rápida) y **MediaPipe Face Mesh** (parpadeo, sonrisa, dirección de mirada y micro-expresiones).
* **Reconocimiento de Personas**: **ArcFace (ResNet-50)** para clustering persona-a-persona, garantizando que cada sujeto tenga fotos de calidad seleccionadas.
* **Auto-Encuadre (YOLOv8)**: Detección de personas de espaldas y encuadre basado en la regla de tercios y espacio de mirada.
* **Búsqueda Semántica Offline (CLIP)**: Consulta en lenguaje natural (ej: *"niños riendo"*, *"primer plano novia"*) sin conexión a internet.

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

## 📊 Estado de Pruebas & Calidad de Código

* **Pruebas de Backend (`pytest`)**: **327 / 327 pruebas aprobadas (100% en verde)** cubriendo modelos, routers, cálculo estético y servicios de exportación.
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

© 2026 Guto Flow. Todos los derechos reservados.
