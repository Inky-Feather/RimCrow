import assert from 'node:assert/strict'
import { test } from 'node:test'
import { ref } from 'vue'
import { useMaintenanceActions } from '../src/app/stores/app/maintenanceActions.js'

const ok = (data) => ({ status: 'success', data })
const deferred = () => {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

test('external update waits for loaded task before refreshing data', async () => {
  const completed = deferred()
  let refreshed = 0
  globalThis.window = { pywebview: { api: { update_external_db: async () => ok({ task_id: 'dataset' }) } } }
  const actions = useMaintenanceActions({
    settings: ref({}), waitForDownload: async id => { assert.equal(id, 'dataset'); await completed.promise },
    refreshModsData: async () => { refreshed++ },
  })
  const update = actions.updateExternalDB('instead_db', { silent: true })
  await new Promise(resolve => setTimeout(resolve, 0))
  assert.equal(refreshed, 0)
  completed.resolve()
  assert.equal(await update, true)
  assert.equal(refreshed, 1)
})

test('cancelled or failed external task does not refresh data', async () => {
  let refreshed = 0
  globalThis.window = { pywebview: { api: { update_external_db: async () => ok({ task_id: 'dataset' }) } } }
  const actions = useMaintenanceActions({
    settings: ref({}), waitForDownload: async () => { throw Object.assign(new Error('cancelled'), { from_task: true }) },
    refreshModsData: async () => { refreshed++ },
  })
  assert.equal(await actions.updateExternalDB('instead_db', { silent: true }), false)
  assert.equal(refreshed, 0)
})

test('late check result cannot replace newer check or timestamp', async () => {
  const calls = []
  const pending = []
  globalThis.window = { pywebview: { api: {
    maintenance_check_external_data: async options => {
      calls.push(options)
      const item = deferred()
      pending.push(item)
      return item.promise
    },
  } } }
  const settings = ref({})
  const actions = useMaintenanceActions({ settings })
  const old = actions.checkExternalDataUpdates({ manual: false, prompt: false })
  const current = actions.checkExternalDataUpdates({ manual: false, prompt: false })
  assert.notEqual(calls[0].check_id, calls[1].check_id)
  pending[1].resolve(ok({ checked_at: 200, items: [], failed: [], updates: [] }))
  assert.equal((await current).checked_at, 200)
  pending[0].resolve(ok({ checked_at: 100, items: [], failed: [], updates: [] }))
  assert.equal(await old, null)
  assert.equal(settings.value.last_external_data_update_check_time, 200)
})
