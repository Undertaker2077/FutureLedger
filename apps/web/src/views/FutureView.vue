<script setup lang="ts">
import { ref } from 'vue'
import { useWorkspace } from '../stores/workspace'

const workspace = useWorkspace(); const salaryDay = ref(17); const purchaseDay = ref(19); const dailyBudget = ref(8000); const floor = ref(300000); const goal = ref(600000); const result = ref<Record<string, unknown> | null>(null); const error = ref(''); const loading = ref(false)
async function simulate() {
  loading.value = true; error.value = ''; result.value = null
  try { const response = await workspace.simulate('demo-goal', { salary_day: salaryDay.value, purchase_day: purchaseDay.value, daily_budget_cents: dailyBudget.value, floor_cents: floor.value, goal_cents: goal.value }); result.value = response.result }
  catch (caught) { error.value = caught instanceof Error ? caught.message : '模拟失败，请重试。' }
  finally { loading.value = false }
}
</script>
<template><section class="card page-card future-page"><span class="eyebrow">DETERMINISTIC CASHFLOW</span><h1>未来账本</h1><p>LLM 只提取目标和约束；余额、日期和可行性由后端确定性模拟，不会自动执行转账。</p><div class="plan-form"><label>工资日<input v-model.number="salaryDay" type="number" min="1" max="30"></label><label>购买日<input v-model.number="purchaseDay" type="number" min="1" max="30"></label><label>每日预算（分）<input v-model.number="dailyBudget" type="number" min="0"></label><label>最低保留（分）<input v-model.number="floor" type="number" min="0"></label><label>目标金额（分）<input v-model.number="goal" type="number" min="0"></label></div><button class="primary-button" :disabled="loading" @click="simulate">{{ loading ? '模拟中…' : '运行 30 天现金流模拟' }}</button><p v-if="error" class="auth-error">{{ error }}</p><div v-if="result" class="notice simulation-result"><b>模拟完成</b><pre>{{ JSON.stringify(result, null, 2) }}</pre></div></section></template>
