// Runtime configuration of the page, read from /config.json at start.
//
// The container renders /config.json from its environment when it starts
// (nginx/default.conf.template), so one image serves every instance. There
// is no default: a missing, unreadable or malformed file is an error the
// page shows, and no request goes to an address nobody configured.

export interface RuntimeConfig {
  // Exact https origin of the API, e.g. https://api.example.com
  apiOrigin: string
}

export class ConfigError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ConfigError'
  }
}

export const CONFIG_PATH = '/config.json'

export function parseConfig(raw: unknown): RuntimeConfig {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw new ConfigError(`${CONFIG_PATH} is not a JSON object`)
  }
  const value = (raw as Record<string, unknown>).apiBaseUrl
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
  return { apiOrigin: url.origin }
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
