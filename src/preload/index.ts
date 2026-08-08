import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('api', {
  getBackendStatus: () => ipcRenderer.invoke('backend:status'),
  getHardwareInfo: () => ipcRenderer.invoke('backend:hardware'),
  sendSettings: (settings: any) => ipcRenderer.invoke('backend:settings:save', settings),
  getSettings: () => ipcRenderer.invoke('backend:settings:get'),
  
  ingestMedia: (directory: string, mode?: string) => ipcRenderer.invoke('backend:ingest', directory, mode || 'cull_edit'),
  getJobStatus: () => ipcRenderer.invoke('backend:job:status'),
  getJobResults: () => ipcRenderer.invoke('backend:job:results'),
  
  checkUndoAvailable: (directory: string) => ipcRenderer.invoke('backend:undo:available', directory),
  undoExport: (directory: string) => ipcRenderer.invoke('backend:undo:run', directory),

  selectFolder: (defaultPath?: string) => ipcRenderer.invoke('backend:select-folder', defaultPath),

  onBackendLog: (callback: (log: string) => void) => {
    const subscription = (_: any, log: string) => callback(log);
    ipcRenderer.on('backend:log', subscription);
    return () => {
      ipcRenderer.removeListener('backend:log', subscription);
    };
  },
  onBackendStatusChange: (callback: (status: string) => void) => {
    const subscription = (_: any, status: string) => callback(status);
    ipcRenderer.on('backend:status-change', subscription);
    return () => {
      ipcRenderer.removeListener('backend:status-change', subscription);
    };
  }
});
