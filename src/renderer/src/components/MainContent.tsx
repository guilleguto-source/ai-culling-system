import React, { useState } from 'react';
import GridView from './GridView';
import DuelView from './DuelView';
import SemanticSearchBar from './SemanticSearchBar';
import StorylineTimeline from './StorylineTimeline';
import { AdvancedPanel } from './AdvancedPanel';
import HomeScreen from './HomeScreen';
import StyleProfileView from './StyleProfileView';
import LibraryView from './LibraryView';
import { apiClient } from '../api/client';
import { useToast } from './Toast';
import { Button } from './ui/Button';

interface MainContentProps {
  jobState: any;
  jobResults: any;
  settings: any;
  viewMode: 'library' | 'grid' | 'duel' | 'calib';
  directory?: string;
  undoAvailable?: boolean;
  onUndoExport?: (dir: string) => Promise<void>;
  onRefreshResults?: () => void;
  onStartIngest?: (dir: string, mode?: string) => void;
  onSelectProject?: (dir: string) => void;
}

export default function MainContent({
  jobState,
  jobResults,
  settings,
  viewMode,
  directory,
  undoAvailable = false,
  onUndoExport,
  onRefreshResults,
  onStartIngest,
  onSelectProject,
}: MainContentProps) {
  const [syncing, setSyncing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [editsApplied, setEditsApplied] = useState(false);
  const [undoing, setUndoing] = useState(false);
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false);
  const [filteredResults, setFilteredResults] = useState<any[] | null>(null);
  const [activeStorylinePaths, setActiveStorylinePaths] = useState<Set<string> | null>(null);
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const { showToast } = useToast();

  const handleUndo = async () => {
    if (!directory || !onUndoExport) return;
    const ok = window.confirm(
      'Se devolverán las estrellas y etiquetas de estas fotos al estado que tenían ANTES del último culling.\n\n¿Continuar?'
    );
    if (!ok) return;
    setUndoing(true);
    try {
      await onUndoExport(directory);
    } finally {
      setUndoing(false);
    }
  };

  const handleApplyEdits = async () => {
    if (!directory) return;
    setApplying(true);
    try {
      const data = await apiClient.applyEdits(directory);
      if (data.success) {
        setEditsApplied(true);
        showToast(`Edición aplicada a ${data.edited} fotos` + (data.preset ? ` · preset ${data.preset}` : ''), 'success');
      } else {
        showToast('Error al aplicar edición', 'error');
      }
    } catch (e: any) {
      showToast(e.message || 'Error de conexión con el backend', 'error');
    } finally {
      setApplying(false);
    }
  };

  const handleLightroomSync = async () => {
    if (!directory) return;
    setSyncing(true);

    const catalogo = settings?.selection_preferences?.lightroom_catalog_path;
    if (catalogo) {
      try {
        const d = await apiClient.getLightroomPendingChanges(directory, catalogo);
        if (d.pendientes > 0) {
          showToast(`Hay ${d.pendientes} cambios pendientes en Lightroom. Guarde los metadatos primero.`, 'info');
          setSyncing(false);
          return;
        }
      } catch { /* continuar si falla */ }
    }

    try {
      const data = await apiClient.reimportXmp(directory);
      if (data.success) {
        const guardadas = (data as any).estilo_aprendido?.guardadas || 0;
        const estilo = guardadas ? ` · ${guardadas} ediciones aprendidas` : '';
        const msg = data.corrections === 0 && !guardadas
          ? (data.hint || 'Sin cambios nuevos en Lightroom')
          : `${data.corrections} correcciones (↑${data.upgraded} ↓${data.downgraded})` +
            (data.total_examples ? ` · ${data.total_examples} ejemplos` : '') +
            estilo;
        showToast(msg, 'success');
      } else {
        showToast('Error al sincronizar con Lightroom', 'error');
      }
    } catch (e: any) {
      showToast(e.message || 'Error de conexión con el backend', 'error');
    } finally {
      setSyncing(false);
    }
  };
  
  // 0. Dedicated top-level views (Library and Style Profile)
  if (viewMode === 'library') {
    return (
      <LibraryView
        directory={directory}
        jobState={jobState}
        jobResults={jobResults}
        onSelectProject={onSelectProject}
        onOpenFolderPicker={() => {
          if (window.api?.selectFolder) {
            window.api.selectFolder(directory).then((res) => {
              if (res && onStartIngest) onStartIngest(res);
            });
          }
        }}
      />
    );
  }

  if (viewMode === 'calib') {
    return <StyleProfileView directory={directory} />;
  }

  const isIdle = !jobState || ['idle', 'stopped', 'unknown'].includes(jobState.status);
  
  // 1. Empty State (HomeScreen)
  if (isIdle && !jobResults) {
    return (
      <HomeScreen
        onStartIngest={(dir, mode) => {
          if (onStartIngest) {
            onStartIngest(dir, mode);
          } else if (window.api?.ingestMedia) {
            window.api.ingestMedia(dir, mode || 'cull_edit');
          }
        }}
        undoAvailable={undoAvailable}
        onUndoExport={onUndoExport}
        lastDirectory={directory}
      />
    );
  }

  // 2. Processing State
  if (jobState && (jobState.status === 'running' || jobState.status === 'processing')) {
    const phases = jobState.phases || [];

    return (
      <div
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: 'var(--color-bg)',
          padding: 'var(--space-6)'
        }}
      >
        <div
          style={{
            width: '100%',
            maxWidth: '520px',
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-8) var(--space-6)',
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-5)',
            boxShadow: 'var(--shadow-md)'
          }}
        >
          <div className="flex items-center gap-2" style={{ alignSelf: 'center', marginBottom: 'var(--space-2)' }}>
            <span className="gf-dot gf-dot-active" />
            <span style={{ fontSize: 'var(--text-lg)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>
              Procesando fotografías
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {phases.length > 0 ? (
              phases.map((phase: any, idx: number) => {
                const isCompleted = phase.status === 'completed';
                const isRunning = phase.status === 'running';
                const isPending = phase.status === 'pending';
                const progress = phase.progress || 0;

                return (
                  <div key={phase.id || idx} style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px',
                    opacity: isPending ? 0.5 : 1
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {isCompleted && <span style={{ color: 'var(--color-success)' }}>✅</span>}
                        {isRunning && <span style={{ color: 'var(--accent-primary)', animation: 'pulse 1.5s infinite' }}>⏳</span>}
                        {isPending && <span style={{ color: 'var(--text-tertiary)' }}>○</span>}
                        <span style={{ 
                          fontSize: 'var(--text-sm)', 
                          fontWeight: isRunning ? 'var(--fw-semibold)' : 'var(--fw-medium)',
                          color: isRunning ? 'var(--text-primary)' : 'var(--text-secondary)'
                        }}>
                          {phase.name}
                        </span>
                      </div>
                      
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: 'var(--text-xs)' }}>
                        {isRunning && jobState.processed !== undefined && jobState.total !== undefined && (
                          <span style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
                            {jobState.processed} / {jobState.total} fotos
                          </span>
                        )}
                        {!isPending && (
                          <span style={{ 
                            color: isCompleted ? 'var(--color-success)' : 'var(--accent-primary)', 
                            fontWeight: 'var(--fw-bold)',
                            fontFamily: 'var(--font-mono)',
                            minWidth: '40px',
                            textAlign: 'right'
                          }}>
                            {isCompleted ? '100%' : `${progress}%`}
                          </span>
                        )}
                      </div>
                    </div>
                    
                    {isRunning && (
                      <div
                        style={{
                          width: '100%',
                          height: '4px',
                          backgroundColor: 'var(--color-surface-elevated)',
                          borderRadius: 'var(--radius-pill)',
                          overflow: 'hidden',
                          marginTop: '2px'
                        }}
                      >
                        <div
                          style={{
                            width: `${Math.max(2, Math.min(100, progress))}%`,
                            height: '100%',
                            backgroundColor: 'var(--accent-primary)',
                            transition: 'width var(--transition-normal)'
                          }}
                        />
                      </div>
                    )}
                  </div>
                );
              })
            ) : (
              // Fallback for old jobs
              <div style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>
                Inicializando fases...
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // 3. Completed State (Results available)
  if (jobResults && jobResults.results) {
    const displayResults = filteredResults || jobResults.results;

    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        {/* Results Header Toolbar */}
        <div
          style={{
            padding: '10px 16px',
            backgroundColor: 'var(--color-surface)',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-4)',
            flexWrap: 'wrap'
          }}
        >
          {/* Semantic AI Search */}
          <SemanticSearchBar
            directory={directory}
            onSearchResults={(searchResults) => {
              const matchedPaths = new Set(searchResults.map((sr: any) => sr.path));
              const filtered = jobResults.results.filter((photo: any) => matchedPaths.has(photo.path));
              setFilteredResults(filtered);
            }}
            onClearSearch={() => setFilteredResults(null)}
          />

          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setIsAdvancedOpen(true)}
              title="Módulos de Revelado Avanzado: 3D-LUT, re-iluminación y retoque de piel"
            >
              ✦ Revelado y Retoque
            </Button>

            {jobResults.stats?.edits_applied === false && !editsApplied && (
              <Button
                variant="primary"
                size="sm"
                onClick={handleApplyEdits}
                disabled={applying || !directory}
                title="Escribe crop + preset + WB + exposición en las fotos seleccionadas"
              >
                {applying ? 'Aplicando…' : 'Aplicar edición'}
              </Button>
            )}

            <Button
              variant="secondary"
              size="sm"
              onClick={handleLightroomSync}
              disabled={syncing || !directory}
              title="Relee los XMP del directorio y aprende de tus correcciones en Lightroom"
            >
              {syncing ? 'Sincronizando…' : 'Sincronizar Lightroom'}
            </Button>

            {undoAvailable && (
              <Button
                variant="danger"
                size="sm"
                onClick={handleUndo}
                disabled={undoing || !directory}
                title="Devuelve estrellas y etiquetas al estado que tenían antes del último culling"
              >
                {undoing ? 'Deshaciendo…' : '↩ Deshacer culling'}
              </Button>
            )}
          </div>
        </div>

        {/* Storyline Event Timeline */}
        <StorylineTimeline 
          directory={directory} 
          onSelectChapter={(chapter) => {
            if (chapter && chapter.paths) {
              setActiveStorylinePaths(new Set(chapter.paths));
            } else {
              setActiveStorylinePaths(null);
            }
          }}
        />

        {/* Active Workspace View */}
        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
          {viewMode === 'grid' && (
            <GridView 
              results={displayResults} 
              selectedPaths={selectedPaths}
              onSelectPaths={setSelectedPaths}
              storylinePaths={activeStorylinePaths}
            />
          )}
          {viewMode === 'duel' && <DuelView results={displayResults} />}
          {viewMode === 'calib' && <StyleProfileView directory={directory} />}
        </div>

        {/* Modal de Revelado Avanzado y Retoque */}
        <AdvancedPanel
          isOpen={isAdvancedOpen}
          onClose={() => setIsAdvancedOpen(false)}
          onRefreshResults={onRefreshResults}
          selectedPaths={Array.from(selectedPaths)}
        />
      </div>
    );
  }

  // 4. Error State
  if (jobState && jobState.status === 'error') {
    return (
      <div className="flex-center" style={{ height: '100%', flexDirection: 'column', gap: '16px', color: 'var(--danger)' }}>
        <h2>El análisis no pudo completarse</h2>
        <p style={{ color: 'var(--text-secondary)' }}>{jobState.error}</p>
      </div>
    );
  }

  return null;
}
