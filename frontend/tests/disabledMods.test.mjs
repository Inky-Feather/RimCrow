import assert from 'node:assert/strict'
import { createPinia, setActivePinia } from 'pinia'
import { useModStore } from '../src/features/mod/stores/modStore.js'
import { useProfileStore } from '../src/features/profiles/profileStore.js'

globalThis.document = { documentElement: { style: { setProperty() {} }, dataset: {}, classList: { toggle() {} } } }
let ghostRequests = 0
globalThis.window = {
  setTimeout, clearTimeout, addEventListener() {}, removeEventListener() {},
  pywebview: { api: { get_workshop_details_by_package_ids: async () => {
    ghostRequests++
    return { status: 'success', data: {} }
  } } },
}
setActivePinia(createPinia())
useProfileStore().activeContext = { game_version: '1.6', local_mods_path: 'G:/Mods' }
const store = useModStore()
const disabled = { package_id: 'author.disabled', path_hash: 'disabled', path: 'G:/Mods/disabled', name: 'Disabled mod', disabled: true, store: 'local', author: ['Author'], version: '2.0' }
const enabled = { package_id: 'author.enabled', path_hash: 'enabled', path: 'G:/Mods/enabled', name: 'Enabled mod', rules: { dependencies: [{ target_id: disabled.package_id }] } }
const load = (allMods, disabledMods, active = []) => store.setMods({ all_mods: allMods, disabled_mods: disabledMods, active_load_order: active })

load([enabled], [disabled], [disabled.package_id, enabled.package_id])
const resolved = store.takeModById(disabled.package_id)
assert.equal(resolved.name, disabled.name)
assert.equal(resolved.path, disabled.path)
assert.equal(resolved.disabled, true)
assert.equal(!!resolved.isMissing, false)
assert.equal(store.allModsMap.has(disabled.package_id), false)
assert.equal(store.hasRealModById(disabled.package_id), false)
assert.equal(store.getAvailableModInstances().some(mod => mod.disabled), false)
assert.equal(store.exportableActiveCount, 1)
store.selectMods([disabled.package_id])
assert.equal(store.lastSelectedMod.author[0], 'Author')
assert.equal(store.lastSelectedMod.disabled, true)
const issues = store.modIssues.get(disabled.package_id)
assert.equal(issues.length, 1)
assert.equal(issues[0].level, 'error')
assert.match(issues[0].message, /已被禁用.*不会在游戏中加载/)
assert.ok(store.modIssues.get(enabled.package_id).some(issue => /已被禁用/.test(issue.message)))
await store.fetchAndCacheGhostMods([disabled.package_id])
assert.equal(ghostRequests, 0)

// 同包名仍有可用副本时，不能把整个包误判为禁用；Steam token 单独识别对应副本。
load([{ ...disabled, disabled: false, path_hash: 'local-enabled' }], [{ ...disabled, store: 'workshop' }])
assert.equal(store.takeModById(disabled.package_id).disabled, false)
assert.equal(store.takeModById(`${disabled.package_id}_steam`).disabled, true)
assert.equal(store.takeModById(`${disabled.package_id}_steam`).store, 'workshop')
assert.equal(store.hasRealModById(`${disabled.package_id}_steam`), false)
assert.equal(!!store.takeModById('author.missing').isMissing, true)

load([{ ...disabled, disabled: false }, enabled], [{ ...disabled, store: 'workshop' }], [`${disabled.package_id}_steam`, enabled.package_id])
assert.ok(store.modIssues.get(enabled.package_id).some(issue => /已被禁用/.test(issue.message)))

// 工坊查询返回前模组状态可能已变化，旧响应不能把真实资产覆盖成缺失对象。
for (const isDisabled of [true, false]) {
  let finish
  window.pywebview.api.get_workshop_details_by_package_ids = () => new Promise(resolve => { finish = resolve })
  load([], [])
  const pending = store.fetchAndCacheGhostMods([disabled.package_id])
  load(isDisabled ? [] : [{ ...disabled, disabled: false }], isDisabled ? [disabled] : [])
  finish({ status: 'success', data: { [disabled.package_id]: { name: 'Old workshop response' } } })
  await pending
  assert.equal(store.takeModById(disabled.package_id).name, disabled.name)
  assert.equal(!!store.takeModById(disabled.package_id).isMissing, false)
}

load([{ ...disabled, disabled: false }], [])
assert.equal(store.takeModById(disabled.package_id).disabled, false)
assert.equal(store.modIssues.get(disabled.package_id), undefined)
