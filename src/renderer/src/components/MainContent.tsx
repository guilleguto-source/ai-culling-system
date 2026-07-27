import React, { useState, useEffect } from 'react';
import GridView from './GridView';
import DuelView from './DuelView';
import CalibrationView from './CalibrationView';
import SemanticSearchBar from './SemanticSearchBar';
import StorylineTimeline from './StorylineTimeline';

interface MainContentProps {
  jobState: any;
  jobResults: any;
  settings: any;
  viewMode: 'grid' | 'duel' | 'calib';
  directory?: string;
}

export default function MainContent({ jobState, jobResults, settings, viewMode, directory }: MainContentProps) {
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string>('');
  const [applying, setApplying] = useState(false);
  const [editsApplied, setEditsApplied] = useState(false);
  const [undoDisponible, setUndoDisponible] = useState(false);
  const [undoing, setUndoing] = useState(false);
  const [filteredResults, setFilteredResults] = useState<any[] | null>(null);

  // ¿Hay respaldo del último culling para este evento?
  useEffect(() => {
    if (!directory) { setUndoDisponible(false); return; }
    (async () => {
      try {
        const r = await fetch(`http://127.0.0.1:8000/undo_export/available?directory=${encodeURIComponent(directory)}`);
        if (r.ok) setUndoDisponible((await r.json()).disponible);
      } catch { /* backend caído */ }
    })();
  }, [directory, jobResults]);

  const handleUndo = async () => {
    if (!directory) return;
    const ok = window.confirm(
      'Se devolverán las estrellas y etiquetas de estas fotos al estado que tenían ANTES del último culling.\n\n¿Continuar?'
    );
    if (!ok) return;
    setUndoing(true);
    setSyncMsg('');
    try {
      const res = await fetch('http://127.0.0.1:8000/undo_export', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ directory }),
      });
      const d = await res.json();
      setSyncMsg(res.ok
        ? `Deshecho: ${d.restauradas} restauradas` +
          (d.limpiadas ? `, ${d.limpiadas} sin marcas` : '') +
          (d.fallidas ? ` · ${d.fallidas} fallaron` : '')
        : (d.detail || 'No se pudo deshacer'));
    } catch {
      setSyncMsg('Error de conexión con el backend');
    } finally {
      setUndoing(false);
    }
  };

  const handleApplyEdits = async () => {
    if (!directory) return;
    setApplying(true);
    setSyncMsg('');
    try {
      const res = await fetch('http://127.0.0.1:8000/apply_edits', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ directory })
      });
      const data = await res.json();
      if (res.ok) {
        setEditsApplied(true);
        setSyncMsg(`Edición aplicada a ${data.edited} fotos` + (data.preset ? ` · preset ${data.preset}` : ''));
      } else {
        setSyncMsg(data.detail || 'Error al aplicar edición');
      }
    } catch (e) {
      setSyncMsg('Error de conexión con el backend');
    } finally {
      setApplying(false);
    }
  };

  const handleLightroomSync = async () => {
    if (!directory) return;
    setSyncing(true);
    setSyncMsg('');

    const catalogo = settings?.selection_preferences?.lightroom_catalog_path;
    if (catalogo) {
      try {
        const r = await fetch('http://127.0.0.1:8000/lightroom/pending_changes', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ directory, catalog_path: catalogo }),
        });
        if (r.ok) {
          const d = await r.json();
          if (d.pendientes > 0) {
            setSyncMsg(d.mensaje);
            setSyncing(false);
            return;
          }
        }
      } catch { /* si el chequeo falla, seguimos con el sync normal */ }
    }

    try {
      const res = await fetch('http://127.0.0.1:8000/reimport_xmp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ directory })
      });
      const data = await res.json();
      if (res.ok) {
        const guardadas = data.estilo_aprendido?.guardadas || 0;
        const estilo = guardadas ? ` · ${guardadas} ediciones aprendidas` : '';
        setSyncMsg(
          data.corrections === 0 && !guardadas
            ? (data.hint || 'Sin cambios nuevos en Lightroom')
            : `${data.corrections} correcciones (↑${data.upgraded} ↓${data.downgraded})` +
              (data.embeddings_available ? ` · ${data.total_examples} ejemplos` : ' · sin aprendizaje (falta modelo CLIP)') +
              estilo
        );
      } else {
        setSyncMsg(data.detail || 'Error al sincronizar');
      }
    } catch (e) {
      setSyncMsg('Error de conexión con el backend');
    } finally {
      setSyncing(false);
    }
  };
  
  const isIdle = !jobState || ['idle', 'stopped', 'unknown'].includes(jobState.status);
  
  if (isIdle && !jobResults) {
    return (
      <div className="flex-center" style={{ height: '100%', flexDirection: 'column', gap: '16px', color: 'var(--text-muted)' }}>
        <div style={{ width: '64px', height: '64px', borderRadius: '50%', backgroundColor: 'var(--bg-tertiary)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
        <h2 style={{ color: 'var(--text-primary)' }}>Elegí una carpeta para empezar</h2>
        <p style={{ color: 'var(--text-secondary)' }}>Tus fotos se analizan 100% localmente de forma privada en tu equipo.</p>
      </div>
    );
  }

  // Job is running
  if (jobState && jobState.status === 'running') {
    return (
      <div className="flex-center" style={{ height: '100%', flexDirection: 'column', gap: '24px' }}>
        <div className="glass-panel animate-fade-in-up" style={{ padding: '36px', width: '420px', textAlign: 'center' }}>
          <h2 style={{ marginBottom: '8px', color: 'var(--text-primary)' }}>Analizando fotos</h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '24px' }}>
            {jobState.processed} / {jobState.total} procesadas
          </p>
          
          <div style={{ width: '100%', height: '8px', backgroundColor: 'var(--bg-tertiary)', borderRadius: '4px', overflow: 'hidden' }}>
            <div style={{ 
              width: `${jobState.progress}%`, 
              height: '100%', 
              background: 'linear-gradient(90deg, var(--accent-primary), var(--accent-hover))',
              transition: 'width 0.3s ease'
            }} />
          </div>
          <div style={{ marginTop: '12px', fontSize: '0.85rem', fontWeight: 600, color: 'var(--accent-primary)' }}>
            {Math.round(jobState.progress)}%
          </div>

          <div style={{ marginTop: '14px', fontSize: '0.82rem', color: 'var(--text-secondary)', fontStyle: 'italic', transition: 'all 0.3s ease' }}>
            {jobState.phase_text || 'Seleccionando y analizando fotos...'}
          </div>
        </div>
      </div>
    );
  }

  // Job completed (Results available)
  if (jobResults && jobResults.results) {
    const displayResults = filteredResults || jobResults.results;

    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        {/* Results Header Stats + Search Bar */}
        <div style={{ padding: '14px 24px', backgroundColor: 'var(--bg-secondary)', borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', gap: '24px' }}>
           <div style={{ display: 'flex', flexDirection: 'column' }}>
             <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Fotos</span>
             <span style={{ fontSize: '1.15rem', fontWeight: 700 }}>{jobResults.stats.total_images}</span>
           </div>
           <div style={{ display: 'flex', flexDirection: 'column' }}>
             <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Ráfagas</span>
             <span style={{ fontSize: '1.15rem', fontWeight: 700 }}>{jobResults.stats.total_clusters}</span>
           </div>
           <div style={{ display: 'flex', flexDirection: 'column', borderLeft: '1px solid var(--border-subtle)', paddingLeft: '20px' }}>
             <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Velocidad</span>
             <span style={{ fontSize: '1.15rem', fontWeight: 700 }}>
               {jobResults.stats.ingest?.images_per_second || 0} <span style={{ fontSize: '0.75rem', fontWeight: 'normal', color: 'var(--text-muted)' }}>img/s</span>
             </span>
           </div>

           {/* Buscador Semántico con IA */}
           <SemanticSearchBar
             directory={directory}
             onSearchResults={(searchResults) => {
               // Filtrar o resaltar fotos según la búsqueda
               const matchedPaths = new Set(searchResults.map((sr: any) => sr.path));
               const filtered = jobResults.results.filter((photo: any) => matchedPaths.has(photo.path));
               setFilteredResults(filtered);
             }}
             onClearSearch={() => setFilteredResults(null)}
           />

           <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '12px' }}>
             {syncMsg && (
               <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{syncMsg}</span>
             )}
             {jobResults.stats?.edits_applied === false && !editsApplied && (
               <button
                 className="btn btn-primary"
                 onClick={handleApplyEdits}
                 disabled={applying || !directory}
                 title="Escribe crop + preset + WB + exposición en las fotos seleccionadas (respeta tus duelos)"
               >
                 {applying ? 'Aplicando…' : 'Aplicar edición'}
               </button>
             )}
             <button
               className="btn btn-secondary"
               onClick={handleLightroomSync}
               disabled={syncing || !directory}
               title="Relee los XMP del directorio y aprende de tus correcciones en Lightroom"
             >
               {syncing ? 'Sincronizando…' : 'Sincronizar desde Lightroom'}
             </button>
             {undoDisponible && (
               <button
                 className="btn btn-secondary"
                 onClick={handleUndo}
                 disabled={undoing || !directory}
                 style={{ color: 'var(--status-blurry-text)' }}
                 title="Devuelve estrellas y etiquetas al estado que tenían antes del último culling"
               >
                 {undoing ? 'Deshaciendo…' : '↩ Deshacer culling'}
               </button>
             )}
           </div>
        </div>

        {/* Storyline Event Timeline */}
        <StorylineTimeline directory={directory} />

        {/* View Area */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {viewMode === 'grid' && <GridView results={displayResults} />}
          {viewMode === 'duel' && <DuelView results={displayResults} />}
          {viewMode === 'calib' && <CalibrationView directory={directory} />}
        </div>
      </div>
    );
  }

  // Error State
  if (jobState && jobState.status === 'error') {
    return (
      <div className="flex-center" style={{ height: '100%', flexDirection: 'column', gap: '16px', color: 'var(--status-blurry-text)' }}>
        <h2>El análisis falló</h2>
        <p>{jobState.error}</p>
      </div>
    );
  }

  return null;
}
