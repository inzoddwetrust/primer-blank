// Runtime configuration of the page, read from /config.json at start.
//
// The container renders /config.json from its environment when it starts
// (nginx/default.conf.template), so one image serves every instance. There
// is no default: a missing, unreadable or malformed file is an error the
// page shows, and no request goes to an address nobody configured.
//
// The instance's languages (protocol 5.2.2) come the same way: LANGUAGES --
// the codes the instance turns on, by commas in the passport's order -- and
// DEFAULT_LANGUAGE, one of them. Each is a language of the product (its
// built-in texts, ./texts); anything else is an error, never a quiet subset.

import { BUILT_IN } from './texts'

export interface RuntimeConfig {
  // Exact https origin of the API, e.g. https://api.example.com
  apiOrigin: string
  // The languages the instance turns on, in the passport's order
  languages: string[]
  // The instance's default language, one of languages
  defaultLanguage: string
}

export class ConfigError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ConfigError'
  }
}

export const CONFIG_PATH = '/config.json'

const LANGUAGE_CODE = /^[a-z]{2,3}$/

function parseOrigin(value: unknown): string {
  if (typeof value !== 'string' || value === '') {
    throw new ConfigError(`${CONFIG_PATH} has no apiBaseUrl`)
  }
  let url: URL
  try {
    url = new URL(value)
  } catch {
    throw new ConfigError(`apiBaseUrl is not a URL: ${value}`)
  }
  if (url.protocol !== 'https:' || value !== url.origin) {
    throw new ConfigError(`apiBaseUrl is not an https origin: ${value}`)
  }
  return url.origin
}

function parseLanguages(value: unknown): string[] {
  if (typeof value !== 'string' || value === '') {
    throw new ConfigError(`${CONFIG_PATH} has no languages`)
  }
  const codes = value.split(',')
  for (const code of codes) {
    if (!LANGUAGE_CODE.test(code)) {
      throw new ConfigError(`languages has a code that is not a language: ${value}`)
    }
    if (!Object.hasOwn(BUILT_IN, code)) {
      throw new ConfigError(`${code} is not a language of the page`)
    }
  }
  if (new Set(codes).size !== codes.length) {
    throw new ConfigError(`languages names a language twice: ${value}`)
  }
  return codes
}

export function parseConfig(raw: unknown): RuntimeConfig {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw new ConfigError(`${CONFIG_PATH} is not a JSON object`)
  }
  const given = raw as Record<string, unknown>
  const apiOrigin = parseOrigin(given.apiBaseUrl)
  const languages = parseLanguages(given.languages)
  const defaultLanguage = given.defaultLanguage
  if (typeof defaultLanguage !== 'string' || !languages.includes(defaultLanguage)) {
    throw new ConfigError(`defaultLanguage is not one of ${languages.join(',')}`)
  }
  return { apiOrigin, languages, defaultLanguage }
}

export async function loadConfig(fetchFn: typeof fetch = fetch): Promise<RuntimeConfig> {
  const response = await fetchFn(CONFIG_PATH, { cache: 'no-store' })
  if (!response.ok) {
    throw new ConfigError(`${CONFIG_PATH} answered ${response.status}`)
  }
  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new ConfigError(`${CONFIG_PATH} is not JSON`)
  }
  return parseConfig(body)
}
