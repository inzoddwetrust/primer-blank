import { describe, expect, it, vi } from 'vitest'
import { CONFIG_PATH, ConfigError, loadConfig, parseConfig } from './config'

function answer(status: number, body: string): typeof fetch {
  return vi.fn(async () => new Response(body, { status })) as unknown as typeof fetch
}

// The languages of an instance, as the container renders them from LANGUAGES
// and DEFAULT_LANGUAGE (protocol 5.2.2)
const LANGS = { languages: 'ru,en', defaultLanguage: 'ru' }

describe('parseConfig', () => {
  it('takes an https origin and the languages in their order', () => {
    expect(parseConfig({ apiBaseUrl: 'https://api.example.com', ...LANGS })).toEqual({
      apiOrigin: 'https://api.example.com',
      languages: ['ru', 'en'],
      defaultLanguage: 'ru',
    })
  })

  it('takes one language', () => {
    const raw = { apiBaseUrl: 'https://api.example.com', languages: 'en', defaultLanguage: 'en' }
    expect(parseConfig(raw).languages).toEqual(['en'])
  })

  it.each([
    ['not an object', null],
    ['an array', []],
    ['no apiBaseUrl', { ...LANGS }],
    ['an empty apiBaseUrl', { apiBaseUrl: '', ...LANGS }],
    ['a scheme with no host', { apiBaseUrl: 'https://', ...LANGS }],
    ['a host with no scheme', { apiBaseUrl: 'api.example.com', ...LANGS }],
    ['http', { apiBaseUrl: 'http://api.example.com', ...LANGS }],
    ['a path', { apiBaseUrl: 'https://api.example.com/v1', ...LANGS }],
    ['a trailing slash', { apiBaseUrl: 'https://api.example.com/', ...LANGS }],
    ['a query', { apiBaseUrl: 'https://api.example.com?x=1', ...LANGS }],
    ['credentials', { apiBaseUrl: 'https://u:p@api.example.com', ...LANGS }],
    ['an unrendered placeholder', { apiBaseUrl: 'https://${API_BASE_URL}', ...LANGS }],
  ])('refuses %s', (_name, raw) => {
    expect(() => parseConfig(raw)).toThrow(ConfigError)
  })

  it.each([
    ['no languages', { defaultLanguage: 'en' }, 'has no languages'],
    ['empty languages', { languages: '', defaultLanguage: 'en' }, 'has no languages'],
    ['an array', { languages: ['en'], defaultLanguage: 'en' }, 'has no languages'],
    ['a region', { languages: 'en-GB', defaultLanguage: 'en' }, 'has a code that'],
    ['a space', { languages: 'en, ru', defaultLanguage: 'en' }, 'has a code that'],
    ['upper case', { languages: 'EN', defaultLanguage: 'en' }, 'has a code that'],
    ['a language the page has not', { languages: 'en,uk', defaultLanguage: 'en' }, 'uk is not'],
    ['a language twice', { languages: 'en,ru,en', defaultLanguage: 'en' }, 'twice'],
    ['no default', { languages: 'en' }, 'defaultLanguage'],
    ['a default off the list', { languages: 'en', defaultLanguage: 'ru' }, 'defaultLanguage'],
    ['an unrendered placeholder', { languages: '${LANGUAGES}', defaultLanguage: 'en' }, 'not a'],
  ])('refuses the languages: %s', (_name, given, message) => {
    expect(() => parseConfig({ apiBaseUrl: 'https://api.example.com', ...given })).toThrow(message)
  })
})

describe('loadConfig', () => {
  it('reads the file at start, uncached', async () => {
    const body = '{"apiBaseUrl":"https://api.example.com","languages":"en","defaultLanguage":"en"}'
    const fetchFn = answer(200, body)
    await expect(loadConfig(fetchFn)).resolves.toEqual({
      apiOrigin: 'https://api.example.com',
      languages: ['en'],
      defaultLanguage: 'en',
    })
    expect(fetchFn).toHaveBeenCalledWith(CONFIG_PATH, { cache: 'no-store' })
  })

  it('refuses a missing file', async () => {
    await expect(loadConfig(answer(404, 'not found'))).rejects.toThrow('answered 404')
  })

  it('refuses a body that is not JSON', async () => {
    await expect(loadConfig(answer(200, '<html>'))).rejects.toThrow('is not JSON')
  })
})
