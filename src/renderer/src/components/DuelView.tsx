import React, { useState, useMemo, useEffect } from 'react';
import Loupe from './Loupe';
import FaceGridAlignment from './FaceGridAlignment';
import { apiClient } from '../api/client';

const TITULO_ELEGIDA: Record<string, string> = {
  gate: 'Elegida por la IA (única sin defectos)',
  gusto: 'Elegida por la IA (tu criterio aprendido)',
  score: 'Elegida por la IA (mejor score)',
  vlm: 'Elegida por la IA (desempate VLM)',
  elo: 'Elegida por la IA (desempate ELO en RAM)',
};

const leerPref = (clave: string, porDefecto: number) => {
  const v = Number(localStorage.getItem(clave));
  return Number.isFinite(v) && v > 0 ? v : porDefecto;
};

export default function DuelView({ results }: { results: any[] }) {
  if (!results || results.length === 0) return null;

  const clusters = useMemo(() => {
    const map = new Map<number, any[]>();
    for (const img of results) {
      if (!map.has(img.cluster_id)) {
        map.set(img.cluster_id, []);
      }
      map.get(img.cluster_id)!.push(img);
    }
    return Array.from(map.values()).filter(group => group.length > 1);
  }, [results]);

  const [currentClusterIdx, setCurrentClusterIdx] = useState(0);
  const [learnedOverrides, setLearnedOverrides] = useState<Record<number, string>>({});
  const [isLearning, setIsLearning] = useState(false);
  const [showFaceGrid, setShowFaceGrid] = useState(true);

  const [cols, setCols] = useState(() => leerPref('duelCols', 2));
  const [rowH, setRowH] = useState(() => leerPref('duelRowH', 75));
  useEffect(() => { localStorage.setItem('duelCols', String(cols)); }, [cols]);
  useEffect(() => { localStorage.setItem('duelRowH', String(rowH)); }, [rowH]);

  if (clusters.length === 0) {
    return (
      <div className="flex-center" style={{ height: '100%', color: 'var(--text-muted)' }}>
        No hay ráfagas para comparar.
      </div>
    );
  }

  const currentGroup = clusters[currentClusterIdx];
  const clusterId = currentGroup[0].cluster_id;

  const representative = currentGroup.find(img => img.path === learnedOverrides[clusterId])
    || currentGroup.find(img => img.is_cluster_representative)
    || currentGroup[0];

  const ordered = [
    representative,
    ...currentGroup
      .filter(img => img !== representative)
      .sort((a, b) => (b.score ?? 0) - (a.score ?? 0)),
  ];

  const [approved, setApproved] = useState<Record<number, boolean>>({});
  const handleApprove = async () => {
    const rival = ordered.find(img => img !== representative);
    if (!rival) return;
    setIsLearning(true);
    try {
      await apiClient.learnPreference(representative.path, rival.path);
      setApproved(prev => ({ ...prev, [clusterId]: true }));
    } catch (e) {
      console.error('Error approving:', e);
    } finally {
      setIsLearning(false);
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT') return;
      if (e.key === 'ArrowRight') {
        e.preventDefault();
        setCurrentClusterIdx(c => Math.min(c + 1, clusters.length - 1));
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        setCurrentClusterIdx(c => Math.max(c - 1, 0));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        handleApprove();
      } else if (e.key === 'f' || e.key === 'F') {
        e.preventDefault();
        setShowFaceGrid(prev => !prev);
      } else if (/^[1-9]$/.test(e.key)) {
        const elegida = ordered[Number(e.key) - 1];
        if (elegida && elegida !== representative) {
          e.preventDefault();
          handleLearnPreference(elegida);
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const handleLearnPreference = async (alt: any) => {
    const target = typeof alt === 'string' ? ordered.find(img => img.path === alt) : alt;
    if (!target || target.path === representative.path) return;
    setIsLearning(true);
    try {
      await apiClient.learnPreference(target.path, representative.path);
      setLearnedOverrides(prev => ({ ...prev, [clusterId]: target.path }));
    } catch (e) {
      console.error("Error learning preference:", e);
    } finally {
      setIsLearning(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: '12px 16px', overflow: 'hidden' }}>
      
      {/* Duel Header */}
      <div className="flex-between glass-panel" style={{ padding: '10px 20px', marginBottom: '10px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <h3 style={{ margin: 0, fontSize: '1.05rem' }}>Comparar la ráfaga</h3>
          <button
            className={showFaceGrid ? 'btn btn-primary' : 'btn btn-secondary'}
            style={{ padding: '4px 10px', fontSize: '0.75rem' }}
            onClick={() => setShowFaceGrid(v => !v)}
            title="Atajo: tecla [F]"
          >
            👁️ Caras [F]
          </button>
        </div>

        {/* Controles de vista: columnas y tamaño dinámico de foto */}
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginLeft: 'auto', marginRight: '16px' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Columnas</span>
          {[2, 3, 4].map(n => (
            <button
              key={n}
              className={cols === n ? 'btn btn-primary' : 'btn btn-secondary'}
              style={{ padding: '4px 10px', fontSize: '0.78rem' }}
              onClick={() => setCols(n)}
            >
              {n}
            </button>
          ))}
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: '6px' }}
            title="Alto de las fotos: auméntalo para ver detalles en fotos verticales">
            Tamaño Foto
          </span>
          <input
            type="range" min={45} max={140} step={5} value={rowH}
            onChange={e => setRowH(Number(e.target.value))}
            style={{ width: '130px', accentColor: 'var(--accent-amber)' }}
          />
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <button 
            className="btn btn-secondary" 
            disabled={currentClusterIdx === 0}
            onClick={() => setCurrentClusterIdx(c => c - 1)}
          >
            Anterior
          </button>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'center' }}>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              {currentClusterIdx + 1} de {clusters.length}
            </span>
            <div style={{
              width: '100px', height: '4px', borderRadius: '2px',
              backgroundColor: 'var(--bg-tertiary)', overflow: 'hidden',
            }}>
              <div style={{
                width: `${((currentClusterIdx + 1) / clusters.length) * 100}%`,
                height: '100%', backgroundColor: 'var(--accent-primary)',
                transition: 'width 0.2s ease',
              }} />
            </div>
          </div>
          <button 
            className="btn btn-secondary" 
            disabled={currentClusterIdx === clusters.length - 1}
            onClick={() => setCurrentClusterIdx(c => c + 1)}
          >
            Siguiente
          </button>
        </div>
      </div>

      {/* Grilla Facial Alineada Side-by-Side */}
      {showFaceGrid && (
        <div style={{ marginBottom: '10px', flexShrink: 0 }}>
          <FaceGridAlignment
            clusterId={clusterId}
            selectedPhotoPath={representative.path}
            onSelectPhoto={(path) => handleLearnPreference(path)}
          />
        </div>
      )}

      {/* Arena de Comparación */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${Math.min(ordered.length, cols)}, 1fr)`,
        gridAutoRows: `minmax(420px, ${rowH}vh)`,
        gap: '16px',
        flex: 1,
        overflowY: 'auto',
        alignContent: 'start',
        paddingRight: '4px',
      }}>
        {ordered.map((img, i) => {
          const isSelected = img === representative;
          return (
            <div
              key={img.path}
              className="glass-panel"
              style={{
                display: 'flex',
                flexDirection: 'column',
                minHeight: 0,
                border: isSelected ? '2px solid var(--status-selected-text)' : '2px solid transparent',
                borderRadius: '8px',
                overflow: 'hidden',
              }}
            >
              <div style={{
                padding: '8px 12px',
                borderBottom: '1px solid var(--border-subtle)',
                color: isSelected ? 'var(--status-selected-text)' : 'var(--text-primary)',
                fontSize: '0.88rem',
                flexShrink: 0,
              }}>
                {isSelected
                  ? <strong>{TITULO_ELEGIDA[img.decided_by] || 'Elegida por la IA'}</strong>
                  : <strong>#{i + 1} · Alternativa</strong>}
              </div>

              {/* Visor de Foto */}
              <div style={{ flex: 1, minHeight: '300px', backgroundColor: '#050507', position: 'relative' }}>
                <Loupe
                  src={apiClient.getThumbnailUrl(img.path, 'duel')}
                  alt={img.filename}
                  style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
                />
              </div>

              <div className="flex-between" style={{ padding: '10px 12px', fontSize: '0.82rem', flexShrink: 0, background: 'rgba(0, 0, 0, 0.4)' }}>
                <div style={{ color: 'var(--text-secondary)' }}>
                  <div style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
                    {img.filename}
                    {img.has_crop && <span title="Reencuadre propuesto — editable en Lightroom"> ✂</span>}
                  </div>
                  <div>
                    {img.score != null && <>Score: {img.score.toFixed(2)} · </>}
                    Nitidez: {Math.round(Math.min(1, (img.blur_score || 0) / 500) * 100)}%
                  </div>
                  {Array.isArray(img.reasons) && img.reasons.length > 0 && (
                    <div style={{ marginTop: '4px', lineHeight: 1.4 }}>
                      {img.reasons.map((r: string, k: number) => (
                        <div key={k} style={{
                          fontSize: '0.74rem',
                          color: r.startsWith('✔') ? 'var(--status-selected-text)'
                               : r.startsWith('✖') ? 'var(--status-blurry-text)'
                               : 'var(--text-muted)',
                        }}>{r}</div>
                      ))}
                    </div>
                  )}
                  {img.label === 'blurry' && <div style={{ color: 'var(--status-blurry-text)' }}>Marked Blurry</div>}
                </div>
                {isSelected ? (
                  approved[clusterId] ? (
                    <span style={{ color: 'var(--status-selected-text)', fontSize: '0.8rem', fontWeight: 600 }}>✓ Aprobada</span>
                  ) : (
                    <button
                      className="btn btn-secondary"
                      style={{ fontSize: '0.8rem', padding: '6px 12px' }}
                      title="Confirmar que estás de acuerdo — también entrena el modelo"
                      onClick={handleApprove}
                      disabled={isLearning || ordered.length < 2}
                    >
                      Aprobar
                    </button>
                  )
                ) : (
                  <button
                    className="btn btn-primary"
                    style={{ fontSize: '0.8rem', padding: '6px 12px' }}
                    onClick={() => handleLearnPreference(img)}
                    disabled={isLearning}
                  >
                    Elegir esta
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
