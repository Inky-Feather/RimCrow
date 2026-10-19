import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import vm from 'node:vm'

const require = createRequire(new URL('../package.json', import.meta.url))
const { computed, ref, reactive, watch, effectScope, nextTick } = require('vue')
const source = readFileSync(new URL('../src/features/settings/panel/SettingsNetworkTab.vue', import.meta.url), 'utf8')

// 镜像草稿校验与保存。
{
  const controls = source.slice(source.indexOf('const githubMirrorCatalog ='), source.indexOf('const hostsState ='))
  const props = reactive({ formData: { github_mirrors: [], github_mirror_id: 'direct', github_dynamic_mirrors_enabled: true, _github_mirrors_path: 'data/github_mirrors.json' } })
  let openedPath = ''
  let errors = 0
  const context = vm.createContext({ ref, reactive, computed, watch, onMounted: () => {}, props, URL, t: (_key, fallback) => fallback,
    toast: { error: () => { errors += 1 } },
    window: { pywebview: { api: {
      github_probe_mirror: async ({ url_template }) => ({ status: 'success', data: {
        support: {
          web: { status: 'supported' }, raw: { status: 'supported' }, archive: { status: 'supported' },
          release_asset: { status: 'unknown' },
        },
        probed_url_template: url_template,
        probed_at: 1,
      } }),
      path_open_file: async path => { openedPath = path; return { status: 'success' } },
    } } },
  })
  vm.runInContext(controls + '\nglobalThis.controls = { githubMirrorOptions, mirrorDraft, mirrorError, handleEditMirror, handleApplyMirror, handleRemoveMirror, handleOpenMirrorsFile }', context)
  const ui = context.controls
  props.formData.github_mirrors = [
    { id: 'preset', label: 'GH-Proxy', support: { web: { status: 'supported' }, raw: { status: 'supported' }, archive: { status: 'supported' }, release_asset: { status: 'supported' } } },
    { id: 'probed', label: 'Custom', support: {
      web: { status: 'supported' }, raw: { status: 'supported' }, archive: { status: 'unsupported' }, release_asset: { status: 'unknown' },
    } },
  ]
  assert.equal(ui.githubMirrorOptions.value[0].label, 'GitHub 直连')
  assert.equal(ui.githubMirrorOptions.value[1].label, '自动选择镜像')
  props.formData.github_mirrors = []
  ui.handleEditMirror()
  Object.assign(ui.mirrorDraft.value, { id: 'custom', label: 'Custom', url_template: 'https://example.org/{url}' })
  assert.equal(props.formData.github_mirrors.length, 0, '弹窗草稿不能提前修改设置')
  await ui.handleApplyMirror()
  assert.equal(props.formData.github_mirror_id, 'custom:custom')
  assert.equal(props.formData.github_mirrors.length, 1)
  const original = props.formData.github_mirrors[0]
  ui.handleEditMirror(original)
  ui.mirrorDraft.value.label = 'Edited'
  assert.equal(original.label, 'Custom')
  ui.mirrorDraft.value.id = 'renamed'
  await ui.handleApplyMirror()
  assert.equal(props.formData.github_mirror_id, 'custom:renamed')
  assert.equal(props.formData.github_mirrors[0].label, 'Edited')

  for (const override of [
    { id: 'renamed' }, { id: 'direct' }, { url_template: 'http://example.org/{url}' },
    { url_template: 'https://example.org/{url}/{url}' },
  ]) {
    ui.handleEditMirror()
    Object.assign(ui.mirrorDraft.value, { id: 'new', label: 'New', url_template: 'https://example.org/{url}', ...override })
    await ui.handleApplyMirror()
    assert.ok(ui.mirrorError.value, '无效定义应给出错误')
    assert.equal(props.formData.github_mirrors.length, 1)
  }
  await ui.handleOpenMirrorsFile()
  assert.equal(openedPath, 'data/github_mirrors.json')
  context.window.pywebview.api.path_open_file = async () => ({ status: 'error' })
  await ui.handleOpenMirrorsFile()
  assert.equal(errors, 1)
  ui.handleRemoveMirror()
  assert.equal(props.formData.github_mirrors.length, 0)
  assert.equal(props.formData.github_mirror_id, 'direct')
  console.log('GitHub 镜像编辑交互测试通过。')
}

// 动态 Hosts 预览与系统写入状态。
{
  // 直接运行组件的状态监听器，验证交互时是否真正发起获取请求。
  const watcher = source.slice(source.indexOf('const hostsState ='), source.indexOf('const secretStatus ='))
  const sourceUrl = 'https://example.invalid/hosts'
  const props = reactive({ formData: { network: { github_hosts_enabled: false, hosts_sources: [{ url: sourceUrl, enabled: true }] } } })
  const timers = new Map()
  let timerId = 0
  let fetchCount = 0
  let cancelCount = 0
  let systemRetryCount = 0
  let status = {
    status: 'idle', source_url: sourceUrl, dynamic_hosts: { 'saved.example': '1.1.1.1' }, effective_hosts: { 'saved.example': '1.1.1.1' }, can_refresh: false,
    preview: { status: 'idle', source_url: '', hosts: {}, source_errors: [] },
  }
  const api = {
    network_refresh_github_hosts: async (network) => {
      assert.deepEqual(JSON.parse(JSON.stringify(network.hosts_sources)), JSON.parse(JSON.stringify(props.formData.network.hosts_sources)))
      if (!network.github_hosts_enabled) {
        cancelCount += 1
        status = { ...status, status: 'idle', preview: { ...status.preview, status: 'idle', source_url: '', hosts: {} } }
        return { status: 'success', data: status }
      }
      fetchCount += 1
      const previewSource = [...new Set(network.hosts_sources.filter(row => row.enabled).map(row => row.url.trim()).filter(Boolean))].join('\n')
      status = { ...status, status: 'ready', error: '', preview: { ...status.preview, status: 'loading', source_url: previewSource, error: '', hosts: {} } }
      return { status: 'success', data: status }
    },
    network_github_hosts_status: async () => ({ status: 'success', data: status }),
    network_apply_system_hosts: async (...args) => {
      assert.equal(args.length, 0, '系统重试不能把未保存的表单值提交给后端')
      systemRetryCount += 1
      status = { ...status, system_hosts: { status: 'authorizing' } }
      return { status: 'success', data: status }
    },
  }
  const context = vm.createContext({ computed, ref, watch, props, window: { pywebview: { api } },
    setTimeout: fn => { timers.set(++timerId, fn); return timerId },
    clearTimeout: id => timers.delete(id),
  })
  let scope = effectScope()
  const mount = () => scope.run(() => vm.runInContext('(() => { ' + watcher + '\nglobalThis.controls = { hostsState, hostsRetry, systemHostsRetry } })()', context))
  const settle = async () => { await nextTick(); await new Promise(resolve => setImmediate(resolve)); await nextTick() }
  const tick = async () => { const [id, fn] = timers.entries().next().value; timers.delete(id); await fn(); await settle() }

  try {
    mount()
    await settle()
    props.formData.network.github_hosts_enabled = true
    await settle()
    assert.equal(fetchCount, 1, '开启开关应立即按未保存的表单获取')
    assert.equal(context.controls.hostsState.value.status, 'loading')
    assert.equal(timers.size, 1)
    status = { ...status, status: 'ready', is_applied: true, preview: { ...status.preview, status: 'ready', source_url: sourceUrl, hosts: { 'preview.example': '2.2.2.2' } } }
    await tick()
    assert.equal(context.controls.hostsState.value.status, 'ready')
    assert.equal(context.controls.hostsState.value.is_applied, true)
    assert.deepEqual(context.controls.hostsState.value.hosts, { 'preview.example': '2.2.2.2' })
    assert.deepEqual(context.controls.hostsState.value.dynamic_hosts, { 'saved.example': '1.1.1.1' })
    assert.equal(timers.size, 0, '获取完成后不应继续每秒轮询状态')
    scope.stop()

    status = { ...status, status: 'loading', can_refresh: true, preview: { ...status.preview, status: 'loading', source_url: sourceUrl } }
    scope = effectScope()
    mount()
    await settle()
    assert.equal(fetchCount, 1, '打开页面不得额外触发下载')
    assert.equal(context.controls.hostsState.value.status, 'loading')
    status = { ...status, status: 'error', error: 'timeout', preview: { ...status.preview, status: 'error', source_url: sourceUrl, error: 'timeout' } }
    await tick()
    assert.equal(context.controls.hostsState.value.error, 'timeout')
    context.controls.hostsRetry.value += 1
    await settle()
    assert.equal(fetchCount, 2, '手动重试应发起一次下载')
    status = { ...status, status: 'ready', is_applied: true, preview: { ...status.preview, status: 'ready', source_url: sourceUrl } }
    await tick()
    assert.equal(context.controls.hostsState.value.status, 'ready')
    assert.equal(timers.size, 0)

    props.formData.network.hosts_sources = [{ url: 'https://other.example/hosts', enabled: true }, { url: 'https://second.example/hosts.json', enabled: false }]
    await settle()
    assert.equal(fetchCount, 3, '来源变更应获取新来源')
    assert.equal(context.controls.hostsState.value.status, 'loading')
    props.formData.network.hosts_sources[1].url = 'https://edited.example/hosts'
    await settle()
    assert.equal(fetchCount, 3, '编辑停用来源不得触发获取')
    props.formData.network.hosts_sources[1].enabled = true
    await settle()
    assert.equal(fetchCount, 4, '启用单个来源应获取更新后的列表')
    props.formData.network.hosts_sources.splice(0, 1)
    await settle()
    assert.equal(fetchCount, 5, '删除启用来源应重新获取并移除旧来源')
    props.formData.network.github_hosts_enabled = false
    await settle()
    assert.equal(fetchCount, 5, '关闭开关不得触发下载')
    assert.equal(cancelCount, 1, '关闭开关应取消旧结果提交')
    assert.equal(context.controls.hostsState.value.status, 'idle')
    assert.deepEqual(Object.keys(props.formData.network).sort(), ['github_hosts_enabled', 'hosts_sources'])
    scope.stop()
    assert.equal(timers.size, 0)

    // 系统写入与动态来源获取独立，即使关闭动态 Hosts 也要显示系统操作结果。
    status = { ...status, system_hosts: { status: 'applying' } }
    scope = effectScope()
    mount()
    await settle()
    assert.equal(context.controls.hostsState.value.system_hosts.status, 'applying')
    assert.equal(timers.size, 1)
    status = { ...status, system_hosts: { status: 'authorizing' } }
    await tick()
    assert.equal(context.controls.hostsState.value.system_hosts.status, 'authorizing')
    assert.equal(timers.size, 1, '等待授权期间应继续查询系统状态')
    status = { ...status, system_hosts: { status: 'error', error_code: 'NETWORK.HOSTS.PERMISSION_DENIED' } }
    await tick()
    assert.equal(context.controls.hostsState.value.system_hosts.status, 'error')
    assert.equal(timers.size, 0)
    const previousFetchCount = fetchCount
    context.controls.systemHostsRetry.value += 1
    await settle()
    assert.equal(systemRetryCount, 1)
    assert.equal(fetchCount, previousFetchCount, '系统写入重试不应重新下载或应用预览 Hosts')
    status = { ...status, system_hosts: { status: 'removed' } }
    await tick()
    assert.equal(timers.size, 0)
    scope.stop()

    let releaseStatus
    let requests = 0
    api.network_github_hosts_status = () => {
      requests += 1
      return new Promise(resolve => { releaseStatus = () => resolve({ status: 'success', data: status }) })
    }
    scope = effectScope()
    mount()
    await settle()
    assert.equal(requests, 1)
    props.formData.network.proxy = { enabled: true }
    await settle()
    assert.equal(requests, 1, '前一次状态请求未返回时不得叠加查询')
    scope.stop()
    releaseStatus()
    await settle()
    assert.equal(requests, 1, '卸载后不得执行排队的旧查询')
  } finally {
    scope.stop()
  }

  const toolsStart = source.indexOf('<section aria-labelledby="network-community-tools-title"')
  assert.ok(toolsStart >= 0)
  const toolsTemplate = source.slice(toolsStart, source.indexOf('</section>', toolsStart) + '</section>'.length)
  const openedUrls = []
  const renderTools = require('vue').compile(toolsTemplate, { isCustomElement: tag => tag === 'ExternalLink' })
  const tools = renderTools({ t: (_key, fallback) => fallback, appStore: { openUrl: url => openedUrls.push(url) } }, [])
  const links = []
  const visit = node => {
    if (node?.type === 'a') links.push(node)
    if (Array.isArray(node?.children)) node.children.forEach(visit)
  }
  visit(tools)
  assert.deepEqual(links.map(link => link.props.href), ['https://steampp.net/', 'https://www.dogfight360.com/blog/18682/'])
  for (const link of links) {
    assert.equal(link.props.target, '_blank')
    assert.equal(link.props.rel, 'noopener noreferrer')
    let prevented = false
    link.props.onClick({ preventDefault: () => { prevented = true } })
    assert.ok(prevented, '卡片点击应使用已有的网址打开逻辑，不能替换设置页面')
  }
  assert.deepEqual(openedUrls, links.map(link => link.props.href))
  console.log('动态 Hosts 界面状态测试通过。')
}
