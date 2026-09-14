<template>
  <div class="page">
    <header class="page-head">
      <h1>文字翻译</h1>
      <p>粘贴文本或上传整个文件；可导出为文本或语音。</p>
    </header>

    <section class="card">
      <div class="row" style="margin-bottom: 12px">
        <div style="flex: 1; min-width: 140px">
          <div class="label">源语言</div>
          <select v-model="sourceLang">
            <option value="auto">自动检测</option>
            <option value="zh">中文</option>
            <option value="en">英语</option>
            <option value="ja">日语</option>
            <option value="ko">韩语</option>
          </select>
        </div>
        <div style="flex: 1; min-width: 140px">
          <div class="label">目标语言</div>
          <select v-model="targetLang">
            <option value="zh">中文</option>
            <option value="en">英语</option>
            <option value="ja">日语</option>
            <option value="ko">韩语</option>
          </select>
        </div>
        <div style="align-self: flex-end; display: flex; gap: 8px; flex-wrap: wrap">
          <button class="primary" :disabled="loading || !input.trim()" @click="runTranslate">
            {{ loading ? '翻译中…' : '翻译' }}
          </button>
          <button :disabled="!result" @click="copyResult">复制</button>
          <button :disabled="!result" @click="downloadTxt">导出文本</button>
          <button :disabled="!result || exportingAudio" @click="exportAudio">
            {{ exportingAudio ? '合成中…' : '导出语音' }}
          </button>
          <button :disabled="!input && !result" @click="clearAll">清空</button>
        </div>
      </div>

      <div class="row" style="margin-bottom: 12px">
        <TtsControls :text="result" :lang="targetLang" :disabled="!result" />
      </div>

      <div class="grid-2">
        <div>
          <div class="label">原文</div>
          <textarea v-model="input" placeholder="输入要翻译的文字…" style="min-height: 220px" />
        </div>
        <div>
          <div class="label">
            译文
            <span v-if="meta" class="muted" style="margin-left: 8px">
              {{ meta.engine }} · {{ meta.latency_ms }}ms
            </span>
          </div>
          <div class="result-box" style="min-height: 220px">
            <template v-if="result">{{ result }}</template>
            <span v-else class="muted">译文将显示在这里</span>
          </div>
        </div>
      </div>
      <div v-if="audioUrl" class="row" style="margin-top: 10px">
        <audio controls :src="audioUrl" style="flex: 1; min-width: 220px"></audio>
        <button @click="downloadAudio">下载 MP3</button>
      </div>
      <div v-if="error" class="muted" style="color: var(--bad); margin-top: 8px">{{ error }}</div>
    </section>

    <section class="card">
      <strong>上传文件整译</strong>
      <p class="muted" style="margin: 6px 0 12px">
        支持 txt / md / srt / vtt / csv / log / html / xml / json / docx / pdf
      </p>
      <div
        class="drop-zone"
        :class="{ dragover }"
        @dragover.prevent="dragover = true"
        @dragleave="dragover = false"
        @drop.prevent="onDrop"
        @click="pickFile"
      >
        <div>{{ fileBusy ? '文件翻译中…' : '点击选择文件，或拖拽到此处' }}</div>
        <div v-if="fileMeta" class="muted" style="margin-top: 6px">
          {{ fileMeta.original_name }} · {{ fileMeta.format }} · {{ fileMeta.chunks }} 段 · {{ fileMeta.engine }}
        </div>
      </div>
      <input
        ref="fileInput"
        type="file"
        accept=".txt,.md,.markdown,.srt,.vtt,.csv,.log,.html,.htm,.xml,.json,.docx,.pdf"
        style="display: none"
        @change="onFile"
      />
      <div v-if="fileMeta?.output_txt" class="row" style="margin-top: 10px">
        <button @click="downloadFileTxt">下载文件译文 TXT</button>
      </div>
    </section>

    <section class="card">
      <div class="row between" style="margin-bottom: 8px">
        <strong>历史记录</strong>
        <button v-if="history.length" @click="clearHistory">清空历史</button>
      </div>
      <div v-if="!history.length" class="empty">暂无历史</div>
      <div v-else>
        <div
          v-for="(item, i) in history"
          :key="i"
          class="history-item"
          @click="restore(item)"
        >
          <div class="muted" style="margin-bottom: 4px">
            {{ item.sourceLang }} → {{ item.targetLang }} · {{ item.time }}
          </div>
          <div style="display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden">
            {{ item.input }}
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import TtsControls from '../components/TtsControls.vue'
import {
  exportFileTts,
  fileAudioUrl,
  fileDownloadUrl,
  translateFile,
  translateTextStream,
  type FileTranslateResult,
  type TranslateResult,
} from '../api/client'

const input = ref('')
const result = ref('')
const sourceLang = ref('auto')
const targetLang = ref('zh')
const loading = ref(false)
const error = ref('')
const meta = ref<TranslateResult | null>(null)

const fileInput = ref<HTMLInputElement | null>(null)
const dragover = ref(false)
const fileBusy = ref(false)
const fileMeta = ref<FileTranslateResult | null>(null)

const exportingAudio = ref(false)
const audioPath = ref('')
const audioUrl = ref('')

interface HistoryItem {
  input: string
  output: string
  sourceLang: string
  targetLang: string
  time: string
}

const history = ref<HistoryItem[]>([])
const HIST_KEY = 'ait_text_history'

function loadHistory() {
  try {
    const raw = localStorage.getItem(HIST_KEY)
    history.value = raw ? JSON.parse(raw) : []
  } catch {
    history.value = []
  }
}

function saveHistory() {
  localStorage.setItem(HIST_KEY, JSON.stringify(history.value.slice(0, 50)))
}

async function runTranslate() {
  error.value = ''
  result.value = ''
  meta.value = null
  loading.value = true
  try {
    const res = await translateTextStream(
      {
        text: input.value,
        source_lang: sourceLang.value,
        target_lang: targetLang.value,
      },
      (full) => {
        result.value = full
      },
    )
    result.value = res.text || result.value
    meta.value = res
    history.value.unshift({
      input: input.value,
      output: result.value,
      sourceLang: sourceLang.value,
      targetLang: targetLang.value,
      time: new Date().toLocaleString(),
    })
    history.value = history.value.slice(0, 50)
    saveHistory()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function copyResult() {
  if (result.value) await navigator.clipboard.writeText(result.value)
}

function downloadTxt() {
  if (!result.value) return
  const blob = new Blob([result.value], { type: 'text/plain;charset=utf-8' })
  triggerDownload(blob, `译文_${Date.now()}.txt`)
}

async function exportAudio() {
  if (!result.value) return
  exportingAudio.value = true
  error.value = ''
  try {
    const res = await exportFileTts({
      text: result.value,
      lang: targetLang.value,
    })
    audioPath.value = res.path
    audioUrl.value = fileAudioUrl(res.path)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    exportingAudio.value = false
  }
}

function downloadAudio() {
  if (!audioUrl.value) return
  triggerDownload(audioUrl.value, `译文_${Date.now()}.mp3`)
}

function triggerDownload(hrefOrBlob: string | Blob, filename: string) {
  const a = document.createElement('a')
  if (typeof hrefOrBlob === 'string') {
    a.href = hrefOrBlob
  } else {
    a.href = URL.createObjectURL(hrefOrBlob)
  }
  a.download = filename
  a.click()
  if (typeof hrefOrBlob !== 'string') {
    setTimeout(() => URL.revokeObjectURL(a.href), 2000)
  }
}

function pickFile() {
  fileInput.value?.click()
}

function onFile(e: Event) {
  const el = e.target as HTMLInputElement
  const file = el.files?.[0]
  el.value = ''
  if (file) void handleFile(file)
}

function onDrop(e: DragEvent) {
  dragover.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) void handleFile(file)
}

async function handleFile(file: File) {
  fileBusy.value = true
  error.value = ''
  fileMeta.value = null
  try {
    const res = await translateFile(file, sourceLang.value, targetLang.value)
    fileMeta.value = res
    input.value = `（来自文件：${file.name}）\n${''}`
    result.value = res.text
    meta.value = {
      text: res.text,
      engine: res.engine || 'file',
      latency_ms: 0,
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    fileBusy.value = false
  }
}

function downloadFileTxt() {
  if (!fileMeta.value?.output_txt) return
  const name = `${(fileMeta.value.original_name || 'file').replace(/\.[^.]+$/, '')}_${targetLang.value}.txt`
  window.open(fileDownloadUrl(fileMeta.value.output_txt, name), '_blank')
}

function clearAll() {
  input.value = ''
  result.value = ''
  meta.value = null
  error.value = ''
  audioPath.value = ''
  audioUrl.value = ''
  fileMeta.value = null
}

function clearHistory() {
  history.value = []
  saveHistory()
}

function restore(item: HistoryItem) {
  input.value = item.input
  result.value = item.output
  sourceLang.value = item.sourceLang
  targetLang.value = item.targetLang
}

onMounted(loadHistory)
onUnmounted(() => {
  /* no-op */
})
</script>
