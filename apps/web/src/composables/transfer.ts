import { ref } from 'vue'

type ActionApi = {
  authorizeAction: (actionId: string, password: string) => Promise<{ authorization_id: string; categories: string[] }>
  confirmAction: (actionId: string, authorizationId: string, category: string) => Promise<unknown>
}

export function useTransferAction(api: ActionApi, actionId: string) {
  const password = ref('')
  const category = ref('购物')
  const categories = ref(['餐饮', '交通', '购物', '娱乐', '订阅', '房租', '医疗', '其他'])
  const authorizationId = ref('')
  const error = ref('')
  const busy = ref(false)
  const completed = ref(false)
  async function authorize() {
    if (busy.value || !password.value || completed.value) return
    busy.value = true; error.value = ''
    try {
      const response = await api.authorizeAction(actionId, password.value)
      authorizationId.value = response.authorization_id
      categories.value = response.categories
      if (!response.categories.includes(category.value)) category.value = response.categories[0]
    } catch (caught) { error.value = caught instanceof Error ? caught.message : '密码验证失败。' }
    finally { password.value = ''; busy.value = false }
  }
  async function confirm() {
    if (busy.value || !authorizationId.value || completed.value) return
    busy.value = true; error.value = ''
    try {
      await api.confirmAction(actionId, authorizationId.value, category.value)
      completed.value = true; authorizationId.value = ''
    } catch (caught) {
      const failure = caught as Error & { code?: string }
      if (failure.code === 'AUTHORIZATION_EXPIRED') authorizationId.value = ''
      error.value = failure.message || '确认失败。'
    } finally { busy.value = false }
  }
  return { password, category, categories, authorizationId, error, busy, completed, authorize, confirm }
}
