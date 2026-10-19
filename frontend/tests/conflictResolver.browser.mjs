import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

// 使用已有 Playwright 环境，不向应用新增依赖；可通过环境变量指定宿主运行时与浏览器。
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')
const entry = `
import { createApp, h, nextTick } from 'vue'
import { createPinia } from 'pinia'
import Toast from 'vue-toastification'
import ConflictResolver from '/src/features/dialogs/ConflictResolver.vue'
import { useModStore } from '/src/features/mod/stores/modStore.js'
import { useAppStore } from '/src/app/stores/appStore.js'
import { useConfirmStore } from '/src/shared/components/modal/confirmStore.js'
import { useContextMenuStore } from '/src/shared/components/context-menu/contextMenuStore.js'
import { vTooltip } from '/src/shared/directives/vTooltip.js'
import { setLocale } from '/src/shared/i18n.js'
import '/src/app/styles/style.css'
window.pywebview = { api: new Proxy({}, { get: (target, key) => target[key] || (async () => ({ status: 'success', data: {} })) }) }
const app = createApp(ConflictResolver)
const pinia = createPinia()
app.use(pinia); app.use(Toast); app.directive('tooltip', vTooltip)
await setLocale('zh-CN')
const mods = useModStore()
window.mods = mods
window.menu = useContextMenuStore()
useAppStore().settings.show_coexistence_message = true
window.confirms = useConfirmStore()
window.fill = async (count, copies = 2) => {
  mods.conflictList = Array.from({ length: count }, (_, i) => ({
    package_id: 'test.' + i,
    items: Array.from({ length: copies }, (_, j) => ({
      name: 'Mod ' + i + ' copy ' + j, package_id: 'test.' + i, path_hash: i + '-' + j,
      path: 'G:/Mods/' + i + '/' + j, store: 'local', supported_versions: ['1.6'], version: '1.0',
    })),
  }))
  await nextTick()
}
window.showDisabled = async () => {
  const [{ default: ModItem }, { default: ModDetails }] = await Promise.all([
    import('/src/features/mod/ModItem.vue'), import('/src/features/mod/ModDetails.vue'),
  ])
  mods.conflictList = []
  mods.setMods({ all_mods: [{ package_id: 'test.enabled', name: 'Enabled test mod', path_hash: 'enabled', path: 'G:/Mods/enabled', disabled: false }], disabled_mods: [{
    package_id: 'test.disabled', name: 'Disabled test mod', path_hash: 'disabled',
    path: 'G:/Mods/disabled', store: 'local', source: 'local', disabled: true, author: ['Known author'],
  }], active_load_order: ['test.disabled'] })
  mods.selectMods(['test.disabled'])
  useAppStore().settings.ui.detail_delay = 0
  const node = document.createElement('div'); node.id = 'disabled-check'; document.body.append(node)
  const details = createApp({ render: () => h('div', [h(ModItem, { item_id: 'test.disabled' }), h(ModItem, { item_id: 'test.enabled' }), h(ModDetails)]) })
  details.use(pinia); details.directive('tooltip', vTooltip); details.directive('preview', {}); details.directive('viewer', {})
  details.mount(node)
  await nextTick()
}
app.mount('#app'); window.ready = true
`
const server = await createServer({
  root: fileURLToPath(new URL('..', import.meta.url)), cacheDir: 'node_modules/.vite-tests/conflict-resolver', server: { port: 0, strictPort: false },
  plugins: [{
    name: 'conflict-check',
    resolveId(id) { if (id === '/__conflict.js') return id },
    load(id) { if (id === '/__conflict.js') return entry },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url !== '/__conflict') return next()
        res.setHeader('Content-Type', 'text/html')
        res.end('<div id="app"></div><script type="module" src="/__conflict.js"></script>')
      })
    },
  }],
})
let browser
try {
  await server.listen()
  browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || undefined })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const errors = []
  page.on('pageerror', error => errors.push(String(error)))
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__conflict`)
  await page.waitForFunction(() => window.ready)
  const list = page.locator('[data-tour="conflict-list"]')
  for (const [count, copies] of [[9, 2], [500, 2], [1, 1000]]) {
    await page.evaluate(([n, c]) => window.fill(n, c), [count, copies])
    await page.getByText('Mod 0 copy 0', { exact: true }).waitFor()
    assert.ok(await page.locator('input[type=radio]').count() < 180)
    await page.getByText('当前范围全删除', { exact: true }).click()
    await page.getByText('当前范围全禁用', { exact: true }).click()
    assert.ok(await page.locator('[role=dialog]').isVisible())
  }
  await list.evaluate(element => { element.scrollTop = element.scrollHeight })
  await page.getByText('Mod 0 copy 999', { exact: true }).waitFor()
  await page.getByText('Mod 0 copy 999', { exact: true }).click()
  await list.evaluate(element => { element.scrollTop = 0 })
  await page.getByText('Mod 0 copy 0', { exact: true }).waitFor()
  await page.evaluate(() => {
    window.confirms.confirmAction = () => new Promise(resolve => { window.finishConfirm = resolve })
    window.pywebview.api.scan_conflicts_resolve = async operations => {
      window.operations = operations
      return { status: 'error', message: 'Test failure' }
    }
  })
  await page.getByText('执行处理', { exact: true }).click()
  await page.waitForFunction(() => window.finishConfirm)
  assert.ok(await list.evaluate(element => element.parentElement.inert))
  await page.evaluate(() => window.finishConfirm(false))
  await page.getByText('执行处理', { exact: true }).waitFor()
  assert.equal(await list.evaluate(element => element.parentElement.inert), false)
  await page.evaluate(() => { window.confirms.confirmAction = async () => true })
  await page.getByText('执行处理', { exact: true }).click()
  await page.waitForFunction(() => window.operations)
  const operations = await page.evaluate(() => window.operations)
  assert.equal(operations.length, 999)
  assert.equal(new Set(operations.map(item => item.target_path_hash)).size, 999)
  assert.ok(operations.every(item => item.action === 'disable' && item.keep_path_hash === '0-999' && item.target_path_hash !== '0-999'))
  await page.getByText('稍后处理', { exact: true }).click()
  await page.evaluate(() => window.fill(9))
  await page.getByText('Mod 0 copy 0', { exact: true }).waitFor()
  await page.getByText('当前范围全删除', { exact: true }).click()
  await page.evaluate(() => {
    window.operations = null
    window.confirms.confirmDeleteAction = async () => ({ confirmed: true, force: true })
  })
  await page.getByText('执行处理', { exact: true }).click()
  await page.waitForFunction(() => window.operations)
  const deletions = await page.evaluate(() => window.operations)
  assert.equal(deletions.length, 9)
  assert.ok(deletions.every(item => item.action === 'delete' && item.force_delete && item.target_path_hash !== item.keep_path_hash))
  await page.evaluate(() => window.showDisabled())
  const disabledPanel = page.locator('#disabled-check')
  assert.ok(await disabledPanel.getByText('已禁用', { exact: true }).count() >= 2)
  assert.ok(await disabledPanel.locator('[role=alert]').isVisible())
  assert.ok(await disabledPanel.getByText('Known author', { exact: true }).isVisible())
  assert.equal(await disabledPanel.getByText(/未知模组/).count(), 0)
  await page.evaluate(() => {
    window.menu.open = (_event, items) => { window.menuItems = items.filter(item => !item.hidden) }
    window.mods.disableMods = async (...args) => { window.restoreArgs = args }
  })
  const openMenu = async ids => {
    await page.evaluate(ids => window.mods.selectMods(ids), ids)
    await disabledPanel.locator(`[data-id="${ids[0]}"]`).click({ button: 'right' })
    return page.evaluate(() => window.menuItems.filter(item => item.commandId === 'mods.disableSelectedFiles' || item.label?.startsWith('解除禁用')).map(item => ({ label: item.label || item.labelOverride, ids: item.args?.modIds })))
  }
  let stateItems = await openMenu(['test.disabled'])
  assert.equal(stateItems.length, 1)
  assert.match(stateItems[0].label, /^解除禁用/)
  await page.evaluate(() => window.menuItems.find(item => item.label?.startsWith('解除禁用')).action())
  assert.deepEqual(await page.evaluate(() => window.restoreArgs), [['disabled'], false, { preserveListState: true }])
  stateItems = await openMenu(['test.enabled'])
  assert.equal(stateItems.length, 1)
  assert.deepEqual(stateItems[0].ids, ['test.enabled'])
  stateItems = await openMenu(['test.disabled', 'test.enabled'])
  assert.equal(stateItems.length, 2)
  assert.deepEqual(stateItems.find(item => item.ids).ids, ['test.enabled'])
  await page.evaluate(() => window.menuItems.find(item => item.label?.startsWith('解除禁用')).action())
  assert.deepEqual(await page.evaluate(() => window.restoreArgs[0]), ['disabled'])
  assert.deepEqual(errors, [])
  console.log('Conflict resolver: bounded rows, 1000 copies, selection persistence, confirmation cancellation, 999 disable and 9 delete operations passed')
} finally {
  await browser?.close()
  await server.close()
}
