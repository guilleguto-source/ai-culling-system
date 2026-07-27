import React from 'react';

/**
 * Convierte los diccionarios `crop` y `develop` provenientes del backend
 * en propiedades CSS nativas (`transform`, `filter`) para previsualización a 0ms.
 */
export function getDynamicStyles(foto: any): React.CSSProperties {
  const styles: React.CSSProperties = {};
  
  if (!foto) return styles;

  // 1. Transformación de Recorte (Crop & Rotate)
  // El crop_dict del backend viene como { left, top, right, bottom, angle } en proporciones 0..1
  if (foto.has_crop && foto.crop) {
    const { left, top, right, bottom, angle } = foto.crop;
    
    // Ancho y alto de la ventana visible
    const cw = right - left;
    const ch = bottom - top;
    
    if (cw > 0 && ch > 0) {
      // Scale para que la parte visible llene el contenedor
      const scaleX = 1 / cw;
      const scaleY = 1 / ch;
      const scale = Math.max(scaleX, scaleY);
      
      // Translate para centrar el recorte
      // El centro original es 0.5, 0.5. El centro del crop es (left + right)/2, (top + bottom)/2.
      const cx = (left + right) / 2;
      const cy = (top + bottom) / 2;
      const tx = (0.5 - cx) * 100;
      const ty = (0.5 - cy) * 100;
      
      // Aplicamos traslación, luego escala, luego rotación.
      styles.transform = `translate(${tx}%, ${ty}%) scale(${scale}) rotate(${angle || 0}deg)`;
      styles.transformOrigin = 'center';
    }
  }

  // 2. Filtros de Revelado Básico (Develop)
  if (foto.develop) {
    const filters: string[] = [];
    
    // Exposición: mapeo rústico de EV a brightness
    if (foto.develop.Exposure2012 !== undefined) {
      const exp = parseFloat(foto.develop.Exposure2012);
      // EV +1 = brillo 150%, EV -1 = brillo 50%
      const brightness = 1 + (exp * 0.5); 
      filters.push(`brightness(${Math.max(0, brightness)})`);
    }
    
    // Temperatura: un hack rústico con sepia y hue-rotate, 
    // pero para no complicar el render de React, usaremos sepia ligero.
    if (foto.develop.Temperature !== undefined) {
      const temp = parseFloat(foto.develop.Temperature);
      // Temp base ~5000. Mayor -> más cálido (sepia). Menor -> más frío.
      if (temp > 5500) {
        filters.push(`sepia(${Math.min(100, (temp - 5500) / 100)}%)`);
      }
    }
    
    // Contraste
    if (foto.develop.Contrast2012 !== undefined) {
      const contrast = parseFloat(foto.develop.Contrast2012);
      // -100 = 0%, 0 = 100%, 100 = 200%
      const c = 1 + (contrast / 100);
      filters.push(`contrast(${Math.max(0, c)})`);
    }

    if (filters.length > 0) {
      styles.filter = filters.join(' ');
    }
  }

  return styles;
}
