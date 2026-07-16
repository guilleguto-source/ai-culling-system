import { app, BrowserWindow } from 'electron';
import path from 'path';
import { startBackend, stopBackend, setupBackendIpc } from './backend';

let mainWindow: BrowserWindow | null = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1024,
    height: 768,
    title: 'Guto Flow',
    icon: path.join(__dirname, '../../assets/icon.ico'),
    webPreferences: {
      preload: path.join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  // CULLING_LOCAL=1: lanzamiento desde el escritorio sin terminal — usa el
  // frontend ya compilado (dist/renderer) y el Python del sistema, sin Vite.
  const useBuiltRenderer = app.isPackaged || process.env.CULLING_LOCAL === '1';
  if (useBuiltRenderer) {
    mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'));
  } else {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  setupBackendIpc();
  startBackend();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', async (e: Electron.Event) => {
  e.preventDefault();
  await stopBackend();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('will-quit', async (e: Electron.Event) => {
  e.preventDefault();
  await stopBackend();
  app.exit(0);
});
