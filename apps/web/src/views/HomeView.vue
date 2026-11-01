<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { useWorkspace } from '../stores/workspace'
const workspace = useWorkspace()
const money = (cents: number) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(cents / 100)
</script>

<template>
  <div class="welcome"><div><span class="eyebrow">FUTURELEDGER</span><h1>你好，{{ workspace.username }}</h1><p>当前登录用户的合成账户余额。</p></div><RouterLink to="/assistant" class="primary-button">✦　问问 AI 助手</RouterLink></div>
  <div v-if="workspace.accountError" class="card page-card"><p class="auth-error">{{ workspace.accountError }}</p><button class="primary-button" @click="workspace.refreshAccounts().catch(() => undefined)">重新加载账户</button></div>
  <div v-else-if="workspace.accounts.length" class="grid summary-grid">
    <article class="card balance-card"><div class="card-head"><span>账户总余额</span><span class="live-label"><i></i>账本快照</span></div><strong class="balance">{{ money(workspace.totalBalanceCents) }}</strong><p>{{ workspace.accounts.length }} 个授权账户 · 登录或转账后刷新</p></article>
    <article v-for="account in workspace.accounts" :key="account.account_id" class="card metric-card"><div class="card-head"><span>{{ account.account_name }}</span></div><strong>{{ money(account.balance_cents) }}</strong><p class="muted">当前合成账本余额</p></article>
  </div>
  <section class="card page-card"><h2>查询收支和交易</h2><p>在智能体小智中查询月份、类别或商户统计，以及收入和支出明细。</p><RouterLink to="/assistant" class="text-link">进入智能体小智 →</RouterLink></section>
  <section class="card page-card"><h2>未来账本</h2><p>调整目标金额、工资日和最低保留余额，运行确定性的 30 天现金流模拟。</p><RouterLink to="/future" class="text-link">运行模拟 →</RouterLink></section>
</template>
