<template>
  <div class="overlay-root">
    <div
      v-for="(line, i) in lines"
      :key="i"
      class="overlay-line"
      :style="{
        left: line.x + 'px',
        top: line.y + 'px',
        width: Math.max(line.w, 40) + 'px',
        minHeight: Math.max(line.h, 18) + 'px',
      }"
    >
      {{ line.text }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

interface OverlayLine {
  x: number
  y: number
  w: number
  h: number
  text: string
}

const lines = ref<OverlayLine[]>([])
let off: (() => void) | undefined

onMounted(() => {
  if (window.desktop) {
    off = window.desktop.onOverlayLines((payload) => {
      lines.value = payload || []
    })
  }
  window.addEventListener('message', onMsg)
})

onUnmounted(() => {
  off?.()
  window.removeEventListener('message', onMsg)
})

function onMsg(e: MessageEvent) {
  if (e.data?.type === 'overlay-lines') {
    lines.value = e.data.lines || []
  }
}
</script>
