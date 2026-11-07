// @vitest-environment node
// nginx/package.js under Node: what validate-skin and validate-texts refuse,
// each problem by its file and token or key, and what the engine serves.
// The same module runs in the image under njs; the image probes run it there.
import { chmodSync, mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import primer, { type NginxRequest } from '../nginx/package.js'

type Tree = Record<string, unknown>

const MANIFEST = 'schema: 1\ncontract: "1.0"\n'
// The product's built-in texts: its languages are their files (en, ru).
const BUILT_IN = fileURLToPath(new URL('./texts', import.meta.url))
const LOGO =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><rect width="8" height="8"/></svg>'

function colors(): Tree {
  return {
    color: {
      $type: 'color',
      brand: { primary: { $value: '#1A73E8' } },
      surface: { $value: '#FFFFFF' },
      text: { $value: '#202124' },
      link: { $value: '{color.brand.primary}' },
    },
  }
}

function typography(): Tree {
  return {
    font: {
      family: { base: { $type: 'fontFamily', $value: ['Inter', 'sans-serif'] } },
      size: { $type: 'dimension', base: { $value: { value: 16, unit: 'px' } } },
      weight: { $type: 'fontWeight', heading: { $value: 'bold' } },
    },
  }
}

const made: string[] = []

afterEach(() => {
  made.splice(0).forEach((dir) => rmSync(dir, { recursive: true, force: true }))
})

function write(root: string, file: string, body: string | Uint8Array): void {
  mkdirSync(dirname(join(root, file)), { recursive: true })
  writeFileSync(join(root, file), body)
}

// A good skin, then ``change`` applied to its files (a value of null removes).
function skin(change: Record<string, string | Uint8Array | Tree | null> = {}): string {
  const root = mkdtempSync(join(tmpdir(), 'skin-'))
  made.push(root)
  const files: Record<string, string | Uint8Array | Tree | null> = {
    'primer-package.yaml': MANIFEST,
    'tokens/color.tokens.json': colors(),
    'tokens/typography.tokens.json': typography(),
    'assets/logo.svg': LOGO,
    ...change,
  }
  Object.keys(files).forEach((file) => {
    const body = files[file]
    if (body === null || body === undefined) {
      return
    }
    const text =
      typeof body === 'string' || body instanceof Uint8Array ? body : JSON.stringify(body)
    write(root, file, text)
  })
  return root
}

function texts(change: Record<string, string | Tree | null> = {}): string {
  const root = mkdtempSync(join(tmpdir(), 'texts-'))
  made.push(root)
  const files: Record<string, string | Tree | null> = {
    'primer-package.yaml': MANIFEST,
    'ui/en.json': { title: 'T', config_error: 'E', api_label: 'A' },
    'ui/ru.json': { title: 'Т' },
    ...change,
  }
  Object.keys(files).forEach((file) => {
    const body = files[file]
    if (body === null || body === undefined) {
      return
    }
    write(root, file, typeof body === 'string' ? body : JSON.stringify(body))
  })
  return root
}

function png(width: number, height: number, size = 33): Uint8Array {
  const bytes = new Uint8Array(size)
  bytes.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], 0)
  const view = new DataView(bytes.buffer)
  view.setUint32(16, width)
  view.setUint32(20, height)
  return bytes
}

function withColor(path: string[], token: Tree): Tree {
  const tree = colors()
  let node = tree.color as Tree
  path.slice(0, -1).forEach((key) => {
    node[key] = node[key] ?? {}
    node = node[key] as Tree
  })
  node[path[path.length - 1] as string] = token
  return tree
}

describe('checkSkin', () => {
  it('takes a good skin and gives its tokens and assets as CSS properties', () => {
    const result = primer.checkSkin(skin({ 'assets/icons/check.svg': LOGO }))
    expect(result.problems).toEqual([])
    expect(result.css).toBe(
      [
        ':root {',
        '  --color-brand-primary: #1a73e8;',
        '  --color-link: #1a73e8;',
        '  --color-surface: #ffffff;',
        '  --color-text: #202124;',
        '  --font-family-base: "Inter", sans-serif;',
        '  --font-size-base: 16px;',
        '  --font-weight-heading: 700;',
        '  --asset-icon-check: url("/skin/assets/icons/check.svg");',
        '  --asset-logo: url("/skin/assets/logo.svg");',
        '}',
        '',
      ].join('\n'),
    )
  })

  it('reads past the .git of a worktree at the root, and only there', () => {
    expect(primer.checkSkin(skin({ '.git': 'gitdir: /opt/x\n' })).problems).toEqual([])
    expect(primer.checkSkin(skin({ 'tokens/.git': 'x' })).problems).toEqual([
      'tokens/.git: not a file of this package: no scripts, HTML or code',
    ])
  })

  it.each([
    [{ 'primer-package.yaml': null }, 'primer-package.yaml: missing'],
    [
      { 'primer-package.yaml': 'schema: 2\ncontract: "1.0"\n' },
      'primer-package.yaml: schema: must be 1, found 2',
    ],
    [
      { 'primer-package.yaml': 'schema: 1\ncontract: "2.0"\n' },
      'primer-package.yaml: contract: 2.x: this frontend reads 1.x',
    ],
    [
      { 'primer-package.yaml': 'schema: 1\ncontract: "1"\n' },
      'primer-package.yaml: contract: must be "X.Y", found "1"',
    ],
    [
      { 'primer-package.yaml': MANIFEST + 'name: x\n' },
      'primer-package.yaml: line 3: only schema and contract',
    ],
  ])('refuses the manifest %#', (change, problem) => {
    expect(primer.checkSkin(skin(change)).problems).toEqual([problem])
  })

  it('takes a manifest with comments', () => {
    const manifest = '# the skin\nschema: 1  # the form\ncontract: "1.3"\n'
    expect(primer.checkSkin(skin({ 'primer-package.yaml': manifest })).problems).toEqual([])
  })

  it.each([
    ['not JSON', { 'tokens/color.tokens.json': '{"color":' }, 'tokens/color.tokens.json: not JSON'],
    [
      'an array',
      { 'tokens/color.tokens.json': '[]' },
      'tokens/color.tokens.json: not a group of tokens',
    ],
    [
      'no token files',
      { 'tokens/color.tokens.json': null, 'tokens/typography.tokens.json': null },
      'tokens/: no *.tokens.json',
    ],
  ])('refuses %s', (_name, change, problem) => {
    expect(primer.checkSkin(skin(change)).problems[0]).toContain(problem)
  })

  it.each([
    ['no $type', withColor(['x'], { $value: 1 }), 'tokens/color.tokens.json: color.x: '],
    [
      'a $type not supported',
      withColor(['x'], { $type: 'shadow', $value: {} }),
      'color.x: $type shadow is not supported',
    ],
    [
      'a $ key not supported',
      withColor(['x'], { $value: '#000000', $extends: 'y' }),
      'color.x: $extends is not supported',
    ],
    ['a color not #hex', withColor(['x'], { $value: 'red' }), 'color.x: not a #hex color'],
    [
      'srgb out of 0..1',
      withColor(['x'], { $value: { colorSpace: 'srgb', components: [2, 0, 0] } }),
      'color.x: not a color',
    ],
    [
      'a name with a space',
      withColor(['bad name'], { $value: '#000000' }),
      'color.bad name: a name of letters',
    ],
    [
      'neither token nor group',
      withColor(['x'], 'plain' as unknown as Tree),
      'color.x: neither a token',
    ],
    [
      'a reference that does not resolve',
      withColor(['x'], { $value: '{color.nope}' }),
      'color.x: reference {color.nope} does not resolve',
    ],
    [
      'two tokens of one CSS name',
      withColor(['brand-primary'], { $value: '#000000' }),
      'color.brand.primary: --color-brand-primary is also color.brand-primary',
    ],
  ])('refuses %s', (_name, tree, problem) => {
    const problems = primer.checkSkin(skin({ 'tokens/color.tokens.json': tree })).problems
    expect(problems.join('\n')).toContain(problem)
  })

  it('takes a no-$type token without a group $type only as a problem of that token', () => {
    const tree = {
      color: {
        $type: 'color',
        brand: { primary: { $value: '#000000' } },
        surface: { $value: '#ffffff' },
        text: { $value: '#111111' },
      },
      misc: { x: { $value: 1 } },
    }
    expect(primer.checkSkin(skin({ 'tokens/color.tokens.json': tree })).problems).toEqual([
      'tokens/color.tokens.json: misc.x: has no $type, its own or its group',
    ])
  })

  it('refuses a cycle by its tokens', () => {
    const tree = colors()
    const color = tree.color as Tree
    color.a = { $value: '{color.b}' }
    color.b = { $value: '{color.a}' }
    const problems = primer.checkSkin(skin({ 'tokens/color.tokens.json': tree })).problems
    expect(problems).toEqual(['tokens/color.tokens.json: color.b: reference {color.a} is a cycle'])
  })

  it('follows a chain of references and refuses one of another $type', () => {
    const tree = colors()
    const color = tree.color as Tree
    color.accent = { $value: '{color.link}' }
    expect(primer.checkSkin(skin({ 'tokens/color.tokens.json': tree })).css).toContain(
      '--color-accent: #1a73e8;',
    )
    color.gap = { $type: 'dimension', $value: '{color.link}' }
    expect(primer.checkSkin(skin({ 'tokens/color.tokens.json': tree })).problems).toEqual([
      'tokens/color.tokens.json: color.gap: $type dimension, its reference color',
    ])
  })

  it('reads the DTCG object forms and keywords', () => {
    const tree = typography()
    const font = tree.font as Tree
    ;(font.size as Tree).heading = { $value: '2rem' }
    const color = withColor(['shade'], {
      $value: { colorSpace: 'srgb', components: [1, 0, 0.5], alpha: 0.5 },
    })
    const result = primer.checkSkin(
      skin({ 'tokens/color.tokens.json': color, 'tokens/typography.tokens.json': tree }),
    )
    expect(result.problems).toEqual([])
    expect(result.css).toContain('--color-shade: #ff008080;')
    expect(result.css).toContain('--font-size-heading: 2rem;')
    expect(result.css).toContain('--font-weight-heading: 700;')
  })

  it.each([
    ['a dimension in em', { $type: 'dimension', $value: '1em' }, 'not a dimension in px or rem'],
    [
      'a family that would end the CSS value',
      { $type: 'fontFamily', $value: 'Inter; } body {' },
      'a font family name of letters',
    ],
    [
      'an empty family list',
      { $type: 'fontFamily', $value: [] },
      'not a font family name or a list',
    ],
    ['a weight over 1000', { $type: 'fontWeight', $value: 1001 }, 'not a font weight'],
    ['a weight keyword unknown', { $type: 'fontWeight', $value: 'fat' }, 'not a font weight'],
    ['a number that is a string', { $type: 'number', $value: '1' }, 'not a number'],
  ])('refuses %s', (_name, token, problem) => {
    const tree = typography()
    ;(tree.font as Tree).x = token
    const problems = primer.checkSkin(skin({ 'tokens/typography.tokens.json': tree })).problems
    expect(problems).toEqual(
      [`tokens/typography.tokens.json: font.x: ${problem}`].map((p) => expect.stringContaining(p)),
    )
  })

  it('refuses a missing required token, in either file', () => {
    const tree = colors()
    delete (tree.color as Tree).text
    expect(primer.checkSkin(skin({ 'tokens/color.tokens.json': tree })).problems).toEqual([
      'tokens/: color.text: a required token is missing',
    ])
    const type = typography()
    delete ((type.font as Tree).family as Tree).base
    expect(primer.checkSkin(skin({ 'tokens/typography.tokens.json': type })).problems).toEqual([
      'tokens/: font.family.base: a required token is missing',
    ])
  })

  it('refuses a required token of another $type', () => {
    const tree = typography()
    ;(tree.font as Tree).family = { base: { $type: 'dimension', $value: '1px' } }
    expect(primer.checkSkin(skin({ 'tokens/typography.tokens.json': tree })).problems).toEqual([
      'tokens/typography.tokens.json: font.family.base: must be of $type fontFamily',
    ])
  })

  it('refuses one token in two files', () => {
    const tree = typography()
    ;(tree as Tree).color = { surface: { $type: 'color', $value: '#000000' } }
    expect(primer.checkSkin(skin({ 'tokens/typography.tokens.json': tree })).problems).toEqual([
      'tokens/typography.tokens.json: color.surface: also in tokens/color.tokens.json',
    ])
  })

  it.each([
    ['a missing logo', { 'assets/logo.svg': null }, 'assets/logo.svg: a required asset is missing'],
    [
      'a script',
      { 'assets/logo.svg': '<svg><script>x()</script></svg>' },
      'assets/logo.svg: has a script',
    ],
    [
      'an event handler',
      { 'assets/logo.svg': '<svg onload="x()"></svg>' },
      'assets/logo.svg: has an event handler',
    ],
    [
      'a javascript: address',
      { 'assets/logo.svg': '<svg><a href="javascript:x()"/></svg>' },
      'has a javascript: address',
    ],
    [
      'a link out',
      { 'assets/logo.svg': '<svg><image href="https://x.test/a.png"/></svg>' },
      'assets/logo.svg: has a link out of the file',
    ],
    ['foreignObject', { 'assets/logo.svg': '<svg><foreignObject/></svg>' }, 'has foreignObject'],
    [
      'an entity',
      { 'assets/logo.svg': '<!DOCTYPE svg [<!ENTITY a "b">]><svg/>' },
      'assets/logo.svg: not an SVG image',
    ],
    [
      'an entity after the root',
      { 'assets/logo.svg': '<svg><!ENTITY a "b"></svg>' },
      'has a DOCTYPE or ENTITY',
    ],
    [
      'HTML named .svg',
      { 'assets/logo.svg': '<html><body/></html>' },
      'assets/logo.svg: not an SVG image',
    ],
    [
      'an SVG too large',
      { 'assets/logo.svg': `<svg>${' '.repeat(64 * 1024)}</svg>` },
      'assets/logo.svg: larger than 65536 bytes',
    ],
    [
      'a PNG that is not one',
      { 'assets/icons/a.png': new Uint8Array(40) },
      'assets/icons/a.png: not a PNG image',
    ],
    [
      'a PNG too wide',
      { 'assets/icons/a.png': png(2048, 16) },
      'assets/icons/a.png: wider or taller than 1024 px',
    ],
    [
      'a PNG too tall',
      { 'assets/icons/a.png': png(16, 2048) },
      'assets/icons/a.png: wider or taller than 1024 px',
    ],
    [
      'a PNG too large',
      { 'assets/icons/a.png': png(16, 16, 256 * 1024 + 1) },
      'assets/icons/a.png: larger than 262144 bytes',
    ],
    ['a script file', { 'assets/app.js': 'x()' }, 'assets/app.js: not a file of this package'],
    ['an HTML file', { 'index.html': '<p>' }, 'index.html: not a file of this package'],
    [
      'an asset of another format',
      { 'assets/logo.gif': 'GIF89a' },
      'assets/logo.gif: not a file of this package',
    ],
  ])('refuses %s', (_name, change, problem) => {
    expect(primer.checkSkin(skin(change)).problems.join('\n')).toContain(problem)
  })

  // an attribute starts after a space of any kind, a slash or a closing
  // quote of either kind; a link is out of the file quoted or not
  it.each([
    ['after a space', '<svg onload="x()"></svg>', 'an event handler'],
    ['after a newline', '<svg\nonload="x()"></svg>', 'an event handler'],
    ['after a tab, in capitals', '<svg\tONLOAD="x()"></svg>', 'an event handler'],
    ['after a slash', '<svg><g/onload=x() /></svg>', 'an event handler'],
    ['after a double quote', '<svg x="1"onload="x()"></svg>', 'an event handler'],
    ['after a single quote', "<svg x='1'onload='x()'></svg>", 'an event handler'],
    ['a space before =', '<svg><g onclick ="x()"/></svg>', 'an event handler'],
    ['a link in double quotes', '<svg><image href="https://x.test/a"/></svg>', 'a link out'],
    ['a link in single quotes', "<svg><image href='//x.test/a'/></svg>", 'a link out'],
    ['a link without quotes', '<svg><image href=https://x.test/a /></svg>', 'a link out'],
    ['an xlink:href without quotes', '<svg><use xlink:href=x.svg#a /></svg>', 'a link out'],
    ['a link after a space in quotes', '<svg><a href=" http://x.test"/></svg>', 'a link out'],
  ])('refuses an SVG with %s', (_name, svg, rule) => {
    expect(primer.checkSkin(skin({ 'assets/logo.svg': svg })).problems).toContain(
      `assets/logo.svg: has ${rule}${rule === 'a link out' ? ' of the file' : ''}`,
    )
  })

  it.each([
    ['a link inside it, quoted', '<svg><use href="#a"/><g id="a"/></svg>'],
    ['a link inside it, unquoted', '<svg><use href=#a /><g id="a"/></svg>'],
    ['an empty link', '<svg><a href=""/></svg>'],
    [
      '"on" inside a word and a text',
      '<svg><g stroke-linejoin="round"/><text>on = off</text></svg>',
    ],
  ])('takes an SVG with %s', (_name, svg) => {
    expect(primer.checkSkin(skin({ 'assets/logo.svg': svg })).problems).toEqual([])
  })

  // the good skin is 6 files and directories; an icons directory and n icons
  // make it 7 + n
  function withIcons(count: number): string {
    const root = skin()
    for (let n = 0; n < count; n += 1) {
      write(root, `assets/icons/i-${String(n).padStart(3, '0')}.svg`, LOGO)
    }
    return root
  }

  it('takes a package of 512 files and directories', () => {
    expect(primer.checkSkin(withIcons(505)).problems).toEqual([])
  })

  it('refuses the 513th file or directory by its name and stops the walk', () => {
    const problems = primer.checkSkin(withIcons(506)).problems
    expect(problems[0]).toBe(
      'tokens/typography.tokens.json: past 512 files and directories: a package is smaller',
    )
    // the file past the limit is not read: its tokens are missing
    expect(problems).toContain('tokens/: font.family.base: a required token is missing')
  })

  it('names only the first entry past the limit: the walk stops there', () => {
    const past = primer
      .checkSkin(withIcons(507))
      .problems.filter((problem) => problem.includes('past 512'))
    expect(past).toEqual([
      'tokens/color.tokens.json: past 512 files and directories: a package is smaller',
    ])
  })

  it('takes an SVG with a link inside itself, a comment and an XML declaration', () => {
    const svg = '<?xml version="1.0"?>\n<!-- logo -->\n<svg><use href="#a"/><g id="a"/></svg>'
    const result = primer.checkSkin(
      skin({ 'assets/logo.svg': svg, 'assets/icons/b.png': png(16, 16) }),
    )
    expect(result.problems).toEqual([])
    expect(result.css).toContain('--asset-icon-b: url("/skin/assets/icons/b.png");')
  })

  it('refuses a symlink and an executable file', () => {
    const root = skin()
    write(root, 'assets/icons/run.svg', LOGO)
    symlinkSync('/etc/passwd', join(root, 'assets/icons/link.svg'))
    chmodSync(join(root, 'assets/icons/run.svg'), 0o755)
    expect(primer.checkSkin(root).problems).toEqual([
      'assets/icons/link.svg: a symlink: a package holds files only',
      'assets/icons/run.svg: executable: a package holds no code',
    ])
  })

  it('refuses a directory that is not one', () => {
    expect(primer.checkSkin('/nonexistent/skin').problems).toContain(
      '/nonexistent/skin: not a directory',
    )
  })
})

describe('checkTexts', () => {
  it('takes good texts by language; a language may give only some keys', () => {
    const result = primer.checkTexts(
      texts({ 'ui/en.json': { title: 'T', config_error: 'E', extra: 'a < b' } }),
      BUILT_IN,
    )
    expect(result).toEqual({
      problems: [],
      texts: { en: { config_error: 'E', extra: 'a < b', title: 'T' }, ru: { title: 'Т' } },
    })
  })

  it('takes a package without one of the languages', () => {
    const result = primer.checkTexts(texts({ 'ui/ru.json': null }), BUILT_IN)
    expect(result).toEqual({
      problems: [],
      texts: { en: { api_label: 'A', config_error: 'E', title: 'T' } },
    })
  })

  it('refuses a language the product does not have, by its file', () => {
    const result = primer.checkTexts(texts({ 'ui/de.json': { title: 'D' } }), BUILT_IN)
    expect(result.problems).toEqual(["ui/de.json: language de is not one of the product's: en, ru"])
    expect(Object.keys(result.texts)).toEqual(['en', 'ru'])
  })

  it.each([
    ['no language', { 'ui/en.json': null, 'ui/ru.json': null }, 'ui/: no <language>.json'],
    ['not JSON', { 'ui/en.json': '{' }, 'ui/en.json: not JSON'],
    ['an array', { 'ui/ru.json': '[]' }, 'ui/ru.json: not an object of texts'],
    ['a value not a string', { 'ui/ru.json': { title: 1 } }, 'ui/ru.json: title: not a string'],
    ['markup', { 'ui/en.json': { title: '<b>T</b>' } }, 'ui/en.json: title: has markup'],
    [
      'a control character',
      { 'ui/en.json': { title: 'T\u0007' } },
      'title: has a control character',
    ],
    [
      'a text too long',
      { 'ui/en.json': { title: 'x'.repeat(501) } },
      'title: longer than 500 characters',
    ],
    ['a bad key', { 'ui/en.json': { 'Bad Key': 'x' } }, 'ui/en.json: Bad Key: a key of'],
    [
      'a region as a language',
      { 'ui/en-GB.json': { title: 'T' } },
      'ui/en-GB.json: language en-GB is not one',
    ],
    ['another file', { 'ui/app.js': 'x()' }, 'ui/app.js: not a file of this package'],
    ['a file out of ui', { 'strings.json': '{}' }, 'strings.json: not a file of this package'],
    ['no manifest', { 'primer-package.yaml': null }, 'primer-package.yaml: missing'],
  ])('refuses %s', (_name, change, problem) => {
    const result = primer.checkTexts(texts(change), BUILT_IN)
    expect(result.problems.join('\n')).toContain(problem)
  })

  it("refuses everything when the product's built-in texts are not there", () => {
    expect(primer.checkTexts(texts(), '/nonexistent/texts').problems).toContain(
      "/nonexistent/texts: the product's built-in texts are not here",
    )
  })
})

describe('the engine', () => {
  function request(): NginxRequest & { status: number; body: string; errors: string[] } {
    const r = {
      headersOut: {} as Record<string, string>,
      status: 0,
      body: '',
      errors: [] as string[],
      return(status: number, body: string) {
        r.status = status
        r.body = body
      },
      error(message: string) {
        r.errors.push(message)
      },
    }
    return r
  }

  it('serves the built-in theme and no texts when no package is mounted', () => {
    const css = request()
    primer.serveSkin(css, '/nonexistent/srv/skin')
    expect([css.status, css.headersOut['Content-Type']]).toEqual([200, 'text/css; charset=utf-8'])
    expect(css.body).not.toContain('--')
    const json = request()
    primer.serveTexts(json, '/nonexistent/srv/texts', BUILT_IN)
    expect([json.status, json.body]).toEqual([200, '{}'])
  })

  it('serves a mounted package (the pair)', () => {
    const css = request()
    primer.serveSkin(css, skin())
    expect([css.status, css.errors]).toEqual([200, []])
    expect(css.body).toContain('--color-brand-primary: #1a73e8;')
    const json = request()
    primer.serveTexts(json, texts(), BUILT_IN)
    expect([json.status, JSON.parse(json.body)]).toEqual([
      200,
      { en: { api_label: 'A', config_error: 'E', title: 'T' }, ru: { title: 'Т' } },
    ])
  })

  // a dictionary of strings, as nginx's shared one: a missing key is undefined
  function dictionary(): Map<string, string> & { sets: number } {
    const map = new Map<string, string>() as Map<string, string> & { sets: number }
    map.sets = 0
    const set = map.set.bind(map)
    map.set = (key: string, value: string) => {
      map.sets += 1
      return set(key, value)
    }
    return map
  }

  it('checks a package once and answers again from the dictionary', () => {
    const cache = dictionary()
    const root = skin()
    const first = request()
    primer.serveSkin(first, root, cache)
    expect([first.status, cache.sets]).toEqual([200, 1])
    // a defect planted in place is not seen: the answer is the kept one
    write(root, 'assets/logo.svg', '<svg><script>x()</script></svg>')
    const again = request()
    primer.serveSkin(again, root, cache)
    expect([again.status, again.body, cache.sets]).toEqual([200, first.body, 1])
    // without the dictionary every request checks the package
    const unkept = request()
    primer.serveSkin(unkept, root)
    expect(unkept.status).toBe(500)
  })

  it('keeps a refusal: 500 and its problems logged on every answer', () => {
    const cache = dictionary()
    const root = texts({ 'ui/de.json': '{}' })
    const answers = [request(), request()]
    answers.forEach((r) => primer.serveTexts(r, root, BUILT_IN, cache))
    expect(answers.map((r) => [r.status, r.errors.length])).toEqual([
      [500, 1],
      [500, 1],
    ])
    expect(cache.sets).toBe(1)
  })

  it("checks again when the package's root changes: a new key", () => {
    const cache = dictionary()
    const root = texts()
    const first = request()
    primer.serveTexts(first, root, BUILT_IN, cache)
    write(root, 'notes.txt', 'x')
    const again = request()
    primer.serveTexts(again, root, BUILT_IN, cache)
    expect([first.status, again.status, cache.sets]).toEqual([200, 500, 2])
  })

  it('refuses an invalid package with 500 and logs its problems', () => {
    const css = request()
    primer.serveSkin(css, skin({ 'assets/logo.svg': null }))
    expect([css.status, css.errors]).toEqual([
      500,
      ['skin package: assets/logo.svg: a required asset is missing'],
    ])
    const json = request()
    primer.serveTexts(json, texts({ 'ui/de.json': '{}' }), BUILT_IN)
    expect([json.status, json.errors]).toEqual([
      500,
      ["texts package: ui/de.json: language de is not one of the product's: en, ru"],
    ])
  })
})
