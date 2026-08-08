import React from 'react';
import { IconSettings, IconHelp } from './icons';
import { Tooltip } from './ui/Tooltip';

interface TopbarProps {
  currentView: string;
  directory?: string;
  jobState?: any;
  jobResults?: any;
  onOpenSettings: () => void;
  onOpenShortcuts?: () => void;
}

export const Topbar: React.FC<TopbarProps> = ({
  currentView,
  directory = '',
  jobState,
  jobResults,
  onOpenSettings,
  onOpenShortcuts
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
    ? directory.replace(/\\/g, '/').split('/').filter(Boolean).pop() || directory
    : '';

  const totalPhotos = jobResults?.summary?.total ?? (jobResults?.results?.length ?? 0);
  const totalClusters = jobResults?.summary?.clusters ?? (
    jobResults?.results
      ? new Set(jobResults.results.map((r: any) => r.cluster_id)).size
      : 0
  );

  const renderViewContext = () => {
    switch (currentView) {
      case 'duel':
        return (
          <div className="flex items-center gap-2">
            <span style={{ fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>
              Comparar Ráfagas
            </span>
            {totalClusters > 0 && (
              <span className="text-secondary" style={{ fontSize: 'var(--text-sm)' }}>
                · {totalClusters} grupos detectados
              </span>
            )}
          </div>
        );
      case 'calib':
      case 'style':
        return (
          <div className="flex items-center gap-2">
            <span style={{ fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>
              Tu Estilo
            </span>
            <span className="text-tertiary" style={{ fontSize: 'var(--text-sm)' }}>
              · Perfil fotográfico aprendido
            </span>
          </div>
        );
      case 'grid':
      default:
        return (
          <div className="flex items-center gap-2">
            <span style={{ fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>
              {folderName ? folderName : 'Culling Workspace'}
            </span>
            {totalPhotos > 0 && (
              <span className="text-secondary text-mono" style={{ fontSize: 'var(--text-sm)' }}>
                · {totalPhotos.toLocaleString()} fotografías
                {totalClusters > 0 ? ` · ${totalClusters} ráfagas` : ''}
              </span>
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

      {/* Quick Actions */}
      <div className="flex items-center gap-2">
        {onOpenShortcuts && (
          <Tooltip content="Atajos de teclado (?)" position="bottom">
            <button
              className="gf-btn gf-btn-ghost gf-btn-sm"
              onClick={onOpenShortcuts}
              aria-label="Atajos de teclado"
              style={{ padding: '6px' }}
            >
              <IconHelp size={16} />
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
            <IconSettings size={16} />
            <span style={{ fontSize: 'var(--text-sm)' }}>Ajustes</span>
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
