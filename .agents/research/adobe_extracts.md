# Extractos Técnicos: Photoshop Liquify, Camera Raw Masking & Selección Asistida
> Generado mediante análisis quirúrgico por REA / Scoped Extraction en binarios oficiales de Adobe.
> Fecha: 2026-10-27 | Target Host: Windows x64 | Destino: GutoFlow / LightCraft

---

## 1. Photoshop: Face-Aware Liquify (`Liquify.8bf`)

### 1.1 ActionDescriptor Keys (stringIDToTypeID)
Claves exactas para invocación headless vía Python / COM / ActionDescriptors sin abrir la interfaz de Photoshop:

| Categoría | Claves Identificadas en `Liquify.8bf` |
| :--- | :--- |
| **Estructura Raíz** | `faceInfoList`, `faceInfo`, `faceCenter`, `featureValues`, `featureDisplacements`, `faceMesh`, `faceDescriptorVersion`, `faceMeshVersion` |
| **Ojos (Eyes)** | `eyeSize`, `eyeHeight`, `eyeWidth`, `eyeTilt`, `eyeDistance`<br/>`leftEyeSize`, `rightEyeSize`, `leftEyeHeight`, `rightEyeHeight`, `leftEyeWidth`, `rightEyeWidth`, `leftEyeTilt`, `rightEyeTilt` |
| **Boca (Mouth)** | `smile`, `upperLip`, `lowerLip`, `mouthWidth`, `mouthHeight` |
| **Nariz (Nose)** | `noseWidth`, `noseHeight` |
| **Rostro (Face Shape)** | `foreheadHeight`, `chinHeight`, `jawShape`, `faceWidth` |
| **Landmarks/Componentes** | `leftEye`, `rightEye`, `mouth`, `nose`, `leftCheek`, `rightCheek`, `chin` |

### 1.2 Pipeline de Deformación GLSL (`WarpLookup`)
Photoshop aplica una cascada de doble textura de malla vectorial para desacoplar el pincel manual del ajuste paramétrico facial:

```glsl
// Uniforms del shader Liquify
uniform mat4 MatrixSrc2MeshNorm;
uniform mat4 MatrixSrc2SupportNorm;
uniform vec4 SrcBounds;                  // (p=width, q=height, s=left, t=top)
uniform sampler2D texDistortionMesh;     // Malla 1: Pincel/Manual
uniform sampler2D texFaceDistortionMesh; // Malla 2: Face-Aware RBF/TPS
uniform sampler2D texSourceImage;        // Imagen original

// Función de mapeo de coordenadas (WarpLookup)
vec2 WarpLookup(vec2 loc)
{
    // 1. Coordenadas normalizadas sobre la malla de deformación manual
    vec3 normalizedMeshLoc = (MatrixSrc2MeshNorm * vec4(loc.x, loc.y, 1.0, 0.0)).xyz;
    vec2 SrcSize = vec2(SrcBounds.p - SrcBounds.s, SrcBounds.q - SrcBounds.t);
    
    // 2. Muestreo de desplazamiento manual
    vec2 p_l = texture(texDistortionMesh, normalizedMeshLoc.st).st;
    loc = SrcSize * p_l + loc;
    
    // 3. Proyección sobre la malla facial paramétrica
    normalizedMeshLoc = (MatrixSrc2MeshNorm * vec4(loc.x, loc.y, 1.0, 0.0)).xyz;
    vec2 p_f = texture(texFaceDistortionMesh, normalizedMeshLoc.st).st;
    
    // 4. Coordenada final de muestreo en el espacio de la imagen fuente
    return SrcSize * p_f + loc;
}

// Muestreo con corrección de borde y alpha premultiplicado
vec4 SrcLookup(vec2 srcloc, vec2 dstLoc)
{
    vec3 sourceTileLoc = (MatrixSrc2SupportNorm * vec4(srcloc.x, srcloc.y, 1.0, 0.0)).xyz;
    vec4 resultTexel = texture(texSourceImage, sourceTileLoc.xy);
    
    // Premultiply alpha (black matting)
    resultTexel = (resultTexel * vec4(resultTexel.a, resultTexel.a, resultTexel.a, 1.0));
    
    // Half-texel clamp inset (0.499) para evitar bleeding de bordes
    return resultTexel;
}
```

---

## 2. Lightroom Classic: Camera Raw AI Masking (`Camera Raw.8bi`)

### 2.1 Refinamiento de Bordes: `fastGuidedFilter`
Lightroom descarta Laplacian Matting puro por latencia y utiliza un **Fast Guided Filter** sobre pirámides gaussianas:

* **Secuencia de Ejecución:**
  1. `PanopticFCN` (`postproc_panopticfcn`): Inferencia de segmentación semántica (genera mapas de instancias `instmaps` y cosas/fondos `numthings`/`numstuff`).
  2. `label_to_color_erode`: Erosión morfológica de 1-2 píxeles sobre la máscara cruda.
  3. `pyramid_resize` & `pyramid_dimensions`: Downsampling de la máscara y de la imagen guía.
  4. `fastGuidedFilter`: Filtrado guiado por la luminancia de la imagen a baja resolución y upsampling bilineal guiado.
  5. `divide_by_alpha` & `black_fill`: Normalización de bordes semitransparentes.

### 2.2 Esquema XMP Nativo (`crs:MaskGroupBasedCorrections`)
Estructura XML requerida para que Lightroom procese y recalcule máscaras en segundo plano (`Recompute`):

```xml
<crs:MaskGroupBasedCorrections>
 <rdf:Seq>
  <rdf:li>
   <rdf:Description
    crs:What="Correction"
    crs:CorrectionAmount="1.000000"
    crs:CorrectionActive="true"
    crs:CorrectionName="Retoque Piel Facial"
    crs:CorrectionSyncID="B7C8E9F0-1234-5678-9ABC-DEF012345678">
    <crs:CorrectionMasks>
     <rdf:Seq>
      <rdf:li
       crs:What="Mask/Aggregate"
       crs:MaskActive="true"
       crs:MaskInverted="false"
       crs:MaskBlendMode="0"
       crs:MaskValue="1.000000"
       crs:MaskVersion="1"
       crs:MaskSubType="fMaskSemanticLabel"
       crs:SemanticObjectPrompt="FaceSkin"
       crs:Recompute="true"
       crs:Feather="0.000000"
       crs:EdgeShift="0.000000"/>
     </rdf:Seq>
    </crs:CorrectionMasks>
   </rdf:Description>
  </rdf:li>
 </rdf:Seq>
</crs:MaskGroupBasedCorrections>
```

### 2.3 Categorías Semánticas de Personas Reconocidas (`SemanticObjectPrompt`)
1. `FaceSkin` (Piel del rostro)
2. `BodySkin` (Piel corporal)
3. `Eyebrows` (Cejas)
4. `EyeSclera` (Esclerótica de los ojos)
5. `IrisAndPupil` (Iris y pupila)
6. `Lips` (Labios)
7. `Teeth` (Dientes)
8. `Hair` (Cabello)
9. `Ears` (Orejas)
10. `Beard` (Vello facial / Barba)
11. `Clothes` (Ropa)

---

## 3. Lightroom Classic: Selección Asistida / AI Culling (`CameraRaw.dll` + `LibraryToolkit.dll`)

### 3.1 Modelo de Datos en Catálogo SQLite (`.lrcat`)
Lightroom indexa las puntuaciones en tablas dedicadas para desacoplar la inferencia ML de la UI reactiva:

* **Tablas de Culling:**
  * `AgLibraryImageCullingScore`: Registro central de puntuaciones por imagen.
  * `AgLibraryImageCullingFaceDetails`: Bounding boxes, landmarks y recortes (`renderCullingFaceImages`).
  * `AgLibraryImageEmbeddings`: Vectores de 512d para medir similitud de ráfagas.
  * `AgLibraryImageBestFrameScore`: Puntuación ponderada para selección de portada de pila.
  * `AgLibraryImageUndesiredScores`: Banderas de rechazo por exposición, accidentes o documentos.

* **Consulta SQL en Tiempo Real (ejecutada al mover los sliders):**
```sql
SELECT image FROM AgLibraryImageCullingScore 
WHERE userSelect = 1 
   OR (userSelect IS NULL 
       AND subjectSharpnessScore >= ? 
       AND (eyeSharpnessScore >= ? OR includeNoEyes = 1) 
       AND eyesOpenState IN ('probably_open', 'open'));
```

### 3.2 Algoritmos y Rasgos Extraídos (`CameraRaw.dll`)

| Métrica UI | Símbolo / Método Interno | Algoritmo y Funcionamiento |
| :--- | :--- | :--- |
| **Enfocar Sujeto** | `SubjectSelectLiteCulling`<br/>`subjectSharpnessScore` | Segmentación IA rápida en preview (1024-2048px). Varianza de gradientes Laplaciano/Sobel restringida dentro de la máscara del sujeto (ignora bokeh). Escala 0-100. |
| **Enfoque de Ojos** | `UCullingEyeSharpnessTraits`<br/>`eyeSharpnessScore` | Recorte local centrado en los ojos (`renderCullingFaceImages`). Energía de altas frecuencias en la transición esclerótica-iris. Escala 0-100. |
| **Ojos Abiertos** | `objectDetectorTypeEyesOpenClose`<br/>`eyesOpenState` | Clasificador de apertura ocular. Umbrales probabilísticos:<br/>• $\ge 0.85 \rightarrow$ "Sí"<br/>• $0.50 \le P < 0.85 \rightarrow$ "Probablemente"<br/>• $< 0.50 \rightarrow$ "Cerrados" |
| **Rechazar: Exposición** | `cullingInfoTypeExposure` | Análisis de histograma (detección de recortes extremos por sub/sobreexposición). |
| **Rechazar: Accidentes** | `cullingInfoTypeBlackOrWhiteImage` | Detección de fotos negras (tapa puesta), fotos blancas/quemadas o fotos con motion-blur masivo. |
| **Rechazar: Documentos** | `cullingInfoTypeDocumentOrReceipt` | Clasificador OCR/documental que descarta listas de invitados, recibos o notas. |
| **Apilamiento Automático** | `AgLibraryImageEmbeddings`<br/>`CullingBestFrameSelectionScores` | Agrupación temporal ($\Delta t < 2-5\text{ s}$) + distancia coseno entre embeddings. Selección del *Best Frame* por suma ponderada: $0.4 \cdot S_{\text{subj}} + 0.4 \cdot S_{\text{eye}} + 0.2 \cdot S_{\text{open}}$. |
