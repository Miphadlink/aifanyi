<template>
  <div class="tts-bar row" style="gap: 8px; flex-wrap: wrap; align-items: center">
    <button
      v-if="!state.playing && !state.paused"
      class="primary"
      :disabled="disabled || state.busy || !text"
      @click="onPlay"
    >
      {{ state.busy ? '合成中…' : '朗读' }}
    </button>
    <button v-if="state.playing" @click="onPause">暂停</button>
    <button v-if="state.paused" class="primary" @click="onResume">继续</button>
    <button v-if="state.playing || state.paused" @click="onStop">停止</button>
    <span v-if="state.error" class="muted" style="color: var(--bad)">{{ state.error }}</span>
    <span v-else-if="state.playing" class="muted">正在朗读…</span>
    <span v-else-if="state.paused" class="muted">已暂停</span>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive } from 'vue'
import { getTtsState, pauseTts, playTtsText, resumeTts, stopTts, subscribeTts } from '../api/ttsPlayer'

const props = defineProps<{
  text: string
  lang?: string
  disabled?: boolean
}>()

const state = reactive(getTtsState())
let off: (() => void) | undefined

function sync() {
  const s = getTtsState()
  state.playing = s.playing
  state.paused = s.paused
  state.busy = s.busy
  state.text = s.text
  state.error = s.error
}

async function onPlay() {
  await playTtsText(props.text, props.lang || 'zh')
  sync()
}

function onPause() {
  pauseTts()
  sync()
}

function onResume() {
  resumeTts()
  sync()
}

function onStop() {
  stopTts()
  sync()
}

onMounted(() => {
  off = subscribeTts(sync)
  sync()
})
onUnmounted(() => {
  off?.()
})
</script>
