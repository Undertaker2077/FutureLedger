<script setup lang="ts">
import { useWorkspace } from '../stores/workspace'
import { useTransferAction } from '../composables/transfer'
const props = defineProps<{ actionId: string }>()
const { password, category, categories, authorizationId, error, busy, completed, authorize, confirm } = useTransferAction(useWorkspace(), props.actionId)
</script>
<template>
  <div v-if="!completed" class="transfer-card">
    <b>需要确认转账</b>
    <label v-if="!authorizationId">登录密码<input v-model="password" type="password" minlength="12" autocomplete="current-password" :disabled="busy"></label>
    <label>用途类别<select v-model="category" :disabled="busy"><option v-for="item in categories" :key="item">{{ item }}</option></select></label>
    <button v-if="!authorizationId" class="primary-button" :disabled="!password || busy" @click="authorize">验证密码</button>
    <button v-else class="primary-button" :disabled="busy" @click="confirm">确认并完成转账</button>
    <small v-if="error" class="auth-error">{{ error }}</small>
  </div>
</template>
