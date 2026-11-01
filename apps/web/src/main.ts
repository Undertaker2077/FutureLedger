import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'
import { pages } from './pages'

const router = createRouter({ history: createWebHistory(), routes: pages })
createApp(App).use(createPinia()).use(router).mount('#app')
