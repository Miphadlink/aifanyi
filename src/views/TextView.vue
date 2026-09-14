<template>
  <div class="page">
    <header class="page-head">
      <h1>文字翻译</h1>
      <p>粘贴或输入文本，流式输出译文；支持历史记录。</p>
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
        <div style="align-self: flex-end; display: flex; gap: 8px">
          <button class="primary" :disabled="loading || !input.trim()" @click="runTranslate">
            {{ loading ? '翻译中…' : '翻译' }}
          </button>
          <button :disabled="!result || speaking" @click="speakResult">
            {{ speaking ? '朗读中…' : '朗读译文' }}
          </button>
          <button :disabled="!result" @click="copyResult">复制</button>
          <button :disabled="!input && !result" @click="clearAll">清空</button>
        </div>
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
      <div v-if="error" class="muted" style="color: var(--bad); margin-top: 8px">{{ error }}</div>
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
import { onMounted, ref } from 'vue'
import { speakText, translateTextStream, type TranslateResult } from '../api/client'

const input = ref('')
const result = ref('')
const sourceLang = ref('auto')
const targetLang = ref('zh')
const loading = ref(false)
const speaking = ref(false)
const error = ref('')
const meta = ref<TranslateResult | null>(null)

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

async function speakResult() {
  if (!result.value) return
  speaking.value = true
  error.value = ''
  try {
    await speakText(result.value, targetLang.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    speaking.value = false
  }
}

function clearAll() {
  input.value = ''
  result.value = ''
  meta.value = null
  error.value = ''
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
</script>
