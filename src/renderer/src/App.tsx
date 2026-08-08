import React, { useState, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import Topbar from './components/Topbar';
import MainContent from './components/MainContent';
import SettingsModal from './components/SettingsModal';
import ShortcutsModal from './components/ShortcutsModal';
import SyncReminder from './components/SyncReminder';
import { ModelDownloadWizard } from './components/ModelDownloadWizard';
import { ToastProvider, useToast } from './components/Toast';
import { apiClient, BACKEND_URL } from './api/client';
import './index.css';

// Fallback for browser testing connected to real FastAPI backend
if (typeof window !== 'undefined' && !window.api) {
  (window as any).api = {
    getBackendStatus: async () => {
      try {
        const res = await apiClient.getHealth();
        return { running: true, status: 'running', url: BACKEND_URL };
      } catch (e) {
        return { running: false, status: 'stopped', url: BACKEND_URL };
      }
    },
    getHardwareInfo: async () => {
      try {
        return await apiClient.getHardware();
      } catch (e) {
        return { using_gpu: false, gpu_provider: null, physical_cores: 0, logical_cores: 0 };
      }
    },
    sendSettings: async (settings: any) => {
      return await apiClient.saveSettings(settings);
    },
    getSettings: async () => {
      return await apiClient.getSettings();
    },
    ingestMedia: async (directory: string, mode: string = 'cull_edit') => {
      return await apiClient.startIngest(directory, mode as any);
    },
    getJobStatus: async () => {
      return await apiClient.getStatus();
    },
    getJobResults: async () => {
      return await apiClient.getResults();
    },
    checkUndoAvailable: async (directory: string) => {
      try {
        return await apiClient.checkUndo(directory);
      } catch (e) {
        return { disponible: false };
      }
    },
    undoExport: async (directory: string) => {
      return await apiClient.undoExport(directory);
    },
    selectFolder: async (_defaultPath?: string) => {
      return null;
    },
    onBackendLog: (_cb: any) => {
      return () => {};
    },
    onBackendStatusChange: (cb: any) => {
      const interval = setInterval(async () => {
        try {
          const res = await apiClient.getHealth();
          cb(res ? 'running' : 'stopped');
        } catch (e) {
          cb('stopped');
        }
      }, 2000);
      return () => clearInterval(interval);
    }
  };
}

function MainApp() {
  const [backendStatus, setBackendStatus] = useState<'starting' | 'running' | 'stopped' | 'error' | 'unknown'>('unknown');
  const [hardwareInfo, setHardwareInfo] = useState<any>(null);
  const [settings, setSettings] = useState<any>(null);
  
  const [jobState, setJobState] = useState<any>(null);
  const [jobResults, setJobResults] = useState<any>(null);
  
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [currentView, setCurrentView] = useState<'grid' | 'duel' | 'calib'>('grid');
  const [lastDirectory, setLastDirectory] = useState<string>(() => localStorage.getItem('lastDirectory') || '');
  const [undoAvailable, setUndoAvailable] = useState<boolean>(false);
  const [staleBackend, setStaleBackend] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [showModelWizard, setShowModelWizard] = useState(false);
  const [isShortcutsOpen, setIsShortcutsOpen] = useState(false);
  const { showToast } = useToast();

  useEffect(() => {
    const handleGlobalKeys = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT' || (e.target as HTMLElement)?.tagName === 'TEXTAREA') return;
      if (e.key === '?' || (e.shiftKey && e.key === '/')) {
        e.preventDefault();
        setIsShortcutsOpen(prev => !prev);
      }
    };
    window.addEventListener('keydown', handleGlobalKeys);
    return () => window.removeEventListener('keydown', handleGlobalKeys);
  }, []);

  // El backend corre desde que se abre la app: si el código en disco cambió
  // después (actualización), este proceso sirve lógica vieja sin avisar.
  useEffect(() => {
    const check = async () => {
      try {
        const d = await apiClient.getHealth();
        setStaleBackend(!!d.stale_code);
      } catch { /* backend caído: ya lo muestra el status normal */ }
    };
    check();
    const t = setInterval(check, 30000);
    return () => clearInterval(t);
  }, []);

  // 1. Initialize backend connection & hardware info
  useEffect(() => {
    const init = async () => {
      try {
        const statusRes = await window.api.getBackendStatus();
        setBackendStatus(statusRes.status as any);
        
        if (statusRes.running) {
          const hw = await window.api.getHardwareInfo();
          setHardwareInfo(hw);
          const st = await window.api.getSettings();
          setSettings(st);
        }
      } catch (err) {
        console.error('Failed initial connection:', err);
      }
    };
    init();

    const unsubStatus = window.api.onBackendStatusChange(async (status) => {
      setBackendStatus(status as any);
      if (status === 'running') {
        const hw = await window.api.getHardwareInfo();
        setHardwareInfo(hw);
        const st = await window.api.getSettings();
        setSettings(st);
        // Verificar si los modelos requeridos están presentes
        try {
          const res = await fetch(`http://127.0.0.1:8000/setup/required_ready`);
          const data = await res.json();
          if (!data.ready) {
            setShowModelWizard(true);
          }
        } catch { /* si falla, no bloqueamos la app */ }
      }
    });

    const unsubLog = window.api.onBackendLog((log) => {
      setLogs((prev) => [...prev.slice(-99), log]);
    });

    return () => {
      unsubStatus();
      unsubLog();
    };
  }, []);

  // 2. Poll Job Status
  useEffect(() => {
    if (backendStatus !== 'running') return;
    
    const pollJob = async () => {
      try {
        const state = await window.api.getJobStatus();
        setJobState(state);
        
        // If job completed, fetch results
        if (state.status === 'completed' && !jobResults) {
          const res = await window.api.getJobResults();
          setJobResults(res);
          showToast('¡Culling completado con éxito!', 'success');
        } else if (state.status !== 'completed') {
          // Clear old results if running a new job
          setJobResults(null);
        }
      } catch (err) {
        // Silently ignore poll errors
      }
    };

    const interval = setInterval(pollJob, 1000);
    return () => clearInterval(interval);
  }, [backendStatus, jobResults, showToast]);

  // 3. Centralized Undo Check
  const checkUndo = useCallback(async (dir?: string) => {
    const targetDir = dir || lastDirectory;
    if (!targetDir.trim() || backendStatus !== 'running') {
      setUndoAvailable(false);
      return;
    }
    try {
      const res = await apiClient.checkUndo(targetDir.trim());
      setUndoAvailable(!!res?.disponible);
    } catch {
      setUndoAvailable(false);
    }
  }, [lastDirectory, backendStatus]);

  useEffect(() => {
    checkUndo();
  }, [checkUndo, jobResults]);

  // Actions
  const handleIngest = async (directory: string, mode: string = 'cull_edit') => {
    try {
      await window.api.ingestMedia(directory, mode);
      setLastDirectory(directory);
      localStorage.setItem('lastDirectory', directory);
      setJobResults(null); // Reset results for new job
      setCurrentView('grid'); // Reset view
      showToast(`Iniciando procesamiento en: ${directory}`, 'info');
    } catch (err: any) {
      console.error('Ingest error:', err);
      showToast(`Error al iniciar culling: ${err?.message || err}`, 'error');
    }
  };

  const handleSaveSettings = async (newSettings: any) => {
    try {
      const res = await window.api.sendSettings(newSettings);
      setSettings(res.settings);
      setIsSettingsOpen(false);
      showToast('Configuración guardada correctamente', 'success');
    } catch (err: any) {
      console.error('Error saving settings:', err);
      showToast(`Error guardando configuración: ${err?.message || err}`, 'error');
    }
  };

  const handleUndoExport = async (directory?: string) => {
    const targetDir = directory || lastDirectory;
    if (!targetDir.trim()) return;
    try {
      const res = await apiClient.undoExport(targetDir.trim());
      if (res.detail || !res.success) {
        showToast(res.detail || 'Error al deshacer exportación', 'error');
      } else {
        const msg = `Rollback exitoso: ${res.restauradas || 0} restauradas` +
          (res.limpiadas ? `, ${res.limpiadas} limpiadas` : '');
        showToast(msg, 'success');
        setUndoAvailable(false);
      }
    } catch (e: any) {
      showToast(`Error de conexión al deshacer: ${e.message || e}`, 'error');
    }
  };

  return (
    <div className="app-shell">
      <Sidebar 
        backendStatus={backendStatus}
        hardwareInfo={hardwareInfo}
        jobState={jobState}
        onStartIngest={handleIngest}
        currentView={currentView}
        onViewChange={setCurrentView}
        hasResults={!!jobResults}
        lastDirectory={lastDirectory}
        onDirectoryChange={(dir) => {
          setLastDirectory(dir);
          localStorage.setItem('lastDirectory', dir);
          checkUndo(dir);
        }}
        undoAvailable={undoAvailable}
        onUndoExport={handleUndoExport}
      />
      
      <main className="main-viewport">
        {staleBackend && (
          <div style={{
            backgroundColor: 'var(--status-blurry-bg)', color: 'var(--status-blurry-text)',
            padding: '8px 16px', fontSize: 'var(--text-sm)', textAlign: 'center',
            borderBottom: '1px solid var(--border-subtle)',
          }}>
            ⚠ El motor se actualizó desde que abriste la app — cierra y vuelve a abrir Guto Flow
            para usar la versión nueva. Lo que corras ahora usará la lógica anterior.
          </div>
        )}
        
        <Topbar
          currentView={currentView}
          directory={lastDirectory}
          jobState={jobState}
          jobResults={jobResults}
          onOpenSettings={() => setIsSettingsOpen(true)}
          onOpenShortcuts={() => setIsShortcutsOpen(true)}
        />

        <div className="content-viewport">
          <SyncReminder active={backendStatus === 'running'} />
          <MainContent
            jobState={jobState}
            jobResults={jobResults}
            settings={settings}
            viewMode={currentView}
            directory={lastDirectory}
            undoAvailable={undoAvailable}
            onUndoExport={handleUndoExport}
            onStartIngest={handleIngest}
          />
        </div>
      </main>

      {isSettingsOpen && (
        <SettingsModal 
          settings={settings}
          onClose={() => setIsSettingsOpen(false)}
          onSave={handleSaveSettings}
        />
      )}

      <ShortcutsModal
        isOpen={isShortcutsOpen}
        onClose={() => setIsShortcutsOpen(false)}
      />

      {showModelWizard && (
        <ModelDownloadWizard
          onComplete={() => setShowModelWizard(false)}
        />
      )}
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <MainApp />
    </ToastProvider>
  );
}
