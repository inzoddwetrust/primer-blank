<script setup lang="ts">
import type { RuntimeConfig } from './config'
import { BUILT_IN, FALLBACK_LANGUAGE, type Texts } from './texts'

withDefaults(
  defineProps<{
    config: RuntimeConfig | null
    error: string | null
    texts?: Texts
  }>(),
  { texts: () => BUILT_IN[FALLBACK_LANGUAGE] as Texts },
)
</script>

<template>
  <main>
    <header>
      <span class="logo" role="img" :aria-label="texts.title" data-test="logo"></span>
      <h1 data-test="title">{{ texts.title }}</h1>
    </header>
    <p v-if="error" role="alert" data-test="config-error">{{ texts.config_error }} {{ error }}</p>
    <p v-else-if="config" data-test="api-origin">{{ texts.api_label }} {{ config.apiOrigin }}</p>
  </main>
</template>

<style scoped>
/* Colors, fonts and the logo come only from the theme's custom properties
   (src/theme.css, overridden by the skin package): no literal here. */
header {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.logo {
  width: 4rem;
  height: 4rem;
  background-image: var(--asset-logo);
  background-repeat: no-repeat;
  background-size: contain;
}

h1 {
  color: var(--color-brand-primary);
  font-size: var(--font-size-heading);
  font-weight: var(--font-weight-heading);
}
</style>
