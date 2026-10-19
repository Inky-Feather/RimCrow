import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')
const entry = `
import { createApp, defineAsyncComponent, h, ref } from 'vue'
import { createPinia } from 'pinia'
import Toast from 'vue-toastification'
import { useAppStore } from '/src/app/stores/appStore.js'
import { useFileSearchStore } from '/src/features/file-search/fileSearchStore.js'
import { vTooltip } from '/src/shared/directives/vTooltip.js'
import { setLocale } from '/src/shared/i18n.js'
import '/src/app/styles/style.css'
const Settings = defineAsyncComponent(() => import('/src/features/mod/ModSettingsManagerModal.vue'))
const Search = defineAsyncComponent(() => import('/src/features/file-search/FileSearchWorkbench.vue'))
const current = ref('')
const content = '<settings><enabled>true</enabled></settings>'
window.pywebview = {api: {
  locale_load_user_messages: async () => ({status:'success',data:{language:'zh-CN',messages:{}}}),
  mod_settings_get_overview: async () => ({status:'success',data:{mod_groups:[{
    group_key:'test', mod_name:'Test mod', status:'active', setting_groups:[{
      key:'test', label:'Duplicate settings', files:[
        {key:'test',name:'Settings.xml',file_path:'G:/Test/Settings.xml',active:true,state_kind:'active'},
        {key:'copy',name:'Backup.xml',file_path:'G:/Test/Backup.xml',state_kind:'coexist_disabled'},
      ],
    }, {key:'single',label:'Single setting',files:[{key:'single',name:'Single.xml',file_path:'G:/Test/Single.xml'}]}],
  }, {
    group_key:'unique',mod_name:'Unique mod',status:'active',setting_groups:[
      {key:'a',label:'Setting A',files:[{key:'a',name:'A.xml',file_path:'G:/Test/A.xml'}]},
      {key:'b',label:'Setting B',files:[{key:'b',name:'B.xml',file_path:'G:/Test/B.xml'}]},
    ],
  }]}}),
}}
const app = createApp({render: () => current.value === 'settings' ? h(Settings,{visible:true}) : current.value === 'search' ? h(Search) : null})
app.use(createPinia()); app.use(Toast); app.directive('tooltip',vTooltip)
await setLocale('zh-CN')
const store = useAppStore()
store.readTextFile = async () => ({content})
Object.assign(useFileSearchStore().viewerState,{filePath:'G:/Test/Settings.xml',content})
window.openPage = name => {store.uiState.showFileSearchWorkbench = name === 'search'; current.value = name}
app.mount('#app'); window.ready = true
`
const server = await createServer({
  root: fileURLToPath(new URL('..', import.meta.url)), cacheDir: 'node_modules/.vite-tests/file-search',
  server: { host: '127.0.0.1', port: 0, strictPort: false },
  plugins: [{
    name: 'file-search-browser-check',
    resolveId: id => id === '/__file-search.js' ? '\0file-search-check' : undefined,
    load: id => id === '\0file-search-check' ? entry : undefined,
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url !== '/__file-search') return next()
        res.setHeader('Content-Type', 'text/html; charset=utf-8')
        res.end('<div id="app"></div><script type="module" src="/__file-search.js"></script>')
      })
    },
  }],
})
let browser
try {
  await server.listen()
  browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || undefined })
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
  const errors = []
  page.on('pageerror', error => errors.push(String(error)))
  page.on('response', response => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`) })
  page.on('requestfailed', request => errors.push(`${request.failure()?.errorText} ${request.url()}`))
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__file-search`)
  await page.waitForFunction(() => window.ready)
  for (const name of ['settings', 'search', 'settings', 'search']) {
    await page.evaluate(name => window.openPage(name), name)
    await page.getByRole('dialog').waitFor()
    await page.locator('.cm-content').filter({ hasText: '<settings><enabled>true</enabled></settings>' }).waitFor()
    assert.equal(await page.locator('.cm-editor').count(), 1)
    await page.evaluate(() => window.openPage(''))
    await page.getByRole('dialog').waitFor({ state: 'detached' })
  }
  await page.evaluate(() => window.openPage('settings'))
  const dialog = page.getByRole('dialog')
  await dialog.locator('article').nth(1).waitFor()
  const selectFilter = async label => {
    await dialog.locator('input[readonly]').click()
    await page.getByRole('button', { name: label, exact: true }).click({ timeout: 3000 })
  }
  await selectFilter('存在重复')
  await dialog.getByText('Single setting', { exact: true }).waitFor({ state: 'detached' })
  assert.equal(await dialog.locator('article').count(), 1)
  assert.equal(await dialog.locator('article section').count(), 1)
  await dialog.getByRole('button', { name: 'Settings.xml', exact: true }).waitFor()
  await dialog.getByRole('button', { name: 'Backup.xml', exact: true }).waitFor()
  const query = dialog.getByPlaceholder('搜索模组、包名、设置或文件')
  await query.fill('Backup.xml')
  await dialog.getByRole('button', { name: 'Settings.xml', exact: true }).waitFor({ state: 'detached' })
  await dialog.getByRole('button', { name: 'Backup.xml', exact: true }).waitFor()
  await query.fill('Single')
  await dialog.getByText('没有匹配的设置文件', { exact: true }).waitFor()
  await query.fill('')
  await selectFilter('当前激活')
  await dialog.getByRole('button', { name: 'Settings.xml', exact: true }).waitFor()
  assert.equal(await dialog.getByRole('button', { name: 'Backup.xml', exact: true }).count(), 0)
  await selectFilter('全部状态')
  await dialog.getByText('Unique mod', { exact: true }).waitFor()
  assert.equal(await dialog.locator('article section').count(), 4)
  assert.deepEqual(errors, [])
  console.log('File search and mod settings: lazy loading, XML preview, repeated opening, duplicate group and keyword/state filters passed.')
} finally {
  await browser?.close()
  await server.close()
}
