<script setup lang="ts">
import { computed } from 'vue'

type Result = {
  answer?: string
  chart?: string
  value_format?: 'money' | 'count'
  rows?: Record<string, unknown>[]
}

const props = defineProps<{ result: Result }>()
const rows = computed(() => props.result.rows || [])
const chart = computed(() => props.result.chart || (rows.value.length ? 'table' : 'metric_card'))

const labels: Record<string, string> = {
  group_key: '时间', series_key: '类别', value_cents: '金额', value: '数值',
  category: '类别', merchant: '商户', account_name: '账户', account_id: '账户',
  posted_at: '日期', amount_cents: '金额', kind: '类型', direction: '方向',
}

function label(key: string) { return labels[key] || key.replaceAll('_', ' ') }
function money(value: unknown) {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? `¥${(numeric / 100).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : String(value ?? '—')
}
function formatValue(key: string, value: unknown) {
  if (key.endsWith('_cents') || key === 'value_cents' || (props.result.value_format === 'money' && typeof value === 'number')) return money(value)
  return String(value ?? '—')
}
function cell(row: Record<string, unknown>, key: string) { return formatValue(key, row[key]) }
const columns = computed(() => {
  const keys: string[] = []
  for (const row of rows.value) for (const key of Object.keys(row)) if (!['id', 'transaction_id'].includes(key) && !keys.includes(key)) keys.push(key)
  return keys
})

const points = computed(() => rows.value.map(row => ({
  group: String(row.group_key ?? row.date ?? row.period ?? ''),
  series: String(row.series_key ?? row.category ?? ''),
  value: Number(row.value_cents ?? row.value ?? row.amount_cents ?? 0),
})))
const groups = computed(() => [...new Set(points.value.map(point => point.group))])
const series = computed(() => [...new Set(points.value.map(point => point.series || '总计'))])
const maxValue = computed(() => Math.max(1, ...points.value.map(point => point.value)))
const palette = ['#087d68', '#d57c4b', '#5877ba', '#a15d9a', '#c3a12d', '#4196a0', '#da6574', '#7d8d43']
function pointValue(group: string, seriesName: string) { return points.value.find(point => point.group === group && (point.series || '总计') === seriesName)?.value || 0 }
function linePath(seriesName: string) {
  if (!groups.value.length) return ''
  const width = 560; const height = 180; const left = 46; const top = 12
  return groups.value.map((group, index) => {
    const x = left + (groups.value.length === 1 ? width / 2 : index * width / (groups.value.length - 1))
    const y = top + height - pointValue(group, seriesName) / maxValue.value * height
    return `${index ? 'L' : 'M'} ${x.toFixed(1)} ${y.toFixed(1)}`
  }).join(' ')
}
</script>

<template>
  <div class="result-card">
    <div v-if="chart === 'metric_card'" class="metric-result"><strong>{{ result.answer || '—' }}</strong><small>查询结果</small></div>
    <div v-else-if="chart === 'line'" class="visual-result"><div class="visual-title">按时间趋势</div><svg viewBox="0 0 640 230" class="result-chart" role="img" aria-label="折线图"><line x1="46" y1="12" x2="46" y2="192" stroke="#dfe9e5"/><line x1="46" y1="192" x2="606" y2="192" stroke="#dfe9e5"/><path v-for="(name, index) in series" :key="name" :d="linePath(name)" fill="none" :stroke="palette[index % palette.length]" stroke-width="3" stroke-linecap="round"/><text v-for="(group, index) in groups" :key="group" :x="46 + (groups.length === 1 ? 280 : index * 560 / (groups.length - 1))" y="215" text-anchor="middle" fill="#87938d" font-size="11">{{ group }}</text></svg><div class="chart-legend result-legend"><span v-for="(name, index) in series" :key="name"><i :style="{background: palette[index % palette.length]}"></i>{{ name }}</span></div></div>
    <div v-else-if="chart === 'bar'" class="visual-result"><div class="visual-title">分类比较</div><div class="bar-chart"><div v-for="(row, index) in rows.slice(0, 20)" :key="index" class="bar-row"><span>{{ String(row.group_key ?? row.category ?? row.series_key ?? '') }}</span><div class="bar-track"><i :style="{width: `${Math.max(2, Number(row.value_cents ?? row.value ?? 0) / maxValue * 100)}%`}"></i></div><b>{{ formatValue('value_cents', row.value_cents ?? row.value) }}</b></div></div></div>
    <div v-else class="table-result"><div class="visual-title">明细结果</div><div class="result-table-wrap"><table><thead><tr><th v-for="key in columns" :key="key">{{ label(key) }}</th></tr></thead><tbody><tr v-for="(row, index) in rows.slice(0, 50)" :key="index"><td v-for="key in columns" :key="key">{{ cell(row, key) }}</td></tr></tbody></table></div></div>
  </div>
</template>
