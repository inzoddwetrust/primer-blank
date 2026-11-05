import { describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  BUILT_IN,
  FALLBACK_LANGUAGE,
  TEXTS_PATH,
  TextsError,
  chooseLanguage,
  loadTexts,
  parseTexts,
} from './texts'

function answer(status: number, body: string): typeof fetch {
  return vi.fn(async () => new Response(body, { status })) as unknown as typeof fetch
}

describe('the built-in texts', () => {
  it('are en and ru, each with every key', () => {
    expect(Object.keys(BUILT_IN).sort()).toEqual(['en', 'ru'])
    expect(Object.keys(BUILT_IN.ru ?? {}).sort()).toEqual(Object.keys(BUILT_IN.en ?? {}).sort())
    expect(BUILT_IN.ru?.config_error).not.toBe(BUILT_IN.en?.config_error)
    expect(FALLBACK_LANGUAGE).toBe('en')
  })
})

describe('the languages of the product', () => {
  // primer.yaml declares what the built-in texts are: the machine checks an
  // instance's languages against the file, the page against its texts
  it('are its built-in texts, as primer.yaml declares them', () => {
    // vitest runs in frontend/, the package's root (vitest.config.ts)
    const file = join(process.cwd(), '..', 'primer.yaml')
    const line = readFileSync(file, 'utf-8')
      .split('\n')
      .find((text) => text.startsWith('languages:'))
    const declared = (line ?? '').replace(/#.*$/, '').match(/\[(.*)\]/)?.[1] ?? ''
    expect(declared.split(',').map((code) => code.trim())).toEqual(Object.keys(BUILT_IN))
  })
})

describe('chooseLanguage', () => {
  // the person's language: the first of the browser's the instance turns on,
  // by its primary subtag; none -- the instance's default
  it.each([
    [['ru-RU', 'en'], ['en', 'ru'], 'en', 'ru'],
    [['de', 'RU'], ['en', 'ru'], 'en', 'ru'],
    [['en-GB', 'ru'], ['en', 'ru'], 'ru', 'en'],
    [['de', 'fr'], ['en', 'ru'], 'ru', 'ru'],
    [[], ['en', 'ru'], 'ru', 'ru'],
    // a language of the product the instance does not turn on is not taken
    [['ru-RU', 'en'], ['en'], 'en', 'en'],
    [['ru'], ['en'], 'en', 'en'],
    // the first turned on wins, in the browser's order, not the instance's
    [['en', 'ru'], ['ru', 'en'], 'ru', 'en'],
  ])('%j of %j, default %s -> %s', (preferred, enabled, fallback, language) => {
    expect(chooseLanguage(preferred, enabled, fallback)).toBe(language)
  })
})

describe('parseTexts', () => {
  it('keeps the built-in texts when the package gives none ({})', () => {
    expect(parseTexts({}, 'ru')).toEqual(BUILT_IN.ru)
  })

  it("takes the package's texts of the language over its built-in ones", () => {
    expect(parseTexts({ ru: { title: 'Праймер', unknown: 'x' } }, 'ru')).toEqual({
      ...BUILT_IN.ru,
      title: 'Праймер',
    })
  })

  it('takes a text only the en part gives as built-in in ru, not as en', () => {
    const raw = { en: { title: 'Primer Blank', api_label: 'Server:' }, ru: { title: 'Праймер' } }
    expect(parseTexts(raw, 'en').api_label).toBe('Server:')
    expect(parseTexts(raw, 'ru')).toEqual({ ...BUILT_IN.ru, title: 'Праймер' })
  })

  it('takes the built-in texts of a language the package does not have', () => {
    expect(parseTexts({ en: { title: 'Primer Blank' } }, 'ru')).toEqual(BUILT_IN.ru)
  })

  it.each([
    ['not an object', null],
    ['an array', []],
    ['a language not an object', { ru: 'x' }],
    ['a text not a string', { ru: { api_label: 1 } }],
  ])('refuses %s', (_name, raw) => {
    expect(() => parseTexts(raw, 'ru')).toThrow(TextsError)
  })

  it('refuses a language the page does not have', () => {
    expect(() => parseTexts({}, 'de')).toThrow('de is not a language of the page')
  })
})

describe('loadTexts', () => {
  it(`reads ${TEXTS_PATH} without the cache`, async () => {
    const fetchFn = answer(200, '{"en":{"api_label":"Server:"}}')
    expect((await loadTexts('en', fetchFn)).api_label).toBe('Server:')
    expect(fetchFn).toHaveBeenCalledWith(TEXTS_PATH, { cache: 'no-store' })
  })

  it('refuses an answer that is not 200 or not JSON', async () => {
    await expect(loadTexts('en', answer(500, 'invalid'))).rejects.toThrow('answered 500')
    await expect(loadTexts('en', answer(200, '<html>'))).rejects.toThrow('is not JSON')
  })
})
