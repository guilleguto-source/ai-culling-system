# Teamwork Project Prompt — Draft

> Status: Step 9 — Ready for launch — awaiting user approval
> Goal: Craft prompt → get user approval → delegate to teamwork_preview

An offline, local AI-powered image culling desktop system similar to Aftershoot to filter, group, and select professional photographs based on technical and aesthetic factors. The system leverages Electron and React/TypeScript for a modern UI, communicating with a local Python backend running ONNX Runtime for high-performance AI inference.

Working directory: `~/teamwork_projects/ai_culling_system`
Integrity mode: demo

## Requirements

### R1. Hybrid Photo Ingestion & Parsing
The backend must read directories containing JPG and RAW images. For RAW files, it must extract embedded JPEG previews to minimize decoding overhead. For all images, it must generate downscaled thumbnails for UI display and AI feature extraction.

### R2. Sequential Culling Pipeline
Implement a multi-stage evaluation pipeline to process images in order of computational cost:
1. **Metadata & Perceptual Hashing**: Group bursts and near-duplicates using `pHash` + timestamp clustering (DBSCAN).
2. **Technical Quality Assessment**: Fast blur detection (Laplacian variance) and exposure/histogram analysis.
3. **Advanced Human Assessment**: Run face detection (YuNet in ONNX) on clusters. For detected faces, evaluate closed eyes (custom classifier) and facial expressions.
4. **Aesthetic Scoring**: Score compositions using a lightweight model.

### R3. Hardware-Agnostic Execution (GPU & CPU Support)
The AI inference backend must automatically detect the host hardware capabilities and load appropriate ONNX Runtime Execution Providers:
- If a compatible GPU is detected, use GPU acceleration (e.g., DirectML on Windows, CUDA if available).
- Fall back gracefully to `CPUExecutionProvider` on machines without a dedicated GPU, optimizing thread allocations (`intra_op_num_threads`) for multi-core CPUs.

### R4. User Interface & Selection Customization
Modern dark-theme React UI with the following panels and configuration capabilities:
- **Calificaciones y Colores Panel (Customizable Ratings & Colors)**:
  - **AI Selections (Selecciones de IA)**:
    - Selected (Seleccionado): 3 Stars, Green color label (editable)
    - Highlights (Destacados): 3 Stars, Blue color label (editable)
  - **For Review (Para revisión)**:
    - Blurry (Borroso): 0 Stars, Red color label (editable)
    - Closed Eyes (Ojos cerrados): 0 Stars, Purple color label (editable)
    - Duplicates (Duplicados): 0 Stars, Yellow color label (editable)
- **Preferencias de Selección Panel (Selection Settings)**:
  - Selectivity Target Slider: Few (Pocas) -> Standard (Estándar) -> More (Más)
  - Customizable Toggles:
    - Detect Duplicates (Detectar duplicados) [ON/OFF]
    - Detect Highlights (Detectar destacados) [ON/OFF]
    - Detect Blurry (Detectar borrosas) [ON/OFF] with Sensitivity Slider: Lenient (Indulgente) -> Moderate (Moderado) -> Strict (Estricto)
    - Detect Closed Eyes (Detectar ojos cerrados) [ON/OFF]
    - Overwrite XMP Ratings (Sobrescribir calificaciones en archivos XMP) [ON/OFF]

### R5. Metadata Export
Write rating, color label, and pick/reject status to Lightroom-compatible `.xmp` sidecar files in the same directory as the source photos, mapping to the user's customized colors and star configurations.

## Acceptance Criteria

### Technical & Functional
- [ ] Backend runs locally as a FastAPI/gRPC process invoked by the Electron main process.
- [ ] Processing a folder of 100 mixed RAW/JPG photos takes under 60 seconds (utilizing embedded JPEG extraction).
- [ ] AI models run successfully and perform culling evaluation on both GPU-equipped and CPU-only devices without crashing.
- [ ] Images are grouped into visual similarity clusters; selecting a cluster shows all members for A/B comparison.
- [ ] UI correctly displays and configures the default star and color mappings (Green=Selected, Blue=Highlights, Red=Blurry, Purple=Closed Eyes, Yellow=Duplicates).
- [ ] Exporting writes valid `.xmp` sidecars containing standard XML namespaces (`xmp`, `xmpDM`, `tiff`, `exif`) matching the selected colors and ratings.

---
*Next: when approved → delegate via invoke_subagent (see Delegation Protocol)*
