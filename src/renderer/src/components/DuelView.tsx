import React, { useState, useMemo } from 'react';

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

  if (clusters.length === 0) {
    return (
      <div className="flex-center" style={{ height: '100%', color: 'var(--text-muted)' }}>
        No duplicates or groups found.
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
        <h3 style={{ margin: 0 }}>Cluster A/B Comparison</h3>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <button 
            className="btn btn-secondary" 
            disabled={currentClusterIdx === 0}
            onClick={() => setCurrentClusterIdx(c => c - 1)}
          >
            Previous Group
          </button>
          <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            {currentClusterIdx + 1} of {clusters.length}
          </span>
          <button 
            className="btn btn-secondary"
            disabled={currentClusterIdx === clusters.length - 1}
            onClick={() => setCurrentClusterIdx(c => c + 1)}
          >
            Next Group
          </button>
        </div>
      </div>

      {/* Arena — 4 por fila, ordenadas: las mejores entran sin scroll.
          Filas de alto fijo: si no, con muchas fotos el grid las aplasta
          en vez de desbordar y no habría nada que scrollear. */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${Math.min(ordered.length, 4)}, 1fr)`,
        gridAutoRows: 'minmax(0, 46vh)',
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
                  ? <strong>Elegida por la IA (mejor score)</strong>
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
                    Blur: {img.blur_score}
                  </div>
                  {img.label === 'blurry' && <div style={{ color: 'var(--status-blurry-text)' }}>Marked Blurry</div>}
                </div>
                {isSelected ? (
                  <span style={{ color: 'var(--status-selected-text)', fontSize: '0.8rem' }}>✓ Elegida</span>
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
