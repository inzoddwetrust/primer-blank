// The instance's packages of the blank's frontend: skin and texts (contract 3
// rule 10, apply: runtime).
//
// One module, three uses:
// - nginx (njs, js_import) serves /skin.css -- the skin's W3C DTCG tokens as
//   CSS custom properties -- and /texts.json -- the texts of the page by
//   language -- from the packages the machine mounts read-only at /srv/skin
//   and /srv/texts. No package mounted: an empty skin.css and {} -- the page
//   keeps its built-in theme and texts;
// - the commands validate-skin <dir> and validate-texts <dir> (validate.js,
//   run by the njs CLI): the machine runs them in the new image before it
//   switches a package (primer.yaml packages.*.validate);
// - Node, in the frontend's tests and in a build that applies a package at
//   build time: the module is written in the subset njs and Node share -- no
//   for..of, spread, destructuring, default parameters, classes or regex
//   flag u.
//
// The product's languages are the files of its built-in texts
// (src/texts/<language>.json of the frontend, in the image at BUILT_IN_DIR): a
// texts package overrides strings of those languages and brings no other
// (protocol 5.2.2).
//
// What a package is (contract "1.0" of the blank's packages) is in the READMEs
// of primer-blank-skin and primer-blank-texts.

import fs from 'fs'

const SKIN_DIR = '/srv/skin'
const TEXTS_DIR = '/srv/texts'
const BUILT_IN_DIR = '/usr/local/lib/primer/texts'
const MANIFEST = 'primer-package.yaml'
const CONTRACT_MAJOR = 1

const COMMON_FILES = [/^primer-package\.yaml$/, /^README\.md$/, /^LICENSE$/]
const TOKEN_FILE = /^tokens\/[a-z0-9-]+\.tokens\.json$/
const ASSET_FILE = /^assets\/(icons\/)?[a-z0-9-]+\.(svg|png)$/
const SKIN_FILES = COMMON_FILES.concat([TOKEN_FILE, ASSET_FILE])
const LANGUAGE_FILE = /^ui\/([^/]+)\.json$/
const TEXTS_FILES = COMMON_FILES.concat([LANGUAGE_FILE])

const REQUIRED_TOKENS = {
  'color.brand.primary': 'color',
  'color.surface': 'color',
  'color.text': 'color',
  'font.family.base': 'fontFamily',
}
const REQUIRED_ASSETS = ['assets/logo.svg']

const JSON_MAX_BYTES = 256 * 1024
const SVG_MAX_BYTES = 64 * 1024
const PNG_MAX_BYTES = 256 * 1024
const PNG_MAX_SIDE = 1024
const TEXT_MAX_CHARS = 500
const PNG_MAGIC = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]

const TYPES = ['color', 'dimension', 'fontFamily', 'fontWeight', 'number']
const TOKEN_KEYS = ['$value', '$type', '$description', '$extensions', '$deprecated']
const GROUP_KEYS = ['$type', '$description', '$extensions', '$deprecated']
const NAME = /^[A-Za-z0-9_-]+$/
const REFERENCE = /^\{([^{}]+)\}$/
const HEX = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/
const DIMENSION = /^(-?[0-9]+(\.[0-9]+)?)(px|rem)$/
const FAMILY = /^[A-Za-z0-9 ._-]+$/
const GENERIC_FAMILIES = ['serif', 'sans-serif', 'monospace', 'cursive', 'system-ui']
const FONT_WEIGHTS = {
  thin: 100,
  hairline: 100,
  'extra-light': 200,
  'ultra-light': 200,
  light: 300,
  normal: 400,
  regular: 400,
  book: 400,
  medium: 500,
  'semi-bold': 600,
  'demi-bold': 600,
  bold: 700,
  'extra-bold': 800,
  'ultra-bold': 800,
  black: 900,
  heavy: 900,
  'extra-black': 950,
  'ultra-black': 950,
}
const SVG_FORBIDDEN = [
  [/<script/i, 'a script'],
  [/\son[a-z]+\s*=/i, 'an event handler'],
  [/javascript:/i, 'a javascript: address'],
  [/<foreignObject/i, 'foreignObject'],
  [/<(iframe|embed|object)/i, 'an embedded document'],
  [/<!(DOCTYPE|ENTITY)/i, 'a DOCTYPE or ENTITY'],
  [/href\s*=\s*["']\s*[^#"'\s]/i, 'a link out of the file'],
]
const TEXT_KEY = /^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$/
const MARKUP = /<[A-Za-z/!?]/
const CONTROL = /[\u0000-\u0008\u000b-\u001f\u007f]/

function report(problems, file, where, text) {
  problems.push(where ? `${file}: ${where}: ${text}` : `${file}: ${text}`)
}

function isDir(path) {
  try {
    return fs.statSync(path).isDirectory()
  } catch (e) {
    if (e.code === 'ENOENT' || e.code === 'ENOTDIR') {
      return false
    }
    throw e
  }
}

// Every regular file of the package, relative to its root; a symlink, an
// executable file or anything that is neither a file nor a directory is a
// problem. ".git" at the root is the worktree's link, not the package's.
function walk(root, rel, files, problems) {
  const path = rel ? `${root}/${rel}` : root
  const entries = fs.readdirSync(path, { withFileTypes: true })
  entries.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))
  entries.forEach((entry) => {
    const name = rel ? `${rel}/${entry.name}` : entry.name
    if (!rel && entry.name === '.git') {
      return
    }
    if (entry.isSymbolicLink()) {
      report(problems, name, '', 'a symlink: a package holds files only')
    } else if (entry.isDirectory()) {
      walk(root, name, files, problems)
    } else if (entry.isFile()) {
      if (fs.statSync(`${root}/${name}`).mode & 0o111) {
        report(problems, name, '', 'executable: a package holds no code')
      }
      files.push(name)
    } else {
      report(problems, name, '', 'not a regular file')
    }
  })
}

function packageFiles(dir, allowed, problems) {
  const files = []
  if (!isDir(dir)) {
    report(problems, dir, '', 'not a directory')
    return files
  }
  walk(dir, '', files, problems)
  files.forEach((file) => {
    if (!allowed.some((pattern) => pattern.test(file))) {
      report(problems, file, '', 'not a file of this package: no scripts, HTML or code')
    }
  })
  return files
}

// primer-package.yaml in block form: "schema: 1" and "contract: "X.Y"".
function checkManifest(dir, files, problems) {
  if (files.indexOf(MANIFEST) < 0) {
    report(problems, MANIFEST, '', 'missing')
    return
  }
  const found = {}
  fs.readFileSync(`${dir}/${MANIFEST}`, 'utf8')
    .split('\n')
    .forEach((raw, index) => {
      const line = raw.replace(/\s+#.*$/, '').replace(/^#.*$/, '')
      if (line.trim() === '') {
        return
      }
      const match = /^(schema|contract):\s*(.*?)\s*$/.exec(line)
      if (match === null) {
        report(problems, MANIFEST, `line ${index + 1}`, 'only schema and contract')
        return
      }
      found[match[1]] = match[2]
    })
  if (found.schema !== '1') {
    report(problems, MANIFEST, 'schema', `must be 1, found ${found.schema}`)
  }
  const contract = /^(["']?)([0-9]+)\.([0-9]+)\1$/.exec(found.contract || '')
  if (contract === null) {
    report(problems, MANIFEST, 'contract', `must be "X.Y", found ${found.contract}`)
  } else if (Number(contract[2]) !== CONTRACT_MAJOR) {
    report(problems, MANIFEST, 'contract', `${contract[2]}.x: this frontend reads 1.x`)
  }
}

// KNOWN CEILING -- a key repeated in one JSON object.
// 1. Mechanism: JSON.parse keeps the last of repeated keys, in njs and Node
//    alike; a token or a text written twice takes its last value, silently.
// 2. Status: acknowledged by design.
// 3. Task: none -- a repeated key changes nothing but which of two values the
//    package's own author wrote wins; no value of the instance, no code.
// 4. Trigger: a package whose look or text is not what its author meant
//    because a key is repeated.
// 5. Fix: a scan of the JSON text for repeated keys per object before
//    JSON.parse, each named with its file and path.
// 6. Rejected: a JSON parser of our own instead of JSON.parse -- a second
//    parser to keep in step with njs and Node for one case.
function readJson(dir, file, problems) {
  const path = `${dir}/${file}`
  if (fs.statSync(path).size > JSON_MAX_BYTES) {
    report(problems, file, '', `larger than ${JSON_MAX_BYTES} bytes`)
    return null
  }
  try {
    return JSON.parse(fs.readFileSync(path, 'utf8'))
  } catch (e) {
    report(problems, file, '', `not JSON: ${e.message}`)
    return null
  }
}

function isObject(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

// The tokens of one file into ``tokens`` by dotted path: {file, type, value}.
function collect(node, file, path, inherited, tokens, problems) {
  const isToken = Object.prototype.hasOwnProperty.call(node, '$value')
  const allowed = isToken ? TOKEN_KEYS : GROUP_KEYS
  const where = path.join('.')
  Object.keys(node).forEach((key) => {
    if (key.charAt(0) === '$' && allowed.indexOf(key) < 0) {
      report(problems, file, where || '(root)', `${key} is not supported`)
    }
  })
  let type = inherited
  if (Object.prototype.hasOwnProperty.call(node, '$type')) {
    type = node.$type
    if (TYPES.indexOf(type) < 0) {
      report(problems, file, where || '(root)', `$type ${type} is not supported`)
      return
    }
  }
  if (isToken) {
    if (tokens[where] !== undefined) {
      report(problems, file, where, `also in ${tokens[where].file}`)
      return
    }
    tokens[where] = { file: file, type: type, value: node.$value }
    return
  }
  Object.keys(node).forEach((key) => {
    if (key.charAt(0) === '$') {
      return
    }
    const name = path.concat([key]).join('.')
    if (!NAME.test(key)) {
      report(problems, file, name, 'a name of letters, digits, _ and - only')
    } else if (!isObject(node[key])) {
      report(problems, file, name, 'neither a token ($value) nor a group')
    } else {
      collect(node[key], file, path.concat([key]), type, tokens, problems)
    }
  })
}

function hex2(n) {
  const text = Math.round(n * 255).toString(16)
  return text.length === 1 ? `0${text}` : text
}

function unitNumber(value) {
  return typeof value === 'number' && isFinite(value) && value >= 0 && value <= 1
}

// The CSS text of a literal value of ``type``, or a problem (a string).
function literal(type, value) {
  if (type === 'color') {
    if (typeof value === 'string') {
      return HEX.test(value) ? { css: value.toLowerCase() } : { problem: `not a #hex color` }
    }
    if (
      isObject(value) &&
      value.colorSpace === 'srgb' &&
      Array.isArray(value.components) &&
      value.components.length === 3 &&
      value.components.every(unitNumber) &&
      (value.alpha === undefined || unitNumber(value.alpha))
    ) {
      const alpha = value.alpha === undefined || value.alpha === 1 ? '' : hex2(value.alpha)
      return { css: `#${value.components.map(hex2).join('')}${alpha}` }
    }
    return { problem: 'not a color: #hex, or srgb components in 0..1' }
  }
  if (type === 'dimension') {
    if (typeof value === 'string' && DIMENSION.test(value)) {
      return { css: value }
    }
    if (
      isObject(value) &&
      typeof value.value === 'number' &&
      isFinite(value.value) &&
      (value.unit === 'px' || value.unit === 'rem')
    ) {
      return { css: `${value.value}${value.unit}` }
    }
    return { problem: 'not a dimension in px or rem' }
  }
  if (type === 'fontFamily') {
    const names = typeof value === 'string' ? [value] : value
    if (!Array.isArray(names) || names.length === 0) {
      return { problem: 'not a font family name or a list of them' }
    }
    if (!names.every((name) => typeof name === 'string' && FAMILY.test(name))) {
      return { problem: 'a font family name of letters, digits, spaces, . _ - only' }
    }
    return {
      css: names
        .map((name) => (GENERIC_FAMILIES.indexOf(name) >= 0 ? name : `"${name}"`))
        .join(', '),
    }
  }
  if (type === 'fontWeight') {
    if (typeof value === 'number' && Number.isInteger(value) && value >= 1 && value <= 1000) {
      return { css: String(value) }
    }
    if (typeof value === 'string' && FONT_WEIGHTS[value] !== undefined) {
      return { css: String(FONT_WEIGHTS[value]) }
    }
    return { problem: 'not a font weight: 1..1000 or a DTCG keyword' }
  }
  if (type === 'number') {
    return typeof value === 'number' && isFinite(value)
      ? { css: String(value) }
      : { problem: 'not a number' }
  }
  return { problem: 'has no $type, its own or its group' }
}

// Resolve every token to {type, css}; references ({a.b}) are followed to a
// literal, a cycle or an unknown token is a problem of the token that has it.
function resolveAll(tokens, problems) {
  const resolved = {}
  function resolve(path, trail) {
    if (resolved[path] !== undefined) {
      return resolved[path]
    }
    const token = tokens[path]
    let result = null
    const reference = typeof token.value === 'string' ? REFERENCE.exec(token.value) : null
    if (reference !== null) {
      const target = reference[1]
      if (tokens[target] === undefined) {
        report(problems, token.file, path, `reference ${token.value} does not resolve`)
      } else if (trail.indexOf(target) >= 0) {
        report(problems, token.file, path, `reference ${token.value} is a cycle`)
      } else {
        const found = resolve(target, trail.concat([target]))
        if (found !== null) {
          if (token.type !== undefined && token.type !== found.type) {
            report(problems, token.file, path, `$type ${token.type}, its reference ${found.type}`)
          } else {
            result = found
          }
        }
      }
    } else {
      const css = literal(token.type, token.value)
      if (css.problem !== undefined) {
        report(problems, token.file, path, css.problem)
      } else {
        result = { type: token.type, css: css.css }
      }
    }
    resolved[path] = result
    return result
  }
  Object.keys(tokens)
    .sort()
    .forEach((path) => resolve(path, [path]))
  return resolved
}

function checkSvg(dir, file, problems) {
  const path = `${dir}/${file}`
  if (fs.statSync(path).size > SVG_MAX_BYTES) {
    report(problems, file, '', `larger than ${SVG_MAX_BYTES} bytes`)
    return
  }
  const text = fs.readFileSync(path, 'utf8')
  const start = text.replace(/^\uFEFF?\s*(<\?xml[^>]*\?>\s*)?(<!--[\s\S]*?-->\s*)*/, '')
  if (!/^<svg[\s>]/.test(start)) {
    report(problems, file, '', 'not an SVG image')
    return
  }
  SVG_FORBIDDEN.forEach((rule) => {
    if (rule[0].test(text)) {
      report(problems, file, '', `has ${rule[1]}`)
    }
  })
}

function checkPng(dir, file, problems) {
  const path = `${dir}/${file}`
  if (fs.statSync(path).size > PNG_MAX_BYTES) {
    report(problems, file, '', `larger than ${PNG_MAX_BYTES} bytes`)
    return
  }
  const bytes = fs.readFileSync(path)
  if (bytes.length < 24 || !PNG_MAGIC.every((byte, index) => bytes[index] === byte)) {
    report(problems, file, '', 'not a PNG image')
    return
  }
  function side(at) {
    return ((bytes[at] << 24) | (bytes[at + 1] << 16) | (bytes[at + 2] << 8) | bytes[at + 3]) >>> 0
  }
  if (side(16) > PNG_MAX_SIDE || side(20) > PNG_MAX_SIDE) {
    report(problems, file, '', `wider or taller than ${PNG_MAX_SIDE} px`)
  }
}

function cssName(path) {
  return `--${path.split('.').join('-')}`
}

// The skin at ``dir``: {problems, css}. ``css`` is the :root block of every
// token and asset, in path order; it is meant only when there is no problem.
function checkSkin(dir) {
  const problems = []
  const files = packageFiles(dir, SKIN_FILES, problems)
  checkManifest(dir, files, problems)
  const tokens = {}
  const tokenFiles = files.filter((file) => TOKEN_FILE.test(file))
  if (tokenFiles.length === 0) {
    report(problems, 'tokens/', '', 'no *.tokens.json')
  }
  tokenFiles.forEach((file) => {
    const tree = readJson(dir, file, problems)
    if (tree === null) {
      return
    }
    if (!isObject(tree)) {
      report(problems, file, '', 'not a group of tokens')
      return
    }
    collect(tree, file, [], undefined, tokens, problems)
  })
  const resolved = resolveAll(tokens, problems)
  Object.keys(REQUIRED_TOKENS).forEach((path) => {
    if (tokens[path] === undefined) {
      report(problems, 'tokens/', path, 'a required token is missing')
    } else if (resolved[path] !== null && resolved[path].type !== REQUIRED_TOKENS[path]) {
      report(problems, tokens[path].file, path, `must be of $type ${REQUIRED_TOKENS[path]}`)
    }
  })
  const assets = files.filter((file) => ASSET_FILE.test(file))
  REQUIRED_ASSETS.forEach((file) => {
    if (assets.indexOf(file) < 0) {
      report(problems, file, '', 'a required asset is missing')
    }
  })
  assets.forEach((file) => {
    if (/\.svg$/.test(file)) {
      checkSvg(dir, file, problems)
    } else {
      checkPng(dir, file, problems)
    }
  })
  const names = {}
  const lines = []
  Object.keys(resolved)
    .sort()
    .forEach((path) => {
      const name = cssName(path)
      if (names[name] !== undefined) {
        report(problems, tokens[path].file, path, `${name} is also ${names[name]}`)
        return
      }
      names[name] = path
      if (resolved[path] !== null) {
        lines.push(`  ${name}: ${resolved[path].css};`)
      }
    })
  assets.forEach((file) => {
    const name = file
      .replace(/^assets\//, '--asset-')
      .replace(/^--asset-icons\//, '--asset-icon-')
      .replace(/\.(svg|png)$/, '')
    if (names[name] !== undefined) {
      report(problems, file, '', `${name} is also ${names[name]}`)
      return
    }
    names[name] = file
    lines.push(`  ${name}: url("/skin/${file}");`)
  })
  return { problems: problems, css: `:root {\n${lines.join('\n')}\n}\n` }
}

// The product's languages: the names of its built-in texts' files in
// ``builtIn``, sorted; none is a problem of the product, not of a package.
function productLanguages(builtIn, problems) {
  const languages = isDir(builtIn)
    ? fs
        .readdirSync(builtIn)
        .filter((name) => /^[a-z]{2,3}\.json$/.test(name))
        .map((name) => name.replace(/\.json$/, ''))
        .sort()
    : []
  if (languages.length === 0) {
    report(problems, builtIn, '', "the product's built-in texts are not here")
  }
  return languages
}

// The strings of one language file: plain strings under keys of a-z, 0-9, _
// and dots; a string the file does not give is the product's built-in one.
function checkStrings(dir, file, problems) {
  const strings = readJson(dir, file, problems)
  const texts = {}
  if (strings === null) {
    return texts
  }
  if (!isObject(strings)) {
    report(problems, file, '', 'not an object of texts')
    return texts
  }
  Object.keys(strings)
    .sort()
    .forEach((key) => {
      const value = strings[key]
      if (!TEXT_KEY.test(key)) {
        report(problems, file, key, 'a key of a-z, 0-9, _ and dots only')
      } else if (typeof value !== 'string') {
        report(problems, file, key, 'not a string')
      } else if (value.length > TEXT_MAX_CHARS) {
        report(problems, file, key, `longer than ${TEXT_MAX_CHARS} characters`)
      } else if (MARKUP.test(value)) {
        report(problems, file, key, 'has markup: texts are plain')
      } else if (CONTROL.test(value)) {
        report(problems, file, key, 'has a control character')
      } else {
        texts[key] = value
      }
    })
  return texts
}

// The texts at ``dir``: {problems, texts} -- ui/<language>.json, each a
// language of the product (``builtIn``, BUILT_IN_DIR when not given); texts
// by language.
function checkTexts(dir, builtIn) {
  const problems = []
  const languages = productLanguages(builtIn === undefined ? BUILT_IN_DIR : builtIn, problems)
  const files = packageFiles(dir, TEXTS_FILES, problems)
  checkManifest(dir, files, problems)
  const texts = {}
  const given = files.filter((file) => LANGUAGE_FILE.test(file))
  if (given.length === 0) {
    report(problems, 'ui/', '', 'no <language>.json')
  }
  given.forEach((file) => {
    const language = LANGUAGE_FILE.exec(file)[1]
    if (languages.indexOf(language) < 0) {
      report(
        problems,
        file,
        '',
        `language ${language} is not one of the product's: ${languages.join(', ')}`,
      )
      return
    }
    texts[language] = checkStrings(dir, file, problems)
  })
  return { problems: problems, texts: texts }
}

function answer(r, status, type, body) {
  r.headersOut['Content-Type'] = type
  r.return(status, body)
}

// GET /skin.css: the skin at ``dir``, or none -- the built-in theme.
function serveSkin(r, dir) {
  if (!isDir(dir)) {
    answer(r, 200, 'text/css; charset=utf-8', '/* no skin package: the built-in theme */\n')
    return
  }
  const skin = checkSkin(dir)
  if (skin.problems.length > 0) {
    r.error(`skin package: ${skin.problems.join('; ')}`)
    answer(r, 500, 'text/plain; charset=utf-8', 'the skin package is invalid\n')
    return
  }
  answer(r, 200, 'text/css; charset=utf-8', skin.css)
}

// GET /texts.json: the texts at ``dir`` by language, or none -- the built-in
// texts. ``builtIn`` -- the product's built-in texts (BUILT_IN_DIR when not
// given).
function serveTexts(r, dir, builtIn) {
  if (!isDir(dir)) {
    answer(r, 200, 'application/json', '{}')
    return
  }
  const texts = checkTexts(dir, builtIn)
  if (texts.problems.length > 0) {
    r.error(`texts package: ${texts.problems.join('; ')}`)
    answer(r, 500, 'text/plain; charset=utf-8', 'the texts package is invalid\n')
    return
  }
  answer(r, 200, 'application/json', JSON.stringify(texts.texts))
}

// nginx (js_content): the packages where the machine mounts them.
function skinCss(r) {
  serveSkin(r, SKIN_DIR)
}

function textsJson(r) {
  serveTexts(r, TEXTS_DIR)
}

export default { checkSkin, checkTexts, serveSkin, serveTexts, skinCss, textsJson }
