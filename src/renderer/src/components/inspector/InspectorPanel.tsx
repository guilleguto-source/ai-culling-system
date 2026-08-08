import React, { useState, useEffect } from 'react';
import { getDynamicStyles } from '../../utils/dynamicStyles';
import { apiClient } from '../../api/client';

const ETIQUETAS: [string, string][] = [
  ['camara', 'Cámara'], ['lente', 'Lente'], ['apertura', 'Apertura'],
  ['iso', 'ISO'], ['velocidad', 'Velocidad'], ['focal', 'Focal'],
];

export default function InspectorPanel({ foto, onClose }: { foto: any; onClose: () => void }) {
  const [exif, setExif] = useState<any>(null);

  useEffect(() => {
    if (!foto) return;
    setExif(null);
    (async () => {
      try {
        const data = await apiClient.getExif(foto.path);
        setExif(data);
      } catch { }
    })();
  }, [foto]);

  if (!foto) return (
    <div style={{
      width: '320px', backgroundColor: 'var(--bg-elevated)', borderLeft: '1px solid var(--border-subtle)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '0.9rem'
    }}>
      Selecciona una foto para ver detalles
    </div>
  );

  const filas = ETIQUETAS.filter(([k]) => exif?.[k]);

  return (
    <div 
      className="inspector-slide-in"
      style={{
        width: '320px',
        backgroundColor: 'var(--bg-elevated)',
        borderLeft: '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
        overflowY: 'auto'
      }}
    >
      <div className="flex-between" style={{ padding: '16px', borderBottom: '1px solid var(--border-subtle)' }}>
        <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-primary)' }}>Inspector</h3>
        <button className="btn btn-secondary" style={{ padding: '4px 8px', fontSize: '0.8rem' }} onClick={onClose}>✕</button>
      </div>

      <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
        
        {/* Vista previa miniatura */}
        <div style={{ width: '100%', aspectRatio: '3/2', backgroundColor: 'var(--bg-deep)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
          <img 
            src={apiClient.getThumbnailUrl(foto.path)} 
            style={{ width: '100%', height: '100%', objectFit: 'contain', ...getDynamicStyles(foto) }}
            alt="Preview"
          />
        </div>

        <div style={{ fontSize: '0.85rem', color: 'var(--text-primary)', wordBreak: 'break-all', fontWeight: 500 }}>
          {foto.filename}
        </div>

        {/* Diagnóstico (Barras de Score) */}
        {foto.diagnostics && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>
              Análisis del Motor
            </div>
            
            {foto.score !== undefined && (
              <div>
                <div className="flex-between" style={{ fontSize: '0.75rem', marginBottom: '6px', color: 'var(--text-secondary)' }}>
                  <span>Afinidad de Estilo</span>
                  <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{Math.round(Math.min(1, foto.score) * 100)}%</span>
                </div>
                <div style={{ height: '4px', backgroundColor: 'var(--bg-surface)', borderRadius: '2px', overflow: 'hidden' }}>
                  <div style={{ width: `${Math.round(Math.min(1, foto.score) * 100)}%`, height: '100%', backgroundColor: 'var(--accent-amber)' }} />
                </div>
              </div>
            )}
            
            {foto.diagnostics.aesthetic_score !== undefined && (
              <div>
                <div className="flex-between" style={{ fontSize: '0.75rem', marginBottom: '6px', color: 'var(--text-secondary)' }}>
                  <span>Composición (Estética)</span>
                  <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{Math.round(foto.diagnostics.aesthetic_score * 100)}%</span>
                </div>
                <div style={{ height: '4px', backgroundColor: 'var(--bg-surface)', borderRadius: '2px', overflow: 'hidden' }}>
                  <div style={{ width: `${Math.round(foto.diagnostics.aesthetic_score * 100)}%`, height: '100%', backgroundColor: 'var(--accent-teal)' }} />
                </div>
              </div>
            )}
            
            {foto.diagnostics.blur_score !== undefined && (
              <div>
                <div className="flex-between" style={{ fontSize: '0.75rem', marginBottom: '6px', color: 'var(--text-secondary)' }}>
                  <span>Nitidez</span>
                  <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{Math.round(Math.min(1, foto.diagnostics.blur_score / 500) * 100)}%</span>
                </div>
                <div style={{ height: '4px', backgroundColor: 'var(--bg-surface)', borderRadius: '2px', overflow: 'hidden' }}>
                  <div style={{ width: `${Math.round(Math.min(1, foto.diagnostics.blur_score / 500) * 100)}%`, height: '100%', backgroundColor: 'var(--accent-blue)' }} />
                </div>
              </div>
            )}
          </div>
        )}

        {/* Insignias de Caras */}
        {foto.diagnostics && foto.diagnostics.valid_face_count > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
            <span className="badge" style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border-strong)' }}>
              👤 {foto.diagnostics.valid_face_count} {foto.diagnostics.valid_face_count === 1 ? 'Cara' : 'Caras'}
            </span>
            {foto.diagnostics.closed_eyes_count > 0 && (
              <span className="badge badge-closed">
                👁 {foto.diagnostics.closed_eyes_count} Ojos Cerrados
              </span>
            )}
            {foto.diagnostics.smiling_count > 0 && (
              <span className="badge badge-selected">
                🙂 {foto.diagnostics.smiling_count} Sonriendo
              </span>
            )}
          </div>
        )}

        {/* Razones Textuales */}
        {Array.isArray(foto.reasons) && foto.reasons.length > 0 && (
          <div style={{ padding: '12px', backgroundColor: 'var(--bg-surface)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '8px', fontWeight: 600 }}>Diagnóstico</div>
            {foto.reasons.map((r: string, i: number) => (
              <div key={i} style={{
                fontSize: '0.8rem',
                marginBottom: '4px',
                color: r.startsWith('✔') ? 'var(--accent-teal)'
                     : r.startsWith('✖') ? 'var(--accent-rose)' : 'var(--text-secondary)',
                lineHeight: 1.4
              }}>{r}</div>
            ))}
          </div>
        )}

        {/* EXIF */}
        {filas.length > 0 && (
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px', fontWeight: 600 }}>
              Datos de Toma
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {filas.map(([clave, texto]) => (
                <div key={clave} className="flex-between" style={{ fontSize: '0.8rem' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>{texto}</span>
                  <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>{exif[clave]}</span>
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
