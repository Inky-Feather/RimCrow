import assert from 'node:assert/strict'

import { hasUsableLanguagePackOwnership, isUsableLanguagePackOwnership, normalizeInstallSource } from '../src/features/mod/lib/modIdentity.js'

assert.equal(isUsableLanguagePackOwnership({ summary_confidence: 'medium' }), true)
assert.equal(isUsableLanguagePackOwnership({ summary_confidence: 'low' }), false)
assert.equal(hasUsableLanguagePackOwnership({ language_pack_owner_result: { summary_confidence: 'high' } }), true)

const gitSource = normalizeInstallSource({
  package_id: 'author.gitmod',
  source_kind: 'git',
  source_origin: 'git_catalog',
  name: 'Git Mod',
  url: 'https://gitgud.io/team/active',
  install_type: 'source',
  default_branch: 'Dev',
})
assert.equal(gitSource.kind, 'git')
assert.equal(gitSource.installType, 'source')
assert.equal(gitSource.defaultBranch, 'Dev')
