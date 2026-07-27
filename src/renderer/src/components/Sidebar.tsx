import React, { useState } from 'react';
import { IconFolder, IconSettings, IconGrid, IconDuel } from './icons';
import LearningPanel from './LearningPanel';

interface SidebarProps {
  backendStatus: string;
  hardwareInfo: any;
  jobState: any;
  onOpenSettings: () => void;
  onStartIngest: (directory: string, mode?: string) => void;
  currentView: 'grid' | 'duel' | 'calib';
  onViewChange: (view: 'grid' | 'duel' | 'calib') => void;
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
      {/* Brand — wordmark Guto Flow con Glow */}
      <div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
          <span style={{
            fontFamily: 'Georgia, "Times New Roman", serif',
            fontWeight: 700, fontSize: '1.8rem', lineHeight: 1,
            color: 'var(--accent-primary)', letterSpacing: '-0.02em',
            textShadow: '0 0 16px rgba(245, 158, 11, 0.4)'
          }}>
            guto
          </span>
          <span style={{
            fontFamily: '"Segoe Script", "Brush Script MT", cursive',
            fontSize: '1.5rem', lineHeight: 1,
            color: 'var(--text-primary)',
          }}>
            Flow
          </span>
        </div>
        <p style={{
          color: 'var(--text-secondary)', fontSize: '0.7rem', marginTop: '6px',
          borderTop: '1px solid var(--border-strong)', paddingTop: '6px',
          textTransform: 'uppercase', letterSpacing: '0.16em', fontWeight: 600,
        }}>
          Smart Workflow Pro
        </p>
      </div>

      {/* Panel de Aprendizaje de IA */}
      <LearningPanel active={backendStatus === 'running'} />

      {/* Indicador de Motor IA Neón */}
      <div className="flex-between" style={{ fontSize: '0.74rem', color: 'var(--text-secondary)', padding: '6px 10px', backgroundColor: 'var(--bg-primary)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}
        title={hardwareInfo
          ? `${hardwareInfo.using_gpu ? hardwareInfo.gpu_provider : 'CPU'} · ${hardwareInfo.physical_cores} núcleos`
          : ''}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className={backendStatus === 'running' ? 'pulse-indicator' : ''} style={{
            display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%',
            backgroundColor: backendStatus === 'running'
              ? 'var(--status-selected-text)' : 'var(--status-blurry-text)',
          }} />
          Motor {backendStatus === 'running' ? 'IA Activo' : backendStatus}
        </span>
        {hardwareInfo && (
          <span>{hardwareInfo.using_gpu ? hardwareInfo.gpu_provider : 'CPU'} ({hardwareInfo.physical_cores}c)</span>
        )}
      </div>

      {/* Área de Nueva Sesión */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <h3 style={{ fontSize: '0.82rem', color: 'var(--text-primary)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700 }}>
          Nueva sesión
        </h3>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            backgroundColor: 'var(--bg-primary)',
            border: '1px solid var(--border-strong)',
            borderRadius: 'var(--radius-md)',
            padding: '8px 12px',
            gap: '8px',
            transition: 'all var(--transition-fast)'
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
              title="Elegir carpeta"
            >
              <IconFolder size={18} style={{ color: 'var(--accent-primary)' }} />
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
                fontSize: '0.85rem'
              }}
            />
          </div>
          
          <button
            className="btn btn-primary"
            onClick={() => handleStart('cull_edit')}
            disabled={!folderInput.trim() || backendStatus !== 'running' || jobState?.status === 'running'}
            style={{ width: '100%', padding: '12px' }}
          >
            {jobState?.status === 'running' ? 'Procesando…' : 'Culling + edición'}
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => handleStart('cull')}
            disabled={!folderInput.trim() || backendStatus !== 'running' || jobState?.status === 'running'}
            style={{ width: '100%', padding: '10px' }}
            title="Solo selecciona (labels/estrellas). Revisas, haces duelos, y aplicas la edición después con un clic."
          >
            Solo culling
          </button>
        </div>
      </div>

      {/* Modos de Vista */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', opacity: hasResults ? 1 : 0.35, pointerEvents: hasResults ? 'auto' : 'none' }}>
        <h3 style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          Modo de vista
        </h3>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button 
            className={`btn ${currentView === 'grid' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => onViewChange('grid')}
            style={{ flex: 1 }}
          >
            <IconGrid size={16} /> Cuadrícula
          </button>
          <button
            className={`btn ${currentView === 'duel' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => onViewChange('duel')}
            style={{ flex: 1 }}
          >
            <IconDuel size={16} /> Comparar
          </button>
        </div>
        <button
          className={`btn ${currentView === 'calib' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => onViewChange('calib')}
          style={{ width: '100%' }}
          title="Enséñale tu criterio: ojos, mirada y sonrisa, cara por cara"
        >
          ◎ Calibración
        </button>
      </div>

      <div style={{ flex: 1 }} />

      {/* Ajustes */}
      <button className="btn btn-secondary" onClick={onOpenSettings} style={{ justifyContent: 'flex-start' }}>
        <IconSettings size={18} />
        Ajustes y preferencias
      </button>
    </div>
  );
}
