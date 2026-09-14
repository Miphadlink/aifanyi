const API_BASE = 'http://127.0.0.1:8765'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export function ping() {
  return request<{ ok: boolean; python: string; ffmpeg: boolean; gpu: string }>('/health')
}

/** Edge TTS：合成并播放。audio 元素播 API 返回的 path。 */
export async function speakText(
  text: string,
  lang = 'zh',
  voice?: string,
): Promise<void> {
  if (!text.trim()) return
  const res = await request<{ path: string; voice: string; error?: string }>('/tts', {
    method: 'POST',
    body: JSON.stringify({ text, lang, voice }),
  })
  if (res.error) throw new Error(res.error)
  const url = `${API_BASE}/tts/audio?path=${encodeURIComponent(res.path)}`
  const audio = new Audio(url)
  await audio.play()
}

export interface TranslateResult {
  text: string
  engine: string
  latency_ms: number
  source_lang?: string
  target_lang?: string
}

export interface SettingsPayload {
  api_base: string
  api_key: string
  model: string
  text_model: string
  image_model: string
  video_model: string
  game_model: string
  target_lang: string
  source_lang: string
  use_local: boolean
  local_model: string
  game_sample_ms: number
}

export function getSettings() {
  return request<SettingsPayload>('/settings')
}

export function saveSettings(payload: Partial<SettingsPayload>) {
  return request<SettingsPayload>('/settings', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/** 用 Base+Key 拉取 OpenAI 兼容 /models 列表 */
export function fetchModels(body?: { api_base?: string; api_key?: string }) {
  return request<{ models: string[] }>('/models', {
    method: 'POST',
    body: JSON.stringify(body || {}),
  })
}

export function translateText(body: {
  text: string
  source_lang?: string
  target_lang?: string
}) {
  return request<TranslateResult>('/translate/text', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function translateTextStream(
  body: { text: string; source_lang?: string; target_lang?: string },
  onChunk: (full: string) => void,
): Promise<TranslateResult> {
  return new Promise(async (resolve, reject) => {
    try {
      const res = await fetch(`${API_BASE}/translate/text/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok || !res.body) {
        throw new Error(await res.text())
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let full = ''
      let meta: TranslateResult | null = null
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value, { stream: true })
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6)
          if (payload === '[DONE]') continue
          try {
            const obj = JSON.parse(payload)
            if (obj.type === 'delta') {
              full += obj.text
              onChunk(full)
            } else if (obj.type === 'meta' || obj.type === 'done') {
              meta = obj as TranslateResult
            }
          } catch {
            // ignore partial JSON
          }
        }
      }
      resolve(meta || { text: full, engine: 'unknown', latency_ms: 0 })
    } catch (e) {
      reject(e)
    }
  })
}

export interface OcrBox {
  box: number[][]
  text: string
  translation?: string
}

export interface ImageTranslateResult {
  source: string
  target: string
  boxes: OcrBox[]
  overlay_data_url?: string
}

export function translateImage(body: {
  image_base64: string
  source_lang?: string
  target_lang?: string
  overlay?: boolean
}) {
  return request<ImageTranslateResult>('/translate/image', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export interface VideoTask {
  task_id: string
  status: string
  progress: number
  message: string
  output_srt?: string
  output_ass?: string
  output_audio?: string
  output_dubbed?: string
}

export function startVideoTask(body: {
  path: string
  target_lang?: string
  source_lang?: string
  use_existing_subs?: boolean
  embed_sub?: boolean
  tts?: boolean
}) {
  return request<VideoTask>('/translate/video', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function getVideoTask(taskId: string) {
  return request<VideoTask>(`/translate/video/${taskId}`)
}

export interface GameSession {
  session_id: string
  game_name: string
  pid: number | null
  window_title: string
  engine: string
  status: string
  candidates?: { path: string; reason: string }[]
}

export function startGame(body: { path: string }) {
  return request<GameSession | { need_confirm: true; candidates: { path: string; reason: string }[] }>(
    '/game/start',
    { method: 'POST', body: JSON.stringify(body) },
  )
}

export function confirmGame(body: { path: string }) {
  return request<GameSession>('/game/confirm', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function stopGame(sessionId: string) {
  return request<{ ok: boolean }>(`/game/${sessionId}/stop`, { method: 'POST' })
}

export function getGameStatus(sessionId: string) {
  return request<GameSession & { lines?: OverlayLine[] }>(`/game/${sessionId}/status`)
}

export interface OverlayLine {
  x: number
  y: number
  w: number
  h: number
  text: string
  original?: string
}

export function setGameCapture(body: { session_id: string; enabled: boolean }) {
  return request<{ ok: boolean }>('/game/capture', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}
