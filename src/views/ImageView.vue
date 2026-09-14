<template>
  <div class="page">
    <header class="page-head">
      <h1>图片翻译</h1>
      <p>粘贴截图或拖入图片，OCR 识别后翻译；支持对照与覆盖。</p>
    </header>

    <section class="card">
      <div
        class="drop-zone"
        :class="{ dragover }"
        @dragover.prevent="dragover = true"
        @dragleave="dragover = false"
        @drop.prevent="onDrop"
        @click="pickFile"
      >
        <div>点击选择图片，或拖拽到此处</div>
        <div class="muted" style="margin-top: 6px">也支持 Ctrl+V 粘贴截图</div>
      </div>
      <input ref="fileInput" type="file" accept="image/*" style="display: none" @change="onFile" />
    </section>

    <section v-if="previewUrl" class="card">
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
        <div style="flex: 1; min-width: 120px">
          <div class="label">输出模式</div>
          <select v-model="overlay">
            <option :value="false">对照模式</option>
            <option :value="true">覆盖模式</option>
          </select>
        </div>
        <button class="primary" style="align-self: flex-end" :disabled="loading" @click="run">
          {{ loading ? '处理中…' : '识别并翻译' }}
        </button>
        <button style="align-self: flex-end" :disabled="!result?.target || speaking" @click="speakAll">
          {{ speaking ? '朗读中…' : '朗读译文' }}
        </button>
      </div>

      <div class="grid-2">
        <div>
          <div class="label">原图 / 覆盖预览</div>
          <img
            class="preview"
            :src="result?.overlay_data_url || previewUrl"
            alt="preview"
          />
        </div>
        <div>
          <div class="label">识别与译文</div>
          <div v-if="!result?.boxes?.length" class="empty">
            {{ result ? '未识别到文字' : '点击上方按钮开始' }}
          </div>
          <div v-else class="card" style="padding: 0; max-height: 420px; overflow: auto">
            <div v-for="(b, i) in result.boxes" :key="i" class="history-item">
              <div class="muted">原文：{{ b.text }}</div>
              <div style="margin-top: 4px; display: flex; justify-content: space-between; gap: 8px">
                <span>{{ b.translation || '—' }}</span>
                <button v-if="b.translation" @click="speakOne(b.translation)">读</button>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-if="error" class="muted" style="color: var(--bad); margin-top: 8px">{{ error }}</div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { speakText, translateImage, type ImageTranslateResult } from '../api/client'

const fileInput = ref<HTMLInputElement | null>(null)
const dragover = ref(false)
const previewUrl = ref('')
const base64 = ref('')
const sourceLang = ref('auto')
const targetLang = ref('zh')
const overlay = ref(false)
const loading = ref(false)
const speaking = ref(false)
const error = ref('')
const result = ref<ImageTranslateResult | null>(null)

function pickFile() {
  fileInput.value?.click()
}

function onFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) readFile(file)
  input.value = ''
}

function onDrop(e: DragEvent) {
  dragover.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file && file.type.startsWith('image/')) readFile(file)
}

function readFile(file: File) {
  const reader = new FileReader()
  reader.onload = () => {
    const url = String(reader.result || '')
    previewUrl.value = url
    const comma = url.indexOf(',')
    base64.value = comma >= 0 ? url.slice(comma + 1) : url
    result.value = null
    error.value = ''
  }
  reader.readAsDataURL(file)
}

function onPaste(e: ClipboardEvent) {
  const item = Array.from(e.clipboardData?.items || []).find((i) => i.type.startsWith('image/'))
  const file = item?.getAsFile()
  if (file) readFile(file)
}

async function run() {
  if (!base64.value) return
  loading.value = true
  error.value = ''
  try {
    result.value = await translateImage({
      image_base64: base64.value,
      source_lang: sourceLang.value,
      target_lang: targetLang.value,
      overlay: overlay.value,
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function speakOne(text: string) {
  speaking.value = true
  error.value = ''
  try {
    await speakText(text, targetLang.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    speaking.value = false
  }
}

async function speakAll() {
  if (result.value?.target) await speakOne(result.value.target)
}

onMounted(() => window.addEventListener('paste', onPaste))
onUnmounted(() => window.removeEventListener('paste', onPaste))
</script>
