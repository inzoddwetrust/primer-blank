// The texts of the page, by language: built in, or the texts package of the
// instance over them (protocol 5.2.2).
//
// The product's languages are its built-in texts, src/texts/<language>.json --
// the same files the image gives nginx/package.js, which refuses a package of
// any other language. The container serves /texts.json from the package the
// machine mounts at /srv/texts, checked there: {<language>: {<key>: text}};
// with no package it serves {}. A text the package does not give in a
// language is the built-in text of that language, never another language's.
//
// The person's language is the first of the browser's languages the instance
// turns on, by its primary subtag; none -- the instance's default. Which
// languages are on and the default come from /config.json (./config, the
// passport through the env, protocol 5.2.2). FALLBACK_LANGUAGE is the page's
// language before that is known -- when /config.json cannot be read.
//
// A texts package that cannot be read or is refused does not stop the page:
// it keeps the built-in texts of its language (textsOrBuiltIn) and says why on
// the console.

import en from './texts/en.json'
import ru from './texts/ru.json'

export interface Texts {
  title: string
  config_error: string
  api_label: string
}

export const BUILT_IN: Readonly<Record<string, Texts>> = { en, ru }

export const FALLBACK_LANGUAGE = 'en'

export class TextsError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'TextsError'
  }
}

export const TEXTS_PATH = '/texts.json'

export function chooseLanguage(
  preferred: readonly string[],
  enabled: readonly string[],
  fallback: string,
): string {
  for (const tag of preferred) {
    const primary = tag.toLowerCase().split('-')[0] ?? ''
    if (enabled.includes(primary)) {
      return primary
    }
  }
  return fallback
}

function builtIn(language: string): Texts {
  const texts = BUILT_IN[language]
  if (texts === undefined) {
    throw new TextsError(`${language} is not a language of the page`)
  }
  return texts
}

export function parseTexts(raw: unknown, language: string): Texts {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw new TextsError(`${TEXTS_PATH} is not a JSON object`)
  }
  const texts: Texts = { ...builtIn(language) }
  const part = (raw as Record<string, unknown>)[language]
  if (part === undefined) {
    return texts
  }
  if (typeof part !== 'object' || part === null || Array.isArray(part)) {
    throw new TextsError(`${TEXTS_PATH}: ${language} is not an object of texts`)
  }
  const given = part as Record<string, unknown>
  for (const key of Object.keys(texts) as (keyof Texts)[]) {
    const value = given[key]
    if (value === undefined) {
      continue
    }
    if (typeof value !== 'string') {
      throw new TextsError(`${TEXTS_PATH}: ${language}.${key} is not a string`)
    }
    texts[key] = value
  }
  return texts
}

export async function loadTexts(language: string, fetchFn: typeof fetch = fetch): Promise<Texts> {
  const response = await fetchFn(TEXTS_PATH, { cache: 'no-store' })
  if (!response.ok) {
    throw new TextsError(`${TEXTS_PATH} answered ${response.status}`)
  }
  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new TextsError(`${TEXTS_PATH} is not JSON`)
  }
  return parseTexts(body, language)
}

// The texts of ``language`` from /texts.json, or -- when the answer is not one
// (not 200, not JSON, not texts, no answer at all) -- its built-in texts, the
// reason given to ``report``. ``language`` is one of the page's (./config).
export async function textsOrBuiltIn(
  language: string,
  report: (message: string) => void = (message) => console.error(message),
  fetchFn: typeof fetch = fetch,
): Promise<Texts> {
  try {
    return await loadTexts(language, fetchFn)
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error)
    report(`texts package not applied, built-in ${language} texts: ${message}`)
    return builtIn(language)
  }
}
