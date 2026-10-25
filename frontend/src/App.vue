<script setup lang="ts">
import type { RuntimeConfig } from './config'

defineProps<{
  config: RuntimeConfig | null
  error: string | null
}>()
</script>

<template>
  <main>
    <h1>primer-blank</h1>
    <p v-if="error" role="alert" data-test="config-error">
      Configuration is not available: {{ error }}
    </p>
    <p v-else-if="config" data-test="api-origin">API: {{ config.apiOrigin }}</p>
  </main>
</template>
