import HomeView from './views/HomeView.vue'
import AssistantView from './views/AssistantView.vue'
import ReviewView from './views/ReviewView.vue'
import BillsView from './views/BillsView.vue'
import SubscriptionsView from './views/SubscriptionsView.vue'
import FutureView from './views/FutureView.vue'
import TasksView from './views/TasksView.vue'
import SettingsView from './views/SettingsView.vue'

export const pages = [
 {path:'/',name:'home',component:HomeView,meta:{title:'总览'}},
 {path:'/bills',name:'bills',component:BillsView,meta:{title:'账单'}},
 {path:'/subscriptions',name:'subscriptions',component:SubscriptionsView,meta:{title:'代扣'}},
 {path:'/future',name:'future',component:FutureView,meta:{title:'未来账本'}},
 {path:'/tasks',name:'tasks',component:TasksView,meta:{title:'任务'}},
 {path:'/settings',name:'settings',component:SettingsView,meta:{title:'偏好'}},
 {path:'/review',name:'review',component:ReviewView,meta:{title:'评审'}},
 {path:'/assistant',name:'assistant',component:AssistantView,meta:{title:'AI 助手'}},
]
