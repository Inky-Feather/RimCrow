<!-- src/components/workspace/views/GithubCommand.vue -->
<template>
  <div class="h-full flex gap-4 p-4 overflow-hidden">
    
    <!-- 左侧：已订阅仓库阵列 (40%) -->
    <div class="w-[40%] flex flex-col bg-bg-inset/80 border border-border-base/10 rounded-2xl overflow-hidden shadow-2xl" data-tour="workspace-github-list">
      <div class="px-4 py-3 bg-bg-overlay/10 border-b border-border-base/10 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <Github class="size-4 text-text-main" />
          <h3 class="text-sm font-bold text-text-main">Git 仓库订阅</h3>
        </div>
        <div class="flex items-center gap-2">
          <div class="grid grid-cols-2 gap-1 p-1 bg-bg-inset/80 rounded-xl border border-border-base/10">
            <button @click="setListMode('subscribed')" class="px-3 py-1.5 rounded-lg text-xs font-bold transition-colors"
              :class="listMode === 'subscribed' ? 'bg-bg-contrast text-text-inverse' : 'text-text-dim hover:text-text-main'">
              已订阅
            </button>
            <button @click="setListMode('recommend')" class="px-3 py-1.5 rounded-lg text-xs font-bold transition-colors"
              :class="listMode === 'recommend' ? 'bg-bg-contrast text-text-inverse' : 'text-text-dim hover:text-text-main'">
              推荐列表
            </button>
          </div>
          <button @click="listMode === 'recommend' ? workspaceStore.fetchGithubProviderCatalog({ force: true }) : workspaceStore.fetchGithubRepos()" v-tooltip="'刷新当前列表'" class="p-1 text-text-dim hover:text-text-main transition-colors">
            <RefreshCw class="size-4" :class="{'animate-spin': workspaceStore.github.isLoading || workspaceStore.github.isCatalogLoading}" />
          </button>
        </div>
      </div>

      <div v-if="listMode === 'recommend'" class="toolbar-surface p-2">

        <div class="mt-2 flex gap-2">
          <div class="w-32 shrink-0">
            <CommonSelect v-model="catalogSourceFilter" :options="catalogSourceOptions" mini />
          </div>
          <div class="relative flex-1">
            <Search class="absolute left-3 top-1/2 -translate-y-1/2 size-3.5 text-text-dim" />
            <input v-model="catalogFilter"
              placeholder="筛选名称、包名、作者或版本"
              class="w-full bg-bg-inset/90 border border-border-base/10 rounded-lg pl-8 pr-3 py-1.5 text-xs text-text-main outline-none focus:border-border-base/18" />
          </div>
        </div>
        <div v-if="workspaceStore.github.catalogMeta.total" class="mt-2 truncate text-[0.6rem] text-text-dim">
          推荐来源: {{ workspaceStore.github.catalogMeta.total || 0 }} 项 / {{ catalogSourceOptions.length - 1 }} 个来源
          <span v-if="workspaceStore.github.catalogMeta.is_stale" class="text-accent-warn">缓存</span>
        </div>

      </div>

      <div v-if="listMode === 'subscribed'" class="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-1">
        <div v-for="repo in workspaceStore.github.subscribedRepos" :key="repo.repo_url"
          @click="selectRepo(repo)"
          class="flex flex-col gap-1 px-3 py-2 rounded-xl border transition-all cursor-pointer group relative overflow-hidden"
          :class="workspaceStore.github.activeRepo?.repo_url === repo.repo_url ? 'bg-bg-overlay/10 border-border-base/18 shadow-inner' : 'border-border-base/10 bg-glass-medium/60 hover:bg-bg-overlay/5'">
          
          <div class="flex justify-between items-center z-10">
            <div class="font-bold text-sm text-text-main truncate">{{ repo.repo_name }}</div>
            
            <div class="flex items-center gap-1 text-[0.65rem] font-mono">
              <span class="px-2 py-0.5 text-text-dim bg-bg-inset/70 rounded">{{ repo.host || repo.provider || 'github.com' }}</span>
              <span class="px-2 py-0.5 text-accent-primary bg-accent-primary/10 rounded">{{ formatInstallType(repo.install_type) }}</span>
              <span class="px-2 py-0.5 rounded bg-accent-highlight/20 text-[0.6rem] font-mono text-accent-highlight border border-accent-highlight/10">
                {{ repo.owner }}
              </span>
            </div>
          </div>
          
          <div class="flex items-center mt-0.5 gap-1 text-[0.65rem] font-mono">
            <span class="px-2 py-1 rounded bg-bg-inset/90 text-[0.65rem] font-mono" :class="githubStatus(repo).tone">
              {{ githubStatus(repo).label }}<template v-if="githubStatus(repo).version"> ({{ githubStatus(repo).version }})</template>
            </span>
          </div>
          
          <div class="absolute right-2 top-1/2 -translate-y-1/2 flex gap-1 bg-glass-medium/60 p-1 rounded-xl backdrop-blur-lg border border-border-base/5 opacity-0 group-hover:opacity-100 transition-all z-20">
            <button @click.stop="openRepoOriginal(repo)" v-tooltip="'打开原始地址'" class="p-2 rounded-lg bg-bg-overlay/10 text-text-dim hover:text-text-main hover:bg-bg-overlay/10 transition-colors">
              <ExternalLink class="size-4" />
            </button>
            <button v-if="repo.local_path || repo.local_folder" @click.stop="openRepoLocal(repo)" v-tooltip="'打开本地目录'" class="p-2 rounded-lg bg-bg-overlay/10 text-text-dim hover:text-text-main hover:bg-bg-overlay/10 transition-colors">
              <FolderOpen class="size-4" />
            </button>
            <button @click.stop="removeRepo(repo.repo_url)" v-tooltip="'移除订阅'" class="p-2 rounded-lg bg-accent-danger/20 text-accent-danger hover:bg-accent-danger hover:text-on-accent-danger transition-colors">
              <Trash2 class="size-4" />
            </button>
          </div>
        </div>
      </div>

      <div v-else class="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-2">
        <div v-if="workspaceStore.github.isCatalogLoading" class="h-full flex items-center justify-center text-xs text-text-dim">
          正在读取推荐列表...
        </div>
        <div v-else-if="workspaceStore.github.catalogError" class="p-3 rounded-xl border border-accent-danger/30 bg-accent-danger/10 text-xs text-accent-danger">
          {{ workspaceStore.github.catalogError }}
        </div>
        <div v-if="!workspaceStore.github.isCatalogLoading && workspaceStore.github.catalogMeta.warning" class="p-3 rounded-xl border border-accent-warn/30 bg-accent-warn/10 text-xs text-accent-warn">
          {{ workspaceStore.github.catalogMeta.warning }}
        </div>
        <div v-else-if="filteredRecommendedRepos.length === 0" class="h-full flex items-center justify-center text-xs text-text-dim">
          没有匹配的推荐项
        </div>
        <div v-for="item in filteredRecommendedRepos" :key="`${item.category}:${item.key}`"
          @click="selectRecommendedItem(item)"
          v-tooltip="catalogItemTooltip(item)"
          class="p-3 rounded-xl border transition-colors cursor-pointer"
          :class="selectedCatalogItem?.key === item.key && selectedCatalogItem?.source_id === item.source_id ? 'bg-bg-overlay/10 border-border-base/18' : 'border-border-base/10 bg-glass-medium/60 hover:bg-bg-overlay/5'">
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
                <span v-if="item.branch" class="px-1.5 py-0.5 rounded bg-accent-secondary/10 text-accent-secondary">branch: {{ item.branch }}</span>
                <span v-for="version in catalogDisplayVersions(item.game_versions)" :key="`${item.key}:${version}`"
                  class="px-1.5 py-0.5 rounded border"
                  :class="catalogVersionClass(version)">
                  {{ version }}
                </span>
                <span v-if="item.workshop_url" class="px-1.5 py-0.5 rounded bg-accent-primary/10 text-accent-primary">Workshop</span>
                <span v-if="subscribedRepoUrls.has(item.url)" class="px-1.5 py-0.5 rounded bg-accent-success/10 text-accent-success">已添加 Git 订阅</span>
                <span v-if="item.workshop_url && isWorkshopSubscribed(item)" class="px-1.5 py-0.5 rounded bg-accent-secondary/10 text-accent-secondary">已订阅创意工坊</span>
              </div>
            </div>
            <button v-if="!isOfficialCatalogItem(item)" @click.stop="subscribeRecommendedItem(item)"
              :disabled="!isInstallable(item) || subscribedRepoUrls.has(item.url) || isParsing"
              v-tooltip="recommendedActionTooltip(item)"
              class="shrink-0 p-2 rounded-lg disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              :class="gitActionButtonClass(item)">
              <ListPlus class="size-4" />
            </button>
          </div>
          <div class="mt-2 flex items-center justify-between gap-2">
            <div class="min-w-0 truncate text-[0.65rem] text-text-dim">
              {{ catalogAuthorText(item) || item.package_id || catalogDisplayName(item) }}
            </div>
            <div class="flex items-center gap-1">
              <button v-if="item.workshop_url" @click.stop="toggleWorkshopSubscription(item)" :disabled="isWorkshopBusy"
                v-tooltip="isWorkshopSubscribed(item) ? '取消订阅创意工坊' : '订阅创意工坊'"
                class="shrink-0 p-1.5 rounded-md transition-colors disabled:opacity-40"
                :class="workshopActionButtonClass(item)">
                <FlagOff v-if="isWorkshopSubscribed(item)" class="size-3.5" />
                <Flag v-else class="size-3.5" />
              </button>
              <button v-if="item.info_url || item.url" @click.stop="openExternal(item.info_url || item.url)"
              v-tooltip="'打开原始地址'"
              class="shrink-0 p-1.5 rounded-md text-text-dim hover:text-text-main hover:bg-bg-overlay/10 transition-colors">
                <ExternalLink class="size-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧：链接解析操作面板 (60%) -->
    <div class="w-[60%] flex flex-col gap-4" data-tour="workspace-github-workspace">
      
      <!-- 顶部：新增仓库解析器 -->
      <div class="bg-bg-inset/80 p-3 rounded-2xl border border-border-base/10 flex items-center gap-3 shadow-lg" data-tour="workspace-github-input">
        <div class="flex-1 relative">
          <Link class="absolute left-4 top-1/2 -translate-y-1/2 size-4 text-text-dim" />
          <input v-model="newRepoUrl" @keydown.enter="parseNewRepo"
            v-tooltip="'支持以下仓库：GitHub、GitLab、GitGud。'"
            placeholder="粘贴公开 Git 仓库地址 如: https://github.com/user/repo (支持 GitHub / GitLab / GitGud)"
            class="w-full bg-bg-inset border border-border-base/10 rounded-xl pl-10 pr-4 py-2.5 text-sm text-text-main outline-none focus:border-border-base/18 transition-all" />
        </div>
        <button @click="parseNewRepo" :disabled="isParsing"
          class="px-6 py-2.5 bg-bg-overlay/10 text-text-main hover:bg-bg-contrast hover:text-text-inverse border border-border-base/18 rounded-xl text-sm font-black transition-all disabled:opacity-50 flex items-center gap-2">
          <span v-if="isParsing" class="animate-spin">⟳</span> 解析地址
        </button>
      </div>

      <!-- 解析结果区 (如果正在解析新仓库) -->
      <div v-if="workspaceStore.github.previewInfo" data-tour="workspace-github-preview" class="p-6 bg-accent-primary/10 border border-accent-primary/30 rounded-2xl animate-in zoom-in-95">
        <h3 class="text-lg font-black text-text-main mb-2">{{ workspaceStore.github.previewInfo.repo }}</h3>
        <p class="text-sm text-text-dim mb-4">
          作者: {{ workspaceStore.github.previewInfo.owner }} | 默认分支: {{ workspaceStore.github.previewInfo.default_branch }}
          <template v-if="repoPreviewTimeText(workspaceStore.github.previewInfo)"> | {{ repoPreviewTimeText(workspaceStore.github.previewInfo) }}</template>
        </p>
        
        <div class="flex gap-4">
          <!-- Source 模式 -->
          <button @click="confirmSubscribe('source')" class="flex-1 p-4 rounded-xl border border-accent-secondary/30 bg-accent-secondary/10 hover:bg-accent-secondary/20 transition-all text-left">
            <div class="font-bold text-accent-secondary mb-1">同步源码分支 (Source)</div>
            <div class="text-xs text-text-dim">获取分支最新代码。适合频繁更新或未发布 Release 的测试版模组。</div>
          </button>

          <!-- Release 模式 -->
          <button @click="confirmSubscribe('release')" :disabled="!workspaceStore.github.previewInfo.has_release"
            class="flex-1 p-4 rounded-xl border border-accent-success/30 bg-accent-success/10 hover:bg-accent-success/20 transition-all text-left disabled:opacity-30 disabled:cursor-not-allowed">
            <div class="font-bold text-accent-success mb-1">获取发行版 (Release)</div>
            <div class="text-xs text-text-dim mb-2">获取作者打包的稳定版。</div>
            <div v-if="workspaceStore.github.previewInfo.has_release" class="inline-block px-2 py-0.5 bg-bg-inset/80 rounded text-[0.65rem] font-mono text-text-main">
              Latest: {{ workspaceStore.github.previewInfo.latest_release_tag }}
            </div>
            <div v-else class="text-xs text-accent-warn">该仓库尚未发布任何 Release</div>
          </button>
        </div>
        <div class="mt-4">
          <div v-if="previewReadme.isLoading" class="text-xs text-text-dim">正在读取 README...</div>
          <div v-else-if="previewReadme.error" class="text-xs text-accent-warn">{{ previewReadme.error }}</div>
          <div v-else-if="previewReadme.content" v-viewer.rebuild="imageViewerOptions" class="prose prose-sm prose-invert max-w-none text-text-dim" v-html="renderMarkdown(previewReadme.content)"></div>
        </div>
      </div>

      <!-- 推荐项详情 -->
      <div v-else-if="selectedCatalogItem" class="flex-1 flex flex-col bg-bg-inset/70 border border-border-base/10 rounded-2xl overflow-hidden shadow-xl">
        <div class="p-6 bg-bg-overlay/5 border-b border-border-base/10 flex items-start justify-between gap-4">
          <div class="min-w-0">
            <h2 class="text-2xl font-black text-text-main truncate">{{ catalogDisplayName(selectedCatalogItem) }}</h2>
            <div class="flex flex-wrap gap-2 mt-2">
              <span class="px-2 py-1 rounded bg-bg-inset/90 text-[0.65rem] font-mono text-text-dim">{{ catalogSourceName(selectedCatalogItem.source_id) || selectedCatalogItem.category }}</span>
              <span class="px-2 py-1 rounded bg-bg-inset/90 text-[0.65rem] font-mono text-text-dim">{{ catalogHostLabel(selectedCatalogItem) }}</span>
              <span v-if="selectedCatalogItem.workshop_url" class="px-2 py-1 rounded bg-accent-primary/10 text-[0.65rem] text-accent-primary">Workshop</span>
              <span v-if="isOfficialCatalogItem(selectedCatalogItem)" v-tooltip="availabilityTooltip(selectedCatalogItem)" class="px-2 py-1 rounded bg-accent-primary/10 text-[0.65rem] text-accent-primary">官方内容</span>
              <span v-if="selectedCatalogItem.not_recommended" v-tooltip="availabilityTooltip(selectedCatalogItem)" class="px-2 py-1 rounded bg-accent-warn/10 text-[0.65rem] text-accent-warn">当前不建议使用</span>
              <span v-if="catalogUpdatedText(selectedCatalogItem)" class="px-2 py-1 rounded bg-bg-inset/90 text-[0.65rem] font-mono text-text-dim">{{ catalogUpdatedText(selectedCatalogItem) }}</span>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button v-if="selectedCatalogItem.workshop_url" @click.stop="toggleWorkshopSubscription(selectedCatalogItem)" :disabled="isWorkshopBusy"
              v-tooltip="isWorkshopSubscribed(selectedCatalogItem) ? '取消订阅创意工坊' : '订阅创意工坊'"
              class="p-3 rounded-xl transition-colors disabled:opacity-40"
              :class="workshopActionButtonClass(selectedCatalogItem)">
              <FlagOff v-if="isWorkshopSubscribed(selectedCatalogItem)" class="size-4" />
              <Flag v-else class="size-4" />
            </button>
            <button v-if="!isOfficialCatalogItem(selectedCatalogItem)" @click.stop="subscribeRecommendedItem(selectedCatalogItem)"
              :disabled="!isInstallable(selectedCatalogItem) || subscribedRepoUrls.has(selectedCatalogItem.url) || isParsing"
              v-tooltip="recommendedActionTooltip(selectedCatalogItem)"
              class="p-3 rounded-xl disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              :class="gitActionButtonClass(selectedCatalogItem)">
              <ListPlus class="size-4" />
            </button>
            <button v-if="selectedCatalogItem.info_url || selectedCatalogItem.url" @click.stop="openExternal(selectedCatalogItem.info_url || selectedCatalogItem.url)"
              v-tooltip="'打开原始地址'"
              class="p-3 rounded-xl bg-bg-overlay/10 text-text-dim hover:text-text-main hover:bg-bg-overlay/10 transition-colors">
              <ExternalLink class="size-4" />
            </button>
          </div>
        </div>
        <div class="flex-1 overflow-y-auto custom-scrollbar p-6">
          <p v-if="selectedCatalogItem.description" class="text-sm text-text-dim leading-relaxed mb-4">{{ selectedCatalogItem.description }}</p>
          <div v-if="selectedCatalogItem.game_versions?.length" class="mb-4 flex flex-wrap items-center gap-1 text-[0.65rem]">
            <span class="text-text-dim mr-1">RimWorld:</span>
            <span v-for="version in catalogDisplayVersions(selectedCatalogItem.game_versions)" :key="version"
              class="px-2 py-1 rounded border"
              :class="catalogVersionClass(version)">
              {{ version }}
            </span>
          </div>
          <div class="mb-4 rounded-lg bg-bg-muted/80 border border-border-base/10 p-3">
            <div class="grid grid-cols-4 gap-3 text-xs">
              <div class="min-w-0 flex items-center gap-2">
                <div class="text-text-dim shrink-0">来源</div>
                <div class="text-text-main font-mono truncate">{{ catalogSourceName(selectedCatalogItem.source_id) || selectedCatalogItem.source_id || '-' }}</div>
              </div>
              <div class="min-w-0 flex items-center gap-2">
                <div class="text-text-dim shrink-0">安装类型</div>
                <div class="text-text-main font-mono">{{ isCatalogZipItem(selectedCatalogItem) ? 'Zip 直链' : 'Git 仓库' }}</div>
              </div>
              <div class="min-w-0 flex items-center gap-2">
                <div class="text-text-dim shrink-0">默认分支</div>
                <div class="text-text-main font-mono truncate">{{ selectedCatalogItem.branch || selectedCatalogItem.default_branch || '-' }}</div>
              </div>
              <div class="min-w-0 flex items-center gap-2">
                <div class="text-text-dim shrink-0">作者</div>
                <div class="text-text-main truncate">{{ catalogAuthorText(selectedCatalogItem) || '-' }}</div>
              </div>
            </div>
          </div>
          <div v-if="catalogDependencies.length" class="mb-4 rounded-lg bg-bg-muted/70 border border-border-base/10 p-3">
            <div class="text-xs font-bold text-text-dim uppercase tracking-widest mb-2">依赖项</div>
            <div class="flex flex-wrap gap-2">
              <span v-for="dep in catalogDependencies" :key="dep.package_id"
                v-tooltip="catalogDependencyTooltip(dep)"
                class="px-2 py-0.5 text-sm group relative rounded border font-mono cursor-default pr-2"
                :class="catalogDependencyClass(dep)">
                {{ dep.name || dep.package_id }} <span class="opacity-50 text-[0.6rem]">({{ dep.package_id }})</span>
                <div v-if="dep.kind !== 'official' && dep.kind !== 'missing'" class="absolute right-0 top-1/2 -translate-y-1/2 opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto flex gap-0.5 justify-center items-center text-[0.6rem] transition-all">
                  <button v-if="dep.kind === 'catalog'" @click.stop="subscribeRecommendedItem(dep.sourceItem)"
                    :disabled="!isInstallable(dep.sourceItem) || subscribedRepoUrls.has(dep.sourceItem?.url) || isParsing"
                    v-tooltip="subscribedRepoUrls.has(dep.sourceItem?.url) ? '该依赖已添加 Git 订阅' : '添加 Git 订阅'"
                    class="p-1.5 cursor-pointer rounded-full disabled:opacity-30 disabled:cursor-not-allowed transition-all scale-90 hover:scale-105"
                    :class="gitActionButtonClass(dep.sourceItem)">
                    <ListPlus class="size-3" />
                  </button>
                  <button v-if="dep.workshopId" @click.stop="toggleWorkshopSubscription(dep)" :disabled="isWorkshopBusy"
                    v-tooltip="isWorkshopSubscribed(dep) ? '取消订阅创意工坊依赖' : '订阅创意工坊依赖'"
                    class="p-1.5 cursor-pointer rounded-full transition-all disabled:opacity-40 scale-90 hover:scale-105"
                    :class="workshopActionButtonClass(dep)">
                    <FlagOff v-if="isWorkshopSubscribed(dep)" class="size-3" />
                    <Flag v-else class="size-3" />
                  </button>
                </div>
              </span>
            </div>
          </div>
          <div v-if="catalogReadme.isLoading" class="text-xs text-text-dim">正在读取 README...</div>
          <div v-else-if="catalogReadme.error" class="text-xs text-accent-warn">{{ catalogReadme.error }}</div>
          <div v-else-if="catalogReadme.content" v-viewer.rebuild="imageViewerOptions" class="prose prose-sm prose-invert max-w-none text-text-dim" v-html="renderMarkdown(catalogReadme.content)"></div>
        </div>
      </div>

      <!-- 选中仓库的操作面板与日志轴 -->
      <div v-else-if="workspaceStore.github.activeRepo" data-tour="workspace-github-panel" class="flex-1 flex flex-col bg-bg-inset/70 border border-border-base/10 rounded-2xl overflow-hidden shadow-xl">
        
        <!-- 操作头部 -->
        <div class="px-4 py-4 bg-bg-overlay/5 border-b border-border-base/10 flex gap-3 items-start">
          <div class="flex-1">
            <div class="flex items-center justify-between gap-0.5">
              <h2 class="text-2xl font-black text-text-main">{{ workspaceStore.github.activeRepo.repo_name }}</h2>
              <span class="px-2 py-1 rounded bg-bg-inset/90 text-[0.65rem] font-mono text-text-dim">
                当前模式: {{ workspaceStore.github.activeRepo.install_type.toUpperCase() }}
              </span>
            </div>
            
            <div class="flex gap-2 mt-2">
              
              <span class="px-2 py-1 rounded bg-bg-inset/90 text-[0.65rem] font-mono text-text-dim border border-border-base/10">
                已部署版本: {{ workspaceStore.github.activeRepo.installed_version || 'NONE' }}
              </span>
              <span class="px-2 py-1 rounded bg-bg-inset/90 text-[0.65rem] font-mono" :class="githubStatus(workspaceStore.github.activeRepo).tone">
                {{ githubStatus(workspaceStore.github.activeRepo).label }}<template v-if="githubStatus(workspaceStore.github.activeRepo).version"> ({{ githubStatus(workspaceStore.github.activeRepo).version }})</template>
              </span>
            </div>
          </div>
          
          <!-- 一键更新/部署按钮 -->
          <div class="flex items-center gap-2">
            <button @click="openRepoOriginal(workspaceStore.github.activeRepo)" v-tooltip="'打开原始地址'"
              class="p-3 rounded-xl bg-bg-overlay/10 text-text-dim hover:text-text-main hover:bg-bg-overlay/10 transition-colors">
              <ExternalLink class="size-4" />
            </button>
            <button v-if="workspaceStore.github.activeRepo.local_path || workspaceStore.github.activeRepo.local_folder" @click="openRepoLocal(workspaceStore.github.activeRepo)" v-tooltip="'打开本地目录'"
              class="p-3 rounded-xl bg-bg-overlay/10 text-text-dim hover:text-text-main hover:bg-bg-overlay/10 transition-colors">
              <FolderOpen class="size-4" />
            </button>
            <button @click="checkAndUpdate" :disabled="isChecking" v-tooltip="'获取并部署当前订阅'"
              class="px-4 py-3 rounded-xl bg-accent-success text-on-accent-success font-black text-sm shadow-[0_0_15px_rgba(var(--rgb-accent-success),0.3)] hover:scale-105 active:scale-95 transition-all flex items-center gap-2 disabled:opacity-50">
              <CloudDownload class="size-4" :class="{'animate-bounce': isChecking}" />
              {{ workspaceStore.github.activeRepo.installed_version ? '获取并部署最新' : '立即部署' }}
            </button>
          </div>
        </div>

        <!-- 本地日志时间线 (Timeline) -->
        <div class="flex-1 overflow-y-auto custom-scrollbar p-6 relative">
          <h4 class="text-xs font-bold text-text-dim uppercase tracking-widest mb-6 flex items-center gap-2">
            <Activity class="size-4" /> 本地执行追踪 (Local Audit Log)
          </h4>

          <div class="relative pl-4">
            <!-- 轨道线 -->
            <div class="absolute left-0.5 top-2 bottom-0 w-px bg-linear-to-b from-text-main/30 to-transparent"></div>
            
            <div v-for="(log, i) in workspaceStore.github.repoTimelines" :key="i" class="mb-6 relative group">
              <!-- 节点圆点 -->
              <div class="absolute -left-[1.2rem] top-1.5 size-3 rounded-full border-2 bg-bg-deep z-10 transition-transform group-hover:scale-150" 
                :class="getLogColor(log.type)"></div>
              
              <div class="flex items-center gap-2">
                <span class="text-xs font-mono text-text-dim">{{ formatDate(log.time) }}</span>
                <span class="px-1.5 py-0.5 rounded text-[0.7rem] font-black uppercase" :class="getLogBgColor(log.type)">
                  {{ log.title }}
                </span>
              </div>
              <div class="text-sm text-text-soft mt-1 leading-relaxed">{{ log.desc }}</div>
            </div>
            
            <div v-if="workspaceStore.github.repoTimelines.length === 0" class="text-sm text-text-disabled italic">
              暂无追踪记录
            </div>
          </div>
        </div>

      </div>

      <!-- 闲置空状态 -->
      <div v-else class="flex-1 flex flex-col items-center justify-center opacity-20 border-2 border-dashed border-border-base/18 rounded-2xl">
        <Github class="size-24 mb-4" />
        <span class="text-sm font-black uppercase tracking-widest">Select or Add a Repository</span>
      </div>

    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { Activity, CloudDownload, ExternalLink, Flag, FlagOff, FolderOpen, Github, Link, ListPlus, RefreshCw, Search, Trash2 } from 'lucide-vue-next'
import { useToast } from 'vue-toastification'
import { useAppStore } from '../../../app/stores/appStore'
import { useWorkspaceStore } from '../workspaceStore'
import { useProfileStore } from '../../profiles/profileStore'
import { checkResult, toUserMessage } from '../../../shared/lib/common'
import { imageViewerOptions } from '../../../shared/lib/domEffects'
import { renderMarkdownContent } from '../../../shared/lib/markdown'
import { isOfficialPackageId } from '../../mod/lib/packageScope'
import CommonSelect from '../../../shared/components/input/CommonSelect.vue'
import { useConfirmStore } from '../../../shared/components/modal/confirmStore'

const toast = useToast()
const appStore = useAppStore()
const workspaceStore = useWorkspaceStore()
const profileStore = useProfileStore()
const confirmStore = useConfirmStore()

const newRepoUrl = ref('')
const isParsing = ref(false)
const isChecking = ref(false)
const isWorkshopBusy = ref(false)
const listMode = ref('subscribed')
const catalogFilter = ref('')
const catalogSourceFilter = ref('all')
const selectedCatalogItem = ref(null)
const catalogReadme = ref({
  isLoading: false,
  content: '',
  error: '',
})
const previewReadme = ref({
  isLoading: false,
  content: '',
  error: '',
})
const catalogDependencies = ref([])
const catalogSelectionSeq = ref(0)

const subscribedRepoUrls = computed(() => new Set(
  workspaceStore.github.subscribedRepos.map(repo => String(repo.repo_url || '').trim())
))
const catalogSourceOptions = computed(() => [
  { value: 'all', label: '全部' },
  ...(workspaceStore.github.catalogMeta.sources || []).map(source => ({
    value: String(source.id || ''),
    label: String(source.label || source.name || source.id || '清单'),
  })).filter(source => source.value)
])
const catalogSourceLabelMap = computed(() => Object.fromEntries(
  (workspaceStore.github.catalogMeta.sources || [])
    .map(source => [String(source.id || ''), String(source.label || source.name || source.id || '')])
    .filter(([id]) => id)
))
const filteredRecommendedRepos = computed(() => {
  const keyword = catalogFilter.value.trim().toLowerCase()
  const sourceId = catalogSourceFilter.value
  const items = workspaceStore.github.recommendedRepos || []
  return items.filter(item => {
    if (sourceId !== 'all' && String(item.source_id || '') !== sourceId) return false
    if (!keyword) return true
    const haystack = [
      item.name,
      item.package_id,
      ...(catalogVersions(item.game_versions)),
      catalogAuthorText(item),
    ].join(' ').toLowerCase()
    return haystack.includes(keyword)
  })
})

onBeforeUnmount(() => {
  workspaceStore.stopGithubTimelinePolling()
})

const resolveMarkdownImageUrl = (url) => /^https?:\/\//i.test(String(url || '')) ? appStore.getRemoteUrl(url) : url
const renderMarkdown = (text) => renderMarkdownContent(text, { resolveImageUrl: resolveMarkdownImageUrl })

const setListMode = async (mode) => {
  listMode.value = mode
  if (mode === 'recommend') await workspaceStore.fetchGithubProviderCatalog()
}

// 解析新仓库链接
const parseNewRepo = async () => {
  if (!newRepoUrl.value) return
  isParsing.value = true
  previewReadme.value = { isLoading: false, content: '', error: '' }
  try {
    const res = await window.pywebview.api.github_fetch_info(newRepoUrl.value)
    if (checkResult(res, "解析 Git 仓库链接")) {
      workspaceStore.github.previewInfo = res.data
      await loadRepoReadme(newRepoUrl.value, res.data?.latest_source_branch || res.data?.default_branch || '', previewReadme)
    }
  } finally {
    isParsing.value = false
  }
}

const openExternal = (url) => {
  if (!url) return
  appStore.openUrl(url)
}

const joinPath = (base, child) => {
  const normalizedBase = String(base || '').trim()
  const normalizedChild = String(child || '').trim()
  if (!normalizedBase || !normalizedChild) return ''
  const separator = normalizedBase.includes('\\') ? '\\' : '/'
  return `${normalizedBase.replace(/[\\/]+$/, '')}${separator}${normalizedChild.replace(/^[\\/]+/, '')}`
}

const openRepoOriginal = (repo) => {
  openExternal(repo?.repo_url)
}

const openRepoLocal = (repo) => {
  const path = repo?.local_path || joinPath(appStore.settings.self_mods_path, repo?.local_folder)
  if (path) appStore.openPath(path)
}

const formatInstallType = (type) => {
  if (type === 'release') return 'Release'
  if (type === 'zip') return 'Zip'
  return 'Source'
}

const isCatalogZipItem = (item) => String(item?.type || '').toLowerCase() === 'zip'
const isOfficialCatalogItem = (item) => isOfficialPackageId(item?.package_id)
const catalogDisplayName = (item) => String(item?.name || item?.package_id || item?.url || '').trim()
const catalogSourceName = (sourceId) => catalogSourceLabelMap.value[String(sourceId || '')] || ''
const catalogAuthorText = (item) => {
  const author = item?.author
  const authorText = Array.isArray(author) ? author.filter(Boolean).join(', ') : String(author || '').trim()
  return authorText || inferProjectAuthor(item?.url || item?.raw_url)
}
const inferProjectAuthor = (url) => {
  try {
    const parsed = new URL(String(url || ''))
    const parts = parsed.pathname.replace(/\.git$/i, '').split('/').filter(Boolean)
    if (parsed.hostname.toLowerCase() === 'github.com') return parts[0] || ''
    const projectParts = parts.includes('-') ? parts.slice(0, parts.indexOf('-')) : parts
    return projectParts.length > 1 ? projectParts.slice(0, -1).join('/') : ''
  } catch {
    return ''
  }
}
const formatDate = (value) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
const catalogUpdatedText = (item) => {
  const value = item?.published_at || item?.released_at || item?.latest_release_published_at || item?.latest_source_commit_at || item?.updated_at || item?.remote_last_modified || ''
  const formatted = formatDate(value)
  if (!formatted) return ''
  return (item?.published_at || item?.released_at || item?.latest_release_published_at) ? `发布: ${formatted}` : `更新: ${formatted}`
}
const repoPreviewTimeText = (info) => {
  const releaseTime = formatDate(info?.latest_release_published_at)
  if (releaseTime) return `发布: ${releaseTime}`
  const sourceTime = formatDate(info?.latest_source_commit_at)
  return sourceTime ? `更新: ${sourceTime}` : ''
}
const catalogItemTooltip = (item) => {
  const lines = [
    catalogDisplayName(item),
    item?.description ? String(item.description).trim() : '',
    item?.package_id ? `包名: ${item.package_id}` : '',
    catalogAuthorText(item) ? `作者: ${catalogAuthorText(item)}` : '',
    catalogUpdatedText(item),
  ].filter(Boolean)
  return lines.join('\n')
}
const catalogHostLabel = (item) => {
  const host = safeUrlHost(item?.url || item?.raw_url)
  return host || String(item?.type || '').trim() || '-'
}
const safeUrlHost = (url) => {
  try {
    return new URL(String(url || '')).host
  } catch {
    return ''
  }
}
const isInstallable = (item) => {
  if (isOfficialCatalogItem(item)) return false
  const type = String(item?.type || '').toLowerCase()
  return !!(item?.url || item?.raw_url) && (!type || type === 'git' || type === 'zip')
}

const formatAvailability = (item) => {
  if (isOfficialCatalogItem(item)) return '官方内容'
  if (item?.not_recommended) return '当前不建议使用'
  if (!isInstallable(item)) return '暂不支持'
  return ''
}

const availabilityTooltip = (item) => {
  if (isOfficialCatalogItem(item)) return '游戏本体或官方 DLC 不需要订阅'
  if (item?.not_recommended) return '该项目可能暂时不兼容，建议确认说明后再添加'
  if (!isInstallable(item)) return '该项目缺少可用下载地址'
  return ''
}

const currentGameShortVersion = computed(() => String(profileStore.activeContext?.game_version || '').match(/^\d+\.\d+/)?.[0] || '')

const catalogVersions = (versions = []) => {
  const values = Array.isArray(versions) ? versions.map(version => String(version || '').trim()).filter(Boolean) : []
  return [...new Set(values)].sort((left, right) => {
    const compared = compareVersionText(left, right)
    return compared || left.localeCompare(right)
  })
}

const catalogDisplayVersions = (versions = []) => {
  const values = catalogVersions(versions)
  if (values.length < 6) return values
  return [`${values[0]} - ${values[values.length - 3]}`, ...values.slice(-2)]
}

const parseVersionSegments = (version) => {
  const match = String(version || '').match(/\d+(?:\.\d+)*/)
  if (!match) return []
  return match[0].split('.').map(part => Number.parseInt(part, 10))
}

const compareVersionText = (left, right) => {
  const leftParts = parseVersionSegments(left)
  const rightParts = parseVersionSegments(right)
  if (!leftParts.length || !rightParts.length) return 0
  const maxLength = Math.max(leftParts.length, rightParts.length)
  for (let index = 0; index < maxLength; index += 1) {
    const diff = (leftParts[index] || 0) - (rightParts[index] || 0)
    if (diff !== 0) return diff
  }
  return 0
}

const versionEquals = (left, right) => {
  const leftParts = parseVersionSegments(left)
  const rightParts = parseVersionSegments(right)
  if (!leftParts.length || !rightParts.length) return false
  return compareVersionText(left, right) === 0
}

const catalogVersionMatchesCurrent = (version) => {
  const text = String(version || '')
  if (text.includes('-')) return false
  return versionEquals(text, currentGameShortVersion.value)
}

const catalogVersionClass = (version) => (
  catalogVersionMatchesCurrent(version)
    ? 'bg-accent-success/70 text-on-accent-success border-accent-success'
    : 'bg-bg-inset/80 text-text-dim border-border-base/10'
)

const githubStatus = (repo) => repo?.status || workspaceStore.getGithubRepoStatus(repo)

const recommendedActionTooltip = (item) => {
  if (isOfficialCatalogItem(item)) return '游戏本体或官方 DLC 不需要订阅'
  if (!isInstallable(item)) return '该项目缺少可用下载地址'
  if (subscribedRepoUrls.value.has(item.url)) return '已添加 Git 订阅'
  return isCatalogZipItem(item) ? '添加为 Git 订阅并部署 zip' : '添加为 Git 订阅'
}

const gitActionButtonClass = (item) => {
  if (subscribedRepoUrls.value.has(item?.url)) return 'bg-accent-primary/10 text-accent-primary'
  if (!isInstallable(item)) return 'bg-bg-overlay/10 text-text-dim'
  return 'bg-accent-primary/15 text-accent-primary hover:bg-accent-primary hover:text-on-accent-primary'
}

const workshopActionButtonClass = (item) => {
  if (isWorkshopSubscribed(item)) return 'bg-accent-danger/15 text-accent-danger hover:bg-accent-danger hover:text-on-accent-danger'
  return 'bg-accent-success/15 text-accent-success hover:bg-accent-success hover:text-on-accent-success'
}

const extractWorkshopId = (url) => {
  const match = String(url || '').match(/[?&]id=(\d+)/) || String(url || '').match(/\/(\d+)(?:[/?#]|$)/)
  return match ? match[1] : ''
}

const isWorkshopSubscribed = (item) => {
  const workshopId = getWorkshopId(item)
  return !!workshopId && workspaceStore.subscribedWorkshopIds.has(workshopId)
}

const toggleWorkshopSubscription = async (item) => {
  const workshopId = getWorkshopId(item)
  if (!workshopId || isWorkshopBusy.value) return
  isWorkshopBusy.value = true
  try {
    const success = isWorkshopSubscribed(item)
      ? await appStore.unsubscribeWorkshopIds([workshopId])
      : await appStore.subscribeWorkshopIds([workshopId])
    if (success) await workspaceStore.fetchLibrariesMods()
  } finally {
    isWorkshopBusy.value = false
  }
}

const getWorkshopId = (item) => {
  return String(item?.workshopId || item?.workshop_id || extractWorkshopId(item?.workshop_url) || '').trim()
}

const loadRepoReadme = async (url, branch, targetRef) => {
  targetRef.value = { isLoading: false, content: '', error: '' }
  if (!url) return
  targetRef.value.isLoading = true
  try {
    const res = await window.pywebview.api.github_fetch_readme(url, branch || '')
    if (res?.status === 'success') {
      targetRef.value.content = String(res.data?.content || '')
      targetRef.value.error = ''
    } else {
      targetRef.value.error = toUserMessage(res?.message, '读取 README 失败。请检查网络连接、仓库地址和分支名称后重试。')
    }
  } catch (error) {
    console.warn('读取 Git 仓库 README 失败:', error)
    targetRef.value.error = toUserMessage(error?.message || error, '读取 README 失败。请检查网络连接、仓库地址和分支名称后重试。')
  } finally {
    targetRef.value.isLoading = false
  }
}

const loadCatalogItemRemoteInfo = async (item, selectionSeq) => {
  if (isCatalogZipItem(item) || !item?.url || !window.pywebview) return
  try {
    const res = await window.pywebview.api.github_fetch_info(item.url, item.branch || '')
    if (catalogSelectionSeq.value !== selectionSeq || selectedCatalogItem.value?.url !== item.url) return
    if (res?.status !== 'success') return
    const patch = {
      latest_release_published_at: res.data?.latest_release_published_at || '',
      latest_source_commit_at: res.data?.latest_source_commit_at || '',
      default_branch: res.data?.default_branch || selectedCatalogItem.value?.branch || '',
    }
    Object.assign(item, patch)
    selectedCatalogItem.value = {
      ...selectedCatalogItem.value,
      ...patch,
    }
  } catch {
    // 推荐项详情的时间是补充信息，失败时保持清单原始内容即可。
  }
}

const resolveCatalogDependencies = async (item) => {
  const deps = buildCatalogDependenciesFromPackageIds(item)
  if (deps.length === 0) {
    catalogDependencies.value = []
    return
  }
  const externalIds = deps
    .filter(dep => dep.kind !== 'catalog' && dep.kind !== 'official')
    .map(dep => dep.package_id)
  const workshopMap = await workspaceStore.getWorkshopDetailsByPackageIdsMap(externalIds)
  catalogDependencies.value = deps.map(dep => {
    const packageId = String(dep.package_id || '').toLowerCase()
    if (isOfficialPackageId(packageId)) {
      return { ...dep, kind: 'official', name: dep.name || '官方内容' }
    }
    const workshop = workshopMap[packageId]
    if (dep.kind === 'catalog') return dep
    if (workshop?.workshopId) {
      return {
        ...dep,
        kind: 'workshop',
        name: workshop.title || dep.package_id,
        workshopId: workshop.workshopId,
        workshop_url: workshop.url || `https://steamcommunity.com/sharedfiles/filedetails/?id=${workshop.workshopId}`,
      }
    }
    return { ...dep, kind: 'missing', name: dep.package_id }
  })
}

const buildCatalogDependenciesFromPackageIds = (item) => {
  const packageIds = Array.isArray(item?.depends) ? item.depends : []
  if (packageIds.length === 0) return []
  const sourceId = String(item?.source_id || '')
  const catalogItems = workspaceStore.github.recommendedRepos || []
  return packageIds.map(packageId => {
    const normalizedId = String(packageId || '').trim().toLowerCase()
    if (isOfficialPackageId(normalizedId)) {
      return { package_id: packageId, kind: 'official', name: '官方内容' }
    }
    const matched = catalogItems.find(candidate => {
      if (sourceId && String(candidate.source_id || '') !== sourceId) return false
      return String(candidate.package_id || '').trim().toLowerCase() === normalizedId
    })
    if (!matched) return { package_id: packageId, kind: 'external' }
    return {
      package_id: packageId,
      kind: 'catalog',
      name: catalogDisplayName(matched) || packageId,
      sourceItem: matched,
    }
  })
}

const catalogDependencyClass = (dep) => {
  if (dep.kind === 'official') return 'border-accent-primary/20 bg-accent-primary/10 text-accent-primary'
  if (dep.kind === 'missing') return 'border-accent-danger/30 bg-accent-danger/10 text-accent-danger'
  if (dep.kind === 'workshop') return isWorkshopSubscribed(dep)
    ? 'border-accent-primary/30 bg-accent-primary/20 text-accent-primary'
    : 'border-border-base/10 bg-bg-overlay/10 text-text-dim'
  if (dep.kind === 'catalog') return subscribedRepoUrls.value.has(dep.sourceItem?.url)
    ? 'border-accent-primary/30 bg-accent-primary/20 text-accent-primary'
    : 'border-border-base/10 bg-bg-overlay/10 text-text-dim'
  return 'border-border-base/10 bg-bg-overlay/10 text-text-dim'
}

const catalogDependencyTooltip = (dep) => {
  const lines = [`包名: ${dep.package_id}`]
  if (dep.kind === 'official') lines.push('游戏本体或官方 DLC，不需要订阅')
  else if (dep.kind === 'catalog') lines.push(subscribedRepoUrls.value.has(dep.sourceItem?.url) ? '已添加 Git 订阅' : '可添加 Git 订阅')
  else if (dep.kind === 'workshop') lines.push(isWorkshopSubscribed(dep) ? '已订阅创意工坊' : '可订阅创意工坊')
  else if (dep.kind === 'missing') lines.push('没有找到可直接添加的来源')
  return lines.join('\n')
}

const selectRecommendedItem = async (item) => {
  const selectionSeq = catalogSelectionSeq.value + 1
  catalogSelectionSeq.value = selectionSeq
  selectedCatalogItem.value = item || null
  workspaceStore.clearActiveGithubRepo()
  workspaceStore.github.previewInfo = null
  previewReadme.value = { isLoading: false, content: '', error: '' }
  catalogReadme.value = { isLoading: false, content: '', error: '' }
  catalogDependencies.value = []
  if (!item) return
  await Promise.all([
    resolveCatalogDependencies(item),
    loadCatalogItemRemoteInfo(item, selectionSeq),
    !isCatalogZipItem(item) && item.url ? loadRepoReadme(item.url, item.branch || '', catalogReadme) : Promise.resolve(),
  ])
}

const subscribeRecommendedItem = async (item) => {
  if (isOfficialCatalogItem(item)) return
  if (isCatalogZipItem(item)) {
    await subscribeCatalogZip(item)
    return
  }
  await useRecommendedRepo(item)
}

// 从 provider 清单选中一个 Git 仓库，先走现有解析预览，再由用户选择 Source/Release。
const useRecommendedRepo = async (item) => {
  if (!isInstallable(item) || subscribedRepoUrls.value.has(item.url)) return
  isParsing.value = true
  try {
    const res = await window.pywebview.api.github_fetch_info(item.url, item.branch || '')
    if (checkResult(res, "解析推荐仓库")) {
      newRepoUrl.value = item.url
      selectedCatalogItem.value = null
      workspaceStore.clearActiveGithubRepo()
      workspaceStore.github.previewInfo = {
        ...res.data,
        suggested_branch: item.branch || res.data.latest_source_branch || res.data.default_branch,
        catalog_item: item,
      }
      await loadRepoReadme(item.url, item.branch || res.data.latest_source_branch || res.data.default_branch || '', previewReadme)
    }
  } finally {
    isParsing.value = false
  }
}

// zip 直链没有远程仓库元数据，订阅记录直接保存清单项本身，后续用签名判断是否变化。
const subscribeCatalogZip = async (item) => {
  if (!isInstallable(item) || subscribedRepoUrls.value.has(item.url)) return
  const payload = {
    url: item.url,
    owner: item.source_id || 'catalog',
    repo: item.name || item.package_id || 'catalog_mod',
    provider: 'catalog_zip',
    host: safeUrlHost(item.raw_url || item.url),
    default_branch: '',
    install_type: 'zip',
    installed_version: '',
    info: item,
  }
  const res = await window.pywebview.api.github_subscribe(payload)
  if (checkResult(res, "建立清单订阅")) {
    toast.success("清单项已成功订阅")
    workspaceStore.fetchGithubRepos()
  }
}

// 确认订阅仓库
const confirmSubscribe = async (type) => {
  const info = workspaceStore.github.previewInfo
  if (!info) return
  const payload = {
    url: newRepoUrl.value,
    owner: info.owner,
    repo: info.repo,
    provider: info.provider,
    host: info.host,
    default_branch: info.suggested_branch || info.latest_source_branch || info.default_branch,
    install_type: type,
    installed_version: '',
    info: info,
  }
  const res = await window.pywebview.api.github_subscribe(payload)
  if (checkResult(res, "建立订阅")) {
    workspaceStore.github.previewInfo = null
    selectedCatalogItem.value = null
    previewReadme.value = { isLoading: false, content: '', error: '' }
    newRepoUrl.value = ''
    toast.success("仓库已成功订阅")
    workspaceStore.fetchGithubRepos()
  }
}

// 选择仓库
const selectRepo = async (repo) => {
  selectedCatalogItem.value = null
  await workspaceStore.selectGithubRepo(repo)
}


// 移除仓库订阅
const removeRepo = async (url) => {
  const repo = workspaceStore.github.subscribedRepos.find(item => item.repo_url === url)
  const ok = await confirmStore.confirmAction(
    '移除订阅',
    `确定要移除 Git 订阅「${repo?.repo_name || url}」吗？\n本地已下载文件不会被删除。`,
    { type: 'error', confirmText: '移除' }
  )
  if (!ok) return
  const res = await window.pywebview.api.github_remove_subscription(url)
  if (checkResult(res, "移除订阅")) {
    if (workspaceStore.github.activeRepo?.repo_url === url) {
      workspaceStore.clearActiveGithubRepo()
    }
    workspaceStore.fetchGithubRepos()
  }
}

// 检查并更新仓库
const checkAndUpdate = async () => {
  const repo = workspaceStore.github.activeRepo
  if (!repo) return
  isChecking.value = true
  try {
    if (repo.install_type === 'zip') {
      const dlRes = await window.pywebview.api.github_trigger_download(repo.repo_url, repo.install_type, repo.online_info?.catalog_signature || '')
      if (checkResult(dlRes, "请求数据传输")) {
        toast.info("已开始获取数据流，请在底部状态栏查看进度", {timeout: 4000})
        workspaceStore.startGithubTimelinePolling(repo.repo_url, { intervalMs: 4000, maxPolls: 15 })
      }
      return
    }
    // 1. 获取最新信息 (看是否有新版本)
    const infoRes = await window.pywebview.api.github_fetch_info(
      repo.repo_url,
      repo.install_type === 'source' ? (repo.target_branch || '') : ''
    )
    let targetVersion = repo.target_branch
    if (infoRes.status === 'success') {
      if (repo.install_type === 'release') {
        targetVersion = infoRes.data.latest_release_tag
      } else {
        targetVersion = infoRes.data.latest_source_branch || repo.target_branch
      }
    } else if (repo.install_type === 'release') {
      targetVersion = repo.online_info?.latest_release_tag || ''
      if (!targetVersion) {
        toast.error("无法获取 Release 版本信息，当前也没有可用缓存")
        return
      }
      toast.warning("Git 仓库信息查询失败，已改用本地缓存的 Release 版本继续部署")
    } else {
      targetVersion = repo.target_branch || repo.online_info?.latest_source_branch || 'main'
      toast.warning("Git 仓库信息查询失败，已跳过元数据刷新，直接按当前分支继续部署")
    }
    // 2. 触发下载引擎 (带着钩子)
    const dlRes = await window.pywebview.api.github_trigger_download(repo.repo_url, repo.install_type, targetVersion)
    if (checkResult(dlRes, "请求数据传输")) {
      toast.info("已开始获取数据流，请在底部状态栏查看进度", {timeout: 4000})
      workspaceStore.startGithubTimelinePolling(repo.repo_url, { intervalMs: 4000, maxPolls: 15 })
    }
  } finally {
    isChecking.value = false
  }
}


// 日志色彩解析
const getLogColor = (action) => {
  if (action === 'error') return 'border-accent-danger'
  if (action === 'success') return 'border-accent-success shadow-[0_0_10px_var(--color-accent-success)]'
  if (action === 'download' || action === 'extract') return 'border-accent-primary animate-pulse'
  return 'border-border-base/18'
}

const getLogBgColor = (action) => {
  if (action === 'error') return 'bg-accent-danger/20 text-accent-danger'
  if (action === 'success') return 'bg-accent-success/20 text-accent-success'
  if (action === 'download' || action === 'extract') return 'bg-accent-primary/20 text-accent-primary'
  return 'bg-bg-overlay/10 text-text-main'
}
</script>

<style scoped>
:deep(.prose) { line-height: 1.65; }
:deep(.prose h1), :deep(.prose h2), :deep(.prose h3) {
  color: var(--color-text-main);
  font-weight: 800;
  margin: 1rem 0 0.5rem;
}
:deep(.prose p), :deep(.prose ul), :deep(.prose ol) { margin: 0.65rem 0; }
:deep(.prose a) { color: var(--color-accent-primary); text-decoration: underline; }
:deep(.prose pre) {
  margin: 0.75rem 0;
  padding: 0.75rem;
  overflow-x: auto;
  background-color: var(--color-bg-inset);
  border: 1px solid var(--color-border-subtle);
  border-radius: 0.5rem;
}
</style>
<!-- END OF FILE -->
