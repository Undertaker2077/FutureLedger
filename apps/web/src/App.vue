<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { useWorkspace } from './stores/workspace'

const workspace = useWorkspace(); const route = useRoute()
const loginMode = ref<'login' | 'register'>('login'); const authUser = ref('test_user'); const authPassword = ref(''); const authError = ref('')
const links = [['/','总览','⌂'],['/bills','账单','▤'],['/subscriptions','代扣','↻'],['/future','未来账本','⌁'],['/tasks','任务','◷'],['/settings','偏好','⚙'],['/review','评审','◇'],['/assistant','智能体小智','✦']]
async function submitAuth() {
  authError.value = ''
  try { if (loginMode.value === 'register') await workspace.register(authUser.value, authPassword.value); await workspace.login(authUser.value, authPassword.value); authPassword.value = '' }
  catch (error) { authError.value = error instanceof Error ? error.message : '认证失败，请重试。' }
}
</script>
<template>
  <div v-if="workspace.authenticated" class="shell">
    <aside class="sidebar"><RouterLink to="/" class="brand"><span class="brand-mark">F</span><span>FutureLedger<small>未来账本</small></span></RouterLink><div class="profile"><div class="avatar">{{ workspace.username.slice(0, 1).toUpperCase() }}</div><div><b>{{ workspace.username }}</b><small>合成账户 · 已隔离</small></div><span class="online-dot"></span></div><nav><RouterLink v-for="item in links" :key="item[0]" :to="item[0]" class="nav-link"><span class="nav-icon">{{ item[2] }}</span>{{ item[1] }}</RouterLink></nav><div class="side-bottom"><div class="bank-badge"><i></i>模拟银行环境</div><button class="logout" @click="workspace.logout">退出登录</button><small>FutureLedger · Preview</small></div></aside>
    <main class="main"><header class="topbar"><div><span class="crumb">工作台</span><span class="slash">/</span><b>{{ String(route.meta.title || '工作台') }}</b></div><div class="top-actions"><span class="mode-pill api"><i></i>LLM API 连接</span><div class="top-avatar">{{ workspace.username.slice(0, 1).toUpperCase() }}</div></div></header><div class="content"><RouterView /></div></main>
  </div>
  <div v-else class="auth-page"><form class="auth-card" @submit.prevent="submitAuth"><div class="brand auth-brand"><span class="brand-mark">F</span><span>FutureLedger<small>未来账本</small></span></div><h1>{{ loginMode === 'login' ? '登录演示工作台' : '首次设置密码' }}</h1><p>仅使用合成账本数据。密码不会进入聊天记录或模型请求。</p><label for="auth-user">演示用户</label><select id="auth-user" v-model="authUser"><option value="test_user">test_user</option><option value="isolation_user">isolation_user</option></select><label for="auth-password">密码</label><input id="auth-password" v-model="authPassword" type="password" minlength="12" required placeholder="至少 12 个字符"><p v-if="authError" class="auth-error">{{ authError }}</p><button class="primary-button auth-submit" :disabled="workspace.authLoading">{{ workspace.authLoading ? '处理中…' : loginMode === 'login' ? '登录' : '设置并登录' }}</button><button type="button" class="link-button" @click="loginMode = loginMode === 'login' ? 'register' : 'login'; authError = ''">{{ loginMode === 'login' ? '首次使用？设置密码' : '已有密码？直接登录' }}</button></form></div>
</template>
