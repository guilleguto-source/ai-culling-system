import React, { useState, useEffect, useRef } from 'react';
import { apiClient } from '../api/client';

interface Chapter {
  id: string;
  name?: string;
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
  
  const [vocabulary, setVocabulary] = useState<string[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState<string>('');
  
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    // Cargar el vocabulario de eventos
    apiClient.getStorylineVocabulary()
      .then(res => {
        if (res.vocabulary) setVocabulary(res.vocabulary);
      })
      .catch(err => console.error('Error cargando vocabulario:', err));
  }, []);

  useEffect(() => {
    if (!directory) return;
    setLoading(true);
    apiClient.getStoryline(directory)
      .then((data) => {
        if (data && data.storyline) {
          setChapters(data.storyline);
        }
      })
      .catch((err) => console.error('Error cargando storyline:', err))
      .finally(() => setLoading(false));
  }, [directory]);

  useEffect(() => {
    if (editingId && inputRef.current) {
      inputRef.current.focus();
    }
  }, [editingId]);

  const handleRenameSubmit = async (chapterId: string) => {
    if (!directory || !editValue.trim()) {
      setEditingId(null);
      return;
    }
    const newName = editValue.trim();
    
    // Update local state optimistic
    setChapters(prev => prev.map(ch => ch.id === chapterId ? { ...ch, name: newName } : ch));
    setEditingId(null);
    
    // Add to vocabulary if new
    if (!vocabulary.includes(newName)) {
      setVocabulary(prev => [...prev, newName]);
    }

    // Call backend
    try {
      await apiClient.renameStorylineChapter(directory, chapterId, newName);
    } catch (err) {
      console.error('Error renombrando capítulo:', err);
    }
  };

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
      <datalist id="storyline-vocabulary">
        {vocabulary.map(term => (
          <option key={term} value={term} />
        ))}
      </datalist>

      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
        <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--accent-primary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          📖 Storyline:
        </span>
      </div>

      <div style={{ display: 'flex', gap: '12px', overflowX: 'auto', paddingBottom: '4px' }}>
        {chapters.map((ch, idx) => {
          const isSelected = selectedId === ch.id;
          const isEditing = editingId === ch.id;

          return (
            <div
              key={ch.id}
              onClick={() => {
                if (!isEditing) {
                  setSelectedId(ch.id);
                  if (onSelectChapter) onSelectChapter(ch);
                }
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                padding: '6px 10px',
                borderRadius: 'var(--radius-md)',
                backgroundColor: isSelected ? 'var(--bg-tertiary)' : 'var(--bg-secondary)',
                border: isSelected ? '1px solid var(--accent-primary)' : '1px solid var(--border-subtle)',
                cursor: isEditing ? 'default' : 'pointer',
                transition: 'all var(--transition-fast)',
                minWidth: '160px'
              }}
              className="glass-card"
            >
              <img
                src={apiClient.getStorylineUrl(ch.medoid_thumb)}
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
                {isEditing ? (
                  <input
                    ref={inputRef}
                    list="storyline-vocabulary"
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    onBlur={() => handleRenameSubmit(ch.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleRenameSubmit(ch.id);
                      if (e.key === 'Escape') setEditingId(null);
                    }}
                    style={{
                      fontSize: '0.78rem',
                      fontWeight: 600,
                      color: 'var(--text-primary)',
                      backgroundColor: 'var(--bg-primary)',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: '4px',
                      padding: '2px 4px',
                      outline: 'none',
                      width: '100px'
                    }}
                  />
                ) : (
                  <span 
                    onDoubleClick={(e) => {
                      e.stopPropagation();
                      setEditValue(ch.name || `Momento ${idx + 1}`);
                      setEditingId(ch.id);
                    }}
                    style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-primary)', cursor: 'text' }}
                    title="Doble clic para renombrar"
                  >
                    {ch.name || `Momento ${idx + 1}`}
                  </span>
                )}
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
