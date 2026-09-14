const { app, BrowserWindow, ipcMain, dialog, shell, Menu } = require('electron')
const path = require('path')
const { spawn, execFile } = require('child_process')
const http = require('http')

const isDev = !app.isPackaged
const API_BASE = 'http://127.0.0.1:8765'
const API_PORT = 8765
let mainWindow = null
let overlayWindow = null
let pythonProc = null

/** 项目根目录：开发=仓库根；打包后用 AI_TRANSLATOR_HOME 或向上找 .venv */
function projectRoot() {
  if (process.env.AI_TRANSLATOR_HOME) {
    return process.env.AI_TRANSLATOR_HOME
  }
  if (isDev) {
    return path.join(__dirname, '..')
  }
  // 从 exe/resources 位置向上查找含 .venv 的目录
  const fs = require('fs')
  let dir = path.dirname(app.getPath('exe'))
  for (let i = 0; i < 6; i++) {
    if (fs.existsSync(path.join(dir, '.venv', 'Scripts', 'python.exe'))) {
      return dir
    }
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  return path.join(app.getAppPath(), '..', '..', '..')
}

function findPython(root) {
  const venv = path.join(root, '.venv', 'Scripts', 'python.exe')
  if (require('fs').existsSync(venv)) {
    return venv
  }
  return null
}

function apiAlive(timeoutMs = 1500) {
  return new Promise((resolve) => {
    const req = http.get(`${API_BASE}/health`, (res) => {
      res.resume()
      resolve(res.statusCode === 200)
    })
    req.on('error', () => resolve(false))
    req.setTimeout(timeoutMs, () => {
      req.destroy()
      resolve(false)
    })
  })
}

function startPythonServer() {
  const root = projectRoot()
  const py = findPython(root)
  if (!py) {
    console.warn('未找到 .venv，请先启动后端或设置 AI_TRANSLATOR_HOME')
    return
  }
  const args = [
    '-m', 'uvicorn', 'server.main:app',
    '--host', '127.0.0.1', '--port', String(API_PORT),
  ]
  pythonProc = spawn(py, args, {
    cwd: root,
    stdio: 'ignore',
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
  })
  pythonProc.on('error', (err) => {
    console.error('Python server failed to start', err)
  })
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1180,
    height: 760,
    minWidth: 960,
    minHeight: 640,
    title: 'AI 智能翻译',
    backgroundColor: '#0f1419',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  if (isDev) {
    mainWindow.loadURL('http://127.0.0.1:5173')
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

function createOverlayWindow() {
  if (overlayWindow) {
    overlayWindow.show()
    return
  }
  overlayWindow = new BrowserWindow({
    width: 900,
    height: 600,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: true,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
    },
  })
  overlayWindow.setIgnoreMouseEvents(true, { forward: true })
  if (isDev) {
    overlayWindow.loadURL('http://127.0.0.1:5173/#/overlay')
  } else {
    overlayWindow.loadFile(path.join(__dirname, '../dist/index.html'), {
      hash: '/overlay',
    })
  }
  overlayWindow.on('closed', () => {
    overlayWindow = null
  })
}

ipcMain.handle('dialog:openFiles', async (_e, filters) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile', 'multiSelections'],
    filters: filters || [{ name: '全部文件', extensions: ['*'] }],
  })
  return result.canceled ? [] : result.filePaths
})

ipcMain.handle('dialog:openDirectory', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
  })
  return result.canceled ? null : result.filePaths[0]
})

ipcMain.handle('dialog:openGame', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile', 'openDirectory'],
    filters: [
      { name: '游戏程序', extensions: ['exe', 'lnk'] },
      { name: '全部文件', extensions: ['*'] },
    ],
  })
  return result.canceled ? null : result.filePaths[0]
})

ipcMain.handle('shell:openPath', async (_e, p) => {
  return shell.openPath(p)
})

ipcMain.handle('overlay:show', async () => {
  createOverlayWindow()
  return true
})

ipcMain.handle('overlay:hide', async () => {
  if (overlayWindow) {
    overlayWindow.hide()
  }
  return true
})

ipcMain.handle('overlay:setClickThrough', async (_e, enabled) => {
  if (!overlayWindow) return false
  overlayWindow.setIgnoreMouseEvents(!!enabled, { forward: true })
  return true
})

ipcMain.handle('overlay:setBounds', async (_e, bounds) => {
  if (!overlayWindow || !bounds) return false
  overlayWindow.setBounds({
    x: Math.round(bounds.x),
    y: Math.round(bounds.y),
    width: Math.round(bounds.width),
    height: Math.round(bounds.height),
  })
  return true
})

ipcMain.handle('app:apiBase', async () => API_BASE)

app.whenReady().then(async () => {
  // 去掉系统默认英文菜单，避免打包后出现 File/Edit/View
  Menu.setApplicationMenu(null)

  const alive = await apiAlive()
  if (!alive) {
    startPythonServer()
    // 等后端就绪，最多约 8s
    for (let i = 0; i < 16; i++) {
      await new Promise((r) => setTimeout(r, 500))
      if (await apiAlive()) break
    }
  }
  createMainWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createMainWindow()
  })
})

app.on('window-all-closed', () => {
  if (pythonProc) {
    pythonProc.kill()
    pythonProc = null
  }
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => {
  if (pythonProc) {
    pythonProc.kill()
    pythonProc = null
  }
})
