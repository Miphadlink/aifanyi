import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import './styles/main.css'

import TextView from './views/TextView.vue'
import ImageView from './views/ImageView.vue'
import VideoView from './views/VideoView.vue'
import GameView from './views/GameView.vue'
import SettingsView from './views/SettingsView.vue'
import OverlayView from './views/OverlayView.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/text' },
    { path: '/text', component: TextView },
    { path: '/image', component: ImageView },
    { path: '/video', component: VideoView },
    { path: '/game', component: GameView },
    { path: '/settings', component: SettingsView },
    { path: '/overlay', component: OverlayView },
  ],
})

createApp(App).use(router).mount('#app')
