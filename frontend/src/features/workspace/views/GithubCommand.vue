<template>
  <div class="h-full min-h-0 grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-4 p-4 overflow-hidden">
    <div class="min-w-0 min-h-0 flex flex-col bg-bg-inset/80 border border-border-base/10 rounded-2xl overflow-hidden shadow-2xl" data-tour="workspace-github-list">
      <div class="px-4 py-3 bg-bg-overlay/10 border-b border-border-base/10 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <Github class="size-4 text-text-main" />
          <h3 class="text-sm font-bold text-text-main">{{ t('ui.workspace.github.title', 'Git 仓库订阅') }}</h3>
        </div>
        <div class="flex items-center gap-2">
          <div class="grid grid-cols-2 gap-1 p-1 bg-bg-inset/80 rounded-xl border border-border-base/10">
            <button @click="setListMode('subscribed')" class="px-3 py-1.5 rounded-lg text-xs font-bold transition-colors" :class="listMode === 'subscribed' ? 'bg-bg-contrast text-text-inverse' : 'text-text-dim hover:text-text-main'">{{ t('ui.workspace.common.subscribed', '已订阅') }}</button>
            <button @click="setListMode('recommend')" class="px-3 py-1.5 rounded-lg text-xs font-bold transition-colors" :class="listMode === 'recommend' ? 'bg-bg-contrast text-text-inverse' : 'text-text-dim hover:text-text-main'">{{ t('ui.workspace.github.tabs.recommend', '推荐列表') }}</button>
          </div>
          <button @click="listMode === 'recommend' ? workspaceStore.fetchGithubProviderCatalog({ force: true }) : workspaceStore.fetchGithubRepos()" v-tooltip="t('ui.workspace.github.refresh.tooltip', '刷新当前列表')" class="p-1 text-text-dim hover:text-text-main transition-colors">
            <RefreshCw class="size-4" :class="{ 'animate-spin': workspaceStore.github.isLoading || workspaceStore.github.isCatalogLoading }" />
          </button>
        </div>
      </div>

      <div v-if="listMode === 'recommend'" class="shrink-0 toolbar-surface p-2">
        <div class="mt-2 flex gap-2">
          <div class="w-32 shrink-0"><CommonSelect v-model="catalogSourceFilter" :options="catalogSourceOptions" mini /></div>
          <div class="relative flex-1">
            <Search class="absolute left-3 top-1/2 -translate-y-1/2 size-3.5 text-text-dim" />
            <input v-model="catalogFilter" :placeholder="t('ui.workspace.github.catalog.filter_placeholder', '筛选名称、包名、作者或版本')" class="w-full bg-bg-inset/90 border border-border-base/10 rounded-lg pl-8 pr-3 py-1.5 text-xs text-text-main outline-none focus:border-border-base/18" />
          </div>
        </div>
        <div v-if="workspaceStore.github.catalogMeta.total" class="mt-2 truncate text-[0.6rem] text-text-dim">
          {{ t('ui.workspace.github.catalog.source_summary', '推荐来源: {total} 项 / {sourceCount} 个来源', { total: workspaceStore.github.catalogMeta.total || 0, sourceCount: catalogSourceOptions.length - 1 }) }}
          <span v-if="workspaceStore.github.catalogMeta.is_stale" class="text-accent-warn">{{ t('ui.workspace.github.catalog.cache_badge', '缓存') }}</span>
        </div>
      </div>

      <div v-if="listMode === 'subscribed'" class="min-h-0 flex-1 overflow-y-auto custom-scrollbar p-2 space-y-1">
        <div v-for="repo in workspaceStore.github.subscribedRepos" :key="repo.repo_url" @click="selectRepo(repo)" class="flex flex-col gap-1 px-3 py-2 rounded-xl border transition-all cursor-pointer group relative overflow-hidden" :class="normalizeRepoUrl(workspaceStore.github.activeRepo?.repo_url) === normalizeRepoUrl(repo.repo_url) ? 'bg-bg-overlay/10 border-border-base/18 shadow-inner' : 'border-border-base/10 bg-glass-medium/60 hover:bg-bg-overlay/5'">
          <div class="flex justify-between items-center z-10">
            <div class="font-bold text-sm text-text-main truncate">{{ repo.repo_name }}</div>
            <div class="flex items-center gap-1 text-[0.65rem] font-mono">
              <span class="px-2 py-0.5 text-text-dim bg-bg-inset/70 rounded">{{ repo.host || repo.provider || 'github.com' }}</span>
              <span class="px-2 py-0.5 text-accent-primary bg-accent-primary/10 rounded">{{ formatInstallType(repo.install_type) }}</span>
              <span class="px-2 py-0.5 rounded bg-accent-highlight/20 text-[0.6rem] font-mono text-accent-highlight border border-accent-highlight/10">{{ repo.owner }}</span>
            </div>
          </div>
          <div class="flex items-center mt-0.5 gap-1 text-[0.65rem] font-mono">
            <span class="px-2 py-1 rounded bg-bg-inset/90 text-[0.65rem] font-mono" :class="githubStatus(repo).tone">{{ githubStatus(repo).label }}<template v-if="githubStatus(repo).version"> ({{ githubStatus(repo).version }})</template></span>
          </div>
          <WorkshopItemActions custom-only size="xs" class="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-all z-20" :before-actions="repoActions(repo)" @click.stop />
        </div>
      </div>

      <div v-else class="min-h-0 flex-1 overflow-y-auto custom-scrollbar p-2 space-y-2">
        <div v-if="workspaceStore.github.isCatalogLoading" class="h-full flex items-center justify-center text-xs text-text-dim">{{ t('ui.workspace.github.catalog.loading', '正在读取推荐列表...') }}</div>
        <div v-else-if="workspaceStore.github.catalogError" class="p-3 rounded-xl border border-accent-danger/30 bg-accent-danger/10 text-xs text-accent-danger">{{ workspaceStore.github.catalogError }}</div>
        <div v-if="!workspaceStore.github.isCatalogLoading && workspaceStore.github.catalogMeta.warning" class="p-3 rounded-xl border border-accent-warn/30 bg-accent-warn/10 text-xs text-accent-warn">{{ workspaceStore.github.catalogMeta.warning }}</div>
        <div v-else-if="filteredRecommendedRepos.length === 0" class="h-full flex items-center justify-center text-xs text-text-dim">{{ t('ui.workspace.github.catalog.empty', '没有匹配的推荐项') }}</div>
        <div v-for="item in filteredRecommendedRepos" :key="`${item.category}:${item.key}`" @click="selectRecommendedItem(item)" v-tooltip="catalogItemTooltip(item)" class="p-3 rounded-xl border transition-colors cursor-pointer" :class="selectedCatalogItem?.key === item.key && selectedCatalogItem?.source_id === item.source_id ? 'bg-bg-overlay/10 border-border-base/18' : 'border-border-base/10 bg-glass-medium/60 hover:bg-bg-overlay/5'">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span class="font-bold text-sm text-text-main truncate">{{ catalogDisplayName(item) }}</span>
                <span v-if="catalogSourceName(item.source_id)" class="shrink-0 px-1.5 py-0.5 rounded bg-accent-primary/10 text-[0.6rem] text-accent-primary">{{ catalogSourceName(item.source_id) }}</span>
                <span v-if="item.not_recommended || !isInstallable(item)" v-tooltip="availabilityTooltip(item)" class="shrink-0 px-1.5 py-0.5 rounded bg-accent-warn/10 text-[0.6rem] text-accent-warn">{{ formatAvailability(item) }}</span>
              </div>
              <div class="mt-1 flex flex-wrap gap-1 text-[0.6rem] font-mono text-text-dim">
                <span class="px-1.5 py-0.5 rounded bg-bg-inset/90 border border-border-base/10">{{ item.category }}</span>
                <span class="px-1.5 py-0.5 rounded bg-bg-inset/90 border border-border-base/10">{{ catalogHostLabel(item) }}</span>
                <span v-if="item.branch" class="px-1.5 py-0.5 rounded bg-accent-secondary/10 text-accent-secondary">{{ t('ui.workspace.github.catalog.branch', '分支：{branch}', { branch: item.branch }) }}</span>
                <span v-for="version in catalogDisplayVersions(item.game_versions)" :key="`${item.key}:${version}`" class="px-1.5 py-0.5 rounded border" :class="catalogVersionClass(version)">{{ version }}</span>
                <span v-if="item.workshop_url" class="px-1.5 py-0.5 rounded bg-accent-primary/10 text-accent-primary">{{ t('ui.workspace.github.catalog.workshop_badge', '工坊') }}</span>
                <span v-if="subscribedRepoUrls.has(normalizeRepoUrl(item.url || item.raw_url))" class="px-1.5 py-0.5 rounded bg-accent-success/10 text-accent-success">{{ t('ui.workspace.github.catalog.git_subscribed', '已添加 Git 订阅') }}</span>
                <span v-if="item.workshop_url && isWorkshopSubscribed(item)" class="px-1.5 py-0.5 rounded bg-accent-secondary/10 text-accent-secondary">{{ t('ui.workspace.github.catalog.workshop_subscribed', '已订阅创意工坊') }}</span>
              </div>
            </div>
          </div>
          <div class="mt-2 flex items-end justify-between gap-2">
            <div class="min-w-0 space-y-0.5 text-[0.65rem] text-text-dim">
              <div class="truncate">{{ catalogAuthorText(item) || item.package_id || catalogDisplayName(item) }}</div>
              <div v-if="catalogUpdatedText(item)" class="truncate">{{ catalogUpdatedText(item) }}</div>
            </div>
            <WorkshopItemActions custom-only size="xs" :before-actions="catalogActions(item)" @click.stop />
          </div>
        </div>
      </div>
    </div>

    <GithubRepoBrowser class="min-w-0" :catalog-item="selectedCatalogItem" :catalog-installable="!!selectedCatalogItem && isInstallable(selectedCatalogItem)" @clear-catalog="selectedCatalogItem = null" />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ExternalLink, Flag, FlagOff, FolderOpen, Github, RefreshCw, Search, Trash2 } from 'lucide-vue-next'
import { useAppStore } from '../../../app/stores/appStore'
import { useWorkspaceStore } from '../workspaceStore'
import { useProfileStore } from '../../profiles/profileStore'
import { useConfirmStore } from '../../../shared/components/modal/confirmStore'
import { isOfficialPackageId } from '../../mod/lib/packageScope'
import CommonSelect from '../../../shared/components/input/CommonSelect.vue'
import WorkshopItemActions from '../../../shared/components/WorkshopItemActions.vue'
import GithubRepoBrowser from './GithubRepoBrowser.vue'
import { getCurrentLocale, t } from '../../../shared/i18n.js'

const appStore = useAppStore()
const workspaceStore = useWorkspaceStore()
const profileStore = useProfileStore()
const confirmStore = useConfirmStore()
const listMode = ref('subscribed')
const catalogFilter = ref('')
const catalogSourceFilter = ref('all')
const selectedCatalogItem = ref(null)
const isWorkshopBusy = ref(false)
const normalizeRepoUrl = (url) => String(url || '').trim().replace(/\/$/, '').replace(/\.git$/i, '')
const subscribedRepoUrls = computed(() => new Set(workspaceStore.github.subscribedRepos.map(repo => normalizeRepoUrl(repo.repo_url)).filter(Boolean)))
const catalogSourceOptions = computed(() => [
  { value: 'all', label: t('ui.workspace.github.catalog.source_all', '全部') },
  ...(workspaceStore.github.catalogMeta.sources || []).map(source => ({ value: String(source.id || ''), label: String(source.label || source.name || source.id || t('ui.workspace.github.catalog.source_catalog', '清单')) })).filter(source => source.value),
])
const catalogSourceName = (sourceId) => workspaceStore.github.catalogMeta.sources?.find(source => String(source.id) === String(sourceId))?.label || String(sourceId || '')
const catalogDisplayName = (item) => String(item?.name || item?.package_id || item?.url || '').trim()
const catalogAuthorText = (item) => {
  const author = item?.author
  if (Array.isArray(author)) return author.filter(Boolean).join(', ')
  if (String(author || '').trim()) return String(author).trim()
  try { return new URL(String(item?.url || '')).pathname.split('/').filter(Boolean).slice(0, -1).join('/') } catch { return '' }
}
const safeUrlHost = (url) => { try { return new URL(String(url || '')).host } catch { return '' } }
const catalogHostLabel = (item) => safeUrlHost(item?.url || item?.raw_url) || String(item?.type || '').trim() || '-'
const isOfficialCatalogItem = (item) => isOfficialPackageId(item?.package_id)
const isInstallable = (item) => {
  if (isOfficialCatalogItem(item)) return false
  const type = String(item?.type || '').toLowerCase()
  return type === 'zip' ? !!item?.url : ['', 'git'].includes(type) && !!(item?.url || item?.raw_url)
}
const catalogDateText = (item) => {
  const value = item?.published_at || item?.released_at || item?.latest_release_published_at || item?.latest_source_commit_at || item?.updated_at || item?.remote_last_modified
  const date = value ? new Date(value) : null
  if (!date || Number.isNaN(date.getTime())) return ''
  return date.toLocaleString(getCurrentLocale(), { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
const catalogUpdatedText = (item) => {
  const time = catalogDateText(item)
  if (!time) return ''
  return item?.published_at || item?.released_at || item?.latest_release_published_at
    ? t('ui.workspace.github.time.published', '发布: {time}', { time })
    : t('ui.workspace.github.time.updated', '更新: {time}', { time })
}
const catalogItemTooltip = (item) => [catalogDisplayName(item), item?.description, item?.package_id ? t('ui.workspace.github.tooltip.package_id', '包名: {packageId}', { packageId: item.package_id }) : '', catalogAuthorText(item) ? t('ui.workspace.github.tooltip.author', '作者: {author}', { author: catalogAuthorText(item) }) : '', catalogUpdatedText(item)].filter(Boolean).join('\n')
const isInstallableOfficial = (item) => isOfficialCatalogItem(item)
const availabilityTooltip = (item) => isInstallableOfficial(item) ? t('ui.workspace.github.catalog.official_tooltip', '游戏本体或官方 DLC 不需要订阅') : item?.not_recommended ? t('ui.workspace.github.catalog.not_recommended_tooltip', '该项目可能暂时不兼容，建议确认说明后再添加') : t('ui.workspace.github.catalog.unsupported_tooltip', '该项目缺少可用下载地址')
const formatAvailability = (item) => isInstallableOfficial(item) ? t('ui.workspace.github.catalog.official', '官方内容') : item?.not_recommended ? t('ui.workspace.github.catalog.not_recommended', '当前不建议使用') : t('ui.workspace.github.catalog.unsupported', '暂不支持')
const currentGameVersion = computed(() => String(profileStore.activeContext?.game_version || '').match(/^\d+\.\d+/)?.[0] || '')
const versionKey = (value) => (String(value || '').match(/\d+(?:\.\d+)*/)?.[0] || '').split('.').map(Number)
const compareVersion = (a, b) => { const left = versionKey(a); const right = versionKey(b); for (let i = 0; i < Math.max(left.length, right.length); i += 1) { const diff = (left[i] || 0) - (right[i] || 0); if (diff) return diff } return String(a).localeCompare(String(b)) }
const catalogDisplayVersions = (versions = []) => {
  const values = [...new Set((Array.isArray(versions) ? versions : []).map(value => String(value || '').trim()).filter(Boolean))].sort(compareVersion)
  return values.length < 6 ? values : [`${values[0]} - ${values[values.length - 3]}`, ...values.slice(-2)]
}
const catalogVersionClass = (version) => compareVersion(version, currentGameVersion.value) === 0 && currentGameVersion.value ? 'bg-accent-success/70 text-on-accent-success border-accent-success' : 'bg-bg-inset/80 text-text-dim border-border-base/10'
const filteredRecommendedRepos = computed(() => {
  const keyword = catalogFilter.value.trim().toLowerCase()
  return (workspaceStore.github.recommendedRepos || []).filter(item => {
    if (catalogSourceFilter.value !== 'all' && String(item.source_id || '') !== catalogSourceFilter.value) return false
    return !keyword || [item.name, item.package_id, ...(item.game_versions || []), catalogAuthorText(item)].join(' ').toLowerCase().includes(keyword)
  })
})
const githubStatus = (repo) => repo?.status || workspaceStore.getGithubRepoStatus(repo)
const extractWorkshopId = (url) => String(url || '').match(/[?&]id=(\d+)/)?.[1] || String(url || '').match(/\/(\d+)(?:[/?#]|$)/)?.[1] || ''
const getWorkshopId = (item) => String(item?.workshopId || item?.workshop_id || extractWorkshopId(item?.workshop_url) || '').trim()
const isWorkshopSubscribed = (item) => { const id = getWorkshopId(item); return !!id && workspaceStore.subscribedWorkshopIds.has(id) }

const setListMode = async (mode) => {
  listMode.value = mode
  if (mode === 'recommend') await workspaceStore.fetchGithubProviderCatalog()
}
const selectRepo = async (repo) => {
  selectedCatalogItem.value = null
  await workspaceStore.selectGithubRepo(repo)
}
const selectRecommendedItem = (item) => {
  selectedCatalogItem.value = item
  const url = normalizeRepoUrl(item.url || item.raw_url)
  const repo = workspaceStore.github.subscribedRepos.find(candidate => normalizeRepoUrl(candidate.repo_url) === url)
  if (repo) void workspaceStore.selectGithubRepo(repo)
  else workspaceStore.clearActiveGithubRepo()
}
const openExternal = (url) => url && appStore.openUrl(url)
const repoActions = (repo) => [
  { key: 'open-repo', label: t('ui.workspace.github.actions.open_original', '打开原始地址'), icon: ExternalLink, onClick: () => openExternal(repo.repo_url) },
  ...(repo.local_path || repo.local_folder ? [{ key: 'open-local', label: t('ui.workspace.github.actions.open_local', '打开本地目录'), icon: FolderOpen, onClick: () => openRepoLocal(repo) }] : []),
  { key: 'remove-repo', label: t('ui.workspace.github.remove.title', '移除订阅'), icon: Trash2, class: 'text-accent-danger hover:text-accent-danger', onClick: () => removeRepo(repo.repo_url) },
]
const catalogActions = (item) => [
  ...(item.workshop_url ? [{ key: 'workshop', label: isWorkshopSubscribed(item) ? t('ui.workspace.github.workshop.unsubscribe', '取消订阅创意工坊') : t('ui.workspace.github.workshop.subscribe', '订阅创意工坊'), icon: isWorkshopSubscribed(item) ? FlagOff : Flag, disabled: isWorkshopBusy.value, onClick: () => toggleWorkshopSubscription(item) }] : []),
  ...(item.info_url || item.url ? [{ key: 'open-repo', label: t('ui.workspace.github.actions.open_original', '打开原始地址'), icon: ExternalLink, onClick: () => openExternal(item.info_url || item.url) }] : []),
]
const openRepoLocal = (repo) => {
  const path = repo?.local_path || (repo?.local_folder && `${String(appStore.settings.self_mods_path || '').replace(/[\\/]+$/, '')}/${String(repo.local_folder).replace(/^[\\/]+/, '')}`)
  if (path) appStore.openPath(path)
}
const formatInstallType = (type) => type === 'release' ? 'Release' : type === 'zip' ? 'Zip' : 'Source'
const toggleWorkshopSubscription = async (item) => {
  const id = getWorkshopId(item)
  if (!id || isWorkshopBusy.value) return
  isWorkshopBusy.value = true
  try {
    const success = isWorkshopSubscribed(item) ? await appStore.unsubscribeWorkshopIds([id]) : await appStore.subscribeWorkshopIds([id])
    if (success) await workspaceStore.fetchLibrariesMods()
  } finally {
    isWorkshopBusy.value = false
  }
}
const removeRepo = async (url) => {
  const repo = workspaceStore.github.subscribedRepos.find(item => normalizeRepoUrl(item.repo_url) === normalizeRepoUrl(url))
  const confirmed = await confirmStore.confirmAction(t('ui.workspace.github.remove.title', '移除订阅'), t('ui.workspace.github.remove.message', '确定要移除 Git 订阅「{name}」吗？\n本地已下载文件不会被删除。', { name: repo?.repo_name || url }), { type: 'error', confirmText: t('ui.workspace.github.remove.confirm', '移除') })
  if (!confirmed) return
  const result = await window.pywebview.api.github_remove_subscription(url)
  if (!checkResult(result, t('ui.workspace.github.remove.title', '移除订阅'))) return
  if (normalizeRepoUrl(workspaceStore.github.activeRepo?.repo_url) === normalizeRepoUrl(url)) workspaceStore.clearActiveGithubRepo()
  await workspaceStore.fetchGithubRepos()
}
</script>
