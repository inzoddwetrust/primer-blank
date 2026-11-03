import { createApp } from 'vue'
import './theme.css'
import App from './App.vue'
import { loadConfig } from './config'
import { BUILT_IN, chooseLanguage, loadTexts, type Texts } from './texts'

async function start(): Promise<void> {
  const language = chooseLanguage(navigator.languages ?? [navigator.language])
  document.documentElement.lang = language
  let texts = BUILT_IN[language] as Texts
  try {
    texts = await loadTexts(language)
    document.title = texts.title
    const config = await loadConfig()
    createApp(App, { config, texts, error: null }).mount('#app')
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error)
    createApp(App, { config: null, texts, error: message }).mount('#app')
  }
}

void start()
