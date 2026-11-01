<script setup lang="ts">
import { ref } from 'vue'
import { useWorkspace, type ChatMessage } from '../stores/workspace'

const workspace = useWorkspace(); const draft = ref(''); const password = ref(''); const category = ref('购物'); const authorizationId = ref(''); const actionError = ref('')
const suggestions = ['这个月的支出是多少？', '8月和9月的各项净支出', '上个月的收入明细', '我想存6000元买电脑，至少留3000元']
async function send(value = draft.value) { const text = value.trim(); if (!text) return; draft.value = ''; await workspace.send(text).catch(() => undefined) }
async function authorize(message: ChatMessage) {
  if (!message.action_id || !password.value) return
  actionError.value = ''
  try { const response = await workspace.authorizeAction(message.action_id, password.value); authorizationId.value = response.authorization_id; if (response.categories?.length && !response.categories.includes(category.value)) category.value = response.categories[0]; password.value = '' }
  catch (error) { actionError.value = error instanceof Error ? error.message : '密码验证失败。' }
}
async function confirm(message: ChatMessage) {
  if (!message.action_id || !authorizationId.value) return
  actionError.value = ''
  try { await workspace.confirmAction(message.action_id, authorizationId.value, category.value); authorizationId.value = '' }
  catch (error) { actionError.value = error instanceof Error ? error.message : '确认失败。' }
}
function displayRow(row: Record<string, unknown>) { return Object.entries(row).filter(([key]) => !['id', 'transaction_id'].includes(key)).map(([key, value]) => `${key}: ${value}`).join(' · ') }
</script>
<template>
  <div class="assistant-layout">
    <section class="card chat-card">
      <div class="chat-head"><div><span class="eyebrow">FUTURELEDGER AI</span><h1>智能体小智</h1></div><span class="mode-pill api"><i></i>LLM API</span></div>
      <div class="chat-body">
        <div v-if="!workspace.messages.length" class="welcome-message"><div class="assistant-avatar">✦</div><h2>你好，我是你的财务助手</h2><p>查询账单、制定存钱计划，或发起需要确认的演示转账。</p><div class="suggestions"><button v-for="question in suggestions" :key="question" @click="send(question)">{{ question }}　↗</button></div></div>
        <div v-for="(message, index) in workspace.messages" :key="index" class="message" :class="message.role">
          <div v-if="message.role === 'assistant'" class="assistant-avatar small">✦</div>
          <div>
            <p>{{ message.text }}</p>
            <div v-if="message.role === 'assistant' && message.rows?.length" class="result-box">
              <div v-for="(row, rowIndex) in message.rows.slice(0, 20)" :key="rowIndex" class="result-row">{{ displayRow(row) }}</div>
              <a v-if="message.query_id" class="text-link" :href="`/api/queries/${message.query_id}/export.csv?session_id=${encodeURIComponent(workspace.sessionId)}`" target="_blank">导出 CSV</a>
            </div>
            <div v-if="message.status === 'confirmation_required'" class="transfer-card">
              <b>需要确认转账</b><p>{{ message.text }}</p>
              <label>登录密码<input v-model="password" type="password" minlength="12" autocomplete="current-password"></label>
              <label>用途类别<select v-model="category"><option v-for="item in message.categories || ['餐饮','交通','购物','娱乐','订阅','房租','医疗','其他']" :key="item">{{ item }}</option></select></label>
              <button v-if="!authorizationId" class="primary-button" :disabled="!password" @click="authorize(message)">验证密码</button>
              <button v-else class="primary-button" @click="confirm(message)">确认并完成转账</button>
              <small v-if="actionError" class="auth-error">{{ actionError }}</small>
            </div>
          </div>
        </div>
        <div v-if="workspace.loading" class="loading-line">正在理解问题并查询授权范围内的数据…</div>
      </div>
      <form class="composer" @submit.prevent="send()"><textarea v-model="draft" rows="2" placeholder="输入你的问题…" @keydown.enter.exact.prevent="send()"></textarea><div class="composer-foot"><span>查询结果不展示 SQL、IntentPlan 或内部流水 ID</span><button class="send-button" :disabled="!draft.trim() || workspace.loading">发送　↑</button></div></form>
    </section>
    <aside class="card assistant-aside"><h3>快捷场景</h3><button @click="draft='2026年9月各类别净支出排名前五'">▤　分析本月支出</button><button @click="draft='最近三个月每月餐饮净支出趋势'">⌁　查看支出趋势</button><button @click="draft='给测试用户B转25元'">↻　演示转账</button><div class="aside-note"><span>ⓘ</span><p>LLM 只负责理解和生成结构化计划，查询、权限和转账确认由后端完成。</p></div><div class="service-status"><i></i><span>当前用户：{{ workspace.username }}<small>仅使用合成数据</small></span></div></aside>
  </div>
</template>
