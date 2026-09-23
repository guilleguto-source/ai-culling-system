import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { CullingEstimate, HardwareProfile, PresetItem } from '../types/api';
import { MetadataPanel, MetadataPayload } from './MetadataPanel';

export interface PreCullingConfig {
  directory: string;
  mode: 'cull' | 'cull_edit';
  eventType: string;
  selectivity: 'few' | 'standard' | 'more';
  presetPath?: string;
  autoCrop?: 'off' | 'minimo' | 'medio' | 'agresivo';
  autoSleep: boolean;
  queue: string[];
  eventGroups: string[][];        // [[dir_A, dir_B], [dir_C]]
  eventGroupTypes: string[];      // eventType per group: ['wedding', 'kids_party']
  metadataPayload?: MetadataPayload;
}

interface PreCullingModalProps {
  isOpen: boolean;
  initialDirectory: string;
  initialQueue?: string[];
  onClose: () => void;
  onConfirm: (config: PreCullingConfig) => void;
}

const EVENT_TYPES = [
  { id: 'wedding', label: 'Matrimonio / Boda', icon: '👰', desc: 'Prioridad máxima a momentos clave y cobertura' },
  { id: 'kids_party', label: 'Fiesta Infantil', icon: '🎂', desc: 'Tolerancia a ráfagas rápidas y sonrisas' },
  { id: 'baptism', label: 'Bautizo / Comunión', icon: '🕊️', desc: 'Máxima nitidez en momentos solemnes' },
  { id: 'baby_shower', label: 'Baby Shower', icon: '🍼', desc: 'Momentos emotivos y fotos de grupo' },
  { id: 'family_outdoor', label: 'Familiar al Aire Libre', icon: '🌳', desc: 'Planos abiertos y fondos naturales' },
  { id: 'night_party', label: 'Fiesta Nocturna', icon: '🌙', desc: 'Optimizado para flash y luz artificial' },
  { id: 'corporate', label: 'Corporativo', icon: '💼', desc: 'Filtro estricto de parpadeos y muecas' },
  { id: 'studio', label: 'Estudio / Retrato', icon: '📸', desc: 'Exigencia máxima en nitidez en ojos' }
];

export const PreCullingModal: React.FC<PreCullingModalProps> = ({
  isOpen,
  initialDirectory,
  initialQueue = [],
  onClose,
  onConfirm
}) => {
  const [activeTab, setActiveTab] = useState<'culling' | 'edit' | 'automation' | 'metadata'>('culling');
  
  // State
  const [enableMetadata, setEnableMetadata] = useState(false);
  const [metadataConfig, setMetadataConfig] = useState<MetadataPayload | null>(null);
  const [eventType, setEventType] = useState('wedding');
  const [selectivity, setSelectivity] = useState<'few' | 'standard' | 'more'>('few');
  const [mode, setMode] = useState<'cull' | 'cull_edit'>('cull_edit');
  const [presetPath, setPresetPath] = useState('');
  const [autoCrop, setAutoCrop] = useState<'off' | 'minimo' | 'medio' | 'agresivo'>('off');
  const [autoSleep, setAutoSleep] = useState(false);
  const [queue, setQueue] = useState<string[]>([]);
  const [folderEventMap, setFolderEventMap] = useState<Record<string, number>>({});
  const [eventTypeMap, setEventTypeMap] = useState<Record<number, string>>({}); // eventNum → eventType
  
  // Data from backend
  const [estimate, setEstimate] = useState<CullingEstimate | null>(null);
  const [isEstimating, setIsEstimating] = useState(false);
  const [presets, setPresets] = useState<PresetItem[]>([]);
  const [hardware, setHardware] = useState<HardwareProfile | null>(null);

  // Sync initial directory & queue
  useEffect(() => {
    if (initialDirectory) {
      const q = Array.isArray(initialQueue) && initialQueue.includes(initialDirectory)
        ? initialQueue
        : [initialDirectory, ...(Array.isArray(initialQueue) ? initialQueue.filter((p) => p !== initialDirectory) : [])];
      setQueue(q);
      // Cleanly assign each folder its event number without retaining orphaned keys
      setFolderEventMap(prev => {
        const next: Record<string, number> = {};
        q.forEach((path, idx) => {
          next[path] = prev[path] ?? (idx + 1);
        });
        return next;
      });
    }
  }, [initialDirectory, initialQueue]);

  // Load hardware profile & presets
  useEffect(() => {
    if (!isOpen) return;

    apiClient.getHardwareProfile()
      .then((h) => setHardware(h))
      .catch(() => {});

    apiClient.getAvailablePresets()
      .then((p) => {
        const safePresets = Array.isArray(p) ? p : [];
        setPresets(safePresets);
        if (safePresets.length > 0 && !presetPath) {
          setPresetPath(safePresets[0].path);
        }
      })
      .catch(() => {
        setPresets([]);
      });
  }, [isOpen]);

  // Dynamic estimate fetching
  useEffect(() => {
    if (!isOpen || !initialDirectory) return;

    setIsEstimating(true);
    apiClient.getCullingEstimate(initialDirectory, eventType, selectivity)
      .then((est) => setEstimate(est))
      .catch((err) => console.error('Error fetching estimate:', err))
      .finally(() => setIsEstimating(false));
  }, [isOpen, initialDirectory, eventType, selectivity]);

  if (!isOpen) return null;

  const handleAddFolder = async () => {
    if (window.api?.selectFolder) {
      const selected = await window.api.selectFolder();
      if (selected && !queue.includes(selected)) {
        const newQueue = [...queue, selected];
        setQueue(newQueue);
        // New folder gets the next available event number
        const maxEvent = Math.max(0, ...Object.values(folderEventMap));
        const newEvNum = maxEvent + 1;
        setFolderEventMap(prev => ({ ...prev, [selected]: newEvNum }));
        // Inherit the global event type for the new event number
        setEventTypeMap(prev => ({ ...prev, [newEvNum]: prev[newEvNum] ?? eventType }));
      }
    }
  };

  const handleRemoveFolder = (pathToRemove: string) => {
    const nextQueue = queue.filter((p) => p !== pathToRemove);
    setQueue(nextQueue);
    setFolderEventMap(prev => {
      const next = { ...prev };
      delete next[pathToRemove];
      return next;
    });
    setEventTypeMap(prev => {
      const remainingEvNums = new Set(
        nextQueue.map(p => folderEventMap[p]).filter((n): n is number => typeof n === 'number')
      );
      const next = { ...prev };
      Object.keys(next).forEach(k => {
        if (!remainingEvNums.has(Number(k))) {
          delete next[Number(k)];
        }
      });
      return next;
    });
  };

  const handleStart = () => {
    // Build eventGroups: array of path-arrays sorted by event number
    const grouped = queue.reduce<Record<number, string[]>>((acc, path) => {
      const ev = folderEventMap[path] ?? 1;
      (acc[ev] = acc[ev] || []).push(path);
      return acc;
    }, {});
    const sortedEvNums = Object.keys(grouped).map(Number).sort((a, b) => a - b);
    const eventGroups = sortedEvNums.map(evNum => grouped[evNum]);
    // Event type per group (fallback to global eventType)
    const eventGroupTypes = sortedEvNums.map(evNum => eventTypeMap[evNum] ?? eventType);

    onConfirm({
      directory: queue[0] || initialDirectory,
      mode,
      eventType,
      selectivity,
      presetPath: mode === 'cull_edit' ? presetPath : undefined,
      autoCrop: mode === 'cull_edit' ? autoCrop : 'off',
      autoSleep,
      queue,
      eventGroups,
      eventGroupTypes,
      metadataPayload: enableMetadata && metadataConfig ? metadataConfig : undefined,
    });
  };

  const folderName = (initialDirectory || '').replace(/\\/g, '/').split('/').filter(Boolean).pop() || initialDirectory;
  const safePresets = Array.isArray(presets) ? presets : [];

  const overlayStyle: React.CSSProperties = {
    position: 'fixed',
    top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(5, 7, 10, 0.85)',
    backdropFilter: 'blur(16px)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 9999,
    padding: '24px'
  };

  const modalStyle: React.CSSProperties = {
    backgroundColor: 'var(--color-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-xl)',
    boxShadow: 'var(--shadow-xl)',
    width: '100%',
    maxWidth: '720px',
    display: 'flex',
    flexDirection: 'column',
    maxHeight: '90vh',
    overflow: 'hidden'
  };

  const headerStyle: React.CSSProperties = {
    padding: '20px 24px',
    borderBottom: '1px solid var(--border-subtle)',
    backgroundColor: 'var(--color-bg)',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center'
  };

  const tabsContainerStyle: React.CSSProperties = {
    display: 'flex',
    borderBottom: '1px solid var(--border-default)',
    backgroundColor: 'var(--color-bg)'
  };

  const getTabStyle = (isActive: boolean): React.CSSProperties => ({
    padding: '16px 20px',
    fontSize: 'var(--text-sm)',
    fontWeight: 'var(--fw-bold)',
    color: isActive ? 'var(--accent-primary)' : 'var(--text-secondary)',
    borderBottom: isActive ? '2px solid var(--accent-primary)' : '2px solid transparent',
    backgroundColor: isActive ? 'rgba(231, 161, 58, 0.05)' : 'transparent',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    borderTop: 'none', borderLeft: 'none', borderRight: 'none',
    outline: 'none',
    transition: 'all var(--t-fast)'
  });

  const contentStyle: React.CSSProperties = {
    padding: '24px',
    overflowY: 'auto',
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    gap: '24px'
  };

  const sectionTitleStyle: React.CSSProperties = {
    fontSize: 'var(--text-xs)',
    fontWeight: 'var(--fw-bold)',
    color: 'var(--text-tertiary)',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    marginBottom: '12px',
    display: 'block'
  };

  return (
    <div style={overlayStyle}>
      <div style={modalStyle}>
        {/* Header */}
        <div style={headerStyle}>
          <div>
            <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 'var(--fw-bold)', color: 'var(--text-primary)', margin: '0 0 4px 0', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>🚀</span> Configuración del Lote
              <span style={{ color: 'var(--accent-primary)' }}>— {folderName}</span>
            </h2>
            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)', margin: 0 }}>
              Personaliza el criterio de la IA antes de procesar
            </p>
          </div>
          {hardware && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '6px 12px', backgroundColor: 'var(--color-surface-elevated)',
              border: '1px solid var(--border-default)', borderRadius: 'var(--radius-pill)',
              fontSize: 'var(--text-xs)', color: 'var(--text-secondary)'
            }}>
              <span>{hardware.specs.has_gpu ? '⚡' : '🖥️'}</span>
              <span style={{ fontWeight: 'var(--fw-medium)' }}>{hardware.tier_label}</span>
            </div>
          )}
        </div>

        {/* Tabs Bar */}
        <div style={tabsContainerStyle}>
          <button style={getTabStyle(activeTab === 'culling')} onClick={() => setActiveTab('culling')}>
            <span>🎯</span> 1. Culling & Evento
          </button>
          <button style={getTabStyle(activeTab === 'edit')} onClick={() => setActiveTab('edit')}>
            <span>🎨</span> 2. Pre-Edición
          </button>
          <button style={getTabStyle(activeTab === 'automation')} onClick={() => setActiveTab('automation')}>
            <span>⚡</span> 3. Automatización {queue.length > 1 && `(${queue.length})`}
          </button>
          <button style={getTabStyle(activeTab === 'metadata')} onClick={() => setActiveTab('metadata')}>
            <span>📝</span> 4. Metadatos & Copyright
          </button>
        </div>

        {/* Tab Content Area */}
        <div style={contentStyle}>
          {/* TAB 1: CULLING & EVENTO */}
          {activeTab === 'culling' && (
            <>
              <div>
                <label style={sectionTitleStyle}>Tipo de Sesión o Evento</label>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
                  {EVENT_TYPES.map((ev) => {
                    const isActive = eventType === ev.id;
                    return (
                      <button
                        key={ev.id}
                        onClick={() => setEventType(ev.id)}
                        style={{
                          padding: '16px 12px',
                          borderRadius: 'var(--radius-md)',
                          border: isActive ? '1px solid var(--accent-primary)' : '1px solid var(--border-default)',
                          backgroundColor: isActive ? 'rgba(231, 161, 58, 0.08)' : 'var(--color-surface-elevated)',
                          color: isActive ? 'var(--accent-primary)' : 'var(--text-secondary)',
                          textAlign: 'left',
                          cursor: 'pointer',
                          display: 'flex',
                          flexDirection: 'column',
                          justifyContent: 'space-between',
                          boxShadow: isActive ? 'var(--shadow-glow-amber)' : 'none',
                          transition: 'all var(--t-fast)'
                        }}
                      >
                        <span style={{ fontSize: '24px', marginBottom: '8px' }}>{ev.icon}</span>
                        <div>
                          <div style={{ fontSize: 'var(--text-xs)', fontWeight: 'var(--fw-bold)', color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)' }}>{ev.label}</div>
                          <div style={{ fontSize: '10px', color: 'var(--text-tertiary)', marginTop: '4px', lineHeight: 1.3 }}>{ev.desc}</div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label style={sectionTitleStyle}>Rigurosidad del Culling (Selectividad)</label>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
                  {[
                    { id: 'few', label: 'Estricto', pct: '~20%', desc: 'Solo lo mejor absoluto' },
                    { id: 'standard', label: 'Estándar', pct: '~35%', desc: 'Selección balanceada' },
                    { id: 'more', label: 'Generoso', pct: '~50%', desc: 'Para entregas amplias' }
                  ].map((s) => {
                    const isActive = selectivity === s.id;
                    return (
                      <button
                        key={s.id}
                        onClick={() => setSelectivity(s.id as any)}
                        style={{
                          padding: '12px 16px',
                          borderRadius: 'var(--radius-md)',
                          border: isActive ? '1px solid var(--accent-primary)' : '1px solid var(--border-default)',
                          backgroundColor: isActive ? 'rgba(231, 161, 58, 0.08)' : 'var(--color-surface-elevated)',
                          textAlign: 'left', cursor: 'pointer',
                          transition: 'all var(--t-fast)'
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--fw-bold)', color: isActive ? 'var(--accent-primary)' : 'var(--text-primary)' }}>{s.label}</span>
                          <span style={{ fontSize: '11px', fontFamily: 'var(--font-mono)', color: isActive ? 'var(--accent-primary)' : 'var(--text-tertiary)' }}>{s.pct}</span>
                        </div>
                        <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '6px' }}>{s.desc}</div>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div style={{
                padding: '16px', borderRadius: 'var(--radius-md)',
                border: '1px solid rgba(231, 161, 58, 0.2)',
                backgroundColor: 'rgba(231, 161, 58, 0.05)',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between'
              }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: 'var(--text-sm)', fontWeight: 'var(--fw-bold)', color: 'var(--accent-primary)' }}>
                    <span>📊 Estimación Dinámica Aproximada</span>
                    {estimate?.is_calibrated && (
                      <span style={{ padding: '2px 8px', fontSize: '10px', backgroundColor: 'var(--accent-primary)', color: 'var(--color-bg)', borderRadius: 'var(--radius-pill)', fontWeight: 'var(--fw-bold)' }}>
                        Aprendido de tus sesiones
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', marginTop: '8px' }}>
                    {isEstimating ? (
                      <span style={{ opacity: 0.7 }}>Calculando estimación...</span>
                    ) : estimate ? (
                      <>
                        De <strong style={{ color: 'var(--text-primary)' }}>{estimate.total_photos} fotos</strong>, la IA conservará aprox.{' '}
                        <strong style={{ color: 'var(--accent-primary)', fontFamily: 'var(--font-mono)', fontSize: 'var(--text-md)' }}>
                          {estimate.min_photos} – {estimate.max_photos} fotos
                        </strong>{' '}
                        ({estimate.estimated_percentage}%)
                      </>
                    ) : (
                      'Analizando carpeta...'
                    )}
                  </div>
                  <p style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '6px', margin: 0 }}>
                    {estimate?.is_calibrated
                      ? `Calibrado con ${estimate.samples_count} sesiones previas de este tipo.`
                      : 'Cálculo teórico orientativo. La IA es conservadora con momentos clave.'}
                  </p>
                </div>
              </div>
            </>
          )}

          {/* TAB 2: PRE-EDICIÓN */}
          {activeTab === 'edit' && (
            <>
              <div>
                <label style={sectionTitleStyle}>Modo de Procesamiento</label>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                  <button
                    onClick={() => setMode('cull_edit')}
                    style={{
                      padding: '16px', borderRadius: 'var(--radius-md)',
                      border: mode === 'cull_edit' ? '1px solid var(--accent-primary)' : '1px solid var(--border-default)',
                      backgroundColor: mode === 'cull_edit' ? 'rgba(231, 161, 58, 0.08)' : 'var(--color-surface-elevated)',
                      textAlign: 'left', cursor: 'pointer'
                    }}
                  >
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--fw-bold)', color: mode === 'cull_edit' ? 'var(--accent-primary)' : 'var(--text-primary)' }}>🚀 Culling + Pre-Edición</div>
                    <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '4px' }}>Selecciona y aplica revelado + recorte XMP</div>
                  </button>
                  <button
                    onClick={() => setMode('cull')}
                    style={{
                      padding: '16px', borderRadius: 'var(--radius-md)',
                      border: mode === 'cull' ? '1px solid var(--accent-primary)' : '1px solid var(--border-default)',
                      backgroundColor: mode === 'cull' ? 'rgba(231, 161, 58, 0.08)' : 'var(--color-surface-elevated)',
                      textAlign: 'left', cursor: 'pointer'
                    }}
                  >
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--fw-bold)', color: mode === 'cull' ? 'var(--accent-primary)' : 'var(--text-primary)' }}>✂️ Solo Culling</div>
                    <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '4px' }}>Solo clasifica, califica y filtra duplicados</div>
                  </button>
                </div>
              </div>

              {mode === 'cull_edit' && (
                <>
                  <div>
                    <label style={sectionTitleStyle}>Preset Lightroom (.XMP)</label>
                    <select
                      value={presetPath}
                      onChange={(e) => setPresetPath(e.target.value)}
                      style={{
                        width: '100%', padding: '12px 16px', borderRadius: 'var(--radius-md)',
                        backgroundColor: 'var(--color-bg)', border: '1px solid var(--border-default)',
                        color: 'var(--text-primary)', fontSize: 'var(--text-sm)', outline: 'none'
                      }}
                    >
                      {safePresets.length === 0 && <option value="">Sin presets detectados</option>}
                      {safePresets.map((p) => (
                        <option key={p.path} value={p.path}>{p.name}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label style={sectionTitleStyle}>Auto-Encuadre Inteligente (Crop)</label>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
                      {[
                        { id: 'off', label: 'Apagado' },
                        { id: 'minimo', label: 'Mínimo' },
                        { id: 'medio', label: 'Medio' },
                        { id: 'agresivo', label: 'Agresivo' }
                      ].map((c) => {
                        const isActive = autoCrop === c.id;
                        return (
                          <button
                            key={c.id}
                            onClick={() => setAutoCrop(c.id as any)}
                            style={{
                              padding: '12px', textAlign: 'center', borderRadius: 'var(--radius-sm)',
                              border: isActive ? '1px solid var(--accent-primary)' : '1px solid var(--border-default)',
                              backgroundColor: isActive ? 'rgba(231, 161, 58, 0.08)' : 'var(--color-surface-elevated)',
                              color: isActive ? 'var(--accent-primary)' : 'var(--text-secondary)',
                              fontSize: 'var(--text-xs)', fontWeight: 'var(--fw-medium)', cursor: 'pointer'
                            }}
                          >
                            {c.label}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </>
              )}
            </>
          )}

          {/* TAB 3: AUTOMATIZACIÓN & COLA */}
          {activeTab === 'automation' && (
            <>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <label style={{ ...sectionTitleStyle, margin: 0 }}>Cola de Carpetas ({queue.length})</label>
                  <button
                    onClick={handleAddFolder}
                    style={{
                      background: 'none', border: 'none', color: 'var(--accent-primary)',
                      fontSize: 'var(--text-xs)', fontWeight: 'var(--fw-bold)', cursor: 'pointer'
                    }}
                  >
                    + Agregar otra carpeta
                  </button>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '180px', overflowY: 'auto' }}>
                 {/* Color palette per event number */}
                 {(() => {
                   const EVENT_COLORS = ['#F59E0B','#3B82F6','#10B981','#8B5CF6','#EF4444','#F97316'];
                   const maxEvent = Math.max(1, ...Object.values(folderEventMap));
                   const eventNums = Array.from({ length: maxEvent + 1 }, (_, i) => i + 1);
                   return queue.map((p) => {
                     const evNum = folderEventMap[p] ?? 1;
                     const color = EVENT_COLORS[(evNum - 1) % EVENT_COLORS.length];
                     return (
                       <div
                         key={p}
                         style={{
                           display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                           padding: '10px 12px', borderRadius: 'var(--radius-sm)',
                           backgroundColor: 'var(--color-bg)',
                           border: `1px solid var(--border-default)`,
                           borderLeft: `4px solid ${color}`,
                           fontSize: 'var(--text-xs)'
                         }}
                       >
                         <div style={{ display: 'flex', alignItems: 'center', gap: '10px', overflow: 'hidden', flex: 1 }}>
                           <select
                             value={evNum}
                             onChange={(e) => setFolderEventMap(prev => ({ ...prev, [p]: Number(e.target.value) }))}
                             style={{
                               background: color + '22', border: `1px solid ${color}`,
                               color: color, borderRadius: '4px', padding: '2px 6px',
                               fontSize: 'var(--text-xs)', fontWeight: 'var(--fw-bold)',
                               cursor: 'pointer', flexShrink: 0,
                             }}
                             title="Número de evento"
                           >
                             {eventNums.map(n => (
                               <option key={n} value={n} style={{ background: 'var(--color-surface)', color: 'var(--text-primary)' }}>
                                 E{n}
                               </option>
                             ))}
                           </select>
                           <span style={{ color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                             {(p || '').replace(/\\/g, '/').split('/').filter(Boolean).pop() ?? p}
                           </span>
                           <span style={{ color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontSize: '10px' }}>
                             {p}
                           </span>
                         </div>
                         {queue.length > 1 && (
                           <button
                             onClick={() => handleRemoveFolder(p)}
                             style={{
                               background: 'none', border: 'none', color: 'var(--text-tertiary)',
                               cursor: 'pointer', padding: '4px 8px', fontSize: '14px', flexShrink: 0,
                             }}
                           >
                             ✕
                           </button>
                         )}
                       </div>
                     );
                   });
                 })()}

                </div>
              </div>

              {/* Per-event type config — only when multiple distinct event numbers exist */}
              {(() => {
                const EVENT_COLORS = ['#F59E0B','#3B82F6','#10B981','#8B5CF6','#EF4444','#F97316'];
                const distinctEvents = [...new Set(Object.values(folderEventMap))].sort((a, b) => a - b);
                if (distinctEvents.length <= 1) return null;
                return (
                  <div style={{ marginTop: '16px', marginBottom: '16px' }}>
                    <label style={{ fontSize: 'var(--text-xs)', fontWeight: 'var(--fw-bold)', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.08em', display: 'block', marginBottom: '8px' }}>
                      Tipo de evento por grupo
                    </label>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      {distinctEvents.map(evNum => {
                        const color = EVENT_COLORS[(evNum - 1) % EVENT_COLORS.length];
                        const currentType = eventTypeMap[evNum] ?? eventType;
                        const folderCount = queue.filter(p => (folderEventMap[p] ?? 1) === evNum).length;
                        return (
                          <div key={evNum} style={{
                            display: 'flex', alignItems: 'center', gap: '10px',
                            padding: '10px 12px', borderRadius: 'var(--radius-sm)',
                            backgroundColor: 'var(--color-bg)',
                            border: `1px solid var(--border-default)`, borderLeft: `4px solid ${color}`,
                          }}>
                            <span style={{ color, fontWeight: 'var(--fw-bold)', fontSize: 'var(--text-xs)', flexShrink: 0 }}>E{evNum}</span>
                            <span style={{ color: 'var(--text-muted)', fontSize: '10px', flexShrink: 0, width: '70px' }}>
                              {folderCount} {folderCount === 1 ? 'carpeta' : 'carpetas'}
                            </span>
                            <select
                              value={currentType}
                              onChange={e => setEventTypeMap(prev => ({ ...prev, [evNum]: e.target.value }))}
                              style={{
                                flex: 1, background: 'var(--color-surface-elevated)', border: '1px solid var(--border-default)',
                                color: 'var(--text-primary)', borderRadius: '4px', padding: '4px 8px',
                                fontSize: 'var(--text-xs)', cursor: 'pointer',
                              }}
                            >
                              {EVENT_TYPES.map(et => (
                                <option key={et.id} value={et.id}>{et.icon} {et.label}</option>
                              ))}
                            </select>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })()}

              <div style={{
                padding: '16px', borderRadius: 'var(--radius-md)',
                border: '1px solid var(--border-default)', backgroundColor: 'var(--color-surface-elevated)',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between'
              }}>
                <div>
                  <div style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--fw-bold)', color: 'var(--text-primary)' }}>
                    💤 Suspender equipo al finalizar todo el lote
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '4px' }}>
                    Espera un margen de 3 minutos para asegurar el vaciado del NAS y luego suspende la PC.
                  </div>
                </div>
                <input
                  type="checkbox"
                  checked={autoSleep}
                  onChange={(e) => setAutoSleep(e.target.checked)}
                  style={{ width: '20px', height: '20px', accentColor: 'var(--accent-primary)', cursor: 'pointer' }}
                />
              </div>
            </>
          )}

          {/* TAB 4: METADATOS & COPYRIGHT */}
          {activeTab === 'metadata' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '16px 18px',
                  backgroundColor: enableMetadata ? 'rgba(231, 161, 58, 0.12)' : 'var(--color-surface-elevated)',
                  border: enableMetadata ? '1px solid var(--accent-primary)' : '1px solid var(--border-default)',
                  borderRadius: 'var(--radius-md)',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease'
                }}
                onClick={() => setEnableMetadata(!enableMetadata)}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <span style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--fw-bold)', color: 'var(--text-primary)' }}>
                    Inyectar metadatos y copyright en este lote
                  </span>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
                    {enableMetadata
                      ? 'Se aplicará el perfil de copyright, evento, ciudad y palabras clave a los archivos XMP.'
                      : 'Deshabilitado por defecto. Las fotos mantendrán intactos sus metadatos originales sin demoras.'}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={enableMetadata}
                  onChange={(e) => setEnableMetadata(e.target.checked)}
                  onClick={(e) => e.stopPropagation()}
                  style={{ width: '22px', height: '22px', accentColor: 'var(--accent-primary)', cursor: 'pointer' }}
                />
              </div>

              <MetadataPanel
                directory={queue[0] || initialDirectory}
                showApplyButton={false}
                showScopeSelector={false}
                disabled={!enableMetadata}
                onChange={(cfg) => setMetadataConfig(cfg)}
              />
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: '16px 24px',
          borderTop: '1px solid var(--border-default)',
          backgroundColor: 'var(--color-bg)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <button
            onClick={onClose}
            style={{
              padding: '10px 16px', background: 'transparent', border: 'none',
              color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', fontWeight: 'var(--fw-semibold)', cursor: 'pointer'
            }}
          >
            Cancelar
          </button>
          <button
            onClick={handleStart}
            style={{
              padding: '12px 24px',
              backgroundColor: 'var(--accent-primary)',
              color: 'var(--color-bg)',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              fontSize: 'var(--text-sm)',
              fontWeight: 'var(--fw-bold)',
              cursor: 'pointer',
              boxShadow: 'var(--shadow-glow-amber)',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}
          >
            <span>🚀</span> Iniciar Culling ({queue.length} {queue.length === 1 ? 'carpeta' : 'carpetas'})
          </button>
        </div>
      </div>
    </div>
  );
};
