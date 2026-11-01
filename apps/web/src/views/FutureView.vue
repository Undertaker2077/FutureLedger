<script setup lang="ts">
import { computed } from 'vue'
import { useWorkspace } from '../stores/workspace'
const ws=useWorkspace()
const result=computed(()=>ws.simulateDemo())
const money=(n:number)=>'¥'+(n/100).toLocaleString('zh-CN',{minimumFractionDigits:2})
</script>
<template><div class="page-intro"><div><span class="eyebrow">DETERMINISTIC SIMULATION</span><h1>未来账本</h1><p>编辑假设后按整数分逐日重算；不是收益或到账保证。</p></div></div><div class="future-layout"><section class="card assumptions"><h2>情景假设</h2><label>工资延迟：<b>{{ws.salaryDelay}} 天</b><input v-model.number="ws.salaryDelay" type="range" min="0" max="10"></label><label>每日支出预算<input v-model.number="ws.dailyBudget" type="number" min="0" step="500"></label><label>最低保留余额<input v-model.number="ws.minBalance" type="number" min="0" step="10000"></label><div class="notice">初始余额、工资及目标支出来自合成演示设定。</div></section><section class="card simulation"><div class="section-head"><div><h2>未来 30 天余额</h2><p>最低余额 {{money(result.min)}} · 第 {{result.minDay}} 天</p></div><span :class="result.feasible?'feasible':'infeasible'">{{result.feasible?'满足保留线':'低于保留线'}}</span></div><div class="balance-bars"><div v-for="d in result.days" :key="d.day" :title="'第'+d.day+'天 '+money(d.balance)" :style="{height:Math.max(5,Math.min(100,d.balance/65000))+'%'}" :class="d.balance<ws.minBalance?'below':''"></div></div><div class="axis"><span>今天</span><span>第{{15+ws.salaryDelay}}天 · 工资预计日</span><span>第30天</span></div><p class="muted">工资延迟后假设第 {{15+ws.salaryDelay}} 天到账；第20天计入目标购买支出 ¥6,800。</p></section></div><div class="notice">当前为本地合成情景，尚未连接 D 现金流服务。</div></template>
