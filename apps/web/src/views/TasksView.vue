<script setup lang="ts">
import { useWorkspace } from '../stores/workspace';const ws=useWorkspace()
</script>
<template><div class="page-intro"><div><span class="eyebrow">OPERATIONS & PLANS</span><h1>任务中心</h1><p>演示任务展示确认状态；实际操作状态必须以服务端和银行查证为准。</p></div></div><div class="task-list"><article v-for="t in ws.tasks" :key="t.id" class="card task-row"><div class="task-mark">◷</div><div class="task-info"><b>{{t.title}}</b><small>{{t.detail}}</small><code>{{t.id}}</code></div><div class="task-actions"><span class="task-status">{{t.status}}</span><button v-if="t.status==='待确认'" class="secondary-button" @click="ws.approveDemoTask(t.id)">本地确认</button></div></article></div><div class="notice">“本地确认”只演示界面状态，不代表银行授权、验证或交易已经发生。</div></template>
