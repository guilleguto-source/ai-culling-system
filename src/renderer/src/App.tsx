import React, { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import MainContent from './components/MainContent';
import SettingsModal from './components/SettingsModal';
import './index.css';

// Fallback for browser testing connected to real FastAPI backend
if (typeof window !== 'undefined' && !window.api) {
  const BACKEND_URL = 'http://127.0.0.1:8000';
  (window as any).api = {
    getBackendStatus: async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/health`);
        if (res.ok) return { running: true, status: 'running', url: BACKEND_URL };
      } catch (e) {}
      return { running: false, status: 'stopped', url: BACKEND_URL };
    },
    getHardwareInfo: async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/hardware`);
        return await res.json();
      } catch (e) {
        return { using_gpu: false, gpu_provider: null, physical_cores: 0, logical_cores: 0 };
      }
    },
    sendSettings: async (settings: any) => {
      const res = await fetch(`${BACKEND_URL}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
      });
      return await res.json();
    },
    getSettings: async () => {
      const res = await fetch(`${BACKEND_URL}/settings`);
      return await res.json();
    },
    ingestMedia: async (directory: string) => {
      const res = await fetch(`${BACKEND_URL}/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ directory })
      });
      return await res.json();
    },
    getJobStatus: async () => {
      const res = await fetch(`${BACKEND_URL}/status`);
      return await res.json();
    },
    getJobResults: async () => {
      const res = await fetch(`${BACKEND_URL}/results`);
      return await res.json();
    },
    onBackendLog: (cb: any) => {
      return () => {};
    },
    onBackendStatusChange: (cb: any) => {
      const interval = setInterval(async () => {
        try {
          const res = await fetch(`${BACKEND_URL}/health`);
          cb(res.ok ? 'running' : 'stopped');
        } catch (e) {
          cb('stopped');
        }
      }, 2000);
      return () => clearInterval(interval);
    }
  };
}

export default function App() {
  const [backendStatus, setBackendStatus] = useState<'starting' | 'running' | 'stopped' | 'error' | 'unknown'>('unknown');
  const [hardwareInfo, setHardwareInfo] = useState<any>(null);
  const [settings, setSettings] = useState<any>(null);
  
  const [jobState, setJobState] = useState<any>(null);
  const [jobResults, setJobResults] = useState<any>(null);
  
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [currentView, setCurrentView] = useState<'grid' | 'duel'>('grid');
  const [lastDirectory, setLastDirectory] = useState<string>('');
  
  const [logs, setLogs] = useState<string[]>([]);

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
  }, [backendStatus, jobResults]);

  // Actions
  const handleIngest = async (directory: string) => {
    try {
      await window.api.ingestMedia(directory);
      setLastDirectory(directory);
      setJobResults(null); // Reset results for new job
      setCurrentView('grid'); // Reset view
    } catch (err) {
      console.error('Ingest error:', err);
      alert(`Error starting culling: ${err}`);
    }
  };

  const handleSaveSettings = async (newSettings: any) => {
    try {
      const res = await window.api.sendSettings(newSettings);
      setSettings(res.settings);
      setIsSettingsOpen(false);
    } catch (err) {
      console.error('Error saving settings:', err);
      alert(`Error saving settings: ${err}`);
    }
  };

  return (
    <div style={{ display: 'flex', height: '100vh', width: '100vw', overflow: 'hidden' }}>
      <Sidebar 
        backendStatus={backendStatus}
        hardwareInfo={hardwareInfo}
        jobState={jobState}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onStartIngest={handleIngest}
        currentView={currentView}
        onViewChange={setCurrentView}
        hasResults={!!jobResults}
      />
      
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <MainContent
          jobState={jobState}
          jobResults={jobResults}
          settings={settings}
          viewMode={currentView}
          directory={lastDirectory}
        />
      </div>

      {isSettingsOpen && (
        <SettingsModal 
          settings={settings}
          onClose={() => setIsSettingsOpen(false)}
          onSave={handleSaveSettings}
        />
      )}
    </div>
  );
}
