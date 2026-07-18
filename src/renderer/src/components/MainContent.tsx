import React, { useState, useEffect } from 'react';
import GridView from './GridView';
import DuelView from './DuelView';
import CalibrationView from './CalibrationView';

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
  const [avisoLightroom, setAvisoLightroom] = useState('');

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

  // Deshacer devuelve las fotos al XMP que tenían ANTES del culling. Toca
  // archivos reales del fotógrafo, así que se confirma explícitamente.
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
    try {
      const res = await fetch('http://127.0.0.1:8000/reimport_xmp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ directory })
      });
      const data = await res.json();
      if (res.ok) {
        {
          const guardadas = data.estilo_aprendido?.guardadas || 0;
          const estilo = guardadas ? ` · ${guardadas} ediciones aprendidas` : '';
          setSyncMsg(
            data.corrections === 0 && !guardadas
              ? (data.hint || 'Sin cambios nuevos en Lightroom')
              : `${data.corrections} correcciones (↑${data.upgraded} ↓${data.downgraded})` +
                (data.embeddings_available ? ` · ${data.total_examples} ejemplos` : ' · sin aprendizaje (falta modelo CLIP)') +
                estilo
          );
        }
      } else {
        setSyncMsg(data.detail || 'Error al sincronizar');
      }
    } catch (e) {
      setSyncMsg('Error de conexión con el backend');
    } finally {
      setSyncing(false);
    }
  };
  
  if (!jobState && !jobResults) {
    return (
      <div className="flex-center" style={{ height: '100%', flexDirection: 'column', gap: '16px', color: 'var(--text-muted)' }}>
        <div style={{ width: '64px', height: '64px', borderRadius: '50%', backgroundColor: 'var(--bg-tertiary)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
        <h2>Elegí una carpeta para empezar</h2>
        <p>Tus fotos se analizan localmente, sin salir de tu equipo.</p>
      </div>
    );
  }

  // Job is running
  if (jobState && jobState.status === 'running') {
    return (
      <div className="flex-center" style={{ height: '100%', flexDirection: 'column', gap: '24px' }}>
        <div className="glass-panel animate-fade-in" style={{ padding: '32px', width: '400px', textAlign: 'center' }}>
          <h2 style={{ marginBottom: '8px' }}>Analizando fotos</h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '24px' }}>
            {jobState.processed} / {jobState.total} procesadas
          </p>
          
          <div style={{ width: '100%', height: '8px', backgroundColor: 'var(--bg-tertiary)', borderRadius: '4px', overflow: 'hidden' }}>
            <div style={{ 
              width: `${jobState.progress}%`, 
              height: '100%', 
              backgroundColor: 'var(--accent-primary)',
              transition: 'width 0.3s ease'
            }} />
          </div>
          <div style={{ marginTop: '12px', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            {Math.round(jobState.progress)}%
          </div>
        </div>
      </div>
    );
  }

  // Job completed (Results available)
  if (jobResults && jobResults.results) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        {/* Results Header Stats */}
        <div style={{ padding: '16px 24px', backgroundColor: 'var(--bg-secondary)', borderBottom: '1px solid var(--border-subtle)', display: 'flex', gap: '24px' }}>
           <div style={{ display: 'flex', flexDirection: 'column' }}>
             <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Fotos</span>
             <span style={{ fontSize: '1.2rem', fontWeight: 600 }}>{jobResults.stats.total_images}</span>
           </div>
           <div style={{ display: 'flex', flexDirection: 'column' }}>
             <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Ráfagas</span>
             <span style={{ fontSize: '1.2rem', fontWeight: 600 }}>{jobResults.stats.total_clusters}</span>
           </div>
           <div style={{ display: 'flex', flexDirection: 'column', borderLeft: '1px solid var(--border-subtle)', paddingLeft: '24px' }}>
             <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Velocidad</span>
             <span style={{ fontSize: '1.2rem', fontWeight: 600 }}>
               {jobResults.stats.ingest?.images_per_second || 0} <span style={{ fontSize: '0.8rem', fontWeight: 'normal' }}>img/s</span>
             </span>
           </div>
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
             {/* Red de seguridad: devuelve las fotos al estado previo al culling */}
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

        {/* View Area */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {viewMode === 'grid' && <GridView results={jobResults.results} />}
          {viewMode === 'duel' && <DuelView results={jobResults.results} />}
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
