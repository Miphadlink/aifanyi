<template>
  <div class="app-shell" :class="{ 'is-overlay': isOverlay }">
    <aside v-if="!isOverlay" class="side-nav">
      <div class="brand">
        <span class="brand-mark">译</span>
        <div>
          <div class="brand-title">AI 智能翻译</div>
          <div class="brand-sub">文字 · 图片 · 视频 · 游戏</div>
        </div>
      </div>
      <nav>
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: $route.path === item.path }"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
      <div class="side-foot">
        <div class="status-dot" :class="apiOk ? 'ok' : 'bad'"></div>
        <span>{{ apiOk ? '本地服务正常' : '本地服务未连接' }}</span>
      </div>
    </aside>
    <main class="main-pane" :class="{ 'overlay-main': isOverlay }">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ping } from './api/client'

const route = useRoute()
const isOverlay = computed(() => route.path === '/overlay')
const apiOk = ref(false)
let timer: number | undefined

const navItems = [
  { path: '/text', label: '文字翻译', icon: '文' },
  { path: '/image', label: '图片翻译', icon: '图' },
  { path: '/video', label: '视频翻译', icon: '影' },
  { path: '/game', label: '游戏翻译', icon: '游' },
  { path: '/settings', label: '设置', icon: '设' },
]

async function checkApi() {
  try {
    await ping()
    apiOk.value = true
  } catch {
    apiOk.value = false
  }
}

onMounted(() => {
  checkApi()
  timer = window.setInterval(checkApi, 8000)
})
onUnmounted(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<style scoped>
.overlay-main {
  padding: 0;
  overflow: hidden;
  background: transparent;
}
</style>
