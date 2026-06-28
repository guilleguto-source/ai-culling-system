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

  if (clusters.length === 0) {
    return (
      <div className="flex-center" style={{ height: '100%', color: 'var(--text-muted)' }}>
        No duplicates or groups found.
      </div>
    );
  }

  const currentGroup = clusters[currentClusterIdx];
  const representative = currentGroup.find(img => img.is_cluster_representative) || currentGroup[0];
  const alternatives = currentGroup.filter(img => img !== representative);

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

      {/* Duel Arena */}
      <div style={{ display: 'flex', gap: '16px', flex: 1, overflow: 'hidden' }}>
        
        {/* Representative Image (Selected) */}
        <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '12px', borderBottom: '1px solid var(--border-subtle)', color: 'var(--status-selected-text)' }}>
            <strong>AI Selected</strong> (Best score)
          </div>
          <div style={{ flex: 1, position: 'relative', backgroundColor: '#000' }}>
            <img 
              src={`http://127.0.0.1:8000/thumbnail?path=${encodeURIComponent(representative.path)}`} 
              style={{ width: '100%', height: '100%', objectFit: 'contain' }}
              alt={representative.filename}
            />
          </div>
          <div style={{ padding: '12px', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
            Blur Score: {representative.blur_score}
          </div>
        </div>

        {/* Alternatives List */}
        <div className="glass-panel" style={{ width: '350px', display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>
          <div style={{ padding: '12px', borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-primary)' }}>
            <strong>Alternatives</strong> ({alternatives.length})
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1px', backgroundColor: 'var(--border-subtle)' }}>
            {alternatives.map((alt, i) => (
              <div key={i} style={{ display: 'flex', backgroundColor: 'var(--bg-elevated)', padding: '8px' }}>
                 <div style={{ width: '100px', height: '70px', flexShrink: 0, backgroundColor: '#000', marginRight: '12px' }}>
                   <img 
                      src={`http://127.0.0.1:8000/thumbnail?path=${encodeURIComponent(alt.path)}`} 
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      alt={alt.filename}
                    />
                 </div>
                 <div style={{ flex: 1, fontSize: '0.8rem', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                    <div style={{ color: 'var(--text-primary)', marginBottom: '4px' }}>{alt.filename}</div>
                    <div style={{ color: 'var(--status-blurry-text)' }}>Blur: {alt.blur_score}</div>
                    {alt.label === 'blurry' && <div style={{ color: 'var(--status-blurry-text)' }}>Marked Blurry</div>}
                 </div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
