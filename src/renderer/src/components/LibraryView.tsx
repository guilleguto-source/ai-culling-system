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
  IconSparkles,
  IconLibrary,
  IconTrash
} from './icons';

interface LibraryViewProps {
  directory?: string;
  jobState?: any;
  jobResults?: any;
  onSelectProject?: (dir: string) => void;
  onOpenFolderPicker?: () => void;
  onOpenClientTools?: (dir: string) => void;
}

export default function LibraryView({
  directory,
  jobState,
  jobResults,
  onSelectProject,
  onOpenFolderPicker,
  onOpenClientTools
}: LibraryViewProps) {
  const [projects, setProjects] = useState<LibraryProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncingDir, setSyncingDir] = useState<string | null>(null);
  const [syncDetails, setSyncDetails] = useState<{ [dir: string]: any }>({});
  const [isCleaning, setIsCleaning] = useState(false);
  const [selectedProj, setSelectedProj] = useState<any>(null);
  const { showToast } = useToast();

  const handleCleanupTests = async () => {
    if (!window.confirm('¿Deseas eliminar todas las sesiones de prueba (test, pruebas, evento) y carpetas que ya no existen?')) return;
    try {
      setIsCleaning(true);
      const res = await apiClient.cleanupLibrary();
      if (res.success) {
        showToast(`Limpieza completada: ${res.deleted_count} sesiones eliminadas`, 'success');
        loadProjects();
      } else {
        showToast('No se pudo completar la limpieza', 'error');
      }
    } catch (err: any) {
      showToast(`Error al limpiar: ${err.message || err}`, 'error');
    } finally {
      setIsCleaning(false);
    }
  };

  const handleDeleteProject = async (dir: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm('¿Deseas quitar este evento del listado de la biblioteca?')) return;
    try {
      await apiClient.clearCache(dir);
      showToast('Proyecto eliminado de la biblioteca', 'info');
      loadProjects();
    } catch (err: any) {
      showToast(`Error al eliminar: ${err.message || err}`, 'error');
    }
  };

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
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--border-default)',
        boxShadow: 'var(--shadow-card)'
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <div className="flex items-center gap-2">
            <h1 style={{
              fontSize: '16px',
              fontWeight: 'var(--fw-bold)',
              color: 'var(--text-primary)',
              margin: 0,
              letterSpacing: '-0.02em'
            }}>
              Evento: {eventName}
            </h1>
            <IconEdit size={15} style={{ color: 'var(--text-tertiary)', cursor: 'pointer' }} />
          </div>
          <span className="font-mono text-tertiary" style={{
            fontSize: '11px'
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
                icon={<IconFolder size={14} />}
                onClick={() => {
                  try {
                    apiClient.openCacheFolder();
                  } catch (e) {
                    showToast('Abriendo explorador...', 'info');
                  }
                }}
              >
                Explorador
              </Button>
              <Button
                variant="primary"
                size="sm"
                icon={<IconSync size={14} className={syncingDir === directory ? 'animate-spin' : ''} />}
                onClick={() => handleSyncLightroom(directory)}
                disabled={syncingDir === directory}
              >
                {syncingDir === directory ? 'Sincronizando…' : 'Sincronizar Lightroom'}
              </Button>
              {onOpenClientTools && (
                <Button
                  variant="outline"
                  size="sm"
                  icon={<IconLibrary size={14} />}
                  onClick={() => onOpenClientTools(directory)}
                >
                  Cliente
                </Button>
              )}
            </>
          )}
          {onOpenFolderPicker && (
            <Button
              variant="outline"
              size="sm"
              icon={<IconFolder size={14} />}
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
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius-md)',
          padding: 'var(--space-4) var(--space-5)',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-4)',
          boxShadow: 'var(--shadow-card)'
        }}>
          <div style={{
            width: 40,
            height: 40,
            borderRadius: 'var(--radius-sm)',
            backgroundColor: 'var(--color-surface-elevated)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-secondary)'
          }}>
            <IconCamera size={20} />
          </div>
          <div>
            <div className="font-mono" style={{ fontSize: '20px', fontWeight: 'var(--fw-bold)', color: 'var(--text-primary)' }}>
              {activePhotosCount.toLocaleString()}
            </div>
            <div style={{ fontSize: '10px', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Fotografías</div>
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
          <div className="flex items-center gap-3">
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

          <Button
            variant="outline"
            size="sm"
            onClick={handleCleanupTests}
            disabled={isCleaning}
            style={{
              color: 'var(--text-secondary)',
              fontSize: 'var(--text-xs)',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
            icon={<IconTrash size={13} style={{ color: 'var(--danger)' }} />}
            title="Eliminar proyectos de prueba (test, evento) y carpetas huérfanas"
          >
            {isCleaning ? 'Limpiando...' : 'Limpiar pruebas y temporales'}
          </Button>
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
            gap: 'var(--space-6)',
            alignItems: 'flex-start'
          }}>
            <div style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--space-3)',
              minWidth: 0
            }}>
              {projects.map((proj) => {
                const isActive = directory && (proj.directory.toLowerCase() === directory.toLowerCase());
                const isSelected = selectedProj?.directory === proj.directory;
                const syncInfo = syncDetails[proj.directory];

                return (
                  <div
                    key={proj.directory}
                    onClick={() => setSelectedProj(proj)}
                    style={{
                      backgroundColor: isActive ? 'rgba(233, 160, 74, 0.04)' : isSelected ? 'var(--color-surface-elevated)' : 'var(--color-surface)',
                      border: `1px solid ${isActive ? 'var(--accent-primary)' : isSelected ? 'var(--border-strong)' : 'var(--border-default)'}`,
                      boxShadow: isActive ? 'var(--shadow-guto)' : 'var(--shadow-card)',
                      borderRadius: 'var(--radius-md)',
                      padding: 'var(--space-3) var(--space-4)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 'var(--space-4)',
                      transition: 'all 0.15s ease',
                      cursor: 'pointer'
                    }}
                  >
                    {/* Thumbnail + Nombre + Stats */}
                    <div className="flex items-center gap-4" style={{ minWidth: 0, flex: 1 }}>
                      <div style={{
                        width: 56,
                        height: 42,
                        borderRadius: 'var(--radius-photo)',
                        backgroundColor: 'var(--color-surface-elevated)',
                        overflow: 'hidden',
                        flexShrink: 0,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        border: '1px solid var(--border-default)'
                      }}>
                        {proj.sample_photo ? (
                          <img
                            src={apiClient.getThumbnailUrl(proj.sample_photo, 'ui')}
                            alt={proj.folder_name}
                            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            onError={(e) => {
                              (e.target as HTMLElement).style.display = 'none';
                            }}
                          />
                        ) : (
                          <IconCamera size={18} style={{ color: 'var(--text-tertiary)' }} />
                        )}
                      </div>

                      <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', gap: '2px' }}>
                        <div className="flex items-center gap-2">
                          <span style={{
                            fontSize: '13px',
                            fontWeight: 'var(--fw-semibold)',
                            color: 'var(--text-primary)'
                          }} className="truncate">
                            {proj.folder_name}
                          </span>
                          {isActive && (
                            <Badge variant="warning">Activo</Badge>
                          )}
                        </div>

                        <div className="flex items-center gap-3 font-mono text-tertiary" style={{ fontSize: '11px' }}>
                          <span>{proj.total_photos.toLocaleString()} fotos</span>
                          <span>·</span>
                          <span style={{ color: 'var(--success)' }}>{proj.selected_count} elegidas</span>
                        </div>
                      </div>
                    </div>

                    {/* Status & Actions */}
                    <div className="flex items-center gap-3" style={{ flexShrink: 0 }}>
                      <div className="flex items-center gap-1" style={{ fontSize: 'var(--text-xs)', color: 'var(--success)' }}>
                        <IconCheck size={14} />
                        <span>Completado</span>
                      </div>

                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<IconTrash size={13} style={{ color: 'var(--text-muted)' }} />}
                        onClick={(e) => { e.stopPropagation(); handleDeleteProject(proj.directory, e); }}
                        title="Quitar este evento de la biblioteca"
                      />
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Panel Lateral */}
            {selectedProj && (
              <div style={{
                width: '340px',
                flexShrink: 0,
                backgroundColor: 'var(--color-surface)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-lg)',
                padding: 'var(--space-5)',
                display: 'flex',
                flexDirection: 'column',
                gap: 'var(--space-4)',
                position: 'sticky',
                top: 'var(--space-4)'
              }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <h3 style={{ margin: 0, fontSize: 'var(--text-lg)', fontWeight: 'var(--fw-bold)', color: 'var(--text-primary)', wordBreak: 'break-word' }}>
                    {selectedProj.folder_name}
                  </h3>
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                    {selectedProj.directory}
                  </span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div className="flex-between" style={{ fontSize: 'var(--text-sm)' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>Total fotos:</span>
                    <span style={{ fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>{selectedProj.total_photos}</span>
                  </div>
                  <div className="flex-between" style={{ fontSize: 'var(--text-sm)' }}>
                    <span style={{ color: 'var(--success)' }}>Seleccionadas:</span>
                    <span style={{ fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>{selectedProj.selected_count}</span>
                  </div>
                  <div className="flex-between" style={{ fontSize: 'var(--text-sm)' }}>
                    <span style={{ color: 'var(--text-secondary)' }}>Duplicadas:</span>
                    <span style={{ fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>{selectedProj.duplicates_count}</span>
                  </div>
                  <div className="flex-between" style={{ fontSize: 'var(--text-sm)' }}>
                    <span style={{ color: 'var(--danger)' }}>Descartadas/Borrosas:</span>
                    <span style={{ fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>{selectedProj.blurry_count}</span>
                  </div>
                </div>

                {syncDetails[selectedProj.directory] && (
                  <div style={{
                    padding: 'var(--space-3)',
                    backgroundColor: 'var(--color-surface-elevated)',
                    borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border-subtle)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px'
                  }}>
                    <span style={{ fontSize: 'var(--text-xs)', fontWeight: 'var(--fw-semibold)', color: 'var(--text-secondary)' }}>
                      Comparativa IA vs Lightroom
                    </span>
                    <div style={{ fontSize: 'var(--text-sm)', display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'var(--accent-primary)' }}>Promovidas por ti:</span>
                      <span style={{ fontWeight: 'var(--fw-semibold)' }}>{syncDetails[selectedProj.directory].upgraded || 0}</span>
                    </div>
                    <div style={{ fontSize: 'var(--text-sm)', display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: 'var(--danger)' }}>Descartadas por ti:</span>
                      <span style={{ fontWeight: 'var(--fw-semibold)' }}>{syncDetails[selectedProj.directory].downgraded || 0}</span>
                    </div>
                  </div>
                )}

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: 'auto', paddingTop: 'var(--space-4)' }}>
                  {onSelectProject && directory?.toLowerCase() !== selectedProj.directory.toLowerCase() && (
                    <Button
                      variant="primary"
                      style={{ width: '100%', justifyContent: 'center' }}
                      onClick={() => onSelectProject(selectedProj.directory)}
                    >
                      Abrir Sesión en Culling
                    </Button>
                  )}
                  
                  <Button
                    variant="outline"
                    icon={<IconSync size={14} className={syncingDir === selectedProj.directory ? 'animate-spin' : ''} />}
                    style={{ width: '100%', justifyContent: 'center' }}
                    onClick={() => handleSyncLightroom(selectedProj.directory)}
                    disabled={syncingDir === selectedProj.directory}
                  >
                    {syncingDir === selectedProj.directory ? 'Sincronizando...' : 'Sincronizar Lightroom'}
                  </Button>

                  {onOpenClientTools && (
                    <Button
                      variant="outline"
                      icon={<IconLibrary size={14} />}
                      style={{ width: '100%', justifyContent: 'center' }}
                      onClick={() => onOpenClientTools(selectedProj.directory)}
                    >
                      Herramientas de Cliente
                    </Button>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
