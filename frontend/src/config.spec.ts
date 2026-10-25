import { describe, expect, it, vi } from 'vitest'
import { CONFIG_PATH, ConfigError, loadConfig, parseConfig } from './config'

function answer(status: number, body: string): typeof fetch {
  return vi.fn(async () => new Response(body, { status })) as unknown as typeof fetch
}

describe('parseConfig', () => {
  it('takes an https origin', () => {
    expect(parseConfig({ apiBaseUrl: 'https://api.example.com' })).toEqual({
      apiOrigin: 'https://api.example.com',
    })
  })

  it.each([
    ['not an object', null],
    ['an array', []],
    ['no apiBaseUrl', {}],
    ['an empty apiBaseUrl', { apiBaseUrl: '' }],
    ['a scheme with no host', { apiBaseUrl: 'https://' }],
    ['a host with no scheme', { apiBaseUrl: 'api.example.com' }],
    ['http', { apiBaseUrl: 'http://api.example.com' }],
    ['a path', { apiBaseUrl: 'https://api.example.com/v1' }],
    ['a trailing slash', { apiBaseUrl: 'https://api.example.com/' }],
    ['a query', { apiBaseUrl: 'https://api.example.com?x=1' }],
    ['credentials', { apiBaseUrl: 'https://u:p@api.example.com' }],
    ['an unrendered placeholder', { apiBaseUrl: 'https://${API_BASE_URL}' }],
  ])('refuses %s', (_name, raw) => {
    expect(() => parseConfig(raw)).toThrow(ConfigError)
  })
})

describe('loadConfig', () => {
  it('reads the file at start, uncached', async () => {
    const fetchFn = answer(200, '{"apiBaseUrl":"https://api.example.com"}')
    await expect(loadConfig(fetchFn)).resolves.toEqual({ apiOrigin: 'https://api.example.com' })
    expect(fetchFn).toHaveBeenCalledWith(CONFIG_PATH, { cache: 'no-store' })
  })

  it('refuses a missing file', async () => {
    await expect(loadConfig(answer(404, 'not found'))).rejects.toThrow('answered 404')
  })

  it('refuses a body that is not JSON', async () => {
    await expect(loadConfig(answer(200, '<html>'))).rejects.toThrow('is not JSON')
  })
})
