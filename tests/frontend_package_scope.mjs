import assert from 'node:assert/strict'
import { isOfficialMod } from '../frontend/src/features/mod/lib/packageScope.js'

assert.equal(isOfficialMod({ package_id: 'ludeon.rimworld' }), true)
assert.equal(isOfficialMod({ package_id: 'ludeon.rimworld.royalty' }), true)
assert.equal(isOfficialMod('ludeon.rimworld.ideology'), true)
assert.equal(isOfficialMod({ packageId: 'ludeon.rimworld.biotech' }), true)
assert.equal(isOfficialMod({ source: 'dlc' }), true)
assert.equal(isOfficialMod({ package_id: 'rimcrow.companion', source: 'self' }), false)
assert.equal(isOfficialMod({ package_id: 'some.mod', source: 'workshop' }), false)
