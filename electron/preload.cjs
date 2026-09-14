const { contextBridge, ipcRenderer, webUtils } = require('electron')

contextBridge.exposeInMainWorld('desktop', {
  apiBase: () => ipcRenderer.invoke('app:apiBase'),
  openFiles: (filters) => ipcRenderer.invoke('dialog:openFiles', filters),
  openDirectory: () => ipcRenderer.invoke('dialog:openDirectory'),
  openGame: () => ipcRenderer.invoke('dialog:openGame'),
  openGameExe: () => ipcRenderer.invoke('dialog:openGameExe'),
  openGameDir: () => ipcRenderer.invoke('dialog:openGameDir'),
  openPath: (p) => ipcRenderer.invoke('shell:openPath', p),
  // Electron 32+ 不再暴露 File.path，必须用 webUtils
  getPathForFile: (file) => {
    try {
      return webUtils.getPathForFile(file)
    } catch {
      return null
    }
  },
  showOverlay: () => ipcRenderer.invoke('overlay:show'),
  hideOverlay: () => ipcRenderer.invoke('overlay:hide'),
  setClickThrough: (enabled) => ipcRenderer.invoke('overlay:setClickThrough', enabled),
  setOverlayBounds: (bounds) => ipcRenderer.invoke('overlay:setBounds', bounds),
  onOverlayLines: (cb) => {
    const handler = (_e, payload) => cb(payload)
    ipcRenderer.on('overlay:lines', handler)
    return () => ipcRenderer.removeListener('overlay:lines', handler)
  },
  pushOverlayLines: (payload) => ipcRenderer.send('overlay:lines', payload),
})
