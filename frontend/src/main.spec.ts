import { afterEach, describe, expect, it, vi } from 'vitest'
import { BUILT_IN } from './texts'

// The page as the browser starts it: src/main.ts against the container's
// /config.json and /texts.json, answered here.
const CONFIG = '{"apiBaseUrl":"https://api.example.com","languages":"en","defaultLanguage":"en"}'

async function page(texts: Response): Promise<{ app: HTMLElement; errors: string[] }> {
  document.body.innerHTML = '<div id="app"></div>'
  const errors: string[] = []
  vi.spyOn(console, 'error').mockImplementation((message: unknown) => {
    errors.push(String(message))
  })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string) => (path === '/config.json' ? new Response(CONFIG) : texts)),
  )
  vi.resetModules()
  await import('./main')
  const app = document.getElementById('app') as HTMLElement
  await vi.waitFor(() => expect(app.querySelector('main')).not.toBeNull())
  return { app, errors }
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('the page and its texts package', () => {
  it('test_probe_DM_74_broken_texts_json_keeps_page_on_built_in_texts', async () => {
    const { app, errors } = await page(new Response('<html>', { status: 200 }))
    expect(app.querySelector('[data-test="config-error"]')).toBeNull()
    expect(app.querySelector('[data-test="api-origin"]')?.textContent).toBe(
      `${BUILT_IN.en?.api_label} https://api.example.com`,
    )
    expect(app.querySelector('[data-test="title"]')?.textContent).toBe(BUILT_IN.en?.title)
    expect(errors).toEqual([
      'texts package not applied, built-in en texts: /texts.json is not JSON',
    ])
  })

  it('keeps the built-in texts when the container refuses the package (500)', async () => {
    const { app, errors } = await page(new Response('invalid', { status: 500 }))
    expect(app.querySelector('[data-test="config-error"]')).toBeNull()
    expect(app.querySelector('[data-test="api-origin"]')?.textContent).toBe(
      `${BUILT_IN.en?.api_label} https://api.example.com`,
    )
    expect(errors).toEqual([
      'texts package not applied, built-in en texts: /texts.json answered 500',
    ])
  })

  it("takes a valid package's texts, with nothing on the console", async () => {
    const { app, errors } = await page(new Response('{"en":{"api_label":"Server:"}}'))
    expect(app.querySelector('[data-test="api-origin"]')?.textContent).toBe(
      'Server: https://api.example.com',
    )
    expect(errors).toEqual([])
  })
})
