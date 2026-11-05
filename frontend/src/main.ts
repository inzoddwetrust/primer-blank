import { createApp } from 'vue'
import './theme.css'
import App from './App.vue'
import { loadConfig } from './config'
import { BUILT_IN, FALLBACK_LANGUAGE, chooseLanguage, loadTexts, type Texts } from './texts'

// The instance's languages are known once /config.json is read: until then --
// and when it cannot be read -- the page speaks the first of the browser's
// languages the product has, else FALLBACK_LANGUAGE.
async function start(): Promise<void> {
  const preferred = navigator.languages ?? [navigator.language]
  let language = chooseLanguage(preferred, Object.keys(BUILT_IN), FALLBACK_LANGUAGE)
  let texts = BUILT_IN[language] as Texts
  try {
    const config = await loadConfig()
    language = chooseLanguage(preferred, config.languages, config.defaultLanguage)
    texts = BUILT_IN[language] as Texts
    document.documentElement.lang = language
    texts = await loadTexts(language)
    document.title = texts.title
    createApp(App, { config, texts, error: null }).mount('#app')
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error)
    document.documentElement.lang = language
    createApp(App, { config: null, texts, error: message }).mount('#app')
  }
}

void start()
