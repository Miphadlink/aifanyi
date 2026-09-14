const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('desktop', {
  apiBase: () => ipcRenderer.invoke('app:apiBase'),
  openFiles: (filters) => ipcRenderer.invoke('dialog:openFiles', filters),
  openDirectory: () => ipcRenderer.invoke('dialog:openDirectory'),
  openGame: () => ipcRenderer.invoke('dialog:openGame'),
  openPath: (p) => ipcRenderer.invoke('shell:openPath', p),
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
