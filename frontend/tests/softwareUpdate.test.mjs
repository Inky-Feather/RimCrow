import assert from 'node:assert/strict'
import test from 'node:test'
import { ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { useUpdateActions, getUpdateSourceDetails, getUpdateStatusText } from '../src/app/stores/app/updateActions.js'
import { usePromptQueueStore } from '../src/features/ai/promptQueueStore.js'
import { useConfirmStore } from '../src/shared/components/modal/confirmStore.js'

const setup = (api = {}) => {
  setActivePinia(createPinia())
  globalThis.window = { pywebview: { api } }
  const state = { isChecking: false, hasUpdate: false, info: null, lastCheckedAt: 0, checkError: '' }
  const actions = useUpdateActions({ updateState: state, upgradeContext: ref({}), isLoading: ref(false), uiState: {}, logMaintenanceCheck() {} })
  return { state, actions }
}
const update = () => ({
  has_update: true, version: '1.2.3', source_name: 'SourceForge', local_status: 'remote', file_size: '70 MB', check_status: 'partial',
  sources: [{ source_name: 'SourceForge', version: '1.2.3', download_url: 'https://sourceforge.example/app.zip', changelog: 'Latest package' }, { source_name: 'GitHub', version: '1.2.3', download_url: 'https://github.example/app.zip', changelog: '## Changes\nOne release' }],
  source_results: [{ source_name: 'SourceForge', status: 'update', version: '1.2.3' }, { source_name: 'GitHub', status: 'update', version: '1.2.3', access_path: 'builtin_mirror' }, { source_name: 'Gitee', status: 'failed' }],
})

test('one release has one item and one action group; checking ends before prompt dismissal', async () => {
  const { state, actions } = setup({ update_check: async () => ({ status: 'success', data: update() }) })
  const pending = actions.checkUpdate()
  await new Promise(setImmediate)
  assert.equal(state.isChecking, false)
  const confirm = useConfirmStore()
  assert.equal(confirm.state.promptItems.length, 1)
  const item = confirm.state.promptItems[0]
  assert.equal(item.descriptionFormat, 'markdown')
  assert.match(item.description, /One release/)
  assert.equal(item.actions.length, 0)
  assert.equal(item.details.length, 3)
  assert.equal(confirm.state.actionButtons.length, 2)
  assert.deepEqual(confirm.state.actionSelector.options.map(option => option.value), ['', 'https://sourceforge.example/app.zip', 'https://github.example/app.zip'])
  assert.ok(state.lastCheckedAt)
  confirm.chooseAction({ scope: 'bulk', action: 'skip' })
  await pending
})

test('no update clears stale results; partial failures are not labelled latest', async () => {
  const { state, actions } = setup({ update_check: async () => ({ status: 'success', data: { has_update: false, check_status: 'partial', source_results: [] } }) })
  state.hasUpdate = true
  state.info = update()
  await actions.checkUpdate()
  assert.equal(state.hasUpdate, false)
  assert.equal(state.info.has_update, false)
  assert.match(getUpdateStatusText(state), /部分/)
  assert.deepEqual(getUpdateSourceDetails({}), [])
})

test('automatic ignored updates stay visible in About without reopening a prompt', async () => {
  const { state, actions } = setup({ update_check: async () => ({ status: 'success', data: { ...update(), is_ignored: true } }) })
  await actions.checkUpdate(false)
  assert.equal(state.hasUpdate, true)
  assert.equal(usePromptQueueStore().activePrompt, null)
})

test('both installation confirmations are required, and either may cancel', async () => {
  for (const answers of [[true, true], [false], [true, false]]) {
    const triggered = []
    const { state, actions } = setup({ update_trigger_action: async (...args) => { triggered.push(args); return { status: 'success', data: {} } } })
    state.info = { ...update(), local_status: 'ready' }
    const calls = []
    useConfirmStore().confirmAction = async (...args) => { calls.push(args); return answers[calls.length - 1] }
    await actions._showInstallPrompt({ path: 'F:/updates/app.zip', version: '1.2.3' })
    assert.equal(calls.length, answers.length)
    assert.deepEqual(triggered, answers.every(Boolean) ? [['1.2.3', true, '']] : [])
  }
})

test('stale prompt cannot start a different release', async () => {
  let prompt
  let triggered = false
  const { state, actions } = setup({ update_trigger_action: async () => { triggered = true } })
  state.info = update()
  usePromptQueueStore().enqueue = async value => { prompt = value }
  await actions.showAvailableUpdate()
  state.info = { ...update(), version: '1.2.4' }
  await prompt.onBulkAction('download')
  assert.equal(triggered, false)
})

test('a fast completion is not overwritten by the download response', async () => {
  const { state, actions } = setup({ update_trigger_action: async () => {
    state.info.local_status = 'ready'
    return { status: 'success', data: { status: 'downloading' } }
  } })
  state.info = update()
  let prompt
  usePromptQueueStore().enqueue = async value => { prompt = value }
  await actions.showAvailableUpdate()
  await prompt.onBulkAction('download')
  assert.equal(state.info.local_status, 'ready')
})

test('a ready response to a download request still requires both confirmations', async () => {
  const triggered = []
  const { state, actions } = setup({ update_trigger_action: async (...args) => {
    triggered.push(args)
    return { status: 'success', data: { status: 'ready', version: '1.2.3', path: 'F:/updates/app.zip' } }
  } })
  state.info = update()
  let prompt
  usePromptQueueStore().enqueue = async value => { prompt = value }
  const titles = []
  useConfirmStore().confirmAction = async title => { titles.push(title); return titles.length === 1 }
  await actions.showAvailableUpdate()
  await prompt.onBulkAction('download')
  assert.equal(titles.length, 2)
  assert.deepEqual(triggered, [['1.2.3', false, '']])
})

test('source details distinguish older releases, missing packages and missing releases', () => {
  const details = getUpdateSourceDetails({ ...update(), source_results: [
    { source_name: 'old', status: 'update', version: '1.2.2' },
    { source_name: 'platform', status: 'no_package' },
    { source_name: 'empty', status: 'no_release' },
  ] })
  assert.match(details[0].value, /1\.2\.2/)
  assert.notEqual(details[1].value, details[2].value)
})

test('source details show the concrete available version', () => {
  const details = getUpdateSourceDetails({ ...update(), source_results: [
    { source_name: 'GitHub', status: 'update', version: '1.2.3' },
  ] })
  assert.match(details[0].value, /1\.2\.3/)
})

test('download selector defaults to automatic and accepts an explicit source', async () => {
  const triggered = []
  const { state, actions } = setup({ update_trigger_action: async (...args) => {
    triggered.push(args)
    return { status: 'success', data: {} }
  } })
  state.info = update()
  let prompt
  usePromptQueueStore().enqueue = async value => { prompt = value }
  await actions.showAvailableUpdate()
  assert.equal(prompt.bulkActions[0].id, 'download')
  assert.equal(prompt.actionSelector.value, '')
  assert.deepEqual(prompt.actionSelector.options.map(option => option.label), ['自动选择（推荐）', 'SourceForge', 'GitHub'])
  await prompt.onBulkAction('download', [], prompt, 'https://github.example/app.zip')
  assert.deepEqual(triggered, [['1.2.3', false, 'https://github.example/app.zip']])
})

test('release notes from all publishing sources use rich rendering', async () => {
  for (const source_name of ['GitHub', 'Gitee', '更新清单', '本地缓存', '蓝奏云']) {
    const { state, actions } = setup()
    state.info = { ...update(), source_name, changelog: '## Changes\n- **Fixed**\n\n<p>HTML notes</p>', sources: [] }
    let prompt
    usePromptQueueStore().enqueue = async value => { prompt = value }
    await actions.showAvailableUpdate()
    assert.equal(prompt.items[0].descriptionFormat, 'markdown', source_name)
  }
})
