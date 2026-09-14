<template>
  <div class="page">
    <header class="page-head">
      <h1>视频翻译</h1>
      <p>支持 mp4/mkv/mov/avi/webm/flv/ts 等；ASR 后导出 SRT/ASS 字幕。</p>
    </header>

    <section class="card">
      <div
        class="drop-zone"
        :class="{ dragover }"
        @dragover.prevent="dragover = true"
        @dragleave="dragover = false"
        @drop.prevent="onDrop"
        @click="pickVideo"
      >
        <div>拖入视频文件，或点击选择</div>
        <div class="muted" style="margin-top: 6px">
          {{ fileName || '也支持 mp3/wav 等音频（仅出字幕）' }}
        </div>
      </div>
      <input
        ref="fileInput"
        type="file"
        accept="video/*,audio/*,.mkv,.ts,.m2ts,.flv,.avi,.wmv"
        style="display: none"
        @change="onFile"
      />
    </section>

    <section v-if="filePath || browserFile" class="card">
      <div class="row" style="margin-bottom: 12px">
        <div style="flex: 1; min-width: 120px">
          <div class="label">源语言</div>
          <select v-model="sourceLang">
            <option value="auto">自动检测</option>
            <option value="zh">中文</option>
            <option value="en">英语</option>
            <option value="ja">日语</option>
            <option value="ko">韩语</option>
          </select>
        </div>
        <div style="flex: 1; min-width: 120px">
          <div class="label">目标语言</div>
          <select v-model="targetLang">
            <option value="zh">中文</option>
            <option value="en">英语</option>
            <option value="ja">日语</option>
            <option value="ko">韩语</option>
          </select>
        </div>
        <label class="row" style="gap: 6px; align-self: flex-end">
          <input type="checkbox" v-model="useExistingSubs" style="width: auto" />
          <span>优先已有字幕轨</span>
        </label>
        <label class="row" style="gap: 6px; align-self: flex-end">
          <input type="checkbox" v-model="embedSub" style="width: auto" />
          <span>嵌入软字幕</span>
        </label>
        <label class="row" style="gap: 6px; align-self: flex-end">
          <input type="checkbox" v-model="useTts" style="width: auto" />
          <span>生成译文配音</span>
        </label>
        <button class="primary" style="align-self: flex-end" :disabled="loading || !canStart" @click="start">
          {{ loading ? '提交中…' : '开始翻译' }}
        </button>
      </div>

      <div v-if="task" class="card">
        <div class="row between" style="margin-bottom: 8px">
          <strong>{{ task.message || task.status }}</strong>
          <span class="tag">{{ Math.round(task.progress) }}%</span>
        </div>
        <div class="progress"><i :style="{ width: task.progress + '%' }"></i></div>
        <div v-if="task.status === 'done'" class="row" style="margin-top: 12px">
          <button v-if="task.output_srt" @click="open(task.output_srt)">打开 SRT</button>
          <button v-if="task.output_ass" @click="open(task.output_ass)">打开 ASS</button>
          <button v-if="task.output_audio" @click="open(task.output_audio)">打开配音 MP3</button>
          <button v-if="task.output_dubbed" @click="open(task.output_dubbed)">打开配音视频</button>
        </div>
      </div>
      <div v-if="error" class="muted" style="color: var(--bad); margin-top: 8px">{{ error }}</div>
      <div v-if="!isElectron" class="muted" style="margin-top: 8px">
        浏览器开发模式：请选择本地文件由后端接收上传路径；完整拖拽请用 Electron 客户端。
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { getVideoTask, startVideoTask, type VideoTask } from '../api/client'

const isElectron = typeof window !== 'undefined' && !!window.desktop
const fileInput = ref<HTMLInputElement | null>(null)
const dragover = ref(false)
const filePath = ref('')
const fileName = ref('')
const browserFile = ref<File | null>(null)
const sourceLang = ref('auto')
const targetLang = ref('zh')
const useExistingSubs = ref(true)
const embedSub = ref(false)
const useTts = ref(false)
const loading = ref(false)
const error = ref('')
const task = ref<VideoTask | null>(null)
let pollTimer: number | undefined

const canStart = computed(() => !!filePath.value || !!browserFile.value)

function pickVideo() {
  fileInput.value?.click()
}

async function onFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  await adoptFile(file)
}

async function onDrop(e: DragEvent) {
  dragover.value = false
  const file = e.dataTransfer?.files?.[0]
  if (!file) return
  let path: string | null = null
  if (window.desktop?.getPathForFile) {
    path = window.desktop.getPathForFile(file)
  }
  if (!path) {
    path = (file as File & { path?: string }).path || null
  }
  if (path) {
    filePath.value = path
    fileName.value = file.name
    browserFile.value = null
    task.value = null
    return
  }
  await adoptFile(file)
}

async function adoptFile(file: File) {
  fileName.value = file.name
  task.value = null
  let path: string | null = null
  if (window.desktop?.getPathForFile) {
    path = window.desktop.getPathForFile(file)
  }
  if (!path) {
    path = (file as File & { path?: string }).path || null
  }
  if (path) {
    filePath.value = path
    browserFile.value = null
    return
  }
  browserFile.value = file
  filePath.value = ''
}

async function start() {
  error.value = ''
  loading.value = true
  try {
    let path = filePath.value
    if (!path && browserFile.value) {
      const fd = new FormData()
      fd.append('file', browserFile.value)
      const res = await fetch('http://127.0.0.1:8765/translate/video/upload', {
        method: 'POST',
        body: fd,
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      path = data.path
      filePath.value = path
    }
    task.value = await startVideoTask({
      path,
      source_lang: sourceLang.value,
      target_lang: targetLang.value,
      use_existing_subs: useExistingSubs.value,
      embed_sub: embedSub.value,
      tts: useTts.value,
    })
    poll()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function poll() {
  stopPoll()
  pollTimer = window.setInterval(async () => {
    if (!task.value) return
    try {
      const next = await getVideoTask(task.value.task_id)
      task.value = next
      if (next.status === 'done' || next.status === 'failed') stopPoll()
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      stopPoll()
    }
  }, 1200)
}

function stopPoll() {
  if (pollTimer) {
    window.clearInterval(pollTimer)
    pollTimer = undefined
  }
}

async function open(p: string) {
  if (window.desktop) await window.desktop.openPath(p)
  else alert(p)
}

onUnmounted(stopPoll)
</script>
