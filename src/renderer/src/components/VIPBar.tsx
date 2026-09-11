import React, { useState, useEffect, useRef } from 'react';
import { apiClient } from '../api/client';
import { VIPSubject } from '../types/api';

interface VIPBarProps {
  directory?: string;
  activeVIPIds: Set<number>;
  onToggleVIP: (identityId: number) => void;
  onClearVIPs: () => void;
}

export const VIPBar: React.FC<VIPBarProps> = ({
  directory,
  activeVIPIds,
  onToggleVIP,
  onClearVIPs
}) => {
  const [subjects, setSubjects] = useState<VIPSubject[]>([]);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editValue, setEditValue] = useState<string>('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!directory) {
      setSubjects([]);
      return;
    }

    apiClient
      .getVIPSubjects(directory)
      .then((res) => {
        if (res && Array.isArray(res.subjects)) {
          setSubjects(res.subjects);
        }
      })
      .catch((err) => {
        console.error('Error cargando VIP subjects:', err);
      });
  }, [directory]);

  useEffect(() => {
    if (editingId !== null && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingId]);

  const handleStartRename = (s: VIPSubject, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(s.id);
    setEditValue(s.name);
  };

  const handleSaveRename = async (identityId: number) => {
    const trimmed = editValue.trim();
    if (!directory || !trimmed) {
      setEditingId(null);
      return;
    }

    setSubjects((prev) =>
      prev.map((item) => (item.id === identityId ? { ...item, name: trimmed } : item))
    );
    setEditingId(null);

    try {
      await apiClient.renameVIPSubject(directory, identityId, trimmed);
    } catch (err) {
      console.error('Error renombrando personaje VIP:', err);
    }
  };

  if (!directory || subjects.length === 0) {
    return null;
  }

  const hasFilterActive = activeVIPIds.size > 0;

  return (
    <div
      style={{
        padding: '8px 24px',
        backgroundColor: 'var(--color-bg)',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        overflowX: 'auto'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
        <span
          style={{
            fontSize: 'var(--text-xs)',
            fontWeight: 'var(--fw-bold)',
            color: 'var(--accent-primary)',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            display: 'flex',
            alignItems: 'center',
            gap: '4px'
          }}
        >
          <span>👑</span> Personajes Principales:
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flex: 1, overflowX: 'auto' }}>
        {subjects.map((sub, idx) => {
          const isActive = activeVIPIds.has(sub.id);
          const isEditing = editingId === sub.id;

          return (
            <div
              key={sub.id}
              onClick={() => {
                if (!isEditing) onToggleVIP(sub.id);
              }}
              title="Clic para filtrar fotos de este personaje. Doble clic para renombrar."
              onDoubleClick={(e) => handleStartRename(sub, e)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '4px 10px',
                borderRadius: 'var(--radius-pill)',
                backgroundColor: isActive ? 'rgba(231, 161, 58, 0.12)' : 'var(--color-surface-elevated)',
                border: isActive ? '1px solid var(--accent-primary)' : '1px solid var(--border-default)',
                cursor: isEditing ? 'default' : 'pointer',
                boxShadow: isActive ? 'var(--shadow-glow-amber)' : 'none',
                transition: 'all var(--transition-fast)',
                userSelect: 'none',
                flexShrink: 0
              }}
            >
              {sub.representative_thumb && (
                <img
                  src={apiClient.getStorylineUrl(sub.representative_thumb)}
                  alt={sub.name}
                  style={{
                    width: '24px',
                    height: '24px',
                    borderRadius: '50%',
                    objectFit: 'cover',
                    border: isActive ? '1px solid var(--accent-primary)' : '1px solid var(--border-subtle)'
                  }}
                  onError={(e) => {
                    (e.target as HTMLElement).style.display = 'none';
                  }}
                />
              )}

              {isEditing ? (
                <input
                  ref={inputRef}
                  type="text"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onBlur={() => handleSaveRename(sub.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSaveRename(sub.id);
                    if (e.key === 'Escape') setEditingId(null);
                  }}
                  style={{
                    fontSize: 'var(--text-xs)',
                    fontWeight: 'var(--fw-bold)',
                    color: 'var(--text-primary)',
                    backgroundColor: 'var(--color-bg)',
                    border: '1px solid var(--accent-primary)',
                    borderRadius: 'var(--radius-xs)',
                    padding: '2px 6px',
                    outline: 'none',
                    width: '100px'
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <span
                  style={{
                    fontSize: 'var(--text-xs)',
                    fontWeight: 'var(--fw-bold)',
                    color: isActive ? 'var(--accent-primary)' : 'var(--text-primary)'
                  }}
                >
                  {sub.name || `Personaje ${idx + 1}`}
                </span>
              )}

              <span
                style={{
                  fontSize: '10px',
                  fontFamily: 'var(--font-mono)',
                  color: isActive ? 'var(--accent-primary)' : 'var(--text-tertiary)',
                  backgroundColor: isActive ? 'rgba(231, 161, 58, 0.2)' : 'rgba(255, 255, 255, 0.04)',
                  padding: '1px 5px',
                  borderRadius: 'var(--radius-pill)'
                }}
              >
                ×{sub.count}
              </span>
            </div>
          );
        })}

        {hasFilterActive && (
          <button
            onClick={onClearVIPs}
            style={{
              padding: '3px 8px',
              fontSize: '11px',
              color: 'var(--text-tertiary)',
              backgroundColor: 'transparent',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              borderRadius: 'var(--radius-sm)',
              transition: 'color var(--transition-fast)'
            }}
            onMouseEnter={(e) => ((e.target as HTMLElement).style.color = 'var(--text-primary)')}
            onMouseLeave={(e) => ((e.target as HTMLElement).style.color = 'var(--text-tertiary)')}
            title="Quitar filtro de personajes"
          >
            ✕ Limpiar filtro
          </button>
        )}
      </div>
    </div>
  );
};
export default VIPBar;
