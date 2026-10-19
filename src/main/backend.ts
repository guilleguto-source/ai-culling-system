import { spawn, ChildProcess } from 'child_process';
import path from 'path';
import fs from 'fs';
import { app, ipcMain, BrowserWindow, dialog } from 'electron';
import http from 'http';
import kill from 'tree-kill';

let pyProcess: ChildProcess | null = null;
const BACKEND_PORT = 8000;
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}`;
let backendStatus: 'starting' | 'running' | 'stopped' | 'error' = 'stopped';

function broadcast(channel: string, ...args: any[]) {
  const windows = BrowserWindow.getAllWindows();
  for (const win of windows) {
    if (!win.isDestroyed()) {
      win.webContents.send(channel, ...args);
    }
  }
}

export function setBackendStatus(status: 'starting' | 'running' | 'stopped' | 'error') {
  backendStatus = status;
  broadcast('backend:status-change', status);
}

export function startBackend() {
  const isDev = !app.isPackaged;
  setBackendStatus('starting');

  if (isDev) {
    // En dev se usa el venv AISLADO de backend/, no la `python` del PATH: con
    // la del sistema, cualquier `pip install` global puede romper la app (pasó:
    // instalar insightface subió numpy y dejó scikit-learn inservible).
    // Si el venv no existe, se cae a `python` del sistema con un aviso.
    const root = path.resolve(__dirname, '../../');
    const backendPath = path.join(root, 'backend');
    const venvPython = path.join(
      backendPath, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'
    );
    const usarVenv = fs.existsSync(venvPython);
    if (!usarVenv) {
      broadcast('backend:log',
        'AVISO: no se encontró backend/.venv; usando la Python del sistema (frágil ante pip global).');
    }
    const env = { ...process.env, PYTHONPATH: backendPath };
    pyProcess = spawn(usarVenv ? venvPython : 'python',
      ['-m', 'uvicorn', 'backend.main:app', '--port', `${BACKEND_PORT}`],
      { cwd: root, env }
    );
  } else {
    // Executable packaged with PyInstaller
    const binaryName = process.platform === 'win32' ? 'backend.exe' : 'backend';
    const distPath = path.join(process.resourcesPath, 'backend', binaryName);
    pyProcess = spawn(distPath, [`--port=${BACKEND_PORT}`]);
  }

  pyProcess.on('error', (err) => {
    console.error('Failed to start backend process:', err);
    broadcast('backend:log', `Failed to start backend: ${err.message}`);
    setBackendStatus('error');
  });

  pyProcess.stdout?.on('data', (data) => {
    const logStr = data.toString();
    console.log(`[Python Stdout]: ${logStr}`);
    broadcast('backend:log', logStr);
  });

  pyProcess.stderr?.on('data', (data) => {
    const logStr = data.toString();
    console.error(`[Python Stderr]: ${logStr}`);
    broadcast('backend:log', logStr);
  });

  pyProcess.on('close', (code) => {
    console.log(`Backend exited with code ${code}`);
    pyProcess = null;
    setBackendStatus('stopped');
  });

  // Continual health monitoring to auto-recover status when backend is responsive
  setInterval(() => {
    const req = http.get(`${BACKEND_URL}/health`, (res) => {
      if (res.statusCode === 200) {
        if (backendStatus !== 'running') {
          setBackendStatus('running');
        }
      } else {
        if (backendStatus === 'running') {
          setBackendStatus('stopped');
        }
      }
    });
    req.on('error', () => {
      if (backendStatus === 'running') {
        setBackendStatus('stopped');
      }
    });
    req.end();
  }, 1500);
}

export async function stopBackend(): Promise<void> {
  if (!pyProcess) {
    setBackendStatus('stopped');
    return;
  }

  return new Promise((resolve) => {
    const pid = pyProcess ? pyProcess.pid : undefined;
    const postData = '';
    const req = http.request(
      {
        hostname: '127.0.0.1',
        port: BACKEND_PORT,
        path: '/shutdown',
        method: 'POST',
        headers: {
          'Content-Length': Buffer.byteLength(postData)
        }
      },
      (res) => {
        console.log(`Shutdown response status: ${res.statusCode}`);
        if (pid) {
          kill(pid, 'SIGKILL', (killErr) => {
            if (killErr) {
              console.error(`tree-kill error on shutdown: ${killErr}`);
            }
            setBackendStatus('stopped');
            pyProcess = null;
            resolve();
          });
        } else {
          setBackendStatus('stopped');
          pyProcess = null;
          resolve();
        }
      }
    );

    req.on('error', (err) => {
      console.error('Failed to trigger shutdown endpoint, killing process tree...', err);
      if (pid) {
        kill(pid, 'SIGKILL', (killErr) => {
          if (killErr) {
            console.error(`tree-kill error on fallback: ${killErr}`);
          }
          setBackendStatus('stopped');
          pyProcess = null;
          resolve();
        });
      } else {
        if (pyProcess) {
          pyProcess.kill('SIGKILL');
        }
        setBackendStatus('stopped');
        pyProcess = null;
        resolve();
      }
    });

    req.write(postData);
    req.end();
  });
}

function makeGetRequest(endpoint: string): Promise<any> {
  return new Promise((resolve, reject) => {
    http.get(`${BACKEND_URL}${endpoint}`, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          reject(e);
        }
      });
    }).on('error', (err) => reject(err));
  });
}

function makePostRequest(endpoint: string, payload: any): Promise<any> {
  return new Promise((resolve, reject) => {
    const postData = JSON.stringify(payload);
    const req = http.request(
      {
        hostname: '127.0.0.1',
        port: BACKEND_PORT,
        path: endpoint,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(postData)
        }
      },
      (res) => {
        let data = '';
        res.on('data', (chunk) => data += chunk);
        res.on('end', () => {
          try {
            resolve(JSON.parse(data));
          } catch (e) {
            reject(e);
          }
        });
      }
    );
    req.on('error', (err) => reject(err));
    req.write(postData);
    req.end();
  });
}

export function setupBackendIpc() {
  ipcMain.handle('backend:status', () => {
    return {
      running: backendStatus === 'running',
      status: backendStatus,
      url: BACKEND_URL
    };
  });

  ipcMain.handle('backend:hardware', () => makeGetRequest('/hardware'));
  ipcMain.handle('backend:settings:get', () => makeGetRequest('/settings'));
  ipcMain.handle('backend:settings:save', (_, settings: any) => makePostRequest('/settings', settings));
  
  ipcMain.handle('backend:ingest', (_, directory: string, mode: string = 'cull_edit') =>
    makePostRequest('/ingest', { directory, mode }));
  ipcMain.handle('backend:job:status', () => makeGetRequest('/status'));
  ipcMain.handle('backend:job:results', () => makeGetRequest('/results'));
  


  ipcMain.handle('backend:select-folder', async (_, defaultPath?: string) => {
    const result = await dialog.showOpenDialog({
      properties: ['openDirectory'],
      defaultPath: defaultPath || '\\\\MYCLOUDEX2ULTRA\\Public\\Guto Gutierrez\\'
    });
    if (result.canceled) {
      return null;
    }
    return result.filePaths[0];
  });

  // --- Gestión de Energía y Suspensión ---
  let powerBlockerId: number | null = null;

  ipcMain.handle('system:prevent-sleep', () => {
    const { powerSaveBlocker } = require('electron');
    if (powerBlockerId === null || !powerSaveBlocker.isStarted(powerBlockerId)) {
      powerBlockerId = powerSaveBlocker.start('prevent-app-suspension');
      console.log(`[PowerSaveBlocker] Bloqueo de suspensión activado (ID: ${powerBlockerId})`);
    }
    return powerBlockerId;
  });

  ipcMain.handle('system:allow-sleep', () => {
    const { powerSaveBlocker } = require('electron');
    if (powerBlockerId !== null && powerSaveBlocker.isStarted(powerBlockerId)) {
      powerSaveBlocker.stop(powerBlockerId);
      console.log(`[PowerSaveBlocker] Bloqueo de suspensión liberado (ID: ${powerBlockerId})`);
      powerBlockerId = null;
    }
    return true;
  });

  ipcMain.handle('system:suspend', async () => {
    const { exec } = require('child_process');
    console.log('[System] Ejecutando orden de suspensión del sistema...');
    
    return new Promise((resolve) => {
      if (process.platform === 'win32') {
        // rundll32 es el método más directo y fiable para suspender en Windows,
        // sin depender de .NET ni de escapes de $false en PowerShell.
        // Parámetros: Hibernate=0 (sleep), Force=1, DisableWakeEvent=0
        exec('rundll32.exe powrprof.dll,SetSuspendState 0,1,0', (err: any) => {
          if (err) {
            console.error('[System] Error al suspender en Windows:', err);
            resolve(false);
          } else {
            resolve(true);
          }
        });
      } else if (process.platform === 'darwin') {
        exec('pmset sleepnow', (err: any) => resolve(!err));
      } else {
        exec('systemctl suspend', (err: any) => resolve(!err));
      }
    });
  });
}
