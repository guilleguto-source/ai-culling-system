# Plan Operativo: Respaldo GutoCraft y Procesamiento Masivo en NAS

## 1. Alcance y Objetivos
1. **Cierre y Respaldo de GutoCraft:**
   - Archivar las fotos de auditoría en `docs/audit_mattes/`.
   - Commit y push en `GUTOFLOW` (`ai-culling-system`).
   - Configuración de `GutoCraft` como repositorio independiente en GitHub (`guilleguto-source/GutoCraft`).
2. **Procesamiento Masivo en Producción (1,951 fotos en NAS):**
   - Carpeta 1: `\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-09-26\Giler` (436 fotos)
   - Carpeta 2: `\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-10-03\Dayana` (679 fotos)
   - Carpeta 3: `\\MYCLOUDEX2ULTRA\Public\Guto Gutierrez\2026\2026-10-03\Gioconda` (836 fotos)

---

## 2. Fases de Ejecución

```
[Fase 1: Respaldo y Git GutoCraft]
  ├── Archivar 4 collages en docs/audit_mattes/
  ├── Commit + Push en repo principal GUTOFLOW
  └── Commit en gutoflow-rust/lightcraft -> remote GutoCraft
        │
        ▼
[Fase 2: Procesamiento Masivo en Lote (GutoFlow + LightCraft)]
  ├── 1. Ingesta, culling y métricas de enfoque en GUTOFLOW
  ├── 2. Generación neural de los 5 planos de máscaras IA (GutoCraft)
  ├── 3. Aplicación de recetas de revelado con capas locales:
  │      - Suavizado sutil de piel (Texture/Clarity negativo)
  │      - Realce de iris (+Exposure, +Clarity)
  │      - Blanqueamiento de dientes (-Saturation, +Exposure)
  │      - Esclera limpia (-Saturation suave)
  │      - Pop de sujeto (+Exposure sutil, contraste)
  └── 4. Escritura de sidecars XMP compatibles con Adobe Lightroom
```

---

## 3. Estado de Ejecución por Carpeta del NAS
- **Giler (407 fotos JPG):** ✅ Completado (407/407 XMP + máscaras binarias generadas, 0 errores).
- **Dayana (679 fotos CR2 RAW):** ✅ Completado (679/679 XMP + máscaras binarias generadas, 0 errores).
- **Gioconda (836 fotos JPG):** ✅ Completado (836/836 XMP + máscaras binarias generadas, 0 errores).
- **TOTAL:** ✅ **1,922 / 1,922 fotos procesadas con éxito (0 fallos).**

---

## 4. Repositorio Remoto GutoCraft
- Repo local sincronizado en rama `gutoflow` (`da36d64`).
- Pendiente: Crear `GutoCraft` en GitHub (https://github.com/new) para habilitar el push final.
