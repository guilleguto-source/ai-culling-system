import { spawn, ChildProcess } from 'child_process';
import path from 'path';
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
    // In dev, spawn python -m uvicorn in the workspace root directory
    const backendPath = path.resolve(__dirname, '../../backend');
    const env = { ...process.env, PYTHONPATH: backendPath };
    pyProcess = spawn('python', ['-m', 'uvicorn', 'backend.main:app', '--port', `${BACKEND_PORT}`], {
      cwd: path.resolve(__dirname, '../../'),
      env: env
    });
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

  // Periodically poll /health to check if running
  const checkInterval = setInterval(() => {
    if (backendStatus !== 'starting') {
      clearInterval(checkInterval);
      return;
    }
    const req = http.get(`${BACKEND_URL}/health`, (res) => {
      if (res.statusCode === 200) {
        setBackendStatus('running');
        clearInterval(checkInterval);
      }
    });
    req.on('error', () => {
      // Not running yet
    });
    req.end();
  }, 500);

  // Stop checking after 10 seconds to avoid infinite loop
  setTimeout(() => {
    clearInterval(checkInterval);
    if (backendStatus === 'starting') {
      setBackendStatus('error');
    }
  }, 10000);
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
}
