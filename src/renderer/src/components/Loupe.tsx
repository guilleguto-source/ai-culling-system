import React, { useRef, useState, useCallback } from 'react';

// Diámetro de la lupa en pantalla y cuánto acerca. La imagen fuente ya viene
// en alta resolución (thumb "duel" = 1600px), así que este zoom es sobre
// detalle real, no un simple estirado de píxeles.
const LENTE_PX = 260;
const ZOOM = 3;

interface Props {
  src: string;
  alt?: string;
  style?: React.CSSProperties;
}

// Lupa de zoom: aparece al pasar el mouse sobre la foto, para cuando dos
// fotos son casi iguales y hay que ver el detalle (ojos, foco) que el
// tamaño en pantalla no muestra.
export default function Loupe({ src, alt, style }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const naturalRef = useRef<{ w: number; h: number }>({ w: 0, h: 0 });
  const [lens, setLens] = useState<{ x: number; y: number; bgX: number; bgY: number } | null>(null);

  const onLoad = useCallback((e: React.SyntheticEvent<HTMLImageElement>) => {
    naturalRef.current = { w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight };
  }, []);

  const onMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const cont = containerRef.current;
    const { w: naturalW, h: naturalH } = naturalRef.current;
    if (!cont || !naturalW || !naturalH) return;
    const rect = cont.getBoundingClientRect();

    // objectFit:contain deja franjas vacías arriba/abajo o a los costados;
    // hay que ubicar el cursor relativo a la imagen VISIBLE, no al contenedor.
    const scale = Math.min(rect.width / naturalW, rect.height / naturalH);
    const dispW = naturalW * scale;
    const dispH = naturalH * scale;
    const offX = (rect.width - dispW) / 2;
    const offY = (rect.height - dispH) / 2;
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;

    if (cx < offX || cx > offX + dispW || cy < offY || cy > offY + dispH) {
      setLens(null);
      return;
    }

    const px = (cx - offX) / dispW;
    const py = (cy - offY) / dispH;
    setLens({
      x: cx,
      y: cy,
      bgX: px * naturalW * ZOOM - LENTE_PX / 2,
      bgY: py * naturalH * ZOOM - LENTE_PX / 2,
    });
  }, []);

  return (
    <div
      ref={containerRef}
      onMouseMove={onMove}
      onMouseLeave={() => setLens(null)}
      style={{ position: 'relative', width: '100%', height: '100%' }}
    >
      <img src={src} alt={alt} onLoad={onLoad} draggable={false} style={style} />
      {lens && (
        <div
          style={{
            position: 'absolute',
            left: lens.x - LENTE_PX / 2,
            top: lens.y - LENTE_PX / 2,
            width: LENTE_PX,
            height: LENTE_PX,
            borderRadius: '50%',
            border: '2px solid var(--accent-primary)',
            boxShadow: '0 4px 20px rgba(0,0,0,0.6)',
            backgroundColor: '#000',
            backgroundImage: `url(${src})`,
            backgroundRepeat: 'no-repeat',
            backgroundSize: `${naturalRef.current.w * ZOOM}px ${naturalRef.current.h * ZOOM}px`,
            backgroundPosition: `-${lens.bgX}px -${lens.bgY}px`,
            pointerEvents: 'none',
            zIndex: 50,
          }}
        />
      )}
    </div>
  );
}
