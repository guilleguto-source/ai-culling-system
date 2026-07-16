import React, { useState } from 'react';
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
        setSyncMsg(
          data.corrections === 0
            ? 'Sin cambios nuevos en Lightroom'
            : `${data.corrections} correcciones (↑${data.upgraded} ↓${data.downgraded})` +
              (data.embeddings_available ? ` · ${data.total_examples} ejemplos` : ' · sin aprendizaje (falta modelo CLIP)')
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
  
  if (!jobState && !jobResults) {
    return (
      <div className="flex-center" style={{ height: '100%', flexDirection: 'column', gap: '16px', color: 'var(--text-muted)' }}>
        <div style={{ width: '64px', height: '64px', borderRadius: '50%', backgroundColor: 'var(--bg-tertiary)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
        <h2>Select a folder to begin</h2>
        <p>Your photos will be analyzed securely offline.</p>
      </div>
    );
  }

  // Job is running
  if (jobState && jobState.status === 'running') {
    return (
      <div className="flex-center" style={{ height: '100%', flexDirection: 'column', gap: '24px' }}>
        <div className="glass-panel animate-fade-in" style={{ padding: '32px', width: '400px', textAlign: 'center' }}>
          <h2 style={{ marginBottom: '8px' }}>Analyzing Photos</h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '24px' }}>
            {jobState.processed} / {jobState.total} processed
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
             <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Total Photos</span>
             <span style={{ fontSize: '1.2rem', fontWeight: 600 }}>{jobResults.stats.total_images}</span>
           </div>
           <div style={{ display: 'flex', flexDirection: 'column' }}>
             <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Clusters Found</span>
             <span style={{ fontSize: '1.2rem', fontWeight: 600 }}>{jobResults.stats.total_clusters}</span>
           </div>
           <div style={{ display: 'flex', flexDirection: 'column', borderLeft: '1px solid var(--border-subtle)', paddingLeft: '24px' }}>
             <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Ingest Speed</span>
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
        <h2>Analysis Failed</h2>
        <p>{jobState.error}</p>
      </div>
    );
  }

  return null;
}
