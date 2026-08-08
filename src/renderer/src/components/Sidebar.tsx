import React from 'react';
import { IconGrid, IconDuel, IconBrain } from './icons';
import { Tooltip } from './ui/Tooltip';

interface SidebarProps {
  backendStatus: string;
  hardwareInfo: any;
  jobState: any;
  onStartIngest: (directory: string, mode?: string) => void;
  currentView: 'grid' | 'duel' | 'calib';
  onViewChange: (view: 'grid' | 'duel' | 'calib') => void;
  hasResults: boolean;
  lastDirectory?: string;
  onDirectoryChange?: (dir: string) => void;
  undoAvailable?: boolean;
  onUndoExport?: (dir: string) => Promise<void>;
}

export default function Sidebar({
  backendStatus,
  hardwareInfo,
  currentView,
  onViewChange,
}: SidebarProps) {
  const isAiActive = backendStatus === 'running';
  const isGpu = hardwareInfo?.using_gpu;
  const hwProvider = hardwareInfo?.gpu_provider || (isGpu ? 'NVIDIA' : 'CPU');

  return (
    <aside className="sidebar-container">
      {/* Brand Header */}
      <div style={{ padding: 'var(--space-5) var(--space-4) var(--space-3) var(--space-4)' }}>
        <div className="flex items-center gap-2">
          <span style={{
            fontSize: 'var(--text-xl)',
            fontWeight: 'var(--fw-bold)',
            letterSpacing: '-0.5px',
            color: 'var(--text-primary)'
          }}>
            guto<span style={{ color: 'var(--accent-primary)', marginLeft: '3px' }}>Flow</span>
          </span>
        </div>
        <div style={{
          fontSize: '10px',
          fontWeight: 'var(--fw-semibold)',
          color: 'var(--text-muted)',
          letterSpacing: '1px',
          marginTop: '2px',
          textTransform: 'uppercase'
        }}>
          Smart Workflow Pro
        </div>
      </div>

      {/* Navigation Groups */}
      <nav style={{ flex: 1, display: 'flex', flexDirection: 'column', paddingTop: 'var(--space-2)' }}>
        <div className="sidebar-section-title">Workspace</div>
        
        <button
          className={`sidebar-nav-item ${currentView === 'grid' ? 'active' : ''}`}
          onClick={() => onViewChange('grid')}
          aria-label="Culling Grid"
        >
          <IconGrid size={17} />
          <span>Culling</span>
        </button>

        <button
          className={`sidebar-nav-item ${currentView === 'duel' ? 'active' : ''}`}
          onClick={() => onViewChange('duel')}
          aria-label="Comparar Ráfagas"
        >
          <IconDuel size={17} />
          <span>Comparar</span>
        </button>

        <div className="sidebar-section-title" style={{ marginTop: 'var(--space-4)' }}>Intelligence</div>

        <button
          className={`sidebar-nav-item ${currentView === 'calib' ? 'active' : ''}`}
          onClick={() => onViewChange('calib')}
          aria-label="Tu Estilo y Calibración"
        >
          <IconBrain size={17} />
          <span>Tu Estilo</span>
        </button>
      </nav>

      {/* Footer Controls & Local AI Engine Status */}
      <div style={{
        padding: 'var(--space-3) var(--space-4)',
        borderTop: '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-3)'
      }}>
        <Tooltip
          content="Procesamiento 100% local. Tus fotografías no salen de este equipo."
          position="top"
        >
          <div
            className="flex items-center gap-2"
            style={{
              padding: '6px 8px',
              backgroundColor: 'var(--color-surface-elevated)',
              borderRadius: 'var(--radius-xs)',
              border: '1px solid var(--border-subtle)',
              cursor: 'default'
            }}
          >
            <span className={`gf-dot ${isAiActive ? 'gf-dot-active' : 'gf-dot-inactive'}`} />
            <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
              <span style={{ fontSize: '11px', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)' }}>
                LOCAL AI
              </span>
              <span style={{ fontSize: '10px', color: 'var(--text-muted)' }} className="truncate">
                {isAiActive ? `Activo · ${hwProvider}` : 'Detenido'}
              </span>
            </div>
          </div>
        </Tooltip>
      </div>
    </aside>
  );
}
