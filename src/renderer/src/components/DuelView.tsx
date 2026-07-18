import React, { useState, useMemo, useEffect } from 'react';

// El título dice QUIÉN decidió. Antes afirmaba siempre "mejor score", que es
// falso cuando gana por un gate técnico (la elegida puede tener score menor).
const TITULO_ELEGIDA: Record<string, string> = {
  gate: 'Elegida por la IA (única sin defectos)',
  gusto: 'Elegida por la IA (tu criterio aprendido)',
  score: 'Elegida por la IA (mejor score)',
};

// Preferencias de vista del duelo, recordadas entre sesiones.
const leerPref = (clave: string, porDefecto: number) => {
  const v = Number(localStorage.getItem(clave));
  return Number.isFinite(v) && v > 0 ? v : porDefecto;
};

export default function DuelView({ results }: { results: any[] }) {
  if (!results || results.length === 0) return null;

  // Group by cluster_id
  const clusters = useMemo(() => {
    const map = new Map<number, any[]>();
    for (const img of results) {
      if (!map.has(img.cluster_id)) {
        map.set(img.cluster_id, []);
      }
      map.get(img.cluster_id)!.push(img);
    }
    return Array.from(map.values()).filter(group => group.length > 1); // Only groups with > 1 img
  }, [results]);

  const [currentClusterIdx, setCurrentClusterIdx] = useState(0);
  const [learnedOverrides, setLearnedOverrides] = useState<Record<number, string>>({});
  const [isLearning, setIsLearning] = useState(false);

  // Columnas y alto de fila. En fotos verticales lo que agranda la imagen es el
  // ALTO de la celda (el ancho sobrante se va en barras negras), por eso el
  // tamaño se regula aparte de las columnas.
  const [cols, setCols] = useState(() => leerPref('duelCols', 2));
  const [rowH, setRowH] = useState(() => leerPref('duelRowH', 62));
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

  // La elegida primero; el resto por score de la IA (mejor calificadas antes),
  // así las 4 primeras — las visibles sin scroll — son las que importan.
  const ordered = [
    representative,
    ...currentGroup
      .filter(img => img !== representative)
      .sort((a, b) => (b.score ?? 0) - (a.score ?? 0)),
  ];

  // Aprobar: hasta ahora solo aprendíamos cuando el usuario CORREGÍA; si estaba
  // de acuerdo, esa señal se perdía. Confirmar genera el par positivo
  // (elegida > mejor alternativa), que es la mitad del aprendizaje que faltaba.
  const [approved, setApproved] = useState<Record<number, boolean>>({});
  const handleApprove = async () => {
    const rival = ordered.find(img => img !== representative);
    if (!rival) return;
    setIsLearning(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/learn_preference', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ winner_path: representative.path, loser_path: rival.path }),
      });
      if (res.ok) setApproved(prev => ({ ...prev, [clusterId]: true }));
    } catch (e) {
      console.error('Error approving:', e);
    } finally {
      setIsLearning(false);
    }
  };

  // Atajos: cullear con teclado es mucho más rápido que con el mouse.
  // 1-9 elegir alternativa · ←/→ navegar · Enter aprobar.
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
    setIsLearning(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/learn_preference', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          winner_path: alt.path,
          loser_path: representative.path
        })
      });
      if (res.ok) {
        setLearnedOverrides(prev => ({ ...prev, [clusterId]: alt.path }));
      }
    } catch (e) {
      console.error("Error learning preference:", e);
    } finally {
      setIsLearning(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: '16px' }}>
      
      {/* Duel Header */}
      <div className="flex-between glass-panel" style={{ padding: '12px 24px', marginBottom: '16px' }}>
        <h3 style={{ margin: 0 }}>Comparar la ráfaga</h3>

        {/* Controles de vista: cuántas por fila y qué tan grandes */}
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
            title="Alto de cada foto: subilo para ver detalle (foco, ojos)">
            Tamaño
          </span>
          <input
            type="range" min={35} max={110} step={5} value={rowH}
            onChange={e => setRowH(Number(e.target.value))}
            style={{ width: '110px' }}
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
          {/* Progreso: cuánto falta para terminar de revisar el evento */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', alignItems: 'center' }}>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              {currentClusterIdx + 1} de {clusters.length}
            </span>
            <div style={{
              width: '120px', height: '4px', borderRadius: '2px',
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

      {/* Arena — ordenadas por score: las mejores entran primero. Columnas y
          alto los elige el usuario. Filas de alto fijo: si no, con muchas fotos
          el grid las aplasta en vez de desbordar y no habría scroll. */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${Math.min(ordered.length, cols)}, 1fr)`,
        gridAutoRows: `minmax(0, ${rowH}vh)`,
        gap: '16px',
        flex: 1,
        overflowY: 'auto',
        alignContent: 'start',
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
              }}
            >
              <div style={{
                padding: '12px',
                borderBottom: '1px solid var(--border-subtle)',
                color: isSelected ? 'var(--status-selected-text)' : 'var(--text-primary)',
              }}>
                {isSelected
                  ? <strong>{TITULO_ELEGIDA[img.decided_by] || 'Elegida por la IA'}</strong>
                  : <strong>#{i + 1} · Alternativa</strong>}
              </div>
              <div style={{ flex: 1, minHeight: 0, backgroundColor: '#000' }}>
                <img
                  src={`http://127.0.0.1:8000/thumbnail?path=${encodeURIComponent(img.path)}&size=duel`}
                  style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
                  alt={img.filename}
                />
              </div>
              <div className="flex-between" style={{ padding: '12px', fontSize: '0.85rem' }}>
                <div style={{ color: 'var(--text-secondary)' }}>
                  <div style={{ color: 'var(--text-primary)' }}>
                    {img.filename}
                    {img.has_crop && <span title="Reencuadre propuesto — editable en Lightroom"> ✂</span>}
                  </div>
                  <div>
                    {img.score != null && <>Score: {img.score.toFixed(2)} · </>}
                    Nitidez: {Math.round(Math.min(1, (img.blur_score || 0) / 500) * 100)}%
                  </div>
                  {/* Por qué ganó o perdió: hechos medidos, no adjetivos. */}
                  {Array.isArray(img.reasons) && img.reasons.length > 0 && (
                    <div style={{ marginTop: '4px', lineHeight: 1.5 }}>
                      {img.reasons.map((r: string, k: number) => (
                        <div key={k} style={{
                          fontSize: '0.75rem',
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
                    <span style={{ color: 'var(--status-selected-text)', fontSize: '0.8rem' }}>✓ Aprobada</span>
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
