import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { createServer } from 'vite'

// 复用宿主浏览器，不安装依赖，不连接真实后端或写入用户配置。
const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_MODULE || 'playwright')
const entry = `
import { createApp, defineComponent, h, KeepAlive, reactive, ref } from 'vue'
import { createPinia } from 'pinia'
import Toast from 'vue-toastification'
import CommonSelect from '/src/shared/components/input/CommonSelect.vue'
import CommonModalShell from '/src/shared/components/modal/CommonModalShell.vue'
import FixedPopover from '/src/shared/components/popover/FixedPopover.vue'
import { openPopovers } from '/src/shared/components/popover/popoverContext.js'
import { useAppStore } from '/src/app/stores/appStore.js'
import { setLocale } from '/src/shared/i18n.js'
import '/src/app/styles/style.css'
window.state = reactive({ a: false, b: false, nested: false, value: 'one', page: 'one', move: 0, scale: 1, hidden: false, editable: false, deactivate: false })
window.openPopovers = openPopovers
const options = [{ label: 'One', value: 'one' }, { label: 'Two', value: 'two' }]
const Panel = defineComponent({
  setup() {
    const anchor = ref(null)
    return () => h(CommonModalShell, {
      show: window.state.a, persistent: true, title: 'Panel A', size: 'custom',
      panelClass: 'w-[40rem] h-[30rem]', contentClass: 'overflow-y-auto',
      onClose: () => window.state.a = false,
    }, {
      default: () => h('div', { class: 'p-8', style: { minHeight: '1000px' } }, [
        h('div', { id: 'moving-trigger', style: { transform: 'translateX(' + window.state.move + 'px) scale(' + window.state.scale + ')', transformOrigin: 'left top', display: window.state.hidden ? 'none' : undefined } }, [
          h(CommonSelect, { label: 'Modal choice', modelValue: window.state.value, options, mini: true, popoverZIndex: 100020, editable: window.state.editable,
            'onUpdate:modelValue': value => window.state.value = value }),
        ]),
        h('button', { ref: anchor, id: 'nested-toggle', class: 'mt-8 p-4', onClick: () => window.state.nested = !window.state.nested }, 'Nested panel'),
        h(FixedPopover, { isOpen: window.state.nested, triggerRef: anchor.value, height: 160,
          onRequestClose: () => window.state.nested = false }, { default: () => h('div', { class: 'p-4', style: { width: '300px' } }, [
            h(CommonSelect, { label: 'Nested choice', options, modelValue: window.state.value, mini: true,
              'onUpdate:modelValue': value => window.state.value = value }),
          ]) }),
      ]),
      footer: () => h(CommonSelect, { label: 'Footer choice', modelValue: window.state.value, options, mini: true, showBottom: true,
        'onUpdate:modelValue': value => window.state.value = value }),
    })
  },
})
const app = createApp({render: () => [
  h('main', { class: 'h-screen bg-bg-surface p-8 text-text-main' }, [
    h(CommonSelect, { label: 'Page choice', modelValue: window.state.page, options, mini: true,
      'onUpdate:modelValue': value => window.state.page = value }),
    h('button', { id: 'page-button' }, 'Page action'),
  ]),
  h(KeepAlive, null, { default: () => window.state.deactivate ? null : h(Panel) }),
  h(CommonModalShell, { show: window.state.b, title: 'Panel B', size: 'custom', panelClass: 'w-[40rem] h-[30rem]', onClose: () => window.state.b = false },
    {default: () => h('button', {id:'top-action', class:'p-12'}, 'Top action')}),
]})
app.use(createPinia()); app.use(Toast); app.directive('tooltip', {})
await setLocale('en')
useAppStore().uiScale = 1
app.mount('#app')
window.ready = true
`
const server = await createServer({
  root: process.cwd(), cacheDir: 'node_modules/.vite-tests/popover', server: { host: '127.0.0.1', port: 5188, strictPort: false },
  plugins: [{ name: 'popover-browser-check',
    resolveId: id => id === '/__popover.js' ? '\0popover-check' : undefined,
    load: id => id === '\0popover-check' ? entry : undefined,
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (req.url !== '/__popover') return next()
        res.setHeader('Content-Type', 'text/html; charset=utf-8')
        res.end('<div id="app"></div><script type="module" src="/__popover.js"></script>')
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
  await page.goto(`http://127.0.0.1:${server.httpServer.address().port}/__popover`)
  await page.waitForFunction(() => window.ready)
  const a = page.getByRole('dialog', { name: 'Panel A', exact: true })
  const popup = page.locator('[data-fixed-popover]')
  const two = page.getByRole('button', { name: 'Two', exact: true })
  const one = page.getByRole('button', { name: 'One', exact: true })
  const openA = async () => {
    await page.evaluate(() => { window.state.a = true })
    await a.waitFor()
    await a.getByText('Modal choice', { exact: true }).click()
    await two.waitFor()
  }
  const assertAligned = async () => {
    await page.waitForFunction(() => {
      const input = document.querySelector('#moving-trigger input')?.getBoundingClientRect()
      const menu = document.querySelector('[data-fixed-popover]')?.getBoundingClientRect()
      return input && menu && Math.abs(menu.left - input.left) < 2 && Math.abs(menu.top - input.bottom - 8) < 2
    })
  }

  // 页面面板必须在随后打开的弹窗之下，不能抢占顶层弹窗的 Esc。
  await page.getByText('Page choice', { exact: true }).click()
  await two.click()
  assert.equal(await page.evaluate(() => window.state.page), 'two')
  await page.getByText('Page choice', { exact: true }).click()
  await page.evaluate(() => { window.state.b = true })
  await page.locator('#top-action').click()
  await page.keyboard.press('Escape')
  await page.waitForFunction(() => !window.state.b)

  await openA()
  assert.equal(await popup.evaluate(el => !!el.closest('[data-popover-scope]')), true)
  await two.click()
  assert.equal(await page.evaluate(() => window.state.value), 'two')
  await a.getByText('Modal choice', { exact: true }).click()
  await a.locator('#moving-trigger input').press('ArrowUp')
  await a.locator('#moving-trigger input').press('Enter')
  assert.equal(await page.evaluate(() => window.state.a), true)

  await a.getByText('Modal choice', { exact: true }).click()
  await assertAligned()
  await page.evaluate(() => { window.state.move = 70; window.state.scale = 0.9 })
  await assertAligned()
  await page.evaluate(() => { window.state.move = 0; window.state.scale = 1 })
  await assertAligned()
  // 纯布局移动与父级平移/缩放，不依赖 resize/scroll 事件。
  await a.evaluate(el => { el.style.transform = 'translate(35px, 25px) scale(0.9)' })
  await page.waitForFunction(() => {
    const trigger = document.querySelector('#moving-trigger input').getBoundingClientRect()
    const menu = document.querySelector('[data-fixed-popover]').getBoundingClientRect()
    return Math.abs(trigger.left - menu.left) < 2
  })
  await a.evaluate(el => { el.style.transform = '' })
  await assertAligned()
  await a.evaluate(el => { el.closest('[data-popover-scope]').style.transform = 'translate(20px, 15px) scale(0.9)' })
  await assertAligned()
  await a.evaluate(el => { el.closest('[data-popover-scope]').style.transform = '' })
  await assertAligned()
  await page.keyboard.press('Escape')
  await page.waitForFunction(() => !document.querySelector('[data-fixed-popover]'))
  assert.equal(await page.evaluate(() => window.state.a), true)

  // 同层后开的弹窗必须盖住旧面板，即使旧面板传入极高的局部值。
  await a.getByText('Modal choice', { exact: true }).click()
  const oldBox = await two.boundingBox()
  await page.evaluate(() => { window.state.b = true })
  await page.waitForFunction(({x,y}) => !document.elementFromPoint(x,y)?.closest('[data-fixed-popover]'), { x: oldBox.x + 5, y: oldBox.y + 5 })
  await page.locator('#top-action').focus()
  await page.keyboard.press('Escape')
  await page.waitForFunction(() => !window.state.b)
  await page.getByRole('dialog', { name: 'Panel B', exact: true }).waitFor({ state: 'hidden' })
  assert.equal(await page.evaluate(() => window.state.a), true)
  await page.keyboard.press('Escape')
  await page.waitForFunction(() => !document.querySelector('[data-fixed-popover]'))
  assert.equal(await page.evaluate(() => window.state.a), true)

  // 子面板挂在父面板内；点击子选项不能被当成父面板外部点击。
  await page.locator('#nested-toggle').click()
  await page.waitForFunction(() => document.querySelector('[data-fixed-popover]')?.getBoundingClientRect().width >= 295, null, { timeout: 2000 })
  await page.getByText('Nested choice', { exact: true }).click()
  await one.click()
  assert.equal(await page.evaluate(() => window.state.nested), true)
  assert.equal(await page.evaluate(() => window.state.value), 'one')
  await page.getByText('Nested choice', { exact: true }).click()
  await page.keyboard.press('Escape')
  assert.equal(await page.evaluate(() => window.state.nested), true)
  await page.keyboard.press('Escape')
  await page.waitForFunction(() => !window.state.nested)
  assert.equal(await page.evaluate(() => window.state.a), true)
  await page.waitForFunction(() => !document.querySelector('[data-fixed-popover]'))

  // 保留挂载的父弹窗隐藏后，不能遗留面板、监听器或下次重开的旧展开状态。
  await a.getByText('Modal choice', { exact: true }).click()
  await page.evaluate(() => { window.state.a = false })
  await page.waitForFunction(() => !document.querySelector('[data-fixed-popover]'))
  await page.waitForFunction(() => window.openPopovers.length === 0)
  await page.evaluate(() => { window.state.a = true })
  await a.waitFor()
  assert.equal(await popup.count(), 0)
  await a.getByText('Modal choice', { exact: true }).click()
  await page.evaluate(() => { window.state.hidden = true })
  await page.waitForFunction(() => !document.querySelector('[data-fixed-popover]'))
  await page.evaluate(() => { window.state.hidden = false })
  await a.getByText('Modal choice', { exact: true }).click()
  await a.locator('.overflow-y-auto').first().evaluate(el => { el.scrollTop = 500 })
  await page.waitForFunction(() => !document.querySelector('[data-fixed-popover]'))
  await a.locator('.overflow-y-auto').first().evaluate(el => { el.scrollTop = 0 })

  await page.setViewportSize({ width: 640, height: 520 })
  await a.getByText('Modal choice', { exact: true }).click()
  await two.waitFor()
  const box = await popup.boundingBox()
  const panel = await a.boundingBox()
  assert.ok(box.x >= Math.max(0, panel.x) && box.x + box.width <= Math.min(640, panel.x + panel.width) + 1)
  assert.ok(box.y >= Math.max(0, panel.y) && box.y + box.height <= Math.min(520, panel.y + panel.height) + 1)
  await two.click()
  await page.waitForFunction(() => !document.querySelector('[data-fixed-popover]'))
  await a.getByText('Footer choice', { exact: true }).click()
  assert.ok((await popup.boundingBox()).height >= 48, 'footer menu must have usable height, not a clipped sliver')
  await one.click({ timeout: 2000 })
  assert.equal(await page.evaluate(() => window.state.value), 'one')
  await page.waitForFunction(() => !document.querySelector('[data-fixed-popover]'))
  await page.evaluate(() => { window.state.editable = true })
  await a.getByText('Modal choice', { exact: true }).click()
  await a.locator('#moving-trigger input').fill('uncommitted draft')
  await page.evaluate(() => { window.state.a = false })
  await page.waitForFunction(() => window.openPopovers.length === 0)
  assert.equal(await page.evaluate(() => window.state.value), 'one', 'hiding the owner must not submit an editable draft')
  await page.waitForFunction(() => !document.querySelector('[data-fixed-popover]'))
  await page.evaluate(() => { window.state.a = true; window.state.editable = false })
  await a.getByText('Modal choice', { exact: true }).click()
  await page.evaluate(() => { window.state.deactivate = true })
  await page.waitForFunction(() => window.openPopovers.length === 0)
  await page.evaluate(() => { window.state.deactivate = false })
  await a.waitFor()
  await page.waitForFunction(() => !document.querySelector('[data-fixed-popover]'))
  await page.evaluate(() => { window.state.a = false })
  assert.deepEqual(errors, [])
  console.log('Popover browser checks passed: actual clicks, page/modal ordering, same-layer modal, nested selects, Escape/Enter, layout/transform following, hidden/scroll cleanup and small viewport.')
} finally {
  await browser?.close()
  await server.close()
}
