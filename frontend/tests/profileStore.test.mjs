import assert from 'node:assert/strict'
import { createPinia, setActivePinia } from 'pinia'

import { useOrderStore } from '../src/features/load-order/orderStore.js'
import { useProfileStore } from '../src/features/profiles/profileStore.js'

const ok = (data = {}) => ({ status: 'success', data })
console.log = () => {}
console.info = () => {}
console.debug = () => {}

const installWindow = (api = {}) => {
  globalThis.document = {
    documentElement: { style: { setProperty() {} }, dataset: {}, classList: { toggle() {} } },
  }
  globalThis.window = {
    pywebview: { api },
    setTimeout,
    clearTimeout,
    addEventListener() {},
    removeEventListener() {},
  }
}

const resetStores = (api = {}) => {
  setActivePinia(createPinia())
  installWindow(api)
}

const deferred = () => {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

async function testLatestOrphanScanWins() {
  const first = deferred()
  let calls = 0
  resetStores({
    profiles_scan_orphaned: async () => {
      calls += 1
      return calls === 1 ? first.promise : ok([{ id: 'newer' }])
    },
  })

  const profileStore = useProfileStore()
  const oldScan = profileStore.scanOrphans()
  await profileStore.scanOrphans()
  first.resolve(ok([{ id: 'older' }]))
  await oldScan

  assert.equal(profileStore.orphanedProfiles.length, 1)
  assert.equal(profileStore.orphanedProfiles[0].id, 'newer')
}

function testClearDeletedProfileBackupRefs() {
  resetStores()
  const orderStore = useOrderStore()
  orderStore.setBackupProfile('deleted')
  orderStore.setBackupOrder({ source_profile_id: 'deleted', active_ids: ['mod.a'], file: 'backup.xml' }, 'backup.xml')
  orderStore.tempImports = [{ source_profile_id: 'deleted' }, { source_profile_id: 'other' }]

  assert.equal(orderStore.clearProfileRefs('deleted', 'default'), true)
  assert.equal(orderStore.backupProfileId, 'default')
  assert.equal(orderStore.currentBackupFile, '')
  assert.deepEqual(orderStore.tempImports.map(item => item.source_profile_id), ['other'])
}

await testLatestOrphanScanWins()
testClearDeletedProfileBackupRefs()

console.log('profileStore.test.mjs passed')
