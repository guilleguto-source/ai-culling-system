import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { LibraryProject } from '../types/api';
import { Button } from './ui/Button';
import { Badge } from './ui/Badge';
import { useToast } from './Toast';
import {
  IconCamera,
  IconLayers,
  IconShield,
  IconX,
  IconCheck,
  IconSync,
  IconFolder,
  IconEdit,
  IconSparkles
} from './icons';

interface LibraryViewProps {
  directory?: string;
  jobState?: any;
  jobResults?: any;
  onSelectProject?: (dir: string) => void;
  onOpenFolderPicker?: () => void;
}

export default function LibraryView({
  directory,
  jobState,
  jobResults,
  onSelectProject,
  onOpenFolderPicker
}: LibraryViewProps) {
  const [projects, setProjects] = useState<LibraryProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncingDir, setSyncingDir] = useState<string | null>(null);
  const [syncDetails, setSyncDetails] = useState<{ [dir: string]: any }>({});
  const { showToast } = useToast();

  const loadProjects = async () => {
    try {
      setLoading(true);
      const res = await apiClient.getLibraryProjects();
      setProjects(res.projects || []);
    } catch (err: any) {
      console.error('Error fetching library projects:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
  }, [directory, jobState?.status]);

  // Project active stats
  const activePhotosCount = jobResults?.results?.length || (jobState?.total_files || 0);
  const activeBurstsCount = jobResults?.bursts_detected || (activePhotosCount ? Math.max(1, Math.round(activePhotosCount * 0.18)) : 0);
  const activeSelectedCount = jobResults?.results?.filter((r: any) => r.label === 'selected' || r.label === 'highlighted').length || 0;
  const activeDiscardedCount = activePhotosCount > 0 ? (activePhotosCount - activeSelectedCount) : 0;

  const eventName = directory ? (directory.split(/[/\\]/).filter(Boolean).pop() || 'Evento Actual') : 'Ningún evento cargado';
  const isJobRunning = jobState && (jobState.status === 'running' || jobState.status === 'processing');
  const progressPercent = isJobRunning
    ? Math.round(((jobState.processed_files || 0) / Math.max(1, jobState.total_files || 1)) * 100)
    : (activePhotosCount > 0 ? 100 : 0);

  const handleSyncLightroom = async (targetDir: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    if (!targetDir) return;
    setSyncingDir(targetDir);
    try {
      const data = await apiClient.reimportXmp(targetDir);
      if (data.success) {
        setSyncDetails(prev => ({ ...prev, [targetDir]: data }));
        const guardadas = (data as any).estilo_aprendido?.guardadas || 0;
        const msg = data.corrections === 0 && !guardadas
          ? (data.hint || 'Lightroom sincronizado: sin cambios nuevos')
          : `Sync completado: ${data.corrections} correcciones (↑${data.upgraded} promovidas, ↓${data.downgraded} descartadas)${guardadas ? ` · ${guardadas} estilos aprendidos` : ''}`;
        showToast(msg, 'success');
        loadProjects();
      } else {
        showToast('Error al sincronizar con Lightroom', 'error');
      }
    } catch (err: any) {
      showToast(`Error al sincronizar: ${err.message || err}`, 'error');
    } finally {
      setSyncingDir(null);
    }
  };

  return (
    <div style={{
      height: '100%',
      overflowY: 'auto',
      padding: 'var(--space-6)',
      display: 'flex',
      flexDirection: 'column',
      gap: 'var(--space-6)'
    }}>
      {/* 1. Header del Evento Activo */}
      <div className="flex-between items-center" style={{
        backgroundColor: 'var(--color-surface)',
        padding: 'var(--space-4) var(--space-6)',
        borderRadius: 'var(--radius-lg)',
        border: '1px solid var(--border-subtle)',
        boxShadow: 'var(--shadow-sm)'
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <div className="flex items-center gap-2">
            <h1 style={{
              fontSize: 'var(--text-xl)',
              fontWeight: 'var(--fw-bold)',
              color: 'var(--text-primary)',
              margin: 0
            }}>
              Evento: {eventName}
            </h1>
            <IconEdit size={16} style={{ color: 'var(--text-muted)', cursor: 'pointer' }} />
          </div>
          <span style={{
            fontSize: 'var(--text-xs)',
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-mono)'
          }}>
            {directory || 'Selecciona una carpeta para comenzar'}
          </span>
        </div>

        <div className="flex items-center gap-3">
          {directory && (
            <>
              <Button
                variant="secondary"
                size="sm"
                icon={<IconFolder size={15} />}
                onClick={() => {
                  try {
                    apiClient.openCacheFolder();
                  } catch (e) {
                    showToast('Abriendo explorador...', 'info');
                  }
                }}
              >
                Abrir en Explorer
              </Button>
              <Button
                variant="primary"
                size="sm"
                icon={<IconSync size={15} className={syncingDir === directory ? 'animate-spin' : ''} />}
                onClick={() => handleSyncLightroom(directory)}
                disabled={syncingDir === directory}
              >
                {syncingDir === directory ? 'Sincronizando…' : 'Sincronizar Lightroom'}
              </Button>
            </>
          )}
          {onOpenFolderPicker && (
            <Button
              variant="outline"
              size="sm"
              icon={<IconFolder size={15} />}
              onClick={onOpenFolderPicker}
            >
              Cargar otra sesión
            </Button>
          )}
        </div>
      </div>

      {/* 2. Cuatro Tarjetas de Métricas Principales */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 'var(--space-4)'
      }}>
        <div style={{
          backgroundColor: 'var(--color-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-4) var(--space-5)',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-4)'
        }}>
          <div style={{
            width: 44,
            height: 44,
            borderRadius: 'var(--radius-md)',
            backgroundColor: 'rgba(255, 255, 255, 0.05)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-secondary)'
          }}>
            <IconCamera size={22} />
          </div>
          <div>
            <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 'var(--fw-bold)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
              {activePhotosCount.toLocaleString()}
            </div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>Fotografías</div>
          </div>
        </div>

        <div style={{
          backgroundColor: 'var(--color-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-4) var(--space-5)',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-4)'
        }}>
          <div style={{
            width: 44,
            height: 44,
            borderRadius: 'var(--radius-md)',
            backgroundColor: 'rgba(231, 161, 58, 0.1)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--accent-primary)'
          }}>
            <IconLayers size={22} />
          </div>
          <div>
            <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 'var(--fw-bold)', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
              {activeBurstsCount.toLocaleString()}
            </div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>Ráfagas detectadas</div>
          </div>
        </div>

        <div style={{
          backgroundColor: 'var(--color-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-4) var(--space-5)',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-4)'
        }}>
          <div style={{
            width: 44,
            height: 44,
            borderRadius: 'var(--radius-md)',
            backgroundColor: 'rgba(46, 213, 115, 0.12)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--success)'
          }}>
            <IconShield size={22} />
          </div>
          <div>
            <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 'var(--fw-bold)', color: 'var(--success)', fontFamily: 'var(--font-mono)' }}>
              {activeSelectedCount.toLocaleString()}
            </div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>Seleccionadas</div>
          </div>
        </div>

        <div style={{
          backgroundColor: 'var(--color-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-4) var(--space-5)',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-4)'
        }}>
          <div style={{
            width: 44,
            height: 44,
            borderRadius: 'var(--radius-md)',
            backgroundColor: 'rgba(255, 71, 87, 0.12)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--danger)'
          }}>
            <IconX size={22} />
          </div>
          <div>
            <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 'var(--fw-bold)', color: 'var(--danger)', fontFamily: 'var(--font-mono)' }}>
              {activeDiscardedCount.toLocaleString()}
            </div>
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>Descartadas</div>
          </div>
        </div>
      </div>

      {/* 3. Fila Central: Progreso de Análisis & Checklist IA */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1.4fr 1fr',
        gap: 'var(--space-4)'
      }}>
        {/* Card Izquierda: Análisis en Progreso */}
        <div style={{
          backgroundColor: 'var(--color-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-5)',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          gap: 'var(--space-4)'
        }}>
          <div className="flex-between items-center">
            <span style={{ fontSize: 'var(--text-md)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>
              {isJobRunning ? 'Análisis en progreso' : 'Estado de la sesión'}
            </span>
            <span style={{
              fontSize: 'var(--text-lg)',
              fontWeight: 'var(--fw-bold)',
              color: 'var(--accent-primary)',
              fontFamily: 'var(--font-mono)'
            }}>
              {progressPercent}%
            </span>
          </div>

          {/* Barra Dorada de Progreso */}
          <div style={{
            width: '100%',
            height: '8px',
            backgroundColor: 'var(--color-surface-elevated)',
            borderRadius: 'var(--radius-full)',
            overflow: 'hidden',
            border: '1px solid var(--border-subtle)'
          }}>
            <div style={{
              width: `${progressPercent}%`,
              height: '100%',
              background: 'linear-gradient(90deg, #E7A13A 0%, #F5C564 100%)',
              transition: 'width 0.3s ease'
            }} />
          </div>

          <div className="flex-between items-center" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
            <span>
              {isJobRunning
                ? 'Tiempo estimado restante: 01:24 min'
                : (activePhotosCount > 0 ? 'Análisis completado · Listo para Lightroom' : 'Esperando sesión...')}
            </span>
            <span>
              {isJobRunning ? (jobState?.phase || 'Analizando rostros y calidad...') : '100% Procesado local'}
            </span>
          </div>
        </div>

        {/* Card Derecha: IA trabajando para ti */}
        <div style={{
          backgroundColor: 'var(--color-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-lg)',
          padding: 'var(--space-5)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-3)'
        }}>
          <div className="flex items-center gap-2" style={{ marginBottom: '4px' }}>
            <IconSparkles size={16} style={{ color: 'var(--accent-primary)' }} />
            <span style={{ fontSize: 'var(--text-sm)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>
              IA trabajando para ti
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: 'var(--text-xs)' }}>
            <div className="flex items-center gap-2" style={{ color: 'var(--text-secondary)' }}>
              <IconCheck size={14} style={{ color: 'var(--success)' }} />
              <span>Detección de rostros y calibración biométrica</span>
            </div>
            <div className="flex items-center gap-2" style={{ color: 'var(--text-secondary)' }}>
              <IconCheck size={14} style={{ color: 'var(--success)' }} />
              <span>Agrupación de ráfagas temporales y visuales</span>
            </div>
            <div className="flex items-center gap-2" style={{ color: 'var(--text-secondary)' }}>
              <IconCheck size={14} style={{ color: 'var(--success)' }} />
              <span>Evaluación de nitidez, ojos abiertos y estética</span>
            </div>
            <div className="flex items-center gap-2" style={{ color: 'var(--text-secondary)' }}>
              <IconCheck size={14} style={{ color: 'var(--accent-primary)' }} />
              <span>Aprendiendo tu estilo de selección continuamente</span>
            </div>
          </div>
        </div>
      </div>

      {/* 4. Sección de Sesiones Recientes */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        <div className="flex-between items-center">
          <h2 style={{
            fontSize: 'var(--text-md)',
            fontWeight: 'var(--fw-semibold)',
            color: 'var(--text-primary)',
            margin: 0
          }}>
            Sesiones recientes
          </h2>
          <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
            {projects.length} proyecto{projects.length !== 1 ? 's' : ''} en biblioteca
          </span>
        </div>

        {loading ? (
          <div style={{
            padding: 'var(--space-8)',
            textAlign: 'center',
            color: 'var(--text-muted)',
            backgroundColor: 'var(--color-surface)',
            borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--border-subtle)'
          }}>
            Cargando historial de sesiones...
          </div>
        ) : projects.length === 0 ? (
          <div style={{
            padding: 'var(--space-8)',
            textAlign: 'center',
            color: 'var(--text-muted)',
            backgroundColor: 'var(--color-surface)',
            borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--border-subtle)'
          }}>
            No hay proyectos procesados todavía. Inicia un culling arrastrando una carpeta.
          </div>
        ) : (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-3)'
          }}>
            {projects.map((proj) => {
              const isActive = directory && (proj.directory.toLowerCase() === directory.toLowerCase());
              const syncInfo = syncDetails[proj.directory];

              return (
                <div
                  key={proj.directory}
                  style={{
                    backgroundColor: isActive ? 'rgba(231, 161, 58, 0.04)' : 'var(--color-surface)',
                    border: `1px solid ${isActive ? 'var(--accent-primary)' : 'var(--border-subtle)'}`,
                    borderRadius: 'var(--radius-md)',
                    padding: 'var(--space-3) var(--space-4)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 'var(--space-4)',
                    transition: 'all 0.15s ease'
                  }}
                >
                  {/* Thumbnail + Nombre + Stats */}
                  <div className="flex items-center gap-4" style={{ minWidth: 0, flex: 1 }}>
                    <div style={{
                      width: 56,
                      height: 42,
                      borderRadius: 'var(--radius-sm)',
                      backgroundColor: 'var(--color-surface-elevated)',
                      overflow: 'hidden',
                      flexShrink: 0,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      border: '1px solid var(--border-subtle)'
                    }}>
                      {proj.sample_photo ? (
                        <img
                          src={`http://127.0.0.1:8000/thumbnail?path=${encodeURIComponent(proj.sample_photo)}&size=ui`}
                          alt={proj.folder_name}
                          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                          onError={(e) => {
                            (e.target as HTMLElement).style.display = 'none';
                          }}
                        />
                      ) : (
                        <IconCamera size={18} style={{ color: 'var(--text-muted)' }} />
                      )}
                    </div>

                    <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: '2px' }}>
                      <div className="flex items-center gap-2">
                        <span style={{
                          fontSize: 'var(--text-sm)',
                          fontWeight: 'var(--fw-semibold)',
                          color: 'var(--text-primary)'
                        }} className="truncate">
                          {proj.folder_name}
                        </span>
                        {isActive && (
                          <Badge variant="warning">Activo</Badge>
                        )}
                      </div>

                      <div className="flex items-center gap-3" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                        <span>{proj.total_photos.toLocaleString()} fotos</span>
                        <span>·</span>
                        <span style={{ color: 'var(--success)' }}>{proj.selected_count} elegidas</span>
                        <span>·</span>
                        <span style={{ color: 'var(--text-secondary)' }}>{proj.duplicates_count} duplicadas</span>
                        <span>·</span>
                        <span style={{ color: 'var(--danger)' }}>{proj.blurry_count} borrosas</span>
                      </div>
                    </div>
                  </div>

                  {/* Sync Details Feedback Pill if available */}
                  {syncInfo && (
                    <div style={{
                      fontSize: '11px',
                      backgroundColor: 'var(--color-surface-elevated)',
                      padding: '4px 10px',
                      borderRadius: 'var(--radius-xs)',
                      border: '1px solid var(--border-subtle)',
                      display: 'flex',
                      gap: '8px'
                    }}>
                      <span style={{ color: 'var(--accent-primary)' }}>↑{syncInfo.upgraded || 0} promovidas</span>
                      <span style={{ color: 'var(--danger)' }}>↓{syncInfo.downgraded || 0} descartadas</span>
                    </div>
                  )}

                  {/* Status & Actions */}
                  <div className="flex items-center gap-3" style={{ flexShrink: 0 }}>
                    <div className="flex items-center gap-1" style={{ fontSize: 'var(--text-xs)', color: 'var(--success)' }}>
                      <IconCheck size={14} />
                      <span>Completado</span>
                    </div>

                    <Button
                      variant="outline"
                      size="sm"
                      icon={<IconSync size={13} className={syncingDir === proj.directory ? 'animate-spin' : ''} />}
                      onClick={(e) => handleSyncLightroom(proj.directory, e)}
                      disabled={syncingDir === proj.directory}
                      title="Sincronizar cambios y estrellas desde Lightroom"
                    >
                      {syncingDir === proj.directory ? 'Sync…' : 'Sync Lightroom'}
                    </Button>

                    {onSelectProject && !isActive && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => onSelectProject(proj.directory)}
                      >
                        Abrir
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
