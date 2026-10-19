<template>
  <div class="min-h-0 flex-1 flex flex-col gap-4" data-tour="workspace-github-workspace">
    <div class="shrink-0 flex items-center gap-3 shadow-lg" data-tour="workspace-github-input">
      <div class="min-w-0 flex-1 relative">
        <Link class="absolute left-4 top-1/2 -translate-y-1/2 size-4 text-text-dim" />
        <input v-model="repoUrl" @keydown.enter="parseRepo" :disabled="state.isLoading"
          v-tooltip="t('ui.workspace.github.input.supported_tooltip', '支持以下仓库：GitHub、GitLab、GitGud。')"
          :placeholder="t('ui.workspace.github.input.placeholder', '粘贴公开 Git 仓库地址 如: https://github.com/user/repo (支持 GitHub / GitLab / GitGud)')"
          class="w-full bg-bg-inset border border-border-base/10 rounded-xl pl-10 pr-4 py-2.5 text-sm text-text-main outline-none focus:border-border-base/18 transition-all" />
      </div>
      <button @click="parseRepo" :disabled="state.isLoading || !repoUrl.trim()"
        class="shrink-0 px-4 py-2 bg-bg-overlay/10 text-text-main hover:bg-bg-contrast hover:text-text-inverse border border-border-base/18 rounded-lg text-sm font-black transition-all disabled:opacity-50 flex items-center gap-2">
        <RefreshCw v-if="state.isLoading" class="size-4 animate-spin" />
        <Search v-else class="size-4" />
        {{ t('ui.workspace.github.input.parse', '解析地址') }}
      </button>
    </div>

    <div v-if="activeRepo" class="shrink-0 w-fit flex gap-2 -mb-2 p-1 bg-bg-inset/80 rounded-xl border border-border-base/10">
      <button @click="viewMode = 'local'" class="px-2 py-1 rounded-lg text-xs font-bold" :class="viewMode === 'local' ? 'bg-bg-contrast text-text-inverse' : 'bg-bg-overlay/10 text-text-dim'">{{ t('ui.workspace.github.local.tab', '本地信息') }}</button>
      <button @click="viewMode = 'remote'" class="px-2 py-1 rounded-lg text-xs font-bold" :class="viewMode === 'remote' ? 'bg-bg-contrast text-text-inverse' : 'bg-bg-overlay/10 text-text-dim'">{{ t('ui.workspace.github.remote.tab', '仓库解析') }}</button>
    </div>

    <div v-if="activeRepo && viewMode === 'local'" class="min-h-0 flex-1 overflow-y-auto custom-scrollbar pr-1 space-y-4">
      <section class="bg-bg-inset/70 border border-border-base/10 rounded-2xl p-5 shadow-xl">
        <div class="flex items-start justify-between gap-4">
          <div class="min-w-0">
            <h2 class="text-2xl font-black text-text-main truncate">{{ activeRepo.repo_name || activeRepo.repo }}</h2>
            <p class="mt-2 text-sm text-text-dim truncate">{{ activeRepo.repo_url }}</p>
          </div>
          <WorkshopItemActions v-if="localRepoActions.length" custom-only size="sm" :before-actions="localRepoActions" />
        </div>
        <div class="mt-4 flex flex-wrap gap-3 text-xs">
          <div><div class="text-text-dim">{{ t('ui.workspace.github.detail.install_type', '部署来源') }}</div><div class="mt-1 text-text-main">{{ formatInstallType(activeRepo.install_type) }}</div></div>
          <div><div class="text-text-dim">{{ t('ui.workspace.github.branch.label', '分支') }}</div><div class="mt-1 text-text-main truncate">{{ activeRepo.target_branch || '-' }}</div></div>
          <div><div class="text-text-dim">{{ t('ui.workspace.github.detail.version', '本地版本') }}</div><div class="mt-1 text-text-main truncate">{{ activeRepo.installed_version || '-' }}</div></div>
          <div><div class="text-text-dim">{{ t('ui.workspace.github.local.status', '更新状态') }}</div><div class="mt-1" :class="activeRepoStatus?.tone">{{ activeRepoStatus?.label || '-' }}</div></div>
        </div>
        <div v-if="activeRepo.local_path || activeRepo.local_folder" class="mt-4 text-xs text-text-dim break-all">{{ activeRepo.local_path || activeRepo.local_folder }}</div>
      </section>
      <section class="bg-bg-inset/70 border border-border-base/10 rounded-2xl p-5 shadow-xl">
        <h4 class="text-xs font-bold text-text-dim tracking-widest mb-5 flex items-center gap-2"><Activity class="size-4" />{{ t('ui.workspace.github.active.local_audit_log', '本地执行追踪 (Local Audit Log)') }}</h4>
        <div v-if="workspaceStore.github.repoTimelines.length" class="relative pl-4">
          <div class="absolute left-0.5 top-2 bottom-0 w-px bg-linear-to-b from-text-main/30 to-transparent"></div>
          <div v-for="(log, index) in workspaceStore.github.repoTimelines" :key="index" class="mb-5 relative">
            <div class="absolute -left-[1.2rem] top-1.5 size-3 rounded-full border-2 bg-bg-deep z-10" :class="getLogColor(log.type)"></div>
            <div class="flex items-center gap-2"><span class="text-xs font-mono text-text-dim">{{ formatDate(log.time) }}</span><span class="px-1.5 py-0.5 rounded text-[0.7rem] font-black" :class="getLogBgColor(log.type)">{{ log.title }}</span></div>
            <div class="text-sm text-text-soft mt-1 leading-relaxed">{{ log.desc }}</div>
          </div>
        </div>
        <div v-else class="text-sm text-text-disabled italic">{{ t('ui.workspace.github.active.no_logs', '暂无追踪记录') }}</div>
      </section>
    </div>

    <div v-else-if="viewMode === 'remote' || !activeRepo" class="min-h-0 flex-1 overflow-y-auto custom-scrollbar pr-1">
      <div v-if="state.error" class="p-4 rounded-2xl border border-accent-danger/30 bg-accent-danger/10 text-sm text-accent-danger">
        {{ state.error }}
      </div>
      <div v-else-if="state.isLoading && !state.info" class="h-full flex items-center justify-center text-sm text-text-dim">
        {{ t('ui.workspace.github.loading', '正在读取仓库信息...') }}
      </div>
      <div v-else-if="state.catalog?.type === 'zip' && props.catalogInstallable" class="bg-bg-inset/70 border border-border-base/10 rounded-2xl p-6 shadow-xl">
        <div class="flex items-start justify-between gap-4">
          <div class="min-w-0">
            <h2 class="text-2xl font-black text-text-main truncate">{{ catalogName }}</h2>
            <p class="mt-2 text-sm text-text-dim">{{ state.catalog.description || state.catalog.package_id || state.catalog.url }}</p>
          </div>
          <div class="shrink-0 flex items-center gap-2">
            <WorkshopItemActions custom-only size="sm" :before-actions="catalogActions" />
            <button @click="deploy" :disabled="state.isDeploying" class="px-4 py-2 rounded-xl bg-accent-success text-on-accent-success font-black text-sm disabled:opacity-50">
              <CloudDownload class="inline size-4 mr-1" :class="{ 'animate-bounce': state.isDeploying }" />
              {{ t('ui.workspace.github.active.deploy_now', '立即部署') }}
            </button>
          </div>
        </div>
        <div class="mt-4 grid grid-cols-2 gap-3 text-xs">
          <div><span class="text-text-dim">{{ t('common.field.source', '来源') }}</span><span class="ml-2 text-text-main">{{ catalogSource }}</span></div>
          <div><span class="text-text-dim">{{ t('common.field.author', '作者') }}</span><span class="ml-2 text-text-main">{{ catalogAuthor || '-' }}</span></div>
        </div>
      </div>
      <div v-else-if="state.catalog && !props.catalogInstallable" class="bg-bg-inset/70 border border-border-base/10 rounded-2xl p-6 shadow-xl">
        <div class="flex items-start justify-between gap-4">
          <div class="min-w-0">
            <h2 class="text-2xl font-black text-text-main truncate">{{ catalogName || t('ui.workspace.github.catalog.unsupported', '暂不支持') }}</h2>
            <p class="mt-2 text-sm text-text-dim">{{ t('ui.workspace.github.catalog.no_deploy_source', '该推荐项没有可用的 Git 仓库或压缩包部署方式。') }}</p>
          </div>
          <WorkshopItemActions custom-only size="sm" :before-actions="catalogActions" />
        </div>
      </div>
      <template v-else-if="state.info">
        <section class="bg-bg-inset/70 border border-border-base/10 rounded-2xl overflow-hidden shadow-xl">
          <div class="p-5 bg-bg-overlay/5 border-b border-border-base/10 flex items-start justify-between gap-4">
            <div class="min-w-0">
              <h2 class="text-2xl font-black text-text-main truncate">{{ state.info.repo }}</h2>
              <div class="mt-2 flex flex-wrap gap-2 items-center text-xs text-text-dim">
                <span>{{ t('common.field.source', '来源') }}: <span class="px-1 py-0.5 rounded bg-bg-inset/90">{{ state.info.host || state.info.provider || '-' }}</span></span>
                <span>{{ t('common.field.author', '作者') }}: <span class="px-1 py-0.5 rounded bg-bg-inset/90">{{ state.info.owner || '-' }}</span></span>
                <span v-if="state.catalog">{{ t('ui.workspace.github.catalog.source', '推荐源') }}: <span class="px-1 py-0.5 rounded bg-accent-primary/10 text-accent-primary">{{ catalogSource }}</span></span>
              </div>
            </div>
            <WorkshopItemActions custom-only size="sm" :before-actions="repoActions" />
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-3 p-4">
            <section v-if="state.info.source_status === 'available'" class="rounded-xl border p-4 flex min-h-64 flex-col gap-3" :class="sourceDeployed ? 'border-accent-primary/60 bg-accent-primary/10' : 'border-border-base/10 bg-bg-inset/50'">
              <div class="flex items-center justify-between"><h3 class="font-black text-text-main">Source</h3><span v-if="sourceDeployed" class="text-xs text-accent-primary">{{ t('ui.workspace.github.deploy.active', '当前部署方式') }}</span></div>
              <p class="text-xs text-text-dim">{{ t('ui.workspace.github.deploy.source_hint', '从选定分支读取源码并部署到本地模组目录。') }}</p>
              <CommonSelect v-model="state.ref" :options="refOptions" mini :label="t('ui.workspace.github.branch.switch', '切换分支')" :disabled="state.isLoading || state.isDeploying" @visible-change="loadRefsOnOpen" @change="changeRef" />
              <CommonSelect v-if="directoryOptions.length > 1" v-model="state.sourceSubpath" mini :options="directoryOptions" :label="t('ui.workspace.github.selection.directory', '模组目录')" :disabled="state.isDeploying" />
              <button @click="deploy('source')" :disabled="!state.ref.trim() || state.isDeploying || (sourceDeployed && !sourceNeedsUpdate)" class="flex min-h-28 flex-1 flex-col justify-between rounded-xl border border-accent-warn/30 bg-accent-warn/15 px-4 py-3 text-left text-text-main transition-colors hover:bg-accent-warn/25 disabled:cursor-not-allowed disabled:opacity-50">
                <div class="flex items-start justify-between gap-3"><span><strong class="block text-sm font-black">{{ sourceActionText }}</strong><span class="mt-1 block text-xs text-text-dim">{{ t('ui.workspace.github.deploy.source_button_hint', '源码部署会跟随当前分支的最新提交。') }}</span></span><CloudDownload class="size-5 shrink-0 text-accent-warn" :class="{ 'animate-bounce': state.isDeploying }" /></div>
                <div class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[0.68rem] text-text-dim"><span>{{ state.ref || '-' }}</span><span>{{ sourceVersion || '-' }}</span><span>{{ formatDate(state.info.latest_source_commit_at) || '-' }}</span></div>
              </button>
            </section>
            <section v-if="state.info.has_release" class="rounded-xl border p-4 flex min-h-64 flex-col gap-3" :class="releaseDeployed ? 'border-accent-primary/60 bg-accent-primary/10' : 'border-border-base/10 bg-bg-inset/50'">
              <div class="flex items-center justify-between"><h3 class="font-black text-text-main">Release</h3><span v-if="releaseDeployed" class="text-xs text-accent-primary">{{ t('ui.workspace.github.deploy.active', '当前部署方式') }}</span></div>
              <p class="text-xs text-text-dim">{{ t('ui.workspace.github.deploy.release_hint', '使用项目发布的打包文件部署，适合普通用户快速安装。') }}</p>
              <CommonSelect :model-value="state.info.latest_release_name || state.info.latest_release_tag" mini :options="releaseVersionOptions" :label="t('ui.workspace.github.selection.release_version', '发行版本')" disabled />
              <CommonSelect v-if="assetOptions.length" v-model="state.assetName" mini :options="assetOptions" :label="t('ui.workspace.github.selection.asset', '发行包文件')" :disabled="state.isDeploying || assetOptions.length < 2" />
              <button @click="deploy('release')" :disabled="state.isDeploying || (assetOptions.length > 1 && !state.assetName) || (releaseDeployed && !releaseNeedsUpdate)" class="flex min-h-28 flex-1 flex-col justify-between rounded-xl border border-accent-success/30 bg-accent-success/15 px-4 py-3 text-left text-text-main transition-colors hover:bg-accent-success/25 disabled:cursor-not-allowed disabled:opacity-50">
                <div class="flex items-start justify-between gap-3"><span><strong class="block text-sm font-black">{{ releaseActionText }}</strong><span class="mt-1 block text-xs text-text-dim">{{ t('ui.workspace.github.deploy.release_button_hint', '发行版部署会使用选定版本的打包文件。') }}</span></span><CloudDownload class="size-5 shrink-0 text-accent-success" :class="{ 'animate-bounce': state.isDeploying }" /></div>
                <div class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[0.68rem] text-text-dim"><span>{{ releaseVersion || '-' }}</span><span>{{ state.assetName || '-' }}</span><span>{{ formatDate(state.info.latest_release_published_at) || '-' }}</span></div>
              </button>
            </section>
          </div>
        </section>

        <section v-if="state.catalog && (state.catalog.description || catalogAuthor || state.catalog.package_id || state.catalog.category || state.catalog.workshop_url || state.catalog.game_versions?.length)" class="mt-4 bg-bg-inset/70 border border-border-base/10 rounded-2xl p-5 shadow-xl">
          <p v-if="state.catalog?.description" class="text-sm text-text-dim leading-relaxed mb-4">{{ state.catalog.description }}</p>
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
            <div v-if="catalogAuthor"><div class="text-text-dim">{{ t('common.field.author', '作者') }}</div><div class="mt-1 text-text-main truncate">{{ catalogAuthor }}</div></div>
            <div v-if="state.catalog.package_id"><div class="text-text-dim">{{ t('ui.workspace.github.detail.package_id', '包名') }}</div><div class="mt-1 text-text-main truncate">{{ state.catalog.package_id }}</div></div>
            <div v-if="state.catalog?.category"><div class="text-text-dim">{{ t('ui.workspace.github.catalog.category', '分类') }}</div><div class="mt-1 text-text-main truncate">{{ state.catalog.category }}</div></div>
          </div>
          <div v-if="state.catalog?.game_versions?.length" class="mt-4 flex flex-wrap gap-1 text-xs">
            <span class="text-text-dim mr-1">{{ t('ui.workspace.github.detail.rimworld_versions', 'RimWorld：') }}</span>
            <span v-for="version in state.catalog.game_versions" :key="version" class="px-2 py-1 rounded border border-border-base/10 bg-bg-inset/80">{{ version }}</span>
          </div>
        </section>

        <section class="mt-4 bg-bg-inset/70 border border-border-base/10 rounded-2xl p-5 shadow-xl">
          <div v-if="state.readme.isLoading" class="text-sm text-text-dim">{{ t('ui.workspace.github.readme.loading', '正在读取 README...') }}</div>
          <div v-else-if="state.readme.error" class="text-sm text-accent-warn">{{ state.readme.error }}</div>
          <div v-else-if="state.readme.content" v-viewer.rebuild="imageViewerOptions" class="prose prose-sm prose-invert max-w-none text-text-dim" v-html="renderMarkdown(state.readme.content)"></div>
          <div v-else class="text-sm text-text-dim">{{ t('ui.workspace.github.readme.empty', '该仓库没有可读取的 README') }}</div>
        </section>

      </template>
      <div v-else class="h-full flex flex-col items-center justify-center opacity-20 border-2 border-dashed border-border-base/18 rounded-2xl">
        <Github class="size-24 mb-4" />
        <span class="text-sm font-black tracking-widest">{{ t('ui.workspace.github.empty.select_or_add', '选择或添加仓库') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { Activity, CloudDownload, ExternalLink, FolderOpen, Github, Link, RefreshCw, Search } from 'lucide-vue-next'
import { useToast } from 'vue-toastification'
import { useAppStore } from '../../../app/stores/appStore'
import { useWorkspaceStore } from '../workspaceStore'
import { checkResult, toUserMessage } from '../../../shared/lib/common'
import { imageViewerOptions } from '../../../shared/lib/domEffects'
import { renderMarkdownContent } from '../../../shared/lib/markdown'
import CommonSelect from '../../../shared/components/input/CommonSelect.vue'
import WorkshopItemActions from '../../../shared/components/WorkshopItemActions.vue'
import { getCurrentLocale, t } from '../../../shared/i18n.js'

const props = defineProps({ catalogItem: { type: Object, default: null }, catalogInstallable: { type: Boolean, default: false } })
const emit = defineEmits(['clear-catalog'])
const pendingBrowserLoads = new Map()
const toast = useToast()
const appStore = useAppStore()
const workspaceStore = useWorkspaceStore()
const repoUrl = ref('')
const requestSeq = ref(0)
const installChoices = reactive({})
const state = reactive({
  catalog: null, info: null, ref: '', refType: 'branch', refs: [],
  assetName: '', sourceSubpath: '', isLoading: false,
  isDetecting: false, isDeploying: false, error: '', readme: { isLoading: false, content: '', error: '' },
})
const viewMode = ref('remote')

const activeRepo = computed(() => {
  const repo = workspaceStore.github.activeRepo
  return repo && normalizeUrl(repo.repo_url) === normalizeUrl(repoUrl.value || state.info?.repo_url) ? repo : null
})
const activeRepoStatus = computed(() => activeRepo.value ? workspaceStore.getGithubRepoStatus(activeRepo.value) : null)
const catalogName = computed(() => String(state.catalog?.name || state.catalog?.package_id || state.catalog?.url || '').trim())
const catalogSource = computed(() => String(state.catalog?.source_id || state.catalog?.type || '-'))
const catalogAuthor = computed(() => {
  const author = state.catalog?.author
  return Array.isArray(author) ? author.filter(Boolean).join(', ') : String(author || '').trim()
})
const refOptions = computed(() => state.refs.map(ref => ({ value: ref, label: ref })))
const assetOptions = computed(() => (state.info?.release_assets || []).map(asset => ({ value: asset.name, label: asset.name })))
const releaseVersionOptions = computed(() => [{ value: state.info?.latest_release_name || state.info?.latest_release_tag || '', label: state.info?.latest_release_name || state.info?.latest_release_tag || '' }])
const directoryOptions = computed(() => (installChoices[state.info?.repo_url]?.source_subpath || []).map(path => ({ value: path, label: path })))
const sourceVersion = computed(() => String(state.info?.latest_source_version || state.info?.latest_source_commit_sha || '').slice(0, 12))
const releaseVersion = computed(() => String(state.info?.latest_release_name || state.info?.latest_release_tag || '').trim())
const repoActions = computed(() => [
  { key: 'open-repo', label: t('ui.workspace.github.actions.open_original', '打开原始地址'), icon: ExternalLink, onClick: () => openExternal(state.info?.repo_url || repoUrl.value) },
  ...(activeRepo.value?.local_path || activeRepo.value?.local_folder ? [{ key: 'open-local', label: t('ui.workspace.github.actions.open_local', '打开本地目录'), icon: FolderOpen, onClick: openLocal }] : []),
  ...(state.catalog?.workshop_url ? [{ key: 'open-workshop', label: t('ui.workspace.github.catalog.open_workshop', '打开创意工坊页面'), icon: Link, onClick: () => openExternal(state.catalog.workshop_url) }] : []),
])
const catalogActions = computed(() => [
  ...(state.catalog?.workshop_url ? [{ key: 'open-workshop', label: t('ui.workspace.github.catalog.open_workshop', '打开创意工坊页面'), icon: Link, onClick: () => openExternal(state.catalog.workshop_url) }] : []),
  ...(state.catalog?.info_url || state.catalog?.raw_url || state.catalog?.url ? [{ key: 'open-original', label: t('ui.workspace.github.actions.open_original', '打开原始地址'), icon: ExternalLink, onClick: () => openExternal(state.catalog.info_url || state.catalog.raw_url || state.catalog.url) }] : []),
])
const localRepoActions = computed(() => activeRepo.value?.local_path || activeRepo.value?.local_folder ? [
  { key: 'open-local', label: t('ui.workspace.github.actions.open_local', '打开本地目录'), icon: FolderOpen, onClick: openLocal },
] : [])
const sourceDeployed = computed(() => activeRepo.value?.install_type === 'source' && !!activeRepo.value.installed_version && activeRepo.value.local_exists === true)
const releaseDeployed = computed(() => activeRepo.value?.install_type === 'release' && !!activeRepo.value.installed_version && activeRepo.value.local_exists === true)
const sourceNeedsUpdate = computed(() => !sourceDeployed.value || activeRepo.value.target_branch !== state.ref || activeRepo.value.install_options?.source_subpath !== state.sourceSubpath || !!activeRepo.value.has_update)
const releaseNeedsUpdate = computed(() => !releaseDeployed.value || activeRepo.value.install_options?.asset_name !== state.assetName || !!activeRepo.value.has_update)
const sourceActionText = computed(() => !sourceDeployed.value ? t('ui.workspace.github.deploy.source', '部署源码') : activeRepo.value.has_update ? t('ui.workspace.github.deploy.update', '更新部署') : sourceNeedsUpdate.value ? t('ui.workspace.github.deploy.redeploy', '重新部署') : t('ui.workspace.github.deploy.current', '已是最新'))
const releaseActionText = computed(() => !releaseDeployed.value ? t('ui.workspace.github.deploy.release', '部署发行版') : activeRepo.value.has_update ? t('ui.workspace.github.deploy.update', '更新部署') : releaseNeedsUpdate.value ? t('ui.workspace.github.deploy.redeploy', '重新部署') : t('ui.workspace.github.deploy.current', '已是最新'))

const normalizeUrl = (url) => String(url || '').trim().replace(/\/$/, '').replace(/\.git$/i, '')
const formatDate = (value) => {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString(getCurrentLocale(), { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
const formatInstallType = (type) => type === 'release' ? 'Release' : type === 'zip' ? 'Zip' : 'Source'
const openExternal = (url) => url && appStore.openUrl(url)
const openLocal = () => {
  const repo = activeRepo.value
  const base = appStore.settings.self_mods_path
  const local = repo?.local_path || (repo?.local_folder && `${String(base || '').replace(/[\\/]+$/, '')}/${String(repo.local_folder).replace(/^[\\/]+/, '')}`)
  if (local) appStore.openPath(local)
}
const renderMarkdown = (content) => renderMarkdownContent(content, { resolveImageUrl: url => /^https?:\/\//i.test(String(url || '')) ? appStore.getRemoteUrl(url) : url })
const getLogColor = (type) => type === 'error' ? 'border-accent-danger' : type === 'success' ? 'border-accent-success' : type === 'download' || type === 'extract' ? 'border-accent-primary animate-pulse' : 'border-border-base/18'
const getLogBgColor = (type) => type === 'error' ? 'bg-accent-danger/20 text-accent-danger' : type === 'success' ? 'bg-accent-success/20 text-accent-success' : type === 'download' || type === 'extract' ? 'bg-accent-primary/20 text-accent-primary' : 'bg-bg-overlay/10 text-text-main'

const resetState = () => {
  requestSeq.value += 1
  state.info = null
  state.error = ''
  state.readme = { isLoading: false, content: '', error: '' }
  state.refs = []
  state.ref = ''
  state.assetName = ''
  state.sourceSubpath = ''
  state.isLoading = false
}

const loadRepo = async (url, { catalog = null, ref = '', refType = 'branch', view = '' } = {}) => {
  const normalizedUrl = normalizeUrl(url)
  if (!normalizedUrl) return
  const refs = normalizedUrl === repoUrl.value ? state.refs : []
  repoUrl.value = normalizedUrl
  state.catalog = catalog
  resetState()
  state.refs = refs
  const seq = requestSeq.value
  state.isLoading = true
  try {
    const key = `${normalizedUrl}\n${ref}\n${refType}`
    let request = pendingBrowserLoads.get(key)
    if (!request) {
      request = window.pywebview.api.github_fetch_browser_info(normalizedUrl, ref || '', refType)
      pendingBrowserLoads.set(key, request)
      request.then(() => pendingBrowserLoads.delete(key), () => pendingBrowserLoads.delete(key))
    }
    const response = await request
    if (seq !== requestSeq.value) return
    if (!checkResult(response, t('ui.workspace.github.action.parse_repo', '解析 Git 仓库链接'))) {
      state.error = toUserMessage(response, t('ui.workspace.github.action.parse_repo', '解析 Git 仓库链接'))
      return
    }
    const data = response.data
    state.info = data.info
    viewMode.value = view || (activeRepo.value ? 'local' : 'remote')
    state.readme = { isLoading: false, content: String(data.readme?.content || ''), error: String(data.readme_error || '') }
    state.ref = ref || data.info.latest_source_branch || data.info.default_branch || ''
    state.refType = data.info.source_ref_type || refType
    state.assetName = activeRepo.value?.install_options?.asset_name || (data.info.release_assets?.length === 1 ? data.info.release_assets[0].name : '')
    state.sourceSubpath = data.info.source_subpath || activeRepo.value?.install_options?.source_subpath || catalog?.subdir || ''
  } catch (error) {
    if (seq === requestSeq.value) state.error = toUserMessage(error, t('ui.workspace.github.action.parse_repo', '解析 Git 仓库链接'))
  } finally {
    if (seq === requestSeq.value) state.isLoading = false
  }
}

const parseRepo = () => {
  if (!repoUrl.value.trim()) return
  if (normalizeUrl(workspaceStore.github.activeRepo?.repo_url) !== normalizeUrl(repoUrl.value)) workspaceStore.clearActiveGithubRepo()
  emit('clear-catalog')
  loadRepo(repoUrl.value, { view: 'remote' })
}

const changeRef = ({ value }) => {
  const ref = String(value || '').trim()
  const loadedRef = String(state.info?.latest_source_branch || state.info?.default_branch || '').trim()
  if (ref && ref !== loadedRef && state.info?.repo_url) {
    loadRepo(state.info.repo_url, { catalog: state.catalog, ref, refType: 'branch', view: viewMode.value })
  }
}

const detectRefs = async () => {
  if (!state.info?.repo_url || state.isDetecting) return
  const url = state.info.repo_url
  state.isDetecting = true
  try {
    const response = await window.pywebview.api.github_fetch_branches(url, 'branch')
    if (!checkResult(response, t('ui.workspace.github.branch.detect', '探测远端分支'))) return
    if (state.info?.repo_url !== url) return
    state.refs = response.data.branches || []
    if (!state.refs.length) toast.info(t('ui.workspace.github.branch.empty', '该仓库没有可用分支'))
  } finally {
    state.isDetecting = false
  }
}

const loadRefsOnOpen = (visible) => {
  if (visible && !state.refs.length) detectRefs()
}

const deploy = async (installType = 'source') => {
  if ((state.catalog?.type !== 'zip' && !state.info) || state.isDeploying) return
  if (state.catalog?.type !== 'zip') {
    if (installType === 'source' && state.info.source_status !== 'available') return
    if (installType === 'release' && !state.info.has_release) return
  }
  state.isDeploying = true
  try {
    let url
    let response
    if (state.catalog?.type === 'zip') {
      url = state.catalog.url
      response = await window.pywebview.api.github_subscribe({ url, owner: state.catalog.source_id || 'catalog', repo: catalogName.value, provider: 'catalog_zip', host: state.catalog.raw_url || url, install_type: 'zip', info: state.catalog })
    } else {
      if (!state.info) return
      url = state.info.repo_url
      const options = { ref_type: state.refType || 'branch', asset_name: installType === 'release' ? state.assetName : '', source_subpath: installType === 'source' ? state.sourceSubpath : '' }
      const payload = { url, default_branch: state.ref, install_type: installType, info: state.info, install_options: options }
      response = activeRepo.value && activeRepo.value.install_type === installType && (installType !== 'source' || activeRepo.value.target_branch === state.ref)
        ? await window.pywebview.api.github_trigger_download(url, installType, installType === 'source' ? state.ref : '', options)
        : await window.pywebview.api.github_subscribe(payload)
    }
    if (response.data?.selection) handleInstallSelection({ detail: response.data.selection })
    if (!checkResult(response, t('ui.workspace.github.action.request_transfer', '请求数据传输'))) return
    toast.info(t('ui.workspace.github.deploy.started', '已开始获取数据流，请在底部状态栏查看进度'), { timeout: 4000 })
    workspaceStore.startGithubTimelinePolling(url, { intervalMs: 4000, maxPolls: 15 })
    await workspaceStore.fetchGithubRepos()
  } finally {
    state.isDeploying = false
  }
}

const handleInstallSelection = (event) => {
  const { repo_url: url, kind, candidates } = event.detail || {}
  if (!url || !kind) return
  installChoices[url] = { ...installChoices[url], [kind]: candidates }
  if (kind === 'asset_name' && state.info?.repo_url === url) {
    state.info.release_assets = candidates.map(name => ({ name }))
    if (candidates.length === 1) state.assetName = candidates[0]
  }
  if (kind === 'source_subpath' && state.info?.repo_url === url && candidates.length === 1) state.sourceSubpath = candidates[0]
  if (candidates.length > 1) toast.warning(kind === 'asset_name' ? t('ui.workspace.github.selection.asset_required', '请选择发行包文件后重新部署') : t('ui.workspace.github.selection.directory_required', '请选择模组目录后重新部署'))
}

watch(() => props.catalogItem, item => {
  resetState()
  state.catalog = item
  if (!item) {
    if (activeRepo.value?.repo_url) repoUrl.value = normalizeUrl(activeRepo.value.repo_url)
    viewMode.value = activeRepo.value ? 'local' : 'remote'
    return
  }
  const url = item.url || item.raw_url || ''
  repoUrl.value = normalizeUrl(url)
  if (item.type === 'zip') {
    viewMode.value = activeRepo.value ? 'local' : 'remote'
    return
  }
  if (!props.catalogInstallable) {
    viewMode.value = activeRepo.value ? 'local' : 'remote'
    return
  }
  loadRepo(url, { catalog: item, ref: item.branch || '', refType: 'branch' })
}, { immediate: true })
watch(() => workspaceStore.github.activeRepo?.repo_url, url => {
  if (!url || props.catalogItem) return
  repoUrl.value = normalizeUrl(url)
  state.catalog = null
  resetState()
  viewMode.value = 'local'
}, { immediate: true })
watch(viewMode, mode => {
  if (mode === 'remote' && activeRepo.value && !state.info) {
    const repo = activeRepo.value
    loadRepo(repo.repo_url, { ref: repo.target_branch || '', refType: repo.install_options?.ref_type || 'branch', view: 'remote' })
  }
})
onMounted(() => window.addEventListener('github-install-selection', handleInstallSelection))
onBeforeUnmount(() => window.removeEventListener('github-install-selection', handleInstallSelection))
</script>

<style scoped>
:deep(.prose) { line-height: 1.65; }
:deep(.prose h1), :deep(.prose h2), :deep(.prose h3) { color: var(--color-text-main); font-weight: 800; margin: 1rem 0 0.5rem; }
:deep(.prose p), :deep(.prose ul), :deep(.prose ol) { margin: 0.65rem 0; }
:deep(.prose a) { color: var(--color-accent-primary); text-decoration: underline; }
:deep(.prose pre) { margin: 0.75rem 0; padding: 0.75rem; overflow-x: hidden; white-space: pre-wrap; overflow-wrap: anywhere; background-color: var(--color-bg-inset); border: 1px solid var(--color-border-subtle); border-radius: 0.5rem; }
</style>
