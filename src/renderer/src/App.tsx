import React, { useState, useEffect, useCallback, useRef } from 'react';
import Sidebar from './components/Sidebar';
import Topbar from './components/Topbar';
import MainContent from './components/MainContent';
import SettingsModal from './components/SettingsModal';
import ShortcutsModal from './components/ShortcutsModal';
import SyncReminder from './components/SyncReminder';
import { ModelDownloadWizard } from './components/ModelDownloadWizard';
import { PreCullingModal, PreCullingConfig } from './components/PreCullingModal';
import { SleepCountdownModal } from './components/SleepCountdownModal';
import { ClientToolsModal } from './components/ClientToolsModal';
import { ToastProvider, useToast } from './components/Toast';
import { apiClient, BACKEND_URL } from './api/client';
import './index.css';

function MainApp() {
  const [backendStatus, setBackendStatus] = useState<'starting' | 'running' | 'stopped' | 'error' | 'unknown'>('unknown');
  const [hardwareInfo, setHardwareInfo] = useState<any>(null);
  const [settings, setSettings] = useState<any>(null);
  
  const [jobState, setJobState] = useState<any>(null);
  const [jobResults, setJobResults] = useState<any>(null);
  
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [currentView, setCurrentView] = useState<'library' | 'grid' | 'duel' | 'calib'>('grid');
  const [lastDirectory, setLastDirectory] = useState<string>(() => localStorage.getItem('lastDirectory') || '');
  const [undoAvailable, setUndoAvailable] = useState<boolean>(false);
  const [staleBackend, setStaleBackend] = useState(false);
  const [showModelWizard, setShowModelWizard] = useState(false);
  const [isShortcutsOpen, setIsShortcutsOpen] = useState(false);
  const [isClientToolsOpen, setIsClientToolsOpen] = useState(false);
  const [clientToolsDir, setClientToolsDir] = useState<string>('');

  // New batch & pre-culling state
  const [preCullingFolder, setPreCullingFolder] = useState<string | null>(null);
  const [batchQueue, setBatchQueue] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem('culling_batch_queue');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [activeConfig, setActiveConfig] = useState<PreCullingConfig | null>(null);
  const [autoSleepActive, setAutoSleepActive] = useState<boolean>(false);
  const autoSleepRef = useRef<boolean>(false);

  useEffect(() => {
    autoSleepRef.current = autoSleepActive;
  }, [autoSleepActive]);

  const [showSleepModal, setShowSleepModal] = useState<boolean>(false);
  const { showToast } = useToast();

  useEffect(() => {
    localStorage.setItem('culling_batch_queue', JSON.stringify(batchQueue));
  }, [batchQueue]);

  useEffect(() => {
    const handleGlobalKeys = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        (e.target as HTMLElement)?.isContentEditable
      ) {
        return;
      }
      if (e.key === '?') {
        e.preventDefault();
        setIsShortcutsOpen((prev) => !prev);
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
          const data = await apiClient.checkSetupReady();
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
          
          // Check if there are more event groups to process
          if (activeConfig && activeConfig.eventGroups && activeConfig.eventGroups.length > 1) {
            // Find which group just finished by checking lastDirectory
            const currentGroupIndex = activeConfig.eventGroups.findIndex(g => g[0] === lastDirectory);
            if (currentGroupIndex >= 0 && currentGroupIndex < activeConfig.eventGroups.length - 1) {
              const nextIndex = currentGroupIndex + 1;
              const nextGroup = activeConfig.eventGroups[nextIndex];
              const [primary, ...extras] = nextGroup;
              
              // Calculate remaining folders in the queue for visual state
              const remainingDirs = activeConfig.eventGroups.slice(nextIndex).flatMap(g => g);
              setBatchQueue(remainingDirs);
              
              const groupLabel = nextGroup.length > 1
                ? `${nextGroup.length} carpetas como 1 evento`
                : (primary || '').replace(/\\/g, '/').split('/').filter(Boolean).pop() ?? primary;

              showToast(`Lote completado. Iniciando: ${groupLabel}`, 'info');
              
              const targetEventType = activeConfig.eventGroupTypes && activeConfig.eventGroupTypes.length > nextIndex
                ? activeConfig.eventGroupTypes[nextIndex]
                : activeConfig.eventType;

              setTimeout(async () => {
                try {
                  await apiClient.startIngest(
                    primary,
                    activeConfig.mode,
                    targetEventType,
                    activeConfig.selectivity,
                    {
                      preset_path: activeConfig.presetPath,
                      auto_crop: activeConfig.autoCrop
                    },
                    extras.length > 0 ? extras : undefined
                  );
                  setLastDirectory(primary);
                  localStorage.setItem('lastDirectory', primary);
                  setJobResults(null);
                } catch (e: any) {
                  showToast(`Error iniciando siguiente lote: ${e.message || e}`, 'error');
                }
              }, 1500);
              return; // Stop here, don't execute "Cola completa" logic
            }
          }
          
          // Cola completa
          setBatchQueue([]);
          showToast('¡Culling completado con éxito!', 'success');
          if (window.api?.allowSleep) {
            await window.api.allowSleep();
          }
          if (autoSleepRef.current) {
            setShowSleepModal(true);
          }
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
  }, [backendStatus, jobResults, batchQueue, activeConfig, autoSleepActive, showToast, lastDirectory]);

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
  const handleStartPreCulling = (directory: string) => {
    setPreCullingFolder(directory);
  };

  const handleConfirmPreCulling = async (config: PreCullingConfig) => {
    setPreCullingFolder(null);
    setActiveConfig(config);
    setAutoSleepActive(config.autoSleep);

    // eventGroups: [[dir_A, dir_B], [dir_C], [dir_D]]
    // Each group = one unified event job. Groups with >1 folder pass extra_directories.
    const groups = config.eventGroups && config.eventGroups.length > 0
      ? config.eventGroups
      : config.queue.map(d => [d]);

    if (groups.length === 0) return;

    const firstDir = groups[0][0];
    try {
      if (window.api?.preventSleep) {
        await window.api.preventSleep();
      }
      // Launch first group immediately
      const [primary, ...extras] = groups[0];
      const targetEventType = config.eventGroupTypes && config.eventGroupTypes.length > 0 
        ? config.eventGroupTypes[0] 
        : config.eventType;
      
      // Inyectar metadatos configurados en el lote antes de iniciar culling
      if (config.metadataPayload) {
        showToast('Inyectando metadatos y copyright al lote...', 'info');
        try {
          const targetFolders = config.queue && config.queue.length > 0 ? config.queue : [primary];
          for (const folder of targetFolders) {
            await apiClient.applyBatchMetadata({
              directory: folder,
              filter_mode: 'all',
              profile_id: config.metadataPayload.profile_id,
              event_type: config.metadataPayload.event_type,
              age: config.metadataPayload.age,
              protagonist: config.metadataPayload.protagonist,
              city: config.metadataPayload.city,
              custom_tags: config.metadataPayload.custom_tags,
              keywords_mode: config.metadataPayload.keywords_mode
            });
          }
        } catch (metaErr: any) {
          console.error('Error aplicando metadatos antes de culling:', metaErr);
          showToast(`Aviso: Error aplicando metadatos: ${metaErr.message || metaErr}`, 'warning');
        }
      }

      await apiClient.startIngest(
        primary,
        config.mode,
        targetEventType,
        config.selectivity,
        { preset_path: config.presetPath, auto_crop: config.autoCrop },
        extras.length > 0 ? extras : undefined
      );
      setLastDirectory(firstDir);
      localStorage.setItem('lastDirectory', firstDir);
      setJobResults(null);
      setCurrentView('grid');
      const groupLabel = groups[0].length > 1
        ? `${groups[0].length} carpetas como 1 evento`
        : (firstDir || '').replace(/\\/g, '/').split('/').filter(Boolean).pop() ?? firstDir;
      showToast(`Iniciando culling (${config.eventType}): ${groupLabel}`, 'info');

      // Remaining groups go to the batch queue (processed sequentially after current job)
      const remainingDirs = groups.length > 1 ? groups.slice(1).flatMap(g => g) : [];
      setBatchQueue(remainingDirs);
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
        onStartIngest={handleStartPreCulling}
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
          onOpenClientTools={lastDirectory ? () => setIsClientToolsOpen(true) : undefined}
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
            onStartIngest={handleStartPreCulling}
            onSelectProject={async (dir) => {
              try {
                const res = await apiClient.loadSession(dir);
                if (res.status === 'completed') {
                  setJobResults({ results: res.results, stats: res.stats });
                  setLastDirectory(dir);
                  localStorage.setItem('lastDirectory', dir);
                  setCurrentView('grid');
                  showToast('Sesión cargada exitosamente', 'success');
                }
              } catch (err: any) {
                showToast(`Error al cargar la sesión: ${err.message}`, 'error');
              }
            }}
            onOpenClientTools={(dir: string) => {
              setClientToolsDir(dir);
              setIsClientToolsOpen(true);
            }}
          />
        </div>
      </main>

      <PreCullingModal
        isOpen={!!preCullingFolder}
        initialDirectory={preCullingFolder || ''}
        initialQueue={preCullingFolder ? [preCullingFolder] : []}
        onClose={() => setPreCullingFolder(null)}
        onConfirm={handleConfirmPreCulling}
      />

      {/* Auto-Sleep Countdown Modal */}
      <SleepCountdownModal
        isOpen={showSleepModal}
        onCancel={() => setShowSleepModal(false)}
      />

      <ClientToolsModal
        isOpen={isClientToolsOpen}
        onClose={() => setIsClientToolsOpen(false)}
        currentDirectory={clientToolsDir}
      />

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
