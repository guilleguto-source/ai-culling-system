import React, { useState, useMemo, useEffect } from 'react';
import InspectorPanel from './inspector/InspectorPanel';
import { getDynamicStyles } from '../utils/dynamicStyles';

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
  const [learningPhoto, setLearningPhoto] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [semanticPaths, setSemanticPaths] = useState<Set<string> | null>(null);

  useEffect(() => {
    const handleKeyDown = async (e: KeyboardEvent) => {
      if (!detalle) return;
      if ((e.target as HTMLElement)?.tagName === 'INPUT') return;

      const key = e.key.toLowerCase();
      if (['a', 'p', 'd', 'x'].includes(key)) {
        e.preventDefault();
        
        const isApprove = key === 'a' || key === 'p';
        setLearningPhoto(detalle.path);
        
        const clusterPhotos = results.filter(r => r.cluster_id === detalle.cluster_id);
        const rival = clusterPhotos.find(r => r.path !== detalle.path);
        
        if (rival) {
          try {
            await fetch('http://127.0.0.1:8000/learn_preference', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                winner_path: isApprove ? detalle.path : rival.path,
                loser_path: isApprove ? rival.path : detalle.path,
              })
            });
            
            detalle.label = isApprove ? 'selected' : 'blurry';
            setDetalle({ ...detalle });
          } catch (err) {
            console.error('Error learning preference:', err);
          }
        }
        setLearningPhoto(null);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [detalle, results]);

  useEffect(() => {
    if (!searchQuery.trim()) {
      setSemanticPaths(null);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const firstPath = results[0]?.path || '';
        const dir = firstPath.substring(0, Math.max(firstPath.lastIndexOf('\\'), firstPath.lastIndexOf('/')));
        
        const r = await fetch(`http://127.0.0.1:8000/search/semantic?q=${encodeURIComponent(searchQuery)}&directory=${encodeURIComponent(dir)}`);
        if (r.ok) {
          const data = await r.json();
          setSemanticPaths(new Set(data.results.map((x: any) => x.path)));
        }
      } catch (e) {
        console.error('Semantic search error', e);
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [searchQuery, results]);

  if (!results || results.length === 0) return null;

  const visibles = useMemo(() => {
    const f = FILTROS.find(([k]) => k === filtro)?.[2] || (() => true);
    let arr = results.filter(f);
    if (semanticPaths) {
      arr = arr.filter(r => semanticPaths.has(r.path));
    }
    return arr;
  }, [results, filtro, semanticPaths]);

  const cuenta = (fn: (r: any) => boolean) => results.filter(fn).length;

  return (
    <div style={{ display: 'flex', width: '100%', height: '100%', overflow: 'hidden' }}>
      <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 0 }}>
        <div style={{
          display: 'flex', gap: '8px', padding: '12px 16px', flexWrap: 'wrap',
          borderBottom: '1px solid var(--border-subtle)', alignItems: 'center'
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
          
          <div style={{ flex: 1 }} />
          <input 
            type="text" 
            placeholder="🔍 Buscar escena..." 
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            style={{ 
              padding: '6px 12px', borderRadius: 'var(--radius-sm)', 
              border: '1px solid var(--border-strong)', background: 'var(--bg-deep)', 
              color: 'var(--text-primary)', fontSize: '0.8rem', outline: 'none', width: '200px'
            }}
          />
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
                opacity: descartada ? 0.45 : 1,
                border: elegida ? '2px solid var(--status-selected-text)' : '2px solid transparent',
              }}>
                <div style={{ width: '100%', aspectRatio: '3 / 4', backgroundColor: '#000', position: 'relative' }}>
                  <img
                    src={`http://127.0.0.1:8000/thumbnail?path=${encodeURIComponent(img.path)}`}
                    style={{ width: '100%', height: '100%', objectFit: 'cover', ...getDynamicStyles(img) }}
                    alt={img.filename}
                    title={Array.isArray(img.reasons) ? img.reasons.join('\n') : undefined}
                  />
                  {img.label && (
                    <div style={{
                      position: 'absolute', top: 8, left: 8,
                      backgroundColor: `var(--status-${img.label.replace('_', '-')}-bg)`,
                      color: `var(--status-${img.label.replace('_', '-')}-text)`,
                      border: `1px solid var(--status-${img.label.replace('_', '-')}-border)`,
                      padding: '3px 7px', borderRadius: 'var(--radius-sm)', fontSize: '0.65rem', fontWeight: 600,
                      backdropFilter: 'blur(4px)',
                      textTransform: 'uppercase'
                    }}>
                      {ETIQUETA[img.label] || img.label}
                    </div>
                  )}
                  {img.score !== undefined && (
                    <div style={{
                      position: 'absolute', top: 8, right: 8,
                      width: '28px', height: '28px', borderRadius: '50%',
                      backgroundColor: 'var(--bg-elevated)', border: '2px solid var(--accent-amber)',
                      color: 'var(--text-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: '0.7rem', fontWeight: 700, backdropFilter: 'blur(4px)'
                    }}>
                      {(img.score * 10).toFixed(1)}
                    </div>
                  )}
                  {img.has_crop && (
                    <div title="Reencuadre propuesto" style={{
                      position: 'absolute', bottom: '6px', right: '6px',
                      backgroundColor: 'rgba(0,0,0,0.6)', borderRadius: '4px',
                      padding: '2px 6px', fontSize: '0.75rem',
                    }}>✂</div>
                  )}
                  {learningPhoto === img.path && (
                    <div style={{
                      position: 'absolute', inset: 0,
                      backgroundColor: 'rgba(232, 146, 60, 0.2)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      backdropFilter: 'blur(2px)'
                    }}>
                      <span style={{ color: 'var(--accent-amber)', fontSize: '2rem' }}>✓</span>
                    </div>
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
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {detalle && <InspectorPanel foto={detalle} onClose={() => setDetalle(null)} />}
    </div>
  );
}
