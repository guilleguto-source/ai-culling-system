import React, { useState, useMemo } from 'react';
import PhotoDetail from './PhotoDetail';

// Etiquetas legibles. Las claves internas (selected, duplicates…) NO se tocan:
// están cableadas al mapeo de estrellas y al XMP.
const ETIQUETA: Record<string, string> = {
  selected: 'Elegida',
  highlighted: 'Destacada',
  duplicates: 'Repetida',
  closed_eyes: 'Ojos cerrados',
  blurry: 'Descartada',
};

const FILTROS: [string, string, (r: any) => boolean][] = [
  ['todas', 'Todas', () => true],
  ['elegidas', 'Elegidas', r => r.label === 'selected' || r.label === 'highlighted'],
  ['repetidas', 'Repetidas', r => r.label === 'duplicates'],
  ['descartes', 'Descartes', r => r.label === 'blurry' || r.label === 'closed_eyes'],
  ['dudosas', 'Dudosas', r => (r.margin ?? 1) < 0.05],
];

export default function GridView({ results }: { results: any[] }) {
  const [filtro, setFiltro] = useState('todas');
  const [detalle, setDetalle] = useState<any>(null);
  if (!results || results.length === 0) return null;

  const visibles = useMemo(() => {
    const f = FILTROS.find(([k]) => k === filtro)?.[2] || (() => true);
    return results.filter(f);
  }, [results, filtro]);

  const cuenta = (fn: (r: any) => boolean) => results.filter(fn).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Filtros: barrer miles de fotos sin scroll infinito. "Dudosas" son las
          decisiones reñidas — revisar 30 de esas rinde más que revisarlas todas. */}
      <div style={{
        display: 'flex', gap: '8px', padding: '12px 16px', flexWrap: 'wrap',
        borderBottom: '1px solid var(--border-subtle)',
      }}>
        {FILTROS.map(([clave, texto, fn]) => {
          const n = cuenta(fn);
          return (
            <button
              key={clave}
              className={filtro === clave ? 'btn btn-primary' : 'btn btn-secondary'}
              style={{ fontSize: '0.78rem', padding: '5px 12px' }}
              onClick={() => setFiltro(clave)}
              disabled={n === 0 && clave !== 'todas'}
            >
              {texto} <span style={{ opacity: 0.6 }}>{n}</span>
            </button>
          );
        })}
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', padding: '16px',
        flex: 1, overflowY: 'auto', alignContent: 'flex-start' }}>
        {visibles.map((img, i) => {
          const descartada = img.label === 'blurry' || img.label === 'closed_eyes';
          const elegida = img.label === 'selected' || img.label === 'highlighted';
          return (
            <div key={i} className="glass-panel" onClick={() => setDetalle(img)}
              style={{ cursor: 'pointer',
              width: '220px', overflow: 'hidden', display: 'flex', flexDirection: 'column',
              // Jerarquía visual: la vista se recorre de un vistazo.
              opacity: descartada ? 0.45 : 1,
              border: elegida ? '2px solid var(--status-selected-text)' : '2px solid transparent',
            }}>
              <div style={{ width: '100%', aspectRatio: '3 / 4', backgroundColor: '#000', position: 'relative' }}>
                <img
                  src={`http://127.0.0.1:8000/thumbnail?path=${encodeURIComponent(img.path)}`}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  alt={img.filename}
                  title={Array.isArray(img.reasons) ? img.reasons.join('\n') : undefined}
                />
                {img.label && (
                  <div style={{
                    position: 'absolute', top: 8, right: 8,
                    backgroundColor: `var(--status-${img.label.replace('_', '-')}-bg)`,
                    color: `var(--status-${img.label.replace('_', '-')}-text)`,
                    padding: '3px 7px', borderRadius: '4px', fontSize: '0.65rem', fontWeight: 600,
                  }}>
                    {ETIQUETA[img.label] || img.label}
                  </div>
                )}
                {img.has_crop && (
                  <div title="Reencuadre propuesto — editable en Lightroom" style={{
                    position: 'absolute', bottom: '6px', right: '6px',
                    backgroundColor: 'rgba(0,0,0,0.6)', borderRadius: '4px',
                    padding: '2px 6px', fontSize: '0.75rem',
                  }}>✂</div>
                )}
              </div>
              <div style={{ padding: '10px 12px', fontSize: '0.8rem' }}>
                <div style={{ color: 'var(--text-primary)', whiteSpace: 'nowrap',
                  overflow: 'hidden', textOverflow: 'ellipsis', marginBottom: '4px' }}>
                  {img.filename}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)' }}>
                  <span>{img.scene_type === 'portrait' ? 'Retrato' : 'Detalle'}</span>
                  <span>Nitidez {Math.round(Math.min(1, (img.blur_score || 0) / 500) * 100)}%</span>
                </div>
                {img.score != null && (
                  <div title={`Score ${img.score.toFixed(2)} — comparable dentro de la ráfaga`}
                    style={{ height: '3px', borderRadius: '2px', marginTop: '6px',
                      backgroundColor: 'var(--bg-tertiary)', overflow: 'hidden' }}>
                    <div style={{
                      width: `${Math.round(Math.min(1, img.score) * 100)}%`, height: '100%',
                      backgroundColor: elegida ? 'var(--status-selected-text)' : 'var(--text-muted)',
                    }} />
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {detalle && <PhotoDetail foto={detalle} onClose={() => setDetalle(null)} />}
    </div>
  );
}
