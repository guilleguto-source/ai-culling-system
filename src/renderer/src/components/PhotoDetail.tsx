import React, { useState, useEffect } from 'react';

const API = 'http://127.0.0.1:8000';

const ETIQUETAS: [string, string][] = [
  ['camara', 'Cámara'], ['lente', 'Lente'], ['apertura', 'Apertura'],
  ['iso', 'ISO'], ['velocidad', 'Velocidad'], ['focal', 'Focal'],
];

/**
 * Detalle de una foto: datos de toma y previsualización de la pre-edición.
 *
 * El preview es una APROXIMACIÓN de lo que hará Camera Raw (exposición, WB y
 * recorte sobre el thumb), no un motor de revelado. Sirve para decidir sí/no
 * antes de escribir el XMP — hasta ahora "Aplicar edición" trabajaba a ciegas.
 */
export default function PhotoDetail({ foto, onClose }: { foto: any; onClose: () => void }) {
  const [exif, setExif] = useState<any>(null);
  const [conEdicion, setConEdicion] = useState(true);

  useEffect(() => {
    if (!foto) return;
    setExif(null);
    (async () => {
      try {
        const r = await fetch(`${API}/exif?path=${encodeURIComponent(foto.path)}`);
        if (r.ok) setExif(await r.json());
      } catch { /* sin EXIF: la sección simplemente no aparece */ }
    })();
  }, [foto]);

  if (!foto) return null;

  const filas = ETIQUETAS.filter(([k]) => exif?.[k]);

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.75)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="glass-panel"
        style={{
          display: 'flex', gap: '16px', padding: '16px',
          maxWidth: '92vw', maxHeight: '92vh',
        }}
      >
        {/* Imagen */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', minWidth: 0 }}>
          <img
            src={`${API}/preview?path=${encodeURIComponent(foto.path)}&con_edicion=${conEdicion}`}
            alt={foto.filename}
            style={{ maxWidth: '70vw', maxHeight: '78vh', objectFit: 'contain', borderRadius: '6px' }}
          />
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <button
              className={conEdicion ? 'btn btn-primary' : 'btn btn-secondary'}
              style={{ fontSize: '0.8rem', padding: '6px 12px' }}
              onClick={() => setConEdicion(true)}
            >
              Con pre-edición
            </button>
            <button
              className={!conEdicion ? 'btn btn-primary' : 'btn btn-secondary'}
              style={{ fontSize: '0.8rem', padding: '6px 12px' }}
              onClick={() => setConEdicion(false)}
            >
              Original
            </button>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginLeft: '6px' }}>
              Aproximación — el revelado final lo hace Lightroom
            </span>
          </div>
        </div>

        {/* Datos */}
        <div style={{ width: '260px', overflowY: 'auto', fontSize: '0.8rem' }}>
          <div className="flex-between" style={{ marginBottom: '10px' }}>
            <strong style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{foto.filename}</strong>
            <button className="btn btn-secondary" style={{ padding: '2px 8px' }} onClick={onClose}>✕</button>
          </div>

          {Array.isArray(foto.reasons) && foto.reasons.length > 0 && (
            <div style={{ marginBottom: '14px', lineHeight: 1.6 }}>
              {foto.reasons.map((r: string, i: number) => (
                <div key={i} style={{
                  fontSize: '0.75rem',
                  color: r.startsWith('✔') ? 'var(--status-selected-text)'
                       : r.startsWith('✖') ? 'var(--status-blurry-text)' : 'var(--text-muted)',
                }}>{r}</div>
              ))}
            </div>
          )}

          {filas.length > 0 && (
            <>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)',
                textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '6px' }}>
                Datos de toma
              </div>
              {filas.map(([clave, texto]) => (
                <div key={clave} className="flex-between" style={{ padding: '3px 0' }}>
                  <span style={{ color: 'var(--text-muted)' }}>{texto}</span>
                  <span>{exif[clave]}</span>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
