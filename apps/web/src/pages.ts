import { defineComponent, h } from 'vue'
import HomeView from './views/HomeView.vue'
import AssistantView from './views/AssistantView.vue'
import FutureView from './views/FutureView.vue'
import ReviewView from './views/ReviewView.vue'

const page = (title: string, description: string, action = '前往智能体小智') => defineComponent({
  setup: () => () => h('section', { class: 'card page-card' }, [
    h('span', { class: 'eyebrow' }, 'FUTURELEDGER WORKSPACE'), h('h1', title), h('p', description),
    h('div', { class: 'notice' }, '当前数据范围为合成账本。需要具体统计或明细时，请使用智能体小智；系统会根据当前登录用户和授权范围查询。'),
    h('a', { class: 'primary-button page-action', href: '/assistant' }, action),
  ]),
})

export const pages = [
  { path: '/', name: 'home', component: HomeView, meta: { title: '总览' } },
  { path: '/bills', name: 'bills', component: page('账单分析', '按月份、类别、商户和账户查看收入、支出、退款和交易明细。'), meta: { title: '账单' } },
  { path: '/subscriptions', name: 'subscriptions', component: page('代扣管理', '查看授权状态、保护项与可取消范围。取消操作必须经过后端确认。', '查看代扣相关说明'), meta: { title: '代扣' } },
  { path: '/future', name: 'future', component: FutureView, meta: { title: '未来账本' } },
  { path: '/tasks', name: 'tasks', component: page('任务中心', '跟踪待补充、待确认、待验证及待查证操作。当前演示的转账确认会在智能体中显示。', '查看待确认操作'), meta: { title: '任务' } },
  { path: '/settings', name: 'settings', component: page('偏好设置', '管理最低余额、保护偏好、通知和记忆。偏好不等于支付授权。', '回到智能体'), meta: { title: '偏好' } },
  { path: '/review', name: 'review', component: ReviewView, meta: { title: '评审' } },
  { path: '/assistant', name: 'assistant', component: AssistantView, meta: { title: '智能体小智' } },
]
