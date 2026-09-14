<template>
  <div class="page">
    <header class="page-head">
      <h1>游戏翻译</h1>
      <p>拖入 exe / 快捷方式 / 游戏文件夹，由本软件启动后实时覆盖译文。</p>
    </header>

    <section class="card">
      <div
        class="drop-zone"
        :class="{ dragover }"
        @dragover.prevent="dragover = true"
        @dragleave="dragover = false"
        @drop.prevent="onDrop"
        @click="pickGame"
      >
        <div>拖入游戏可执行文件或文件夹，或点击选择</div>
        <div class="muted" style="margin-top: 6px">支持 Unity / RPG Maker / Godot 等；不注入进程</div>
      </div>
    </section>

    <section v-if="candidates.length" class="card">
      <strong>检测到多个候选程序，请选择主程序：</strong>
      <div style="margin-top: 10px">
        <div
          v-for="c in candidates"
          :key="c.path"
          class="history-item"
          @click="confirmCandidate(c.path)"
        >
          <div>{{ c.path }}</div>
          <div class="muted">{{ c.reason }}</div>
        </div>
      </div>
    </section>

    <section v-if="session" class="card">
      <div class="row between" style="margin-bottom: 12px">
        <div>
          <strong>{{ session.game_name }}</strong>
          <span class="tag" style="margin-left: 8px">{{ session.engine }}</span>
          <span class="badge" :class="session.status === 'running' ? 'ok' : 'bad'" style="margin-left: 8px">
            {{ session.status }}
          </span>
        </div>
        <div class="row">
          <button :disabled="!canOverlay" @click="toggleCapture">
            {{ capturing ? '停止实时翻译' : '开始实时翻译' }}
          </button>
          <button @click="showOverlay">显示浮窗</button>
          <button @click="hideOverlay">隐藏浮窗</button>
          <button @click="stop">结束会话</button>
        </div>
      </div>
      <label class="row" style="gap: 6px; margin-top: 8px">
        <input type="checkbox" v-model="autoSpeak" style="width: auto" />
        <span>自动朗读最新译文（Edge TTS）</span>
      </label>
      <div class="muted">PID: {{ session.pid || '—' }} · 窗口: {{ session.window_title || '等待窗口…' }}</div>
      <div v-if="error" class="muted" style="color: var(--bad); margin-top: 8px">{{ error }}</div>
      <div v-if="lastLines.length" style="margin-top: 12px">
        <div class="label">最近译文</div>
        <div v-for="(l, i) in lastLines" :key="i" class="history-item">
          <div class="muted">{{ l.original || '' }}</div>
          <div>{{ l.text }}</div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import {
  confirmGame,
  setGameCapture,
  speakText,
  startGame,
  stopGame,
  getGameStatus,
  type GameSession,
  type OverlayLine,
} from '../api/client'

const dragover = ref(false)
const candidates = ref<{ path: string; reason: string }[]>([])
const session = ref<GameSession | null>(null)
const capturing = ref(false)
const autoSpeak = ref(false)
const lastSpoken = ref('')
const error = ref('')
const lastLines = ref<OverlayLine[]>([])
let pollTimer: number | undefined

const canOverlay = computed(() => !!session.value && session.value.status === 'running')

async function pickGame() {
  if (!window.desktop) {
    error.value = '请使用 Electron 客户端选择游戏'
    return
  }
  const p = await window.desktop.openGame()
  if (p) await launch(p)
}

async function onDrop(e: DragEvent) {
  dragover.value = false
  const file = e.dataTransfer?.files?.[0]
  const path = (file as (File & { path?: string }) | undefined)?.path
  if (!path) {
    error.value = '未获取到文件路径，请用点击选择'
    return
  }
  await launch(path)
}

async function launch(path: string) {
  error.value = ''
  candidates.value = []
  try {
    const res = await startGame({ path })
    if ('need_confirm' in res && res.need_confirm) {
      candidates.value = res.candidates
      return
    }
    session.value = res as GameSession
    startPoll()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

async function confirmCandidate(path: string) {
  try {
    session.value = await confirmGame({ path })
    candidates.value = []
    startPoll()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

async function toggleCapture() {
  if (!session.value) return
  const next = !capturing.value
  try {
    await setGameCapture({ session_id: session.value.session_id, enabled: next })
    capturing.value = next
    if (next) {
      await showOverlay()
      if (window.desktop) await window.desktop.setClickThrough(true)
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

async function showOverlay() {
  if (window.desktop) await window.desktop.showOverlay()
}

async function hideOverlay() {
  if (window.desktop) await window.desktop.hideOverlay()
}

async function stop() {
  if (!session.value) return
  try {
    await stopGame(session.value.session_id)
    capturing.value = false
    await hideOverlay()
    session.value = null
    stopPoll()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

function startPoll() {
  stopPoll()
  pollTimer = window.setInterval(async () => {
    if (!session.value) return
    try {
      const s = await getGameStatus(session.value.session_id)
      session.value = { ...session.value, ...s }
      if (s.lines?.length) {
        lastLines.value = s.lines.slice(-8).reverse()
        if (window.desktop) window.desktop.pushOverlayLines(s.lines)
        await maybeSpeak(s.lines)
      }
      if (s.status !== 'running') {
        capturing.value = false
        stopPoll()
      }
    } catch {
      // 忽略单次失败
    }
  }, 800)
}

/** 只朗读最新且与上次不同的译文，避免刷屏 */
async function maybeSpeak(lines: OverlayLine[]) {
  if (!autoSpeak.value || !capturing.value) return
  const latest = [...lines].reverse().find((l) => l.text && l.text.trim())
  if (!latest) return
  if (latest.text === lastSpoken.value) return
  lastSpoken.value = latest.text
  try {
    await speakText(latest.text, 'zh')
  } catch {
    // 朗读失败不打断游戏翻译
  }
}

function stopPoll() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
}

onUnmounted(() => {
  stopPoll()
})
</script>
