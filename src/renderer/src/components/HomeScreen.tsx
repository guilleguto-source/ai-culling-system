import React, { useState, useEffect } from 'react';
import { IconFolder } from './icons';
import { Button } from './ui/Button';

interface RecentSession {
  path: string;
  name: string;
  date: string;
  totalPhotos?: number;
}

interface HomeScreenProps {
  onStartIngest: (directory: string, mode?: string) => void;
  undoAvailable?: boolean;
  onUndoExport?: (dir: string) => Promise<void>;
  lastDirectory?: string;
}

export const HomeScreen: React.FC<HomeScreenProps> = ({
  onStartIngest,
  undoAvailable = false,
  onUndoExport,
  lastDirectory = ''
}) => {
  const [isDragOver, setIsDragOver] = useState(false);
  const [selectedFolder, setSelectedFolder] = useState(lastDirectory);
  const [selectedMode, setSelectedMode] = useState<'cull_edit' | 'cull_only'>('cull_edit');
  const [recentSessions, setRecentSessions] = useState<RecentSession[]>([]);
  const [isUndoing, setIsUndoing] = useState(false);

  // Load recent sessions from localStorage
  useEffect(() => {
    try {
      const stored = localStorage.getItem('guto_recent_sessions');
      if (stored) {
        setRecentSessions(JSON.parse(stored));
      }
    } catch {
      // ignore
    }
  }, []);

  const saveRecentSession = (dir: string) => {
    try {
      const name = dir.replace(/\\/g, '/').split('/').filter(Boolean).pop() || dir;
      const newSession: RecentSession = {
        path: dir,
        name,
        date: new Date().toLocaleDateString()
      };
      const filtered = recentSessions.filter(s => s.path !== dir);
      const updated = [newSession, ...filtered].slice(0, 5);
      setRecentSessions(updated);
      localStorage.setItem('guto_recent_sessions', JSON.stringify(updated));
    } catch {
      // ignore
    }
  };

  const handleSelectFolder = async () => {
    if (window.api?.selectFolder) {
      const selected = await window.api.selectFolder(selectedFolder || undefined);
      if (selected) {
        setSelectedFolder(selected);
      }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const droppedPath = (e.dataTransfer.files[0] as any).path;
      if (droppedPath) {
        setSelectedFolder(droppedPath);
        saveRecentSession(droppedPath);
        onStartIngest(droppedPath, selectedMode);
      }
    }
  };

  const handleStart = () => {
    if (selectedFolder.trim()) {
      saveRecentSession(selectedFolder.trim());
      onStartIngest(selectedFolder.trim(), selectedMode);
    }
  };

  const handleUndo = async () => {
    if (!selectedFolder.trim() || !onUndoExport) return;
    setIsUndoing(true);
    try {
      await onUndoExport(selectedFolder.trim());
    } finally {
      setIsUndoing(false);
    }
  };

  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 'var(--space-8) var(--space-6)',
        backgroundColor: 'var(--color-bg)',
        overflowY: 'auto'
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '520px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 'var(--space-6)',
          margin: '0 auto'
        }}
      >
        {/* DropZone Central */}
        <div
          onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={handleDrop}
          style={{
            width: '100%',
            backgroundColor: 'var(--color-surface-elevated)',
            border: `1px dashed ${isDragOver ? 'var(--accent-primary)' : 'var(--border-default)'}`,
            borderRadius: 'var(--radius-xl)',
            padding: '64px 48px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            textAlign: 'center',
            gap: 'var(--space-5)',
            boxShadow: isDragOver ? 'var(--shadow-glow-amber)' : 'var(--shadow-md)',
            transition: 'border-color var(--transition-fast), box-shadow var(--transition-fast), transform var(--transition-fast)',
            transform: isDragOver ? 'scale(1.01)' : 'scale(1)'
          }}
        >
          <div
            style={{
              width: '56px',
              height: '56px',
              borderRadius: 'var(--radius-md)',
              backgroundColor: 'var(--color-surface-hover)',
              border: '1px solid var(--border-subtle)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: isDragOver ? 'var(--accent-primary)' : 'var(--text-secondary)'
            }}
          >
            <IconFolder size={28} />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
            <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)', letterSpacing: '-0.3px' }}>
              {isDragOver ? 'Suelta la carpeta para comenzar' : 'Arrastra una carpeta con tus fotografías'}
            </h2>
            <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-tertiary)' }}>
              o selecciona una carpeta para comenzar el culling inteligente
            </p>
          </div>

          <div className="flex items-center gap-3" style={{ width: '100%', maxWidth: '340px', marginTop: 'var(--space-2)' }}>
            <Button
              variant="primary"
              size="md"
              onClick={handleSelectFolder}
              className="flex-1"
              icon={<IconFolder size={16} />}
            >
              {selectedFolder ? 'Cambiar carpeta' : 'Seleccionar carpeta'}
            </Button>

            {selectedFolder && (
              <Button
                variant="secondary"
                size="md"
                onClick={handleStart}
              >
                Comenzar
              </Button>
            )}
          </div>

          {selectedFolder && (
            <div
              className="truncate text-mono"
              style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--text-muted)',
                maxWidth: '90%',
                backgroundColor: 'var(--color-surface-hover)',
                padding: '4px 10px',
                borderRadius: 'var(--radius-xs)',
                border: '1px solid var(--border-subtle)'
              }}
              title={selectedFolder}
            >
              {selectedFolder}
            </div>
          )}

          {/* Format pills */}
          <div className="flex items-center gap-2" style={{ marginTop: 'var(--space-1)' }}>
            {['RAW', 'JPG', 'JPEG', 'TIFF', 'DNG'].map((fmt) => (
              <span
                key={fmt}
                style={{
                  fontSize: '10px',
                  fontWeight: 'var(--fw-semibold)',
                  color: 'var(--text-tertiary)',
                  backgroundColor: 'var(--color-surface-hover)',
                  padding: '2px 8px',
                  borderRadius: 'var(--radius-pill)',
                  border: '1px solid var(--border-subtle)',
                  fontFamily: 'var(--font-mono)'
                }}
              >
                {fmt}
              </span>
            ))}
          </div>
        </div>

        {/* Mode Selector */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            backgroundColor: 'var(--color-surface-elevated)',
            borderRadius: 'var(--radius-pill)',
            border: '1px solid var(--border-subtle)',
            padding: '3px'
          }}
        >
          <button
            className={`gf-btn gf-btn-sm ${selectedMode === 'cull_edit' ? 'gf-btn-primary' : 'gf-btn-ghost'}`}
            onClick={() => setSelectedMode('cull_edit')}
            style={{ borderRadius: 'var(--radius-pill)', fontSize: 'var(--text-xs)' }}
          >
            Culling + Edición
          </button>
          <button
            className={`gf-btn gf-btn-sm ${selectedMode === 'cull_only' ? 'gf-btn-primary' : 'gf-btn-ghost'}`}
            onClick={() => setSelectedMode('cull_only')}
            style={{ borderRadius: 'var(--radius-pill)', fontSize: 'var(--text-xs)' }}
          >
            Solo Culling
          </button>
        </div>

        {/* Undo Action if available */}
        {undoAvailable && selectedFolder && (
          <Button
            variant="danger"
            size="sm"
            onClick={handleUndo}
            disabled={isUndoing}
          >
            {isUndoing ? 'Deshaciendo...' : '↶ Deshacer exportación XMP'}
          </Button>
        )}

        {/* Recent Sessions */}
        {recentSessions.length > 0 && (
          <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            <span className="sidebar-section-title" style={{ padding: 0 }}>Sesiones recientes</span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1)' }}>
              {recentSessions.map((session) => (
                <div
                  key={session.path}
                  onClick={() => {
                    setSelectedFolder(session.path);
                    onStartIngest(session.path, selectedMode);
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    backgroundColor: 'var(--color-surface)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    cursor: 'pointer',
                    transition: 'background-color var(--transition-fast), border-color var(--transition-fast)'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = 'var(--color-surface-hover)';
                    e.currentTarget.style.borderColor = 'var(--border-default)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = 'var(--color-surface)';
                    e.currentTarget.style.borderColor = 'var(--border-subtle)';
                  }}
                >
                  <div className="flex items-center gap-2 truncate">
                    <IconFolder size={14} className="text-tertiary" />
                    <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-primary)' }}>{session.name}</span>
                  </div>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>{session.date}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Privacy Note */}
        <div className="flex items-center gap-2" style={{ color: 'var(--text-muted)', fontSize: 'var(--text-xs)' }}>
          <span>🔒</span>
          <span>100% procesamiento local y privado. Tus fotos nunca salen de este equipo.</span>
        </div>
      </div>
    </div>
  );
};

export default HomeScreen;
