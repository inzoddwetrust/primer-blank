// The types of nginx/package.js for the TypeScript that imports it (its tests,
// or a build of another product that applies a package at build time).

export interface Checked {
  problems: string[]
}

export interface Skin extends Checked {
  css: string
}

export interface PackageTexts extends Checked {
  texts: Record<string, Record<string, string>>
}

export interface NginxRequest {
  headersOut: Record<string, string>
  return(status: number, body: string): void
  error(message: string): void
}

declare const primer: {
  checkSkin(dir: string): Skin
  checkTexts(dir: string, builtIn?: string): PackageTexts
  serveSkin(r: NginxRequest, dir: string): void
  serveTexts(r: NginxRequest, dir: string, builtIn?: string): void
  skinCss(r: NginxRequest): void
  textsJson(r: NginxRequest): void
}

export default primer
