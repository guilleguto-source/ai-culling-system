import React from 'react';
import { IconSettings, IconHelp, IconLibrary } from './icons';
import { Tooltip } from './ui/Tooltip';

interface TopbarProps {
  currentView: string;
  directory?: string;
  jobState?: any;
  jobResults?: any;
  onOpenSettings: () => void;
  onOpenShortcuts?: () => void;
  onOpenClientTools?: () => void;
}

export const Topbar: React.FC<TopbarProps> = ({
  currentView,
  directory = '',
  jobState,
  jobResults,
  onOpenSettings,
  onOpenShortcuts,
  onOpenClientTools
}) => {
  const isProcessing = jobState?.status === 'processing';
  const progressPercent = jobState?.progress
    ? Math.round(
        typeof jobState.progress === 'object'
          ? (jobState.progress.percent ?? 0)
          : Number(jobState.progress) || 0
      )
    : 0;

  // Extract folder name from directory path
  const folderName = directory
    ? (directory || '').replace(/\\/g, '/').split('/').filter(Boolean).pop() || directory
    : '';

  const totalPhotos = jobResults?.summary?.total ?? (jobResults?.results?.length ?? 0);
  const totalClusters = jobResults?.summary?.clusters ?? (
    jobResults?.results
      ? new Set(jobResults.results.map((r: any) => r.cluster_id)).size
      : 0
  );

  const renderViewContext = () => {
    switch (currentView) {
      case 'library':
        return (
          <div className="flex items-center gap-2">
            <span style={{ fontSize: '15px', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
              Biblioteca de Sesiones
            </span>
            <span className="text-tertiary" style={{ fontSize: 'var(--text-xs)' }}>
              · Historial y Sincronización
            </span>
          </div>
        );
      case 'duel':
        return (
          <div className="flex items-center gap-2">
            <span style={{ fontSize: '15px', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
              Comparar Ráfagas
            </span>
            {totalClusters > 0 && (
              <span className="text-secondary font-mono" style={{ fontSize: 'var(--text-xs)' }}>
                · {totalClusters} grupos detectados
              </span>
            )}
          </div>
        );
      case 'calib':
      case 'style':
        return (
          <div className="flex items-center gap-2">
            <span style={{ fontSize: '15px', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
              Tu Estilo
            </span>
            <span className="text-tertiary" style={{ fontSize: 'var(--text-xs)' }}>
              · Perfil fotográfico aprendido
            </span>
          </div>
        );
      case 'grid':
      default:
        return (
          <div className="flex items-center gap-2.5">
            <span style={{ fontSize: '15px', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
              {folderName ? folderName : 'Culling Workspace'}
            </span>
            {totalPhotos > 0 && (
              <div className="flex items-center gap-1.5 font-mono text-secondary" style={{ fontSize: 'var(--text-xs)' }}>
                <span className="text-tertiary">·</span>
                <span>{totalPhotos.toLocaleString()} fotos</span>
                {totalClusters > 0 && (
                  <>
                    <span className="text-tertiary">·</span>
                    <span>{totalClusters} ráfagas</span>
                  </>
                )}
              </div>
            )}
          </div>
        );
    }
  };

  return (
    <header className="topbar-container">
      {/* View & Session Context */}
      <div className="flex items-center gap-3">
        {renderViewContext()}
      </div>

      {/* Quick Actions & Processing Indicator */}
      <div className="flex items-center gap-3">
        {isProcessing && (
          <div className="flex items-center gap-2 text-xs font-mono" style={{ color: 'var(--accent-primary)', marginRight: '4px' }}>
            <span className="gf-dot gf-dot-warning" />
            <span>{progressPercent}%</span>
          </div>
        )}

        {onOpenShortcuts && (
          <Tooltip content="Atajos de teclado (?)" position="bottom">
            <button
              className="gf-btn gf-btn-ghost gf-btn-sm"
              onClick={onOpenShortcuts}
              aria-label="Atajos de teclado"
              style={{ padding: '6px 8px' }}
            >
              <IconHelp size={15} />
            </button>
          </Tooltip>
        )}

        {onOpenClientTools && (
          <Tooltip content="Herramientas de Cliente" position="bottom">
            <button
              className="gf-btn gf-btn-ghost gf-btn-sm"
              onClick={onOpenClientTools}
              aria-label="Herramientas Cliente"
              style={{ gap: '6px', color: 'var(--accent-primary)' }}
            >
              <IconLibrary size={15} />
              <span style={{ fontSize: 'var(--text-xs)', fontWeight: 'var(--fw-medium)' }}>Cliente</span>
            </button>
          </Tooltip>
        )}

        <Tooltip content="Configuración y DAM" position="bottom">
          <button
            className="gf-btn gf-btn-ghost gf-btn-sm"
            onClick={onOpenSettings}
            aria-label="Configuración"
            style={{ gap: '6px' }}
          >
            <IconSettings size={15} />
            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 'var(--fw-medium)' }}>Ajustes</span>
          </button>
        </Tooltip>
      </div>

      {/* 2px Progress Line during processing */}
      {isProcessing && (
        <div className="topbar-progress-line">
          <div
            className="topbar-progress-fill"
            style={{ width: `${Math.max(2, Math.min(100, progressPercent))}%` }}
          />
        </div>
      )}
    </header>
  );
};

export default Topbar;
