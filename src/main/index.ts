import { app, BrowserWindow } from 'electron';
import path from 'path';
import { startBackend, stopBackend, setupBackendIpc } from './backend';

let mainWindow: BrowserWindow | null = null;

async function loadApp(win: BrowserWindow) {
  const isDev = !app.isPackaged && process.env.CULLING_LOCAL !== '1';
  const localHtmlPath = path.join(__dirname, '../renderer/index.html');

  if (!isDev) {
    await win.loadFile(localHtmlPath);
    return;
  }

  const viteUrl = 'http://localhost:5173';
  let loaded = false;
  
  for (let attempt = 1; attempt <= 6; attempt++) {
    if (win.isDestroyed()) return;
    try {
      await win.loadURL(viteUrl);
      loaded = true;
      break;
    } catch {
      await new Promise((r) => setTimeout(r, 600));
    }
  }

  if (!loaded && !win.isDestroyed()) {
    console.warn('Vite dev server no disponible en 5173. Usando bundle local compilado.');
    await win.loadFile(localHtmlPath);
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: '#131417',
    title: 'Guto Flow',
    icon: path.join(__dirname, '../../assets/icon.ico'),
    webPreferences: {
      preload: path.join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  loadApp(mainWindow);

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
