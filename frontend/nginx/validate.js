#!/usr/bin/njs
// validate-skin <dir> | validate-texts <dir>: a package checked before the
// machine switches to it (primer.yaml packages.*.validate). Both commands are
// symlinks to this script; the name it is run by says which check. Every
// problem is printed with its file and token or key; any problem is a non-zero
// exit (njs exits 1 on an uncaught error).

import primer from '/usr/local/lib/primer/package.js'

const command = String(process.argv[1]).split('/').pop()
const check =
  command === 'validate-skin'
    ? primer.checkSkin
    : command === 'validate-texts'
      ? primer.checkTexts
      : null
if (check === null) {
  throw new Error(`run as validate-skin or validate-texts, not ${command}`)
}
if (process.argv.length !== 3) {
  throw new Error(`usage: ${command} <dir>`)
}
const dir = process.argv[2]
const result = check(dir)
result.problems.forEach((problem) => console.log(`${command}: ${problem}`))
if (result.problems.length > 0) {
  throw new Error(`${command}: ${dir}: ${result.problems.length} problem(s)`)
}
console.log(`${command}: ${dir}: ok`)
