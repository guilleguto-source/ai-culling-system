import React from 'react';
import { IconGrid, IconDuel, IconBrain, IconLibrary } from './icons';
import { Tooltip } from './ui/Tooltip';

interface SidebarProps {
  backendStatus: string;
  hardwareInfo: any;
  jobState: any;
  onStartIngest: (directory: string, mode?: string) => void;
  currentView: 'library' | 'grid' | 'duel' | 'calib';
  onViewChange: (view: 'library' | 'grid' | 'duel' | 'calib') => void;
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
      <div style={{ padding: 'var(--space-6) var(--space-5) var(--space-4) var(--space-5)' }}>
        <div className="flex items-center gap-2">
          <span style={{
            fontSize: '18px',
            fontWeight: 'var(--fw-bold)',
            letterSpacing: '0.04em',
            color: 'var(--text-primary)',
            textTransform: 'uppercase'
          }}>
            GUTO <span style={{ color: 'var(--accent-primary)' }}>FLOW</span>
          </span>
        </div>
        <div style={{
          fontSize: '9px',
          fontWeight: 'var(--fw-medium)',
          color: 'var(--text-tertiary)',
          letterSpacing: '0.12em',
          marginTop: '4px',
          textTransform: 'uppercase'
        }}>
          Digital Darkroom
        </div>
      </div>

      {/* Navigation Groups */}
      <nav style={{ flex: 1, display: 'flex', flexDirection: 'column', paddingTop: 'var(--space-2)' }}>
        <div className="sidebar-section-title">Espacio de Trabajo</div>

        <button
          className={`sidebar-nav-item ${currentView === 'library' ? 'active' : ''}`}
          onClick={() => onViewChange('library')}
          aria-label="Biblioteca de Sesiones"
          style={{ justifyContent: 'space-between' }}
        >
          <div className="flex items-center gap-3">
            <IconLibrary size={16} />
            <span>Biblioteca</span>
          </div>
          <span className="font-mono text-tertiary" style={{ fontSize: '10px', opacity: 0.6 }}>1</span>
        </button>
        
        <button
          className={`sidebar-nav-item ${currentView === 'grid' ? 'active' : ''}`}
          onClick={() => onViewChange('grid')}
          aria-label="Culling Grid"
          style={{ justifyContent: 'space-between' }}
        >
          <div className="flex items-center gap-3">
            <IconGrid size={16} />
            <span>Culling</span>
          </div>
          <span className="font-mono text-tertiary" style={{ fontSize: '10px', opacity: 0.6 }}>2</span>
        </button>

        <button
          className={`sidebar-nav-item ${currentView === 'duel' ? 'active' : ''}`}
          onClick={() => onViewChange('duel')}
          aria-label="Comparar Ráfagas"
          style={{ justifyContent: 'space-between' }}
        >
          <div className="flex items-center gap-3">
            <IconDuel size={16} />
            <span>Comparar</span>
          </div>
          <span className="font-mono text-tertiary" style={{ fontSize: '10px', opacity: 0.6 }}>3</span>
        </button>

        <div className="sidebar-section-title" style={{ marginTop: 'var(--space-5)' }}>Inteligencia</div>

        <button
          className={`sidebar-nav-item ${currentView === 'calib' ? 'active' : ''}`}
          onClick={() => onViewChange('calib')}
          aria-label="Tu Estilo y Calibración"
          style={{ justifyContent: 'space-between' }}
        >
          <div className="flex items-center gap-3">
            <IconBrain size={16} />
            <span>Tu Estilo</span>
          </div>
          <span className="font-mono text-tertiary" style={{ fontSize: '10px', opacity: 0.6 }}>4</span>
        </button>
      </nav>

      {/* Footer Controls & Local AI Engine Status */}
      <div style={{
        padding: 'var(--space-4) var(--space-5)',
        borderTop: '1px solid var(--border-default)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-3)'
      }}>
        <Tooltip
          content="Procesamiento 100% local en este equipo."
          position="top"
        >
          <div
            className="flex items-center gap-2"
            style={{
              padding: '6px 10px',
              backgroundColor: 'var(--color-surface-elevated)',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-default)',
              cursor: 'default'
            }}
          >
            <span className={`gf-dot ${isAiActive ? 'gf-dot-active' : 'gf-dot-inactive'}`} />
            <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
              <span style={{ fontSize: '10px', fontWeight: 'var(--fw-semibold)', color: 'var(--text-primary)', letterSpacing: '0.04em' }}>
                MOTOR LOCAL
              </span>
              <span style={{ fontSize: '9px', color: 'var(--text-tertiary)' }} className="truncate font-mono">
                {isAiActive ? `Activo · ${hwProvider}` : 'Inactivo'}
              </span>
            </div>
          </div>
        </Tooltip>
      </div>
    </aside>
  );
}
