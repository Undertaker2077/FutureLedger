import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { PlanningSimulation, PlanningScenario } from '../types/planning'

export type ChatResult = {
  status: string
  route?: string
  answer?: string
  message?: string
  chart?: string
  value_format?: 'money' | 'count'
  rows?: Record<string, unknown>[]
  query_id?: string
  action_id?: string
  categories?: string[]
  group_label?: string
  series_label?: string
  result?: PlanningSimulation
  scenarios?: PlanningScenario[]
  assumptions?: string[]
}
export type ChatMessage = ChatResult & { role: 'user' | 'assistant'; text: string }
export type AccountSnapshot = { account_id: string; account_name: string; balance_cents: number }
type ApiError = Error & { status?: number; code?: string }
const credentialText = /(?:\bsk-[a-z0-9_-]{12,}|\b(?:api[ _-]?key|bearer)\s*[:：=]\s*[^\s,，]+|(?:密码|验证码|password|passwd|otp)\s*(?:[:：=]|是|为|\bis\b)\s*[^\s,，。]+|(?:密码|password|passwd)\s+(?!help\b|reset\b|verify\b|length\b|policy\b)[a-z0-9!@#$%^&*_.-]{4,}|(?:验证码|\botp)\s*\d{4,8}(?!\d)|\bbearer\s+[a-z0-9_.-]{12,})/i

function errorFromResponse(status: number, body: unknown): ApiError {
  const detail = typeof body === 'object' && body !== null && 'detail' in body ? (body as { detail?: unknown }).detail : body
  const payload = typeof detail === 'object' && detail !== null ? detail as Record<string, unknown> : {}
  const error = new Error(String(payload.message || detail || `请求失败（${status}）`)) as ApiError
  error.status = status
  error.code = typeof payload.code === 'string' ? payload.code : undefined
  return error
}

export const useWorkspace = defineStore('workspace', () => {
  let generation = 0
  const username = ref('')
  const authToken = ref('')
  const sessionId = ref('')
  const messages = ref<ChatMessage[]>([])
  const loading = ref(false)
  const error = ref('')
  const authLoading = ref(false)
  const pendingAction = ref<ChatResult | null>(null)
  const accounts = ref<AccountSnapshot[]>([])
  const accountError = ref('')
  const totalBalanceCents = computed(() => accounts.value.reduce((total, account) => total + account.balance_cents, 0))
  const authenticated = computed(() => Boolean(authToken.value && username.value && sessionId.value))

  function clearLocalSession() {
    generation += 1
    username.value = ''; authToken.value = ''; sessionId.value = ''; messages.value = []; pendingAction.value = null
    accounts.value = []; accountError.value = ''; loading.value = false; authLoading.value = false; error.value = ''
  }

  async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
    const requestedGeneration = generation
    const headers = new Headers(init.headers)
    if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
    const response = await fetch(path, { ...init, headers })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) {
      const failure = errorFromResponse(response.status, body)
      if (requestedGeneration === generation && (failure.code === 'UNAUTHENTICATED' || failure.code === 'FORBIDDEN')) clearLocalSession()
      throw failure
    }
    return body as T
  }

  async function register(user: string, password: string) {
    await api('/api/auth/register', { method: 'POST', body: JSON.stringify({ username: user, password }) })
  }
  async function createSession() {
    const requestedGeneration = generation
    const response = await api<{ session_id: string }>('/api/sessions', { method: 'POST', body: JSON.stringify({ auth_token: authToken.value, dataset_id: 'personal_ledger' }) })
    if (requestedGeneration === generation) sessionId.value = response.session_id
  }
  async function login(user: string, password: string) {
    clearLocalSession()
    const requestedGeneration = generation
    authLoading.value = true; error.value = ''
    try {
      const response = await api<{ auth_token: string; username: string }>('/api/auth/login', { method: 'POST', body: JSON.stringify({ username: user, password }) })
      if (requestedGeneration !== generation) return
      username.value = response.username; authToken.value = response.auth_token
      await createSession()
      if (requestedGeneration !== generation) return
      await refreshAccounts().catch(() => undefined)
    } finally { if (requestedGeneration === generation) authLoading.value = false }
  }
  async function logout() {
    const token = authToken.value
    clearLocalSession()
    if (token) await api('/api/auth/logout', { method: 'POST', body: JSON.stringify({ auth_token: token }) }).catch(() => undefined)
  }
  async function refreshAccounts() {
    const requestedGeneration = generation
    accountError.value = ''; accounts.value = []
    try {
      const result = await api<{ accounts: AccountSnapshot[] }>(`/api/accounts?session_id=${encodeURIComponent(sessionId.value)}`)
      if (requestedGeneration === generation) accounts.value = result.accounts
    } catch (caught) {
      if (requestedGeneration === generation) accountError.value = caught instanceof Error ? caught.message : '账户余额刷新失败'
      throw caught
    }
  }
  async function send(text: string) {
    if (!authenticated.value) throw new Error('请先登录')
    if (credentialText.test(text)) {
      const blocked: ChatResult = { status: 'blocked', message: '请移除密码、验证码或 API key；验证只在独立密码框进行。' }
      messages.value.push({ ...blocked, role: 'assistant', text: blocked.message! })
      return blocked
    }
    if (loading.value) throw new Error('请等待当前查询完成')
    const requestedGeneration = generation
    loading.value = true; error.value = ''
    messages.value.push({ role: 'user', text, status: 'sent' })
    try {
      const response = await api<ChatResult>('/api/ask', { method: 'POST', body: JSON.stringify({ session_id: sessionId.value, question: text }) })
      if (requestedGeneration !== generation) return response
      messages.value.push({ ...response, role: 'assistant', text: response.answer || response.message || '请求已处理。' })
      pendingAction.value = response.status === 'confirmation_required' ? response : null
      return response
    } catch (caught) {
      const failure = caught as ApiError
      if (requestedGeneration === generation) {
        error.value = failure.message
        messages.value.push({ role: 'assistant', status: 'error', text: `请求失败：${failure.message}` })
      }
      throw failure
    } finally { if (requestedGeneration === generation) loading.value = false }
  }
  async function authorizeAction(actionId: string, password: string) {
    return api<{ authorization_id: string; categories: string[] }>(`/api/actions/${actionId}/authorize`, { method: 'POST', body: JSON.stringify({ session_id: sessionId.value, password }) })
  }
  async function confirmAction(actionId: string, authorizationId: string, category: string) {
    const requestedGeneration = generation
    const response = await api<ChatResult>(`/api/actions/${actionId}/confirm`, { method: 'POST', body: JSON.stringify({ session_id: sessionId.value, authorization_id: authorizationId, category }) })
    if (requestedGeneration !== generation) return response
    for (const message of messages.value) if (message.action_id === actionId) message.status = response.status
    messages.value.push({ ...response, role: 'assistant', text: response.message || '转账处理完成。' }); pendingAction.value = null
    await refreshAccounts().catch(() => undefined)
    return response
  }
  async function simulate(planId: string, body: Record<string, number>) {
    return api<{ result: Record<string, unknown>; status: string }>(`/api/plans/${planId}/simulate`, { method: 'POST', body: JSON.stringify({ session_id: sessionId.value, plan_version: 1, ...body }) })
  }
  return { username, sessionId, messages, loading, error, authLoading, pendingAction, authenticated, accounts, accountError, totalBalanceCents, refreshAccounts, register, login, logout, send, authorizeAction, confirmAction, simulate }
})
