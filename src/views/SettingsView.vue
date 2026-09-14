<template>
  <div class="page">
    <header class="page-head">
      <h1>设置</h1>
      <p>翻译引擎、分场景模型、语言默认值。密钥仅保存在本机。</p>
    </header>

    <section class="card">
      <div class="grid-2">
        <div>
          <div class="label">API Base（OpenAI 兼容）</div>
          <input v-model="form.api_base" placeholder="https://api.openai.com/v1" />
        </div>
        <div>
          <div class="label">API Key</div>
          <input v-model="form.api_key" type="password" placeholder="sk-..." />
        </div>
      </div>

      <div class="row" style="margin-top: 12px">
        <button :disabled="fetchingModels" @click="doFetchModels">
          {{ fetchingModels ? '获取中…' : '获取模型列表' }}
        </button>
        <span class="muted">
          用上方 Base + Key 请求 /models；{{ models.length ? `已加载 ${models.length} 个` : '未获取' }}
        </span>
      </div>
      <div v-if="modelsError" class="muted" style="color: var(--bad); margin-top: 6px">
        {{ modelsError }}
      </div>

      <div class="grid-2" style="margin-top: 16px">
        <div>
          <div class="label">默认模型（未分场景时回退）</div>
          <select v-if="models.length" v-model="form.model">
            <option value="">— 手动输入 —</option>
            <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
          </select>
          <input v-if="!models.length" v-model="form.model" placeholder="agnes-2.5-flash" />
        </div>
        <div>
          <div class="label">文字翻译模型</div>
          <select v-if="models.length" v-model="form.text_model">
            <option value="">跟随默认</option>
            <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
          </select>
          <input v-if="!models.length" v-model="form.text_model" placeholder="留空=默认模型" />
        </div>
        <div>
          <div class="label">图片翻译模型</div>
          <select v-if="models.length" v-model="form.image_model">
            <option value="">跟随默认</option>
            <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
          </select>
          <input v-if="!models.length" v-model="form.image_model" placeholder="留空=默认模型" />
        </div>
        <div>
          <div class="label">视频翻译模型</div>
          <select v-if="models.length" v-model="form.video_model">
            <option value="">跟随默认</option>
            <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
          </select>
          <input v-if="!models.length" v-model="form.video_model" placeholder="agnes-video-v2.0" />
        </div>
        <div>
          <div class="label">游戏翻译模型</div>
          <select v-if="models.length" v-model="form.game_model">
            <option value="">跟随默认</option>
            <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
          </select>
          <input v-if="!models.length" v-model="form.game_model" placeholder="留空=默认模型" />
        </div>
        <div>
          <div class="label">默认目标语言</div>
          <select v-model="form.target_lang">
            <option value="zh">中文</option>
            <option value="en">英语</option>
            <option value="ja">日语</option>
            <option value="ko">韩语</option>
          </select>
        </div>
        <div>
          <div class="label">默认源语言</div>
          <select v-model="form.source_lang">
            <option value="auto">自动检测</option>
            <option value="zh">中文</option>
            <option value="en">英语</option>
            <option value="ja">日语</option>
            <option value="ko">韩语</option>
          </select>
        </div>
        <div>
          <div class="label">游戏采样间隔 (ms)</div>
          <input v-model.number="form.game_sample_ms" type="number" min="150" max="2000" step="50" />
        </div>
        <div>
          <div class="label">本地离线翻译（Ollama）</div>
          <label class="row" style="gap: 8px">
            <input type="checkbox" v-model="form.use_local" style="width: auto" />
            <span>优先走本地模型</span>
          </label>
        </div>
        <div>
          <div class="label">本地模型名</div>
          <input v-model="form.local_model" placeholder="qwen2.5:7b-instruct" />
        </div>
      </div>

      <div class="row" style="margin-top: 16px">
        <button class="primary" :disabled="saving" @click="save">
          {{ saving ? '保存中…' : '保存设置' }}
        </button>
        <button @click="load">重新加载</button>
        <span v-if="message" class="muted">{{ message }}</span>
      </div>
      <div v-if="error" class="muted" style="color: var(--bad); margin-top: 8px">{{ error }}</div>
    </section>

    <section v-if="health" class="card">
      <strong>环境状态</strong>
      <div style="margin-top: 10px">
        <div>Python：{{ health.python }}</div>
        <div>ffmpeg：{{ health.ffmpeg ? '已安装' : '未安装（视频功能不可用）' }}</div>
        <div>GPU：{{ health.gpu }}</div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  fetchModels,
  getSettings,
  ping,
  saveSettings,
  type SettingsPayload,
} from '../api/client'

const form = ref<SettingsPayload>({
  api_base: '',
  api_key: '',
  model: '',
  text_model: '',
  image_model: '',
  video_model: 'agnes-video-v2.0',
  game_model: '',
  target_lang: 'zh',
  source_lang: 'auto',
  use_local: false,
  local_model: '',
  game_sample_ms: 300,
})
const saving = ref(false)
const message = ref('')
const error = ref('')
const health = ref<Awaited<ReturnType<typeof ping>> | null>(null)
const models = ref<string[]>([])
const fetchingModels = ref(false)
const modelsError = ref('')

async function load() {
  error.value = ''
  try {
    form.value = { ...form.value, ...(await getSettings()) }
    health.value = await ping()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

async function doFetchModels() {
  fetchingModels.value = true
  modelsError.value = ''
  try {
    const res = await fetchModels({
      api_base: form.value.api_base,
      api_key: form.value.api_key,
    })
    models.value = res.models || []
    if (!models.value.length) modelsError.value = '列表为空'
    message.value = `已获取 ${models.value.length} 个模型`
  } catch (e) {
    modelsError.value = e instanceof Error ? e.message : String(e)
  } finally {
    fetchingModels.value = false
  }
}

async function save() {
  saving.value = true
  error.value = ''
  message.value = ''
  try {
    form.value = { ...form.value, ...(await saveSettings(form.value)) }
    message.value = '已保存'
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>
