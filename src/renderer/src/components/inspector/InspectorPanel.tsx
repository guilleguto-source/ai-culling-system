import React, { useState, useEffect } from 'react';
import { getDynamicStyles } from '../../utils/dynamicStyles';
import { apiClient } from '../../api/client';
import { useToast } from '../Toast';

const ETIQUETAS: [string, string][] = [
  ['camara', 'Cámara'], ['lente', 'Lente'], ['apertura', 'Apertura'],
  ['iso', 'ISO'], ['velocidad', 'Velocidad'], ['focal', 'Focal'],
];

export default function InspectorPanel({ foto, onClose }: { foto: any; onClose: () => void }) {
  const [exif, setExif] = useState<any>(null);
  const [chapters, setChapters] = useState<any[]>([]);
  const [moving, setMoving] = useState(false);
  const { showToast } = useToast();

  const directory = foto ? foto.path.substring(0, Math.max(foto.path.lastIndexOf('\\'), foto.path.lastIndexOf('/'))) : '';

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

  useEffect(() => {
    if (!directory) return;
    (async () => {
      try {
        const data = await apiClient.getStoryline(directory);
        if (data && data.storyline) setChapters(data.storyline);
      } catch { }
    })();
  }, [directory]);

  const handleOverrideChapter = async (chapterId: string) => {
    if (!directory || !foto) return;
    setMoving(true);
    try {
      await apiClient.overrideStorylineChapter(directory, foto.path, chapterId);
      showToast('Movida al nuevo momento. Recarga para ver los cambios.', 'success');
    } catch (e: any) {
      showToast('Error moviendo foto: ' + e.message, 'error');
    } finally {
      setMoving(false);
    }
  };

  if (!foto) return (
    <div style={{
      width: 'var(--inspector-width)',
      backgroundColor: 'var(--color-surface)',
      borderLeft: '1px solid var(--border-default)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: 'var(--text-tertiary)',
      fontSize: 'var(--text-sm)',
      padding: 'var(--space-4)'
    }}>
      Selecciona una foto para inspeccionar
    </div>
  );

  const filas = ETIQUETAS.filter(([k]) => exif?.[k]);

  return (
    <div 
      className="inspector-slide-in"
      style={{
        width: 'var(--inspector-width)',
        backgroundColor: 'var(--color-surface)',
        borderLeft: '1px solid var(--border-default)',
        display: 'flex',
        flexDirection: 'column',
        overflowY: 'auto'
      }}
    >
      <div className="flex-between" style={{ padding: '14px 20px', borderBottom: '1px solid var(--border-default)' }}>
        <span style={{ fontSize: '13px', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)', letterSpacing: '0.04em', textTransform: 'uppercase' }}>
          Inspector
        </span>
        <button
          className="gf-btn gf-btn-ghost gf-btn-sm"
          style={{ padding: '4px 8px', fontSize: '12px' }}
          onClick={onClose}
          aria-label="Cerrar inspector"
        >
          ✕
        </button>
      </div>

      <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
        
        {/* Vista previa miniatura */}
        <div style={{ width: '100%', aspectRatio: '3/2', backgroundColor: 'var(--color-bg)', borderRadius: 'var(--radius-photo)', overflow: 'hidden' }}>
          <img 
            src={apiClient.getThumbnailUrl(foto.path)} 
            style={{ width: '100%', height: '100%', objectFit: 'contain', ...getDynamicStyles(foto) }}
            alt="Preview"
          />
        </div>

        <div className="font-mono" style={{ fontSize: '12px', color: 'var(--text-primary)', wordBreak: 'break-all', fontWeight: 'var(--fw-medium)' }}>
          {foto.filename}
        </div>

        {/* Diagnóstico (Barras de Score) */}
        {foto.diagnostics && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div style={{ fontSize: '10px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 'var(--fw-bold)' }}>
              Análisis del Motor
            </div>
            
            {foto.score !== undefined && (
              <div>
                <div className="flex-between" style={{ fontSize: '11px', marginBottom: '6px', color: 'var(--text-secondary)' }}>
                  <span>Afinidad de Estilo</span>
                  <span className="font-mono" style={{ fontWeight: 'var(--fw-bold)', color: 'var(--accent-primary)' }}>{Math.round(Math.min(1, foto.score) * 100)}%</span>
                </div>
                <div style={{ height: '4px', backgroundColor: 'var(--color-surface-hover)', borderRadius: '2px', overflow: 'hidden' }}>
                  <div style={{ width: `${Math.round(Math.min(1, foto.score) * 100)}%`, height: '100%', backgroundColor: 'var(--accent-primary)', boxShadow: 'var(--shadow-guto)' }} />
                </div>
              </div>
            )}
            
            {foto.diagnostics.aesthetic_score !== undefined && (
              <div>
                <div className="flex-between" style={{ fontSize: '11px', marginBottom: '6px', color: 'var(--text-secondary)' }}>
                  <span>Composición</span>
                  <span className="font-mono" style={{ fontWeight: 'var(--fw-bold)', color: 'var(--text-primary)' }}>{Math.round(foto.diagnostics.aesthetic_score * 100)}%</span>
                </div>
                <div style={{ height: '4px', backgroundColor: 'var(--color-surface-hover)', borderRadius: '2px', overflow: 'hidden' }}>
                  <div style={{ width: `${Math.round(foto.diagnostics.aesthetic_score * 100)}%`, height: '100%', backgroundColor: 'var(--success)' }} />
                </div>
              </div>
            )}
            
            {foto.diagnostics.blur_score !== undefined && (
              <div>
                <div className="flex-between" style={{ fontSize: '11px', marginBottom: '6px', color: 'var(--text-secondary)' }}>
                  <span>Nitidez</span>
                  <span className="font-mono" style={{ fontWeight: 'var(--fw-bold)', color: 'var(--text-primary)' }}>{Math.round(Math.min(1, foto.diagnostics.blur_score / 500) * 100)}%</span>
                </div>
                <div style={{ height: '4px', backgroundColor: 'var(--color-surface-hover)', borderRadius: '2px', overflow: 'hidden' }}>
                  <div style={{ width: `${Math.round(Math.min(1, foto.diagnostics.blur_score / 500) * 100)}%`, height: '100%', backgroundColor: 'var(--color-info)' }} />
                </div>
              </div>
            )}
          </div>
        )}

        {/* Insignias de Caras */}
        {foto.diagnostics && foto.diagnostics.valid_face_count > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            <span className="gf-badge" style={{ fontSize: '10px' }}>
              👤 {foto.diagnostics.valid_face_count} {foto.diagnostics.valid_face_count === 1 ? 'Cara' : 'Caras'}
            </span>
            {foto.diagnostics.closed_eyes_count > 0 && (
              <span className="gf-badge gf-badge-reject" style={{ fontSize: '10px' }}>
                👁 {foto.diagnostics.closed_eyes_count} Cerrados
              </span>
            )}
            {foto.diagnostics.smiling_count > 0 && (
              <span className="gf-badge gf-badge-pick" style={{ fontSize: '10px' }}>
                🙂 {foto.diagnostics.smiling_count} Sonriendo
              </span>
            )}
          </div>
        )}

        {/* Razones Textuales */}
        {Array.isArray(foto.reasons) && foto.reasons.length > 0 && (
          <div style={{ padding: '12px', backgroundColor: 'var(--color-surface-elevated)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-default)' }}>
            <div style={{ fontSize: '10px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '8px', fontWeight: 'var(--fw-bold)' }}>Diagnóstico</div>
            {foto.reasons.map((r: string, i: number) => (
              <div key={i} style={{
                fontSize: '11px',
                marginBottom: '4px',
                color: r.startsWith('✔') ? 'var(--success)'
                     : r.startsWith('✖') ? 'var(--danger)' : 'var(--text-secondary)',
                lineHeight: 1.4
              }}>{r}</div>
            ))}
          </div>
        )}

        {/* EXIF */}
        {filas.length > 0 && (
          <div>
            <div style={{ fontSize: '10px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '10px', fontWeight: 'var(--fw-bold)' }}>
              Datos de Toma
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {filas.map(([clave, texto]) => (
                <div key={clave} className="flex-between" style={{ fontSize: '11px' }}>
                  <span style={{ color: 'var(--text-tertiary)' }}>{texto}</span>
                  <span className="font-mono" style={{ color: 'var(--text-primary)', fontWeight: 'var(--fw-medium)' }}>{exif[clave]}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Storyline Reassignment */}
        {chapters.length > 0 && (
          <div>
            <div style={{ fontSize: '10px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '8px', fontWeight: 'var(--fw-bold)' }}>
              Momento (Storyline)
            </div>
            <select
              disabled={moving}
              onChange={(e) => {
                if (e.target.value) handleOverrideChapter(e.target.value);
              }}
              value={chapters.find(c => c.paths?.includes(foto.path))?.id || ''}
              style={{
                width: '100%',
                padding: '8px 10px',
                backgroundColor: 'var(--color-bg)',
                color: 'var(--text-primary)',
                border: '1px solid var(--border-default)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '11px',
                outline: 'none'
              }}
            >
              <option value="" disabled>Selecciona momento...</option>
              {chapters.map(ch => (
                <option key={ch.id} value={ch.id}>{ch.name || ch.id}</option>
              ))}
            </select>
          </div>
        )}

      </div>
    </div>
  );
}
