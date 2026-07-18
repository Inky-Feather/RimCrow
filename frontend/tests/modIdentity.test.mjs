import assert from 'node:assert/strict'

import { hasUsableLanguagePackOwnership, isUsableLanguagePackOwnership } from '../src/features/mod/lib/modIdentity.js'

assert.equal(isUsableLanguagePackOwnership({ summary_confidence: 'medium' }), true)
assert.equal(isUsableLanguagePackOwnership({ summary_confidence: 'low' }), false)
assert.equal(hasUsableLanguagePackOwnership({ language_pack_owner_result: { summary_confidence: 'high' } }), true)

