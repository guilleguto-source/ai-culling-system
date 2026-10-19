# Guto Flow 2.0 — Auditoría de UI/UX (Fase 0)

> Fecha: 2026-08-07  
> Proyecto: `ai_culling_system` (Guto Flow)  
> Stack: Electron + React 18 + TypeScript + Vite + FastAPI (ONNX Runtime)

---

## 1. Estado de Compilación Inicial
- **`npm run build:frontend`**: ✅ Exitoso (vite v5.4.21, 51 módulos transformados, 0 errores TypeScript).
- **Entorno**: Soporte dual Electron IPC (`window.api`) y fallback directo HTTP para browser testing (`apiClient`).

---

## 2. Inventario de Componentes y Estado Visual

| Componente | Líneas | Inline Styles | Dependencias / APIs | Diagnóstico |
|---|---|---|---|---|
| `App.tsx` | 311 | Sí (layout `100vw/100vh`, banner stale) | `apiClient`, `window.api`, Polling | Centraliza estado global. Debe montar `Topbar` y envolver en nuevo layout. |
| `Sidebar.tsx` | 265 | Sí (abundantes `style={{}}`) | `LearningPanel`, `icons.tsx` | Contiene input de carpeta y stats que deben moverse a HomeScreen y Tu Estilo. |
| `MainContent.tsx` | 266 | Sí | `GridView`, `DuelView`, `CalibrationView`, `AdvancedPanel`, `Storyline` | Orquesta vistas. Falta Empty State formal (HomeScreen con drag & drop). |
| `GridView.tsx` | 214 | Sí (tags de colores) | `InspectorPanel`, `apiClient` | Funcional. Necesita badges limpios y densidad adaptable. |
| `DuelView.tsx` | 309 | Sí | `Loupe`, `FaceGridAlignment`, `apiClient` | Sólido con ELO/learning. Solo requiere nuevo envoltorio visual. |
| `LearningPanel.tsx` | 102 | Sí | `apiClient.getLearningSummary()` | Obtiene datos reales. Debe evolucionar a la vista completa "Tu Estilo". |
| `SettingsModal.tsx` | 550+ | Sí | `apiClient.getSettings()` | Denso. Requiere nueva jerarquía visual por pestañas. |
| `PhotoDetail.tsx` | 230+ | Sí | Metadatos y razones IA | Funcional como base de Inspector. |
| `Toast.tsx` | 80+ | Sí | Context Provider | Funciona bien. Estilos a refinar a tokens. |
| `icons.tsx` | 130+ | No | SVG puros | Excelente base de iconografía vectorial sin dependencias externas. |

---

## 3. Estado de Tokens y CSS
- **`tokens.css`**: Actualmente solo cuenta con 34 líneas y una paleta parcial con valores antiguos de `--bg-deep: #07080C`. Faltan tokens de superficie `#0B0D10` a `#20262E`, escala tipográfica, espaciado uniforme de 4px, radios y transiciones estándar.
- **`index.css`**: Mezcla variables legacy (`--status-selected-bg`, etc.) con valores hardcodeados y fuentes no estandarizadas.
- **Fuentes**: `index.html` importaba `Outfit`, cuando la especificación requiere **`Inter`** (UI general) y **`JetBrains Mono`** (datos técnicos y métricas).

---

## 4. Fuentes de Datos Reales (Sin Mocks)
- **Estado del Motor**: `apiClient.getHealth()` + `apiClient.getHardware()` (CPU / NVIDIA, cores).
- **Resultados de Culling**: `jobResults.summary` (total, bursts, picks, rejects, scores).
- **Aprendizaje / Estilo**: `apiClient.getLearningSummary()` (`total_photos`, `learned_decisions`, `faces_calibrated`, `maturity`).
- **Cluster / Duelos**: `cluster_id`, `is_representative`, `reasons`, `face_metrics`.

---

## 5. Plan de Acción Inmediato (Fases 1 y 2)
1. Inyectar `Inter` y `JetBrains Mono` en `index.html`.
2. Crear arquitectura modular CSS (`tokens.css`, `global.css`, `layout.css`, `components.css`, `utilities.css`).
3. Construir componentes UI atómicos reutilizables (`Button`, `Badge`, `Stat`, `Tooltip`, `useCountUp`).
4. Construir `Topbar.tsx` contextual con barra de progreso de 2px.
5. Rediseñar `Sidebar.tsx` con navegación `Biblioteca`, `Culling`, `Comparar`, `Tu Estilo`, `Ajustes` y badge IA inferior.
6. Integrar todo en `App.tsx` manteniendo intacto el flujo de datos e IPC.
