"""
Photoshop Face-Aware Liquify Automation (Headless via ActionDescriptors)
Claves extraídas de Liquify.8bf mediante ingeniería inversa.
Permite aplicar retoques paramétricos faciales sin abrir la interfaz gráfica.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import json
import logging

logger = logging.getLogger(__name__)

@dataclass
class FaceLiquifyParams:
    # Ojos (Eyes)
    eye_size: float = 0.0          # [-100, 100]
    eye_height: float = 0.0        # [-100, 100]
    eye_width: float = 0.0         # [-100, 100]
    eye_tilt: float = 0.0          # [-100, 100]
    eye_distance: float = 0.0      # [-100, 100]
    left_eye_size: Optional[float] = None
    right_eye_size: Optional[float] = None
    left_eye_height: Optional[float] = None
    right_eye_height: Optional[float] = None
    left_eye_width: Optional[float] = None
    right_eye_width: Optional[float] = None
    left_eye_tilt: Optional[float] = None
    right_eye_tilt: Optional[float] = None

    # Nariz (Nose)
    nose_height: float = 0.0       # [-100, 100]
    nose_width: float = 0.0        # [-100, 100]

    # Boca (Mouth)
    smile: float = 0.0             # [-100, 100]
    upper_lip: float = 0.0         # [-100, 100]
    lower_lip: float = 0.0         # [-100, 100]
    mouth_width: float = 0.0       # [-100, 100]
    mouth_height: float = 0.0      # [-100, 100]

    # Forma del Rostro (Face Shape)
    forehead_height: float = 0.0   # [-100, 100]
    chin_height: float = 0.0       # [-100, 100]
    jaw_shape: float = 0.0         # [-100, 100]
    face_width: float = 0.0        # [-100, 100]

    def to_descriptor_map(self) -> Dict[str, float]:
        """Mapea los atributos de la clase a las claves exactas de Liquify.8bf."""
        mapping = {
            "eyeSize": self.eye_size,
            "eyeHeight": self.eye_height,
            "eyeWidth": self.eye_width,
            "eyeTilt": self.eye_tilt,
            "eyeDistance": self.eye_distance,
            "leftEyeSize": self.left_eye_size if self.left_eye_size is not None else self.eye_size,
            "rightEyeSize": self.right_eye_size if self.right_eye_size is not None else self.eye_size,
            "leftEyeHeight": self.left_eye_height if self.left_eye_height is not None else self.eye_height,
            "rightEyeHeight": self.right_eye_height if self.right_eye_height is not None else self.eye_height,
            "leftEyeWidth": self.left_eye_width if self.left_eye_width is not None else self.eye_width,
            "rightEyeWidth": self.right_eye_width if self.right_eye_width is not None else self.eye_width,
            "leftEyeTilt": self.left_eye_tilt if self.left_eye_tilt is not None else self.eye_tilt,
            "rightEyeTilt": self.right_eye_tilt if self.right_eye_tilt is not None else self.eye_tilt,
            "noseHeight": self.nose_height,
            "noseWidth": self.nose_width,
            "smile": self.smile,
            "upperLip": self.upper_lip,
            "lowerLip": self.lower_lip,
            "mouthWidth": self.mouth_width,
            "mouthHeight": self.mouth_height,
            "foreheadHeight": self.forehead_height,
            "chinHeight": self.chin_height,
            "jawShape": self.jaw_shape,
            "faceWidth": self.face_width,
        }
        return {k: max(-100.0, min(100.0, float(v))) for k, v in mapping.items()}

    def to_extendscript(self, face_index: int = 0) -> str:
        """
        Genera el bloque ExtendScript (JSX) para despachar el ActionDescriptor
        directamente al plugin Liquify.8bf en segundo plano.
        """
        params = self.to_descriptor_map()
        
        jsx_lines = [
            "// Auto-generated ExtendScript for Headless Face-Aware Liquify",
            "(function() {",
            "    var descLiquify = new ActionDescriptor();",
            "    var descFaceInfo = new ActionDescriptor();",
            "    var descFeatureValues = new ActionDescriptor();",
            "",
            "    // Asignar parámetros Face-Aware a través de stringIDToTypeID",
        ]
        
        for key, val in params.items():
            if val != 0.0:
                jsx_lines.append(f'    descFeatureValues.putDouble(stringIDToTypeID("{key}"), {val});')
        
        jsx_lines.extend([
            f'    descFaceInfo.putObject(stringIDToTypeID("featureValues"), stringIDToTypeID("featureValues"), descFeatureValues);',
            f'    var listFaceInfo = new ActionList();',
            f'    listFaceInfo.putObject(stringIDToTypeID("faceInfo"), descFaceInfo);',
            f'    descLiquify.putList(stringIDToTypeID("faceInfoList"), listFaceInfo);',
            f'    descLiquify.putInteger(stringIDToTypeID("faceDescriptorVersion"), 2);',
            f'    executeAction(stringIDToTypeID("liquify"), descLiquify, DialogModes.NO);',
            "})();"
        ])
        
        return "\n".join(jsx_lines)


class PhotoshopLiquifyDispatcher:
    """Despachador para interactuar con Adobe Photoshop mediante COM (Windows)."""

    def __init__(self):
        self._app = None

    def _get_app(self):
        if self._app is None:
            try:
                import win32com.client
                self._app = win32com.client.Dispatch("Photoshop.Application")
            except Exception as e:
                logger.error("Error al conectar con Photoshop via COM: %s", str(e))
                raise RuntimeError(f"Photoshop COM dispatch failed: {e}") from e
        return self._app

    def apply_face_liquify(self, params: FaceLiquifyParams) -> bool:
        """Aplica la deformación facial paramétrica al documento activo en Photoshop."""
        try:
            app = self._get_app()
            jsx_script = params.to_extendscript()
            app.DoJavaScript(jsx_script)
            logger.info("Face-Aware Liquify aplicado exitosamente.")
            return True
        except Exception as e:
            logger.error("Fallo al ejecutar DoJavaScript en Photoshop: %s", str(e))
            raise
