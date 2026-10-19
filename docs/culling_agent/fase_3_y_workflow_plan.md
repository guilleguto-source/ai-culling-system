# Especificación Técnica: Fase 3 (Revelado Avanzado) y Mejoras de Workflow UI

Documento de referencia completa para el desarrollo de la **Fase 3** (Tratamiento y Revelado Inteligente de Fotos) y la integración de las **Herramientas de Workflow & UX**.

---

## Parte 1: Módulo Avanzado de Revelado y Tratamiento (Fase 3)

Todas las técnicas operan mediante **procesado 100% no destructivo** sobre archivos sidecar XMP (`.xmp`) y metadatos paramétricos. Los archivos fuente originales (`.RAW`, `.CR3`, `.NEF`, `.ARW`, `.DNG`, `.JPG`) permanecen intactos y reversibles en 1 clic desde Lightroom o Camera Raw.

| # | Tecnología / Pilar | Funcionamiento Técnico | Repositorios & Enlaces de Origen (GitHub) |
|---|---|---|---|
| **1** | **Neural 3D-LUTs (Color Grading Adaptativo)** | Una red convolucional ligera predice una curva 3D-LUT adaptada al tono y color de la toma, procesando la gradación a resolución completa en GPU en <2ms. | • [Image-Adaptive-3DLUT](https://github.com/HuiZeng/Image-Adaptive-3DLUT)<br>• [NILUT (Neural Implicit LUT)](https://github.com/NILUT) |
| **2** | **Edición Focalizada en Tonos de Piel (`Skin-Aware Edit`)** | Aísla los píxeles de piel humana con MediaPipe y ajusta de forma selectiva `crs:Temperature`, `crs:Tint` y luminancia en espacio YCbCr/HSV sin alterar el fondo. | • [MediaPipe Face Mesh (Google)](https://github.com/google-ai-edge/mediapipe)<br>• [RetouchML](https://github.com/ju-leon/RetouchML) |
| **3** | **Rescate Tonal de Altas Luces y Sombras (`DarkIR`)** | Recupera detalles en vestidos blancos o fondos deslumbrados y rescata sombras profundas sin amplificar el ruido del sensor. | • [DarkIR (Ganador NTIRE 2025)](https://github.com/cidautai/DarkIR)<br>• [Awesome-Low-Light-Enhancement](https://github.com/zhihongz/awesome-low-light-image-enhancement) |
| **4** | **Re-Iluminación Facial (`Portrait Relighting`)** | Estima la geometría 3D del rostro y el mapa normal de luz para suavizar destellos de flash o ajustar sombras duras en la cara. | • [IC-Light (lllyasviel)](https://github.com/lllyasviel/IC-Light)<br>• [PortraitRelighting (CVPR)](https://github.com/GhostCai/PortraitRelighting) |
| **5** | **Aprendizaje de Tu Estilo de Edición (`Deep Preset`)** | Red entrenada con pares de tu historial (RAW original vs tu versión editada en Lightroom) para replicar automáticamente tu firma visual en sesiones futuras. | • [Deep Preset](https://github.com/minhmanho/deep_preset)<br>• [Neural Preset (Meta)](https://github.com/facebookresearch/neural_preset) |
| **6** | **Dodge & Burn y Retoque de Piel (`RetouchFormer`)** | Aplica separación de frecuencias asistida por Transformers. Separa la capa de textura de la de color para corregir manchas o rojeces sin borrar los poros. | • [RetouchFormer (AAAI)](https://github.com/Davidcoach/RetouchFormer_AAAI_24)<br>• [Auto-Retoucher](https://github.com/wasidy/auto_retoucher) |
| **7** | **Enderezado de Perspectiva y Reencuadre Geométrico** | Calcula la inclinación del horizonte con la transformada de Hough y ajusta la composición de tercios guardando las coordenadas en `crs:Crop*` de XMP. | • [RapidRAW GPU Auto-Crop](https://github.com/RapidRAW)<br>• [Implementación local en `services/auto_crop.py`](file:///C:/Users/Guill/teamwork_projects/ai_culling_system/backend/services/auto_crop.py) |

---

## Parte 2: Herramientas de Workflow, UX y Comparación

Estas tres funcionalidades complementan el flujo de trabajo para brindar máxima transparencia y control al usuario antes de exportar a Lightroom:

### 1. Grilla de Comparación de Caras ("Face Grid Alignment")
- **Inspiración:** Narrative Select.
- **Funcionamiento:** Muestra una matriz de recortes alineados de los rostros detectados en cada ráfaga en la interfaz (zoom automático al 100% sobre cada cara).
- **Utilidad:** Permite verificar al instante quién tiene los ojos abiertos, la mejor sonrisa o la mirada fija a cámara sin hacer zoom manual foto por foto.

### 2. Desempate por Preferencia Humana (ImageReward Elo Ranking)
- **Inspiración:** Sistemas de puntuación Elo en ajedrez / IA.
- **Funcionamiento:** Mantiene un ranking competitivo ultrarrápido en RAM sobre los embeddings visuales para resolver empates estéticos en ráfagas reñidas.
- **Utilidad:** Evita invocar modelos VLM pesados (Ollama) cuando la preferencia humana aprendida puede desempatar la ráfaga en milisegundos.

### 3. Panel UI "Duelo V1 vs V2"
- **Inspiración:** Paneles de prueba A/B en desarrollo.
- **Funcionamiento:** Interfaz gráfica dedicada que muestra las fotos elegidas por el sistema **V1 (Legacy/Heurístico)** frente al **V2 (7-Ejes + VIP + CPBD)** lado a lado.
- **Utilidad:** Permite inspeccionar qué fotos cambiaron, por qué motivo ganó el V2 y decidir la aplicación final de metadatos con total confianza.

---

## Arquitectura de Archivos Proyectada para la Fase 3

```
backend/
├── services/
│   ├── neural_lut.py          # Color grading 3D-LUT adaptativo
│   ├── skin_tone_edit.py      # Pre-edición de tonos de piel
│   ├── dark_ir_recovery.py    # Rescate de luces/sombras
│   ├── portrait_relighting.py # Re-iluminación facial
│   ├── deep_preset.py         # Clonación de tu estilo desde Lightroom
│   ├── skin_retouch.py        # Dodge & burn / Retoque de piel frecuencial
│   ├── auto_crop.py           # Perfeccionamiento de enderezado y tercios
│   └── elo_ranking.py         # ImageReward Elo ranking en RAM
└── tests/
    └── test_phase3_pipeline.py# Suite de pruebas unitarias de revelado

src/renderer/src/components/
├── FaceGridAlignment.tsx      # Matriz de inspección de rostros en ráfagas
└── EngineDuelPanel.tsx        # Panel comparador A/B V1 vs V2
```
