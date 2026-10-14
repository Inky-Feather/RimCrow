import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'

// 执行组件中的实际函数，省去挂载整套应用和 pywebview。
function componentFunctions(path, names, context) {
  const { descriptor } = parse(readFileSync(new URL(path, import.meta.url), 'utf8'))
  const { scriptSetupAst } = compileScript(descriptor, { id: path })
  const declarations = scriptSetupAst.filter(node => node.type === 'VariableDeclaration'
    && node.declarations.some(declaration => names.includes(declaration.id.name)))
  assert.equal(declarations.length, names.length)
  const code = declarations.map(node => descriptor.scriptSetup.content.slice(node.start, node.end)).join('\n')
  return runInNewContext(`${code}\n;({ ${names.join(', ')} })`, context)
}

const calls = []
const resolvedLinks = new Map([
  ['https://github.com/author/mod/tree/rimworld-1.6', ['https://github.com/author/mod', 'rimworld-1.6']],
  ['https://github.com/author/mod/tree/feature/rimworld?tab=readme', ['https://github.com/author/mod', 'feature/rimworld']],
  ['https://github.com/author/mod/tree/old', ['https://github.com/author/mod', 'old']],
  ['https://gitgud.io/team/mod/-/tree/dev/About', ['https://gitgud.io/team/mod', 'dev']],
])
const context = {
  newRepoUrl: { value: '' }, newRepoBranch: { value: '' }, isParsing: { value: false },
  newInstallOptions: { value: { ref_type: 'branch', asset_name: '', source_subpath: '' } },
  repoQuerySeq: { value: 0 },
  previewReadme: { value: {} }, selectedCatalogItem: { value: null },
  workspaceStore: { github: {}, fetchGithubRepos() {} },
  t: (_key, fallback) => fallback, checkResult: result => result.status === 'success',
  toast: { success() {} },
  loadRepoReadme: async (url, branch) => calls.push(['readme', url, branch]),
  window: { pywebview: { api: {
    github_fetch_info: async (url, branch) => {
      calls.push(['info', url, branch])
      const [repoUrl, linkBranch] = resolvedLinks.get(url) || [url, 'main']
      return { status: 'success', data: { repo_url: repoUrl, owner: 'author', repo: 'mod', default_branch: 'main', latest_source_branch: branch || linkBranch, source_status: 'available' } }
    },
    github_subscribe: async payload => {
      calls.push(['subscribe', payload])
      return { status: 'success' }
    },
  } } },
}
const github = componentFunctions('../src/features/workspace/views/GithubCommand.vue', ['parseNewRepo', 'confirmSubscribe'], context)
for (const [url, explicitBranch, expectedBranch] of [
  ['https://github.com/author/mod/tree/rimworld-1.6', '', 'rimworld-1.6'],
  ['https://github.com/author/mod/tree/feature/rimworld?tab=readme', '', 'feature/rimworld'],
  ['https://github.com/author/mod/tree/old', 'rimworld-1.7', 'rimworld-1.7'],
  ['https://github.com/author/mod', '', 'main'],
  ['https://gitgud.io/team/mod/-/tree/dev/About', '', 'dev'],
]) {
  calls.length = 0
  context.newRepoUrl.value = url
  context.newRepoBranch.value = explicitBranch
  await github.parseNewRepo()
  const expectedUrl = resolvedLinks.get(url)?.[0] || url
  assert.equal(calls[0][1], url)
  assert.equal(calls[0][2], explicitBranch)
  assert.equal(calls[1][2], expectedBranch)
  await github.confirmSubscribe('source')
  assert.equal(calls[2][1].url, expectedUrl)
  assert.equal(calls[2][1].default_branch, expectedBranch)
}

const branchContext = {
  ...context,
  isChecking: { value: false }, isDetectingBranches: { value: false },
  repoBranches: { value: {} }, activeRepoBranch: { value: 'feature/1.7' },
  activeInstallOptions: { value: { ref_type: 'branch', asset_name: '', source_subpath: '' } },
  confirmStore: { open: async () => true },
  workspaceStore: {
    github: { activeRepo: { repo_url: 'https://github.com/author/mod', target_branch: 'main', repo_name: 'mod', owner: 'author', install_type: 'source' } },
    fetchGithubRepos: async () => calls.push(['refresh']),
    startGithubTimelinePolling: url => calls.push(['poll', url]),
  },
}
branchContext.window = { pywebview: { api: {
  ...context.window.pywebview.api,
  github_fetch_branches: async url => ({ status: 'success', data: { repo_url: url, branches: ['main', 'feature/1.7'] } }),
} } }
const branchControls = componentFunctions('../src/features/workspace/views/GithubCommand.vue', ['branchOptions', 'handleDetectBranches', 'handleSwitchBranch'], branchContext)
calls.length = 0
await branchControls.handleDetectBranches(true)
assert.equal(branchControls.branchOptions('https://github.com/author/mod')[1].value, 'feature/1.7')
assert.equal(branchControls.branchOptions('https://github.com/author/mod', 'tag').length, 0)
await branchControls.handleSwitchBranch()
assert.equal(calls.find(call => call[0] === 'subscribe')[1].default_branch, 'feature/1.7')
assert.equal(calls.find(call => call[0] === 'subscribe')[1].installed_version, undefined)
assert.equal(branchContext.isChecking.value, false)

calls.length = 0
branchContext.confirmStore.open = async () => false
await branchControls.handleSwitchBranch()
assert.equal(calls.length, 0)

calls.length = 0
branchContext.confirmStore.open = async () => true
branchContext.toast.error = message => calls.push(['error', message])
branchContext.window.pywebview.api.github_fetch_info = async () => ({ status: 'success', data: { source_status: 'missing' } })
await branchControls.handleSwitchBranch()
assert.equal(calls.some(call => call[0] === 'subscribe'), false)
assert.equal(calls[0][0], 'error')

const dragContext = {
  DRAG_THRESHOLD: 4,
  dragState: { active: true, moved: false, startX: 0, startY: 0, offsetX: 0, offsetY: 0 },
  dragOffset: { value: { x: 0, y: 0 } }, isPanelOpen: { value: false },
  rootRef: { value: {
    getBoundingClientRect: () => ({ left: 780, top: 76, width: 200, height: 32 }),
    parentElement: { getBoundingClientRect: () => ({ left: 4, right: 996, top: 64, bottom: 796 }) },
  } },
}
const guide = componentFunctions('../src/features/guide/GuideCenter.vue', ['handlePointerMove'], dragContext)
guide.handlePointerMove({ clientX: -10000, clientY: -10000 })
assert.equal(dragContext.dragOffset.value.x, -776)
assert.equal(dragContext.dragOffset.value.y, -12)
dragContext.dragOffset.value = { x: 0, y: 0 }
guide.handlePointerMove({ clientX: 10000, clientY: 10000 })
assert.equal(dragContext.dragOffset.value.x, 16)
assert.equal(dragContext.dragOffset.value.y, 688)
console.log('Git branch selection and guide drag bounds passed')
