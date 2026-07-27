import React, { useState, useEffect } from 'react';

interface Chapter {
  id: string;
  start_time: string;
  end_time: string;
  photo_count: number;
  medoid_thumb: string;
  medoid_path: string;
}

interface StorylineTimelineProps {
  directory?: string;
  onSelectChapter?: (chapter: Chapter) => void;
}

export default function StorylineTimeline({ directory, onSelectChapter }: StorylineTimelineProps) {
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    if (!directory) return;
    setLoading(true);
    fetch(`http://127.0.0.1:8000/storyline?gap=30`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && data.storyline) {
          setChapters(data.storyline);
        }
      })
      .catch((err) => console.error('Error cargando storyline:', err))
      .finally(() => setLoading(false));
  }, [directory]);

  if (!directory || chapters.length === 0) return null;

  return (
    <div style={{
      padding: '12px 24px',
      backgroundColor: 'var(--bg-primary)',
      borderBottom: '1px solid var(--border-subtle)',
      display: 'flex',
      alignItems: 'center',
      gap: '16px',
      overflowX: 'auto'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', shrink: 0 }}>
        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--accent-primary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          📖 Storyline:
        </span>
      </div>

      <div style={{ display: 'flex', gap: '12px', overflowX: 'auto', paddingBottom: '4px' }}>
        {chapters.map((ch, idx) => {
          const isSelected = selectedId === ch.id;
          return (
            <div
              key={ch.id}
              onClick={() => {
                setSelectedId(ch.id);
                if (onSelectChapter) onSelectChapter(ch);
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                padding: '6px 10px',
                borderRadius: 'var(--radius-md)',
                backgroundColor: isSelected ? 'var(--bg-tertiary)' : 'var(--bg-secondary)',
                border: isSelected ? '1px solid var(--accent-primary)' : '1px solid var(--border-subtle)',
                cursor: 'pointer',
                transition: 'all var(--transition-fast)',
                minWidth: '160px'
              }}
              className="glass-card"
            >
              <img
                src={`http://127.0.0.1:8000${ch.medoid_thumb}`}
                alt="Medoid"
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: 'var(--radius-sm)',
                  objectFit: 'cover'
                }}
                onError={(e) => { (e.target as HTMLElement).style.display = 'none'; }}
              />
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Capítulo {idx + 1}
                </span>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                  {ch.start_time} - {ch.end_time} ({ch.photo_count} fotos)
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
