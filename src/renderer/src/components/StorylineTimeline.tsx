import React, { useState, useEffect, useRef } from 'react';
import { apiClient } from '../api/client';

import { StorylineChapter } from '../types/api';

interface StorylineTimelineProps {
  directory?: string;
  onSelectChapter?: (chapter: StorylineChapter | null) => void;
}

export default function StorylineTimeline({ directory, onSelectChapter }: StorylineTimelineProps) {
  const [chapters, setChapters] = useState<StorylineChapter[]>([]);
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
      padding: '10px 24px',
      backgroundColor: 'var(--color-bg)',
      borderBottom: '1px solid var(--border-default)',
      display: 'flex',
      alignItems: 'center',
      gap: '14px',
      overflowX: 'auto'
    }}>
      <datalist id="storyline-vocabulary">
        {vocabulary.map(term => (
          <option key={term} value={term} />
        ))}
      </datalist>

      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
        <span style={{ fontSize: '10px', fontWeight: 'var(--fw-bold)', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          STORYLINE:
        </span>
      </div>

      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', overflowX: 'auto', paddingBottom: '2px' }}>
        {chapters.map((ch, idx) => {
          const isSelected = selectedId === ch.id;
          const isEditing = editingId === ch.id;
          const isBroll = ch.is_broll;

          return (
            <div
              key={ch.id}
              onClick={() => {
                if (!isEditing) {
                  if (isSelected) {
                    setSelectedId(null);
                    if (onSelectChapter) onSelectChapter(null);
                  } else {
                    setSelectedId(ch.id);
                    if (onSelectChapter) onSelectChapter(ch);
                  }
                }
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '4px 8px 4px 5px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: isSelected ? 'var(--color-surface-elevated)' : 'var(--color-surface)',
                border: '1px solid',
                borderColor: isSelected ? 'var(--accent-primary)' : 'var(--border-default)',
                boxShadow: isSelected ? '0 0 10px var(--accent-glow)' : 'var(--shadow-card)',
                cursor: isEditing ? 'default' : 'pointer',
                transition: 'all var(--transition-fast)',
                flexShrink: 0,
                opacity: selectedId && !isSelected ? 0.5 : 1
              }}
            >
              <img
                src={apiClient.getStorylineUrl(ch.medoid_thumb)}
                alt="Medoid"
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: 'var(--radius-photo)',
                  objectFit: 'cover'
                }}
                onError={(e) => { (e.target as HTMLElement).style.display = 'none'; }}
              />
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
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
                      fontSize: '11px',
                      fontWeight: 600,
                      color: 'var(--text-primary)',
                      backgroundColor: 'var(--color-bg)',
                      border: '1px solid var(--border-focus)',
                      borderRadius: 'var(--radius-xs)',
                      padding: '1px 4px',
                      outline: 'none',
                      width: '100px'
                    }}
                  />
                ) : (
                  <div className="flex items-center gap-1.5">
                    {isBroll && (
                      <span style={{ fontSize: '10px' }} title="B-Roll / Detalles">🎬</span>
                    )}
                    <span 
                      onDoubleClick={(e) => {
                        e.stopPropagation();
                        setEditValue(ch.name || `Momento ${idx + 1}`);
                        setEditingId(ch.id);
                      }}
                      style={{
                        fontSize: '11px',
                        fontWeight: 'var(--fw-semibold)',
                        color: isSelected ? 'var(--accent-primary)' : 'var(--text-primary)',
                        cursor: 'text'
                      }}
                      title="Doble clic para renombrar"
                    >
                      {ch.name || `Momento ${idx + 1}`}
                    </span>
                  </div>
                )}
                <span className="font-mono" style={{ fontSize: '10px', color: 'var(--text-tertiary)' }}>
                  {ch.start_time} - {ch.end_time} ({ch.photo_count})
                </span>
              </div>
            </div>
          );
        })}

        {selectedId && (
          <button
            onClick={() => {
              setSelectedId(null);
              if (onSelectChapter) onSelectChapter(null);
            }}
            style={{
              padding: '4px 10px',
              fontSize: '10px',
              fontWeight: 'var(--fw-semibold)',
              color: 'var(--text-secondary)',
              backgroundColor: 'transparent',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-sm)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              whiteSpace: 'nowrap',
              flexShrink: 0,
              transition: 'all var(--transition-fast)'
            }}
            title="Ver todas las fotos del evento"
          >
            ✕ Ver todo
          </button>
        )}
      </div>
    </div>
  );
}
