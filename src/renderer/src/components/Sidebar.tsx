import React, { useState } from 'react';
import { IconFolder, IconSettings, IconGrid, IconDuel } from './icons';

interface SidebarProps {
  backendStatus: string;
  hardwareInfo: any;
  jobState: any;
  onOpenSettings: () => void;
  onStartIngest: (directory: string, mode?: string) => void;
  currentView: 'grid' | 'duel';
  onViewChange: (view: 'grid' | 'duel') => void;
  hasResults: boolean;
}

export default function Sidebar({
  backendStatus,
  hardwareInfo,
  jobState,
  onOpenSettings,
  onStartIngest,
  currentView,
  onViewChange,
  hasResults
}: SidebarProps) {
  const [folderInput, setFolderInput] = useState('\\\\MYCLOUDEX2ULTRA\\Public\\Guto Gutierrez\\');

  const handleSelectFolder = async () => {
    if (window.api.selectFolder) {
      const selected = await window.api.selectFolder(folderInput || undefined);
      if (selected) {
        setFolderInput(selected);
      }
    }
  };

  const handleStart = (mode: string) => {
    if (folderInput.trim()) {
      onStartIngest(folderInput.trim(), mode);
    }
  };

  return (
    <div style={{
      width: '280px',
      backgroundColor: 'var(--bg-secondary)',
      borderRight: '1px solid var(--border-subtle)',
      display: 'flex',
      flexDirection: 'column',
      padding: '24px 16px',
      gap: '24px',
      zIndex: 10
    }}>
      {/* Brand — wordmark Guto Flow */}
      <div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
          <span style={{
            fontFamily: 'Georgia, "Times New Roman", serif',
            fontWeight: 700, fontSize: '1.7rem', lineHeight: 1,
            color: 'var(--accent-primary)', letterSpacing: '-0.02em',
          }}>
            guto
          </span>
          <span style={{
            fontFamily: '"Segoe Script", "Brush Script MT", cursive',
            fontSize: '1.45rem', lineHeight: 1,
            color: 'var(--text-primary)',
          }}>
            Flow
          </span>
        </div>
        <p style={{
          color: 'var(--text-muted)', fontSize: '0.72rem', marginTop: '6px',
          borderTop: '1px solid var(--border-strong)', paddingTop: '4px',
          textTransform: 'uppercase', letterSpacing: '0.14em', fontWeight: 600,
        }}>
          Smart Workflow
        </p>
      </div>

      {/* Connection Status */}
      <div className="glass-panel" style={{ padding: '12px', fontSize: '0.85rem' }}>
        <div className="flex-between" style={{ marginBottom: '8px' }}>
          <span style={{ color: 'var(--text-secondary)' }}>Backend Engine</span>
          <span style={{ 
            color: backendStatus === 'running' ? 'var(--status-selected-text)' : 'var(--status-blurry-text)',
            display: 'flex',
            alignItems: 'center',
            gap: '6px'
          }}>
            <span style={{ 
              display: 'inline-block', 
              width: '8px', height: '8px', 
              borderRadius: '50%', 
              backgroundColor: 'currentColor' 
            }} />
            {backendStatus === 'running' ? 'Online' : backendStatus}
          </span>
        </div>
        {hardwareInfo && (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
            Hardware: {hardwareInfo.using_gpu ? hardwareInfo.gpu_provider : 'CPU Mode'} 
            ({hardwareInfo.physical_cores} Cores)
          </div>
        )}
      </div>

      {/* Start Job Area */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <h3 style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          New Session
        </h3>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border-strong)',
            borderRadius: 'var(--radius-md)',
            padding: '8px 12px',
            gap: '8px'
          }}>
            <div 
              onClick={handleSelectFolder}
              style={{ 
                cursor: 'pointer', 
                display: 'flex', 
                alignItems: 'center', 
                padding: '4px',
                borderRadius: '4px'
              }}
              className="hover-bg-secondary"
              title="Browse Folder"
            >
              <IconFolder size={18} className="text-primary" style={{ color: 'var(--accent-primary)' }} />
            </div>
            <input 
              type="text" 
              placeholder="C:\Photos\Wedding..."
              value={folderInput}
              onChange={(e) => setFolderInput(e.target.value)}
              style={{
                flex: 1,
                background: 'transparent',
                border: 'none',
                color: 'var(--text-primary)',
                outline: 'none',
                fontSize: '0.9rem'
              }}
            />
          </div>
          
          <button
            className="btn btn-primary"
            onClick={() => handleStart('cull_edit')}
            disabled={!folderInput.trim() || backendStatus !== 'running' || jobState?.status === 'running'}
            style={{ width: '100%', padding: '12px' }}
          >
            {jobState?.status === 'running' ? 'Procesando...' : 'Culling + Edición'}
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => handleStart('cull')}
            disabled={!folderInput.trim() || backendStatus !== 'running' || jobState?.status === 'running'}
            style={{ width: '100%', padding: '10px' }}
            title="Solo selecciona (labels/estrellas). Revisas, haces duelos, y aplicas la edición después con un clic."
          >
            Solo Culling
          </button>
        </div>
      </div>

      {/* View Toggles (only if we have results) */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', opacity: hasResults ? 1 : 0.3, pointerEvents: hasResults ? 'auto' : 'none' }}>
        <h3 style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          View Mode
        </h3>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button 
            className={`btn ${currentView === 'grid' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => onViewChange('grid')}
            style={{ flex: 1 }}
          >
            <IconGrid size={16} /> Grid
          </button>
          <button 
            className={`btn ${currentView === 'duel' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => onViewChange('duel')}
            style={{ flex: 1 }}
          >
            <IconDuel size={16} /> Duel
          </button>
        </div>
      </div>

      <div style={{ flex: 1 }} />

      {/* Settings */}
      <button className="btn btn-secondary" onClick={onOpenSettings} style={{ justifyContent: 'flex-start' }}>
        <IconSettings size={18} />
        Settings & Preferences
      </button>
    </div>
  );
}
