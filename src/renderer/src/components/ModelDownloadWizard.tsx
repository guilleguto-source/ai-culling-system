import React, { useEffect, useState, useRef } from 'react';
import { apiClient, BACKEND_URL } from '../api/client';

interface ModelStatus {
  id: string;
  display_name: string;
  size_mb: number;
  required: boolean;
  description: string;
  present: boolean;
  download_status: string;
  download_progress: number;
  download_error: string | null;
}

interface ModelDownloadWizardProps {
  onComplete: () => void;
}

export const ModelDownloadWizard: React.FC<ModelDownloadWizardProps> = ({ onComplete }) => {
  const [models, setModels] = useState<ModelStatus[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [phase, setPhase] = useState<'catalog' | 'downloading' | 'done'>('catalog');
  const [liveProgress, setLiveProgress] = useState<Record<string, { progress: number; status: string; error: string | null }>>({});
  const eventSourceRef = useRef<EventSource | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadCatalog();
    return () => {
      eventSourceRef.current?.close();
    };
  }, []);

  const loadCatalog = async () => {
    try {
      const data = await apiClient.getSetupModels();
      const m: ModelStatus[] = data.models;
      setModels(m);
      // Pre-seleccionar modelos requeridos y los no presentes recomendados
      const preselected = new Set(
        m
          .filter(x => x.required && !x.present)
          .map(x => x.id)
      );
      setSelected(preselected);
    } catch (e: any) {
      setError(`No se pudo conectar con el backend: ${e.message}`);
    }
  };

  const toggleModel = (id: string, required: boolean) => {
    if (required) return; // los requeridos no se pueden deseleccionar
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleStartDownload = async () => {
    if (selected.size === 0) {
      onComplete();
      return;
    }
    setPhase('downloading');

    try {
      await apiClient.startModelDownload(Array.from(selected));

      // SSE para progreso en tiempo real
      const es = new EventSource(apiClient.getModelDownloadStreamUrl());
      eventSourceRef.current = es;

      es.onmessage = (ev) => {
        try {
          const states: { id: string; status: string; download_progress: number; download_error: string | null }[] = JSON.parse(ev.data);
          const map: Record<string, any> = {};
          let allDone = true;
          states.forEach(s => {
            map[s.id] = { progress: s.download_progress, status: s.status, error: s.download_error };
            if (selected.has(s.id) && s.status !== 'done' && s.status !== 'error') {
              allDone = false;
            }
          });
          setLiveProgress(map);
          if (allDone) {
            es.close();
            setPhase('done');
          }
        } catch { /* ignore parse error */ }
      };

      es.addEventListener('done', () => {
        es.close();
        setPhase('done');
      });

      es.onerror = () => {
        es.close();
        setPhase('done');
      };
    } catch (e: any) {
      setError(`Error iniciando descarga: ${e.message}`);
    }
  };

  const totalSelectedMb = models
    .filter(m => selected.has(m.id))
    .reduce((acc, m) => acc + m.size_mb, 0);

  const missingRequired = models.filter(m => m.required && !m.present);

  if (phase === 'done') {
    return (
      <div style={overlayStyle}>
        <div style={cardStyle}>
          <div style={{ textAlign: 'center', padding: '24px' }}>
            <div style={{ fontSize: '3rem', marginBottom: '16px' }}>✅</div>
            <h2 style={{ color: '#f4f4f5', margin: '0 0 8px' }}>¡Modelos listos!</h2>
            <p style={{ color: '#a1a1aa', marginBottom: '24px' }}>
              Guto Flow está listo para usarse.
            </p>
            <button
              onClick={onComplete}
              style={primaryBtnStyle}
            >
              Comenzar
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (phase === 'downloading') {
    return (
      <div style={overlayStyle}>
        <div style={{ ...cardStyle, width: '500px' }}>
          <h2 style={{ color: '#f4f4f5', margin: '0 0 4px' }}>Descargando modelos de IA</h2>
          <p style={{ color: '#a1a1aa', fontSize: '0.8rem', marginBottom: '20px' }}>
            Esto sólo ocurre una vez. Puedes dejar la app en segundo plano.
          </p>

          {models.filter(m => selected.has(m.id)).map(m => {
            const live = liveProgress[m.id];
            const progress = live?.progress ?? 0;
            const status = live?.status ?? 'waiting';
            const err = live?.error;

            return (
              <div key={m.id} style={{ marginBottom: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ fontSize: '0.82rem', color: '#d4d4d8' }}>{m.display_name}</span>
                  <span style={{ fontSize: '0.75rem', color: err ? '#f87171' : status === 'done' ? '#86efac' : '#71717a' }}>
                    {err ? 'Error' : status === 'done' ? '✓ Listo' : status === 'verifying' ? 'Verificando…' : `${Math.round(progress)}%`}
                  </span>
                </div>
                <div style={{ height: '6px', backgroundColor: '#27272a', borderRadius: '3px', overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    width: `${progress}%`,
                    background: err
                      ? '#ef4444'
                      : status === 'done'
                      ? '#22c55e'
                      : 'linear-gradient(90deg, #0ea5e9, #38bdf8)',
                    transition: 'width 0.4s ease',
                    borderRadius: '3px',
                  }} />
                </div>
                {err && (
                  <p style={{ color: '#f87171', fontSize: '0.72rem', marginTop: '4px' }}>{err}</p>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // Phase: catalog
  return (
    <div style={overlayStyle}>
      <div style={{ ...cardStyle, width: '560px', maxHeight: '88vh', overflow: 'auto' }}>
        {/* Header */}
        <div style={{ marginBottom: '20px' }}>
          <h2 style={{ color: '#f4f4f5', margin: '0 0 6px' }}>Modelos de IA — Primera ejecución</h2>
          <p style={{ color: '#a1a1aa', fontSize: '0.82rem', margin: 0 }}>
            Guto Flow necesita descargar algunos modelos de IA para funcionar.
            Los opcionales mejoran la experiencia pero no son indispensables.
          </p>
        </div>

        {error && (
          <div style={{ backgroundColor: '#7f1d1d', color: '#fca5a5', padding: '10px 14px', borderRadius: '6px', marginBottom: '16px', fontSize: '0.8rem' }}>
            {error}
          </div>
        )}

        {/* Model list */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '20px' }}>
          {models.map(m => {
            const isSelected = selected.has(m.id);
            const isPresent = m.present;

            return (
              <div
                key={m.id}
                onClick={() => !isPresent && toggleModel(m.id, m.required)}
                style={{
                  backgroundColor: isPresent ? '#14532d22' : isSelected ? '#0c4a6e44' : '#27272a',
                  border: `1px solid ${isPresent ? '#166534' : isSelected ? '#0369a1' : '#3f3f46'}`,
                  borderRadius: '8px',
                  padding: '12px 14px',
                  cursor: isPresent ? 'default' : 'pointer',
                  transition: 'all 0.15s',
                  opacity: isPresent ? 0.7 : 1,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px' }}>
                      <span style={{
                        width: '16px', height: '16px', borderRadius: '4px',
                        backgroundColor: isPresent ? '#22c55e' : isSelected ? '#0ea5e9' : '#52525b',
                        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: '10px', flexShrink: 0,
                      }}>
                        {isPresent ? '✓' : isSelected ? '✓' : ''}
                      </span>
                      <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#f4f4f5' }}>
                        {m.display_name}
                      </span>
                      {m.required && (
                        <span style={{ fontSize: '0.65rem', backgroundColor: '#7c2d12', color: '#fdba74', padding: '1px 6px', borderRadius: '10px' }}>
                          Requerido
                        </span>
                      )}
                      {isPresent && (
                        <span style={{ fontSize: '0.65rem', backgroundColor: '#14532d', color: '#86efac', padding: '1px 6px', borderRadius: '10px' }}>
                          Ya instalado
                        </span>
                      )}
                    </div>
                    <p style={{ margin: '0 0 0 24px', fontSize: '0.75rem', color: '#a1a1aa' }}>
                      {m.description}
                    </p>
                  </div>
                  <span style={{ fontSize: '0.75rem', color: '#71717a', marginLeft: '12px', flexShrink: 0, paddingTop: '2px' }}>
                    {m.size_mb >= 100 ? `${Math.round(m.size_mb)} MB` : `${m.size_mb} MB`}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid #27272a', paddingTop: '16px' }}>
          <div style={{ fontSize: '0.8rem', color: '#71717a' }}>
            {selected.size > 0
              ? `Seleccionados: ~${Math.round(totalSelectedMb)} MB`
              : 'Ninguno seleccionado'}
          </div>
          <div style={{ display: 'flex', gap: '10px' }}>
            {missingRequired.length === 0 && (
              <button
                onClick={onComplete}
                style={secondaryBtnStyle}
              >
                Omitir por ahora
              </button>
            )}
            <button
              onClick={handleStartDownload}
              disabled={selected.size === 0}
              style={{
                ...primaryBtnStyle,
                opacity: selected.size === 0 ? 0.5 : 1,
                cursor: selected.size === 0 ? 'not-allowed' : 'pointer',
              }}
            >
              {selected.size === 0 ? 'Selecciona al menos uno' : `Descargar ${selected.size} modelo${selected.size > 1 ? 's' : ''}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

// ─── Styles ──────────────────────────────────────────────────────────────────

const overlayStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  backgroundColor: 'rgba(0,0,0,0.85)',
  backdropFilter: 'blur(8px)',
  zIndex: 2000,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
};

const cardStyle: React.CSSProperties = {
  backgroundColor: '#18181b',
  border: '1px solid #27272a',
  borderRadius: '12px',
  padding: '28px',
  boxShadow: '0 24px 60px rgba(0,0,0,0.7)',
  color: '#e4e4e7',
  maxWidth: '92vw',
};

const primaryBtnStyle: React.CSSProperties = {
  padding: '10px 20px',
  backgroundColor: '#0284c7',
  border: 'none',
  borderRadius: '8px',
  color: '#fff',
  fontWeight: 600,
  fontSize: '0.85rem',
  cursor: 'pointer',
};

const secondaryBtnStyle: React.CSSProperties = {
  padding: '10px 16px',
  backgroundColor: '#3f3f46',
  border: 'none',
  borderRadius: '8px',
  color: '#d4d4d8',
  fontSize: '0.85rem',
  cursor: 'pointer',
};
