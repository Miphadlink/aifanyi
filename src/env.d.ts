/// <reference types="vite/client" />

interface OverlayLine {
  x: number
  y: number
  w: number
  h: number
  text: string
  original?: string
}

interface DesktopBridge {
  apiBase: () => Promise<string>
  openFiles: (filters?: { name: string; extensions: string[] }[]) => Promise<string[]>
  openDirectory: () => Promise<string | null>
  openGame: () => Promise<string | null>
  openPath: (p: string) => Promise<string>
  showOverlay: () => Promise<boolean>
  hideOverlay: () => Promise<boolean>
  setClickThrough: (enabled: boolean) => Promise<boolean>
  setOverlayBounds: (b: { x: number; y: number; width: number; height: number }) => Promise<boolean>
  onOverlayLines: (cb: (lines: OverlayLine[]) => void) => () => void
  pushOverlayLines: (lines: OverlayLine[]) => void
}

interface Window {
  desktop?: DesktopBridge
}
