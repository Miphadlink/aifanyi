/**
 * 全局唯一 TTS 播放器：同一时刻只允许一路朗读。
 * 提供 播放 / 暂停 / 继续 / 停止。
 */
import { API_BASE } from './client'

type Listener = () => void

let audio: HTMLAudioElement | null = null
let currentText = ''
const listeners = new Set<Listener>()

function emit() {
  for (const fn of listeners) fn()
}

function ensureAudio(): HTMLAudioElement {
  if (!audio) {
    audio = new Audio()
    audio.addEventListener('ended', () => {
      currentText = ''
      emit()
    })
    audio.addEventListener('pause', () => emit())
    audio.addEventListener('play', () => emit())
    audio.addEventListener('error', () => {
      currentText = ''
      emit()
    })
  }
  return audio
}

export interface TtsPlayerState {
  playing: boolean
  paused: boolean
  busy: boolean
  text: string
  error: string
}

let busy = false
let lastError = ''

export function getTtsState(): TtsPlayerState {
  const a = audio
  return {
    playing: !!a && !a.paused && !a.ended && a.currentTime > 0 || (!!a && !a.paused && !a.ended),
    paused: !!a && a.paused && a.currentTime > 0 && !a.ended,
    busy,
    text: currentText,
    error: lastError,
  }
}

export function subscribeTts(fn: Listener): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

/** 停止当前朗读（若有） */
export function stopTts() {
  if (!audio) return
  audio.pause()
  audio.currentTime = 0
  audio.removeAttribute('src')
  audio.load()
  currentText = ''
  lastError = ''
  busy = false
  emit()
}

/** 暂停当前朗读 */
export function pauseTts() {
  if (audio && !audio.paused) {
    audio.pause()
    emit()
  }
}

/** 从暂停处继续 */
export function resumeTts() {
  if (audio && audio.paused && audio.src) {
    void audio.play().then(() => emit()).catch(() => emit())
  }
}

/**
 * 朗读一段文本：会先停掉上一路，再请求 TTS 并播放。
 */
export async function playTtsText(text: string, lang = 'zh', voice?: string): Promise<void> {
  const t = (text || '').trim()
  if (!t) return

  // 新朗读打断旧的
  stopTts()
  busy = true
  lastError = ''
  currentText = t
  emit()

  try {
    const res = await fetch(`${API_BASE}/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: t, lang, voice }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok || data.error) {
      throw new Error(data.detail || data.error || `HTTP ${res.status}`)
    }
    const url = `${API_BASE}/tts/audio?path=${encodeURIComponent(data.path)}`
    const a = ensureAudio()
    a.src = url
    await a.play()
  } catch (e) {
    lastError = e instanceof Error ? e.message : String(e)
    currentText = ''
  } finally {
    busy = false
    emit()
  }
}
