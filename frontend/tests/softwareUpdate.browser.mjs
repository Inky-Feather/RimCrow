import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdir, readFile } from 'node:fs/promises'
import { createServer } from 'vite'

// 使用宿主已有浏览器环境；所有后端动作由隔离页面的假接口承接。
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')
const releaseNotes = await readFile(new URL('./fixtures/update-v0.24.12.txt', import.meta.url), 'utf8')
const entry = `
import { createApp, defineAsyncComponent, h } from 'vue'
import { createPinia } from 'pinia'
import Toast from 'vue-toastification'
import About from '/src/features/settings/panel/SettingsAboutTab.vue'
const Confirm = defineAsyncComponent(() => import('/src/shared/components/modal/Confirm.vue'))
import { useAppStore } from '/src/app/stores/appStore.js'
import { useStartupStore } from '/src/app/stores/startupStore.js'
import { useConfirmStore } from '/src/shared/components/modal/confirmStore.js'
import { vTooltip } from '/src/shared/directives/vTooltip.js'
import { setLocale } from '/src/shared/i18n.js'
import '/src/app/styles/style.css'
window.info = {
  has_update: true, version: '1.2.3', source_name: 'SourceForge', file_size: '70 MB', local_status: 'remote', check_status: 'partial',
  sources: [{source_name:'SourceForge',version:'1.2.3',download_url:'https://sourceforge.example/app.zip',changelog:'Latest package'}, {source_name:'GitHub',version:'1.2.3',download_url:'https://github.example/app.zip',changelog:${JSON.stringify(releaseNotes)}}],
  source_results: [{source_name:'SourceForge',status:'update',version:'1.2.3'}, {source_name:'GitHub',status:'update',version:'1.2.3',access_path:'builtin_mirror'}, {source_name:'Gitee',status:'failed',error:'暂时无法检查'}],
}
window.reply = window.info
window.triggered = []
window.pywebview = {api: new Proxy({
  update_check: async () => ({status:'success',data:structuredClone(window.reply)}),
  update_trigger_action: async (version) => {window.triggered.push(version);return {status:'success',data:{}}},
}, {get:(target,key)=>target[key] || (async()=>({status:'success',data:{}}))})}
const app = createApp({ render: () => h('main', {class:'min-h-screen bg-bg-surface p-4 text-text-main'}, [h(About, {formData:{}}), useConfirmStore().isVisible ? h(Confirm) : null]) })
app.use(createPinia()); app.use(Toast); app.directive('tooltip',vTooltip)
await setLocale('zh-CN')
window.app = useAppStore(); window.confirms = useConfirmStore()
useStartupStore().run = async ({setupEventListeners}) => setupEventListeners()
await window.app.initialize()
window.app.appVersion = '1.0.0'
app.mount('#app')
window.ready = true
`
const server = await createServer({
  root: process.cwd(), cacheDir: 'node_modules/.vite-tests/software-update', server: { host: '127.0.0.1', port: 5187, strictPort: false },
  plugins: [{ name: 'software-update-browser-check',
    resolveId: id => id === '/__update.js' ? '\0software-update-check' : undefined,
    load: id => id === '\0software-update-check' ? entry : undefined,
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url !== '/__update') return next()
        res.setHeader('Content-Type', 'text/html; charset=utf-8')
        res.end('<div id="app"></div><script type="module" src="/__update.js"></script>')
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
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__update`)
  await page.waitForFunction(() => window.ready)
  await page.getByRole('button', { name: '检查更新', exact: true }).click()
  await page.waitForFunction(() => window.confirms.isVisible)
  assert.equal(await page.evaluate(() => window.confirms.state.promptItems.length), 1)
  assert.equal(await page.evaluate(() => window.app.updateState.isChecking), false)
  const dialog = page.getByRole('dialog')
  await dialog.locator('.prompt-description-rich h2').filter({ hasText: /What.s Changed/ }).waitFor({ timeout: 5000 })
  await dialog.locator('.prompt-description-rich h3').first().waitFor()
  assert.ok(await dialog.locator('.prompt-description-rich ol li').count() > 0)
  await dialog.getByText('来源详情', { exact: true }).click()
  await dialog.getByText('发现新版本 v1.2.3 · 通过内置镜像读取', { exact: true }).waitFor()
  await dialog.getByText('下载来源', { exact: true }).waitFor()
  await dialog.getByText('下载来源', { exact: true }).click()
  assert.equal(await page.getByRole('button', { name: '自动选择（推荐）', exact: true }).count(), 1)
  assert.equal(await page.getByRole('button', { name: 'SourceForge', exact: true }).count(), 1)
  assert.equal(await page.getByRole('button', { name: 'GitHub', exact: true }).count(), 1)
  // 必须实际命中选项，元素存在并不能证明没有被确认弹窗遮挡。
  await page.getByRole('button', { name: 'GitHub', exact: true }).click()
  assert.equal(await page.evaluate(() => window.confirms.state.actionSelector.value), 'https://github.example/app.zip')
  assert.equal(await page.evaluate(() => window.confirms.isVisible), true)
  await dialog.getByText('下载来源', { exact: true }).click()
  await page.keyboard.press('Escape')
  assert.equal(await page.evaluate(() => window.confirms.isVisible), true)
  await dialog.getByText('下载来源', { exact: true }).click()
  await page.getByRole('button', { name: '自动选择（推荐）', exact: true }).click()
  await dialog.getByRole('button', { name: '下载更新', exact: true }).waitFor()
  if (process.env.UPDATE_SCREENSHOT_DIR) {
    await mkdir(process.env.UPDATE_SCREENSHOT_DIR, { recursive: true })
    await dialog.locator('.overflow-y-auto').last().evaluate(el => { el.scrollTop = 0 })
    await dialog.getByText('下载来源', { exact: true }).click()
    await page.getByRole('button', { name: 'GitHub', exact: true }).waitFor()
    await page.screenshot({ path: `${process.env.UPDATE_SCREENSHOT_DIR}/software-update-desktop.png`, animations: 'disabled' })
    await page.keyboard.press('Escape')
  }
  await page.getByRole('button', { name: '以后再说', exact: true }).click()
  await page.getByRole('button', { name: '查看更新', exact: true }).click()
  await page.getByRole('button', { name: '以后再说', exact: true }).click()
  await page.evaluate(() => {
    window.app.updateState.info.local_status = 'downloading'
    window.dispatchEvent(new CustomEvent('global-progress', {detail: {id:'failed-update', type:'update', status:'failed', metrics:{}}}))
  })
  assert.equal(await page.evaluate(() => window.app.updateState.info.local_status), 'remote')
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('global-progress', {detail: {
    id:'ready-update', type:'update', status:'success', metrics:{ready_to_install:true, version:'1.2.3', path:'F:/updates/app.zip'},
  }})))
  await page.getByText('确认安装更新？', { exact: true }).waitFor()
  await page.getByRole('button', { name: '取消', exact: true }).click()
  assert.equal(await page.evaluate(() => window.app.updateState.info.local_file_path), 'F:/updates/app.zip')
  await page.getByRole('button', { name: '查看更新', exact: true }).click()
  await page.getByRole('button', { name: '立即安装', exact: true }).click()
  await page.getByText('确认安装更新？', { exact: true }).waitFor()
  await page.getByRole('button', { name: '确认安装', exact: true }).click()
  await page.getByText('准备重启', { exact: true }).waitFor()
  await page.getByRole('button', { name: '取消', exact: true }).click()
  assert.deepEqual(await page.evaluate(() => window.triggered), [])
  await page.setViewportSize({ width: 640, height: 600 })
  await page.getByRole('button', { name: '查看更新', exact: true }).click()
  await dialog.getByText('来源详情', { exact: true }).click()
  const bounds = await dialog.boundingBox()
  assert.ok(bounds.y >= 0 && bounds.y + bounds.height <= 601)
  if (process.env.UPDATE_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.UPDATE_SCREENSHOT_DIR}/software-update-small.png` })
  assert.equal(await dialog.locator('.overflow-y-auto').last().evaluate(el => el.scrollWidth <= el.clientWidth + 1), true)
  await page.getByRole('button', { name: '以后再说', exact: true }).click()
  for (const source_name of ['GitHub', 'Gitee', '更新清单', '蓝奏云', '本地缓存']) {
    await page.evaluate(source_name => {
      window.app.updateState.info = {
        ...window.info, source_name, sources: [], local_status: 'remote',
        changelog: '## Markdown 标题\n\n- **加粗条目**\n\n1. 有序条目\n\n<p><em>HTML 内容</em><br>第二行</p>\n\n<script>window.unsafeUpdateNote = true</script>\n\n<a href="javascript:window.unsafeUpdateNote=true" onclick="window.unsafeUpdateNote=true">危险链接</a>',
      }
    }, source_name)
    await page.getByRole('button', { name: '查看更新', exact: true }).click()
    const description = dialog.locator('.prompt-description-rich')
    await description.locator('h2').filter({ hasText: 'Markdown 标题' }).waitFor()
    await description.locator('li strong').filter({ hasText: '加粗条目' }).waitFor()
    await description.locator('p em').filter({ hasText: 'HTML 内容' }).waitFor()
    assert.equal(await description.locator('br').count(), 1)
    assert.equal(await description.locator('ul').evaluate(el => getComputedStyle(el).listStyleType), 'disc')
    assert.equal(await description.locator('ol').evaluate(el => getComputedStyle(el).listStyleType), 'decimal')
    assert.equal(await description.locator('script, [onclick], [href^="javascript:"]').count(), 0)
    assert.equal(await page.evaluate(() => window.unsafeUpdateNote), undefined)
    await page.getByRole('button', { name: '以后再说', exact: true }).click()
  }
  // Mini 确认框的外部点击判定也必须把所属面板算作内部。
  await page.evaluate(() => {
    void window.confirms.open({
      title: 'Mini selector check', mode: 'confirm',
      actionSelector: { label: 'Mini source', value: 'auto', options: [
        { label: 'Mini automatic', value: 'auto' }, { label: 'Mini manual', value: 'manual' },
      ] },
    }, document.querySelector('button'))
  })
  await page.getByRole('dialog', { name: 'Mini selector check' }).getByText('Mini source', { exact: true }).click()
  await page.getByRole('button', { name: 'Mini manual', exact: true }).click()
  assert.equal(await page.evaluate(() => window.confirms.isVisible), true)
  assert.equal(await page.evaluate(() => window.confirms.state.actionSelector.value), 'manual')
  await page.getByRole('button', { name: '取消', exact: true }).click()
  assert.deepEqual(errors, [])
  console.log('Software update browser checks passed: single release, source details, two confirmations, small viewport, Markdown + HTML and sanitization across five sources.')
} finally {
  await browser?.close()
  await server.close()
}
