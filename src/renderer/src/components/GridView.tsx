import React from 'react';

export default function GridView({ results }: { results: any[] }) {
  if (!results || results.length === 0) return null;

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', padding: '16px' }}>
      {results.map((img, i) => (
        <div key={i} className="glass-panel" style={{ width: '220px', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {/* Image Thumbnail via Backend Endpoint */}
          <div style={{ width: '100%', height: '150px', backgroundColor: '#000', position: 'relative' }}>
            <img 
              src={`http://127.0.0.1:8000/thumbnail?path=${encodeURIComponent(img.path)}`} 
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              alt={img.filename}
            />
            {/* Label Badge */}
            {img.label && (
              <div style={{ 
                position: 'absolute', top: 8, right: 8, 
                backgroundColor: `var(--status-${img.label.replace('_', '-')}-bg)`,
                color: `var(--status-${img.label.replace('_', '-')}-text)`,
                padding: '4px 8px', borderRadius: '4px', fontSize: '0.7rem', fontWeight: 'bold',
                textTransform: 'uppercase'
              }}>
                {img.label.replace('_', ' ')}
              </div>
            )}
          </div>
          <div style={{ padding: '12px', fontSize: '0.8rem' }}>
            <div style={{ color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginBottom: '4px' }}>
              {img.filename}
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)' }}>
              <span>{img.scene_type}</span>
              <span>Blur: {img.blur_score}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
