import { createApp } from 'vue'
import App from './App.vue'
import { loadConfig } from './config'

loadConfig()
  .then((config) => createApp(App, { config, error: null }).mount('#app'))
  .catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error)
    createApp(App, { config: null, error: message }).mount('#app')
  })
