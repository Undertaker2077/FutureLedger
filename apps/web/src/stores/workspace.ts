import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

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
}
export type ChatMessage = ChatResult & { role: 'user' | 'assistant'; text: string }
type ApiError = Error & { status?: number; code?: string }

function errorFromResponse(status: number, body: unknown): ApiError {
  const detail = typeof body === 'object' && body !== null && 'detail' in body ? (body as { detail?: unknown }).detail : body
  const payload = typeof detail === 'object' && detail !== null ? detail as Record<string, unknown> : {}
  const error = new Error(String(payload.message || detail || `请求失败（${status}）`)) as ApiError
  error.status = status
  error.code = typeof payload.code === 'string' ? payload.code : undefined
  return error
}

export const useWorkspace = defineStore('workspace', () => {
  const username = ref('')
  const authToken = ref('')
  const sessionId = ref('')
  const messages = ref<ChatMessage[]>([])
  const loading = ref(false)
  const error = ref('')
  const authLoading = ref(false)
  const pendingAction = ref<ChatResult | null>(null)
  const authenticated = computed(() => Boolean(authToken.value && username.value && sessionId.value))

  async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers)
    if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
    const response = await fetch(path, { ...init, headers })
    const body = await response.json().catch(() => ({}))
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) { authToken.value = ''; sessionId.value = '' }
      throw errorFromResponse(response.status, body)
    }
    return body as T
  }

  async function register(user: string, password: string) {
    await api('/api/auth/register', { method: 'POST', body: JSON.stringify({ username: user, password }) })
  }
  async function createSession() {
    const response = await api<{ session_id: string }>('/api/sessions', { method: 'POST', body: JSON.stringify({ auth_token: authToken.value, dataset_id: 'personal_ledger' }) })
    sessionId.value = response.session_id
  }
  async function login(user: string, password: string) {
    authLoading.value = true; error.value = ''
    try {
      const response = await api<{ auth_token: string; username: string }>('/api/auth/login', { method: 'POST', body: JSON.stringify({ username: user, password }) })
      username.value = response.username; authToken.value = response.auth_token
      await createSession()
    } finally { authLoading.value = false }
  }
  async function logout() {
    if (authToken.value) await api('/api/auth/logout', { method: 'POST', body: JSON.stringify({ auth_token: authToken.value }) }).catch(() => undefined)
    username.value = ''; authToken.value = ''; sessionId.value = ''; messages.value = []; pendingAction.value = null
  }
  async function send(text: string) {
    if (!authenticated.value) throw new Error('请先登录')
    loading.value = true; error.value = ''
    messages.value.push({ role: 'user', text, status: 'sent' })
    try {
      const response = await api<ChatResult>('/api/ask', { method: 'POST', body: JSON.stringify({ session_id: sessionId.value, question: text }) })
      messages.value.push({ ...response, role: 'assistant', text: response.answer || response.message || '请求已处理。' })
      pendingAction.value = response.status === 'confirmation_required' ? response : null
      return response
    } catch (caught) {
      const failure = caught as ApiError; error.value = failure.message
      messages.value.push({ role: 'assistant', status: 'error', text: `请求失败：${failure.message}` }); throw failure
    } finally { loading.value = false }
  }
  async function authorizeAction(actionId: string, password: string) {
    return api<{ authorization_id: string; categories: string[] }>(`/api/actions/${actionId}/authorize`, { method: 'POST', body: JSON.stringify({ session_id: sessionId.value, password }) })
  }
  async function confirmAction(actionId: string, authorizationId: string, category: string) {
    const response = await api<ChatResult>(`/api/actions/${actionId}/confirm`, { method: 'POST', body: JSON.stringify({ session_id: sessionId.value, authorization_id: authorizationId, category }) })
    messages.value.push({ ...response, role: 'assistant', text: response.message || '转账处理完成。' }); pendingAction.value = null; return response
  }
  async function simulate(planId: string, body: Record<string, number>) {
    return api<{ result: Record<string, unknown>; status: string }>(`/api/plans/${planId}/simulate`, { method: 'POST', body: JSON.stringify({ session_id: sessionId.value, plan_version: 1, ...body }) })
  }
  return { username, sessionId, messages, loading, error, authLoading, pendingAction, authenticated, register, login, logout, send, authorizeAction, confirmAction, simulate }
})
