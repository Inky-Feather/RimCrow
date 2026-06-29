<!-- src/components/workspace/views/WorkshopBrowser.vue -->
<template>
  <div class="grid h-full grid-cols-[minmax(360px,38%)_minmax(0,1fr)] gap-4 overflow-hidden p-4 max-[1180px]:grid-cols-[minmax(330px,40%)_minmax(0,1fr)]">
    
    <!-- 左侧：检索与结果 -->
    <section class="relative flex min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl border border-border-base/10 bg-bg-inset/80 shadow-2xl" data-tour="workspace-workshop-results">
      <div class="relative z-20 flex shrink-0 flex-col gap-3 border-b border-border-base/10 bg-bg-muted/70 p-4" data-tour="workspace-workshop-search">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0 flex items-center gap-5">
            <div class="flex items-center gap-2 text-md font-bold text-accent-primary">
              <Globe class="size-3.5" />
              <span>{{ workshopSourceTitle }}</span>
            </div>
            <span class="font-mono text-sm text-text-soft">{{ workshopDisplayTotal }} 项结果</span>
          </div>
          <div class="flex items-center gap-2">
            
            <CommonSwitch v-model="workspaceStore.workshopSearch.isEnhancedMode" :mini="true" :disabled="!workshopSearchReady" @change="toggleEnhancedMode"
              label="增强模式" description="开启后使用专用接口获取更完整的工坊信息；关闭该功能后，系统会依靠本地缓存工坊库以及公开接口来读取工坊相关信息；受本地缓存库的局限，查询到的结果并不完整，也无法获取刚发布的最新模组。" />
          </div>
        </div>

        <TagSearchInput class="min-w-0" ref="workshopSearchInputRef" list-color="primary"
          v-model="workspaceStore.workshopSearch.queryTokens" v-model:logic="workspaceStore.workshopSearch.queryLogic"
          :controller="workshopSearchController" :placeholder="workshopSearchPlaceholder" :input-help-text="workshopInputHelpText"
          @search="triggerSearchNow">
          <template #icon>
            <Search class="size-3.5 text-text-dim" />
          </template>
          <template #right>
            <div class="flex items-center justify-center gap-1">
              <button @click="submitWorkshopSearch" :disabled="!workshopSearchReady || workspaceStore.workshopSearch.isLoading"
                class="inline-flex h-[1.85rem] shrink-0 items-center justify-center rounded-lg border border-accent-primary/40 bg-accent-primary/15 px-2.5 text-[0.7rem] font-extrabold text-accent-primary transition-all hover:bg-accent-primary hover:text-on-accent-primary active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50">
                搜索
              </button>
              <button ref="advancedButtonRef" @click="toggleAdvancedPanel" v-tooltip="'排序与高级搜索'"
                class="inline-flex h-[1.85rem] shrink-0 items-center justify-center gap-1.5 rounded-lg border border-border-base/10 bg-bg-inset/85 px-2.5 text-[0.7rem] text-text-dim transition-all hover:border-accent-primary/40 hover:text-accent-primary active:scale-[0.98]">
                <SlidersHorizontal class="size-3.5" />
                <span class="max-w-24 truncate text-[0.7rem] font-bold">{{ workshopSortStateLabel }}</span>
              </button>
            </div>
          </template>
        </TagSearchInput>


        <!-- 高级面板使用 FixedPopover，避免左侧列表区域裁剪或挤占结果列表高度。 -->
        <FixedPopover :is-open="workspaceStore.workshopSearch.advancedOpen" :trigger-ref="advancedButtonRef"
          :min-width="320" :max-width="340" :max-height="420" :offset="6" @request-close="closeAdvancedPanel" >
          <div ref="advancedPanelRef" class="popover-surface w-80 rounded-xl border border-border-base/18 bg-bg-surface/98 p-3 text-xs">
            <div class="flex flex-col gap-3">
            <template v-if="workspaceStore.workshopSearch.isEnhancedMode">
              <CommonSelect v-model="workspaceStore.workshopSearch.language" :options="languageOptions" label="查询语言" mini class="min-w-0" />
              <CommonSelect v-model="workspaceStore.workshopSearch.searchTextTarget" :options="WORKSHOP_TEXT_TARGET_OPTIONS" label="查询范围" mini class="min-w-0" />
            </template>
            <div v-else class="rounded-lg border border-border-base/10 bg-bg-inset/60 px-2 py-1.5 text-xs text-text-dim">
              缓存搜索使用本地数据库内容，不支持查询语言和查询范围。
            </div>
            <div class="border-t border-border-base/10 pt-3">
              <div class="mb-1.5 text-[0.7rem] font-black text-text-main">排序</div>
              <div class="grid grid-cols-2 gap-4">
                <div class="space-y-1">
                  <div class="text-[0.65rem] font-bold text-text-dim">顺序</div>
                  <button v-for="option in workshopSortPanelOptions" :key="option.value" type="button"
                    class="flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left transition-colors"
                    :class="[
                      isWorkshopSortOptionDisabled(option) ? 'text-text-disabled cursor-not-allowed opacity-45' : 'hover:text-text-main',
                      !isWorkshopSortOptionDisabled(option) && workshopActiveSortValue === option.value ? 'text-text-main' : 'text-text-dim'
                    ]"
                    :disabled="isWorkshopSortOptionDisabled(option)"
                    @click="selectWorkshopSort(option.value)" v-tooltip="option.desc || option.label">
                    <span class="size-3 rounded-full border"
                      :class="!isWorkshopSortOptionDisabled(option) && workshopActiveSortValue === option.value ? 'border-accent-primary bg-accent-primary shadow-[0_0_8px_currentColor]' : 'border-text-disabled bg-text-disabled/20'"></span>
                    <span>{{ option.label }}</span>
                  </button>
                </div>
                <div class="space-y-1">
                  <div class="text-[0.65rem] font-bold text-text-dim">时间</div>
                  <button v-for="option in WORKSHOP_DAY_RANGE_OPTIONS" :key="option.value" type="button"
                    class="flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left transition-colors"
                    :class="[
                      isWorkshopDayOptionDisabled(option) ? 'text-text-disabled cursor-not-allowed opacity-45' : 'hover:text-text-main',
                      !isWorkshopDayOptionDisabled(option) && Number(workspaceStore.workshopSearch.days) === option.value ? 'text-text-main' : 'text-text-dim'
                    ]"
                    :disabled="isWorkshopDayOptionDisabled(option)"
                    @click="selectWorkshopDays(option.value)">
                    <span class="size-3 rounded-full border"
                      :class="!isWorkshopDayOptionDisabled(option) && Number(workspaceStore.workshopSearch.days) === option.value ? 'border-accent-primary bg-accent-primary shadow-[0_0_8px_currentColor]' : 'border-text-disabled bg-text-disabled/20'"></span>
                    <span>{{ option.label }}</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
          </div>
        </FixedPopover>
        <div v-if="workshopDisplayBanner" class="flex items-center justify-between gap-2 rounded-xl border border-accent-primary/20 bg-accent-primary/10 px-3 py-2 text-xs">
          <span class="min-w-0 truncate font-bold text-accent-primary">{{ workshopDisplayBanner }}</span>
          <button @click="closeTransientList" class="shrink-0 rounded-lg border border-border-base/10 bg-bg-inset px-2 py-1 text-[0.65rem] font-bold text-text-dim transition-colors hover:text-text-main">
            返回搜索结果
          </button>
        </div>
      </div>

      <!-- 列表内容区 -->
      <div class="content-surface relative flex-1 overflow-hidden">
        
        <!-- 首次加载大遮罩 -->
        <div v-if="workshopDisplayLoading && workshopDisplayResults.length === 0" class="absolute inset-0 z-10 flex flex-col items-center justify-center bg-bg-deep/50 text-accent-primary backdrop-blur-sm">
          <div class="mb-3 size-9 rounded-full border-2 border-current border-t-transparent animate-spin"></div>
          <span class="text-xs font-bold tracking-[0.18em]">{{ workshopLoadingText }}</span>
        </div>

        <!-- 动态高度虚拟列表 -->
        <DynamicScroller v-if="workshopDisplayResults.length > 0"
          ref="scrollerRef" class="h-full custom-scrollbar bg-bg-inset/75 p-2.5" :items="workshopDisplayResults" :min-item-size="itemMinHeight" key-field="workshop_id"
          @scroll="handleScroll" >
          <template #default="{ item, index, active }">
            <DynamicScrollerItem :item="item" :active="active" :size-dependencies="[item.title, item.short_description, item.package_id, item.tags?.length, item.game_versions?.length]" :data-index="index">
            <div class="pb-2">
              <div @click="selectMod(item)" v-tooltip="buildResultTooltip(item)"
                class="group relative flex min-h-[4.7rem] cursor-pointer items-center gap-3 overflow-hidden rounded-[0.85rem] border border-border-base/5 bg-bg-surface/55 p-[0.65rem] transition-all hover:-translate-y-px hover:border-accent-primary/25 hover:bg-accent-primary/10"
                :class="workspaceStore.workshopSearch.selectedId === item.workshop_id ? 'border-accent-primary/40 bg-accent-primary/15 shadow-[inset_3px_0_0_var(--color-accent-primary),0_12px_28px_rgba(6,182,212,0.08)]' : ''">
                <div v-if="workspaceStore.workshopSearch.isEnhancedMode" class="size-[3.45rem] shrink-0 overflow-hidden rounded-xl border border-border-base/10 bg-bg-inset/90">
                  <img v-if="item.preview_url" class="h-full w-full object-cover" loading="lazy" :src="appStore.getRemoteUrl(item.preview_url)" :alt="item.display_title || item.title || item.name || '工坊项目封面'" />
                  <div v-else class="flex h-full w-full items-center justify-center text-text-disabled">
                    <Image class="size-4" />
                  </div>
                </div>
                <span v-if="getWorkshopItemStatus(item.workshop_id).isSubscribed"
                  class="absolute left-2 top-2 rounded-md border border-accent-primary/30 bg-accent-primary/90 px-1.5 py-0.5 text-[0.58rem] font-black text-on-accent-primary shadow-lg">
                  已订阅
                </span>
                <WorkshopItemActions :workshop-id="item.workshop_id" :show-unsubscribe="getWorkshopItemStatus(item.workshop_id).isSubscribed"
                  colorful size="xs" class="absolute right-2 top-2 z-5 pointer-events-none opacity-0 transition-opacity duration-200 group-hover:pointer-events-auto group-hover:opacity-100" />

                <div class="min-w-0 flex-1 space-y-1.5">
                  <div v-if="item.shows_translated_title" class="truncate text-[0.64rem] font-bold leading-none text-text-dim">
                    {{ item.original_title }}
                  </div>
                  <div class="truncate text-sm font-bold leading-snug transition-colors"
                    :class="workspaceStore.workshopSearch.selectedId === item.workshop_id ? 'text-text-main' : 'text-text-soft group-hover:text-accent-primary'">
                    {{ item.display_title || item.title || item.name || '未知模组' }}
                  </div>
                  <div class="flex items-center justify-between gap-2">
                    <div class="flex min-w-0 items-center gap-1.5">
                      <span class="min-w-0 truncate font-mono text-[0.68rem] text-text-dim" :title="item.package_id || item.author_label || item.display_description || ''">
                        {{ item.package_id || item.author_label || item.display_description || 'N/A' }}
                      </span>
                      <span v-for="version in item.game_versions.slice(0, 3)" :key="`${item.workshop_id}-${version}`"
                        class="shrink-0 rounded-md border border-accent-primary/20 bg-accent-primary/10 px-1.5 py-0.5 text-[0.58rem] font-black text-accent-primary">
                        {{ version }}
                      </span>
                    </div>
                    <div class="flex shrink-0 items-center gap-1 text-[0.68rem]">
                      <span v-if="item.stats?.subscriptions" class="rounded-md border border-accent-primary/20 bg-accent-primary/10 px-1.5 py-0.5 font-bold text-accent-primary" v-tooltip="'订阅人数'">
                        {{ formatCount(item.stats.subscriptions) }}
                      </span>
                      <div class="rounded-md border border-border-base/10 bg-bg-inset/80 px-1.5 py-0.5 font-mono font-bold text-text-dim" v-tooltip="'工坊ID'">
                        {{ item.workshop_id }}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            </DynamicScrollerItem>
          </template>

          <!-- 滚动到底部的 Loading 指示器 (插槽) -->
          <template #after>
            <!-- 修复：加入 isLocalFetching 判定，防止网络请求结束后 Loading 瞬间消失导致高度坍塌 -->
            <div v-if="(workshopDisplayLoading && workshopDisplayResults.length > 0) || isLocalFetching" class="flex items-center justify-center py-4 text-text-dim">
              <div class="mr-2 size-4 rounded-full border-2 border-accent-primary border-t-transparent animate-spin"></div>
              <span class="text-xs">加载更多...</span>
            </div>
            <div v-else-if="!workshopDisplayHasMore && workshopDisplayResults.length > 0" class="py-4 text-center text-xs text-text-disabled">
              已显示全部结果
            </div>
          </template>
        </DynamicScroller>

        <!-- 空状态 -->
        <div v-else-if="!workshopDisplayLoading" class="absolute inset-0 flex flex-col items-center justify-center px-8 text-center text-text-disabled">
          <Cpu class="mb-4 size-14 opacity-45" />
          <span class="text-sm font-bold tracking-[0.18em] text-text-dim">暂无结果</span>
          <span class="mt-2 max-w-xs text-xs leading-5 text-text-subtle">换一个关键词、标签或排序条件再试。</span>
        </div>

      </div>
    </section>

    <!-- 右侧：详情展示 -->
    <section class="relative flex min-h-0 min-w-0 flex-col overflow-hidden rounded-2xl border border-border-base/10 bg-bg-inset/80 shadow-2xl" data-tour="workspace-workshop-detail">
      
      <template v-if="selectedMod">
        <!-- 顶部导航面包屑/后退栏 -->
        <div v-if="workspaceStore.workshopSearch.historyStack.length > 0" class="absolute left-4 top-4 z-20 flex items-center">
          <button @click="workspaceStore.goBackWorkshopDetail" class="flex items-center gap-1 rounded-xl border border-border-base/18 bg-bg-inset/80 px-3 py-1.5 text-xs font-bold text-text-main shadow-lg backdrop-blur-md transition-all hover:border-accent-primary/50 hover:text-accent-primary">
            <svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
            返回上一层
          </button>
        </div>
        <!-- 头部 Banner -->
        <div class="group relative h-[clamp(10rem,18vh,13.5rem)] shrink-0 overflow-hidden border-b border-border-base/10">
          <!-- 背景 -->
          <div class="absolute inset-0 z-0 overflow-hidden">
            <img v-if="selectedPreviewUrl" :src="selectedPreviewUrl" :alt="selectedDisplayTitle || '工坊项目背景'"
              class="h-full w-full scale-[1.03] object-cover object-center opacity-74 blur-[10px] transition-[filter,transform,opacity] duration-700 group-hover:blur-[18px] group-hover:opacity-86 group-hover:brightness-70" />
            <div v-else class="h-full w-full bg-bg-inset/95"></div>
          </div>
          <!-- 上下阴影遮罩 -->
          <div class="pointer-events-none absolute inset-0 z-1 bg-linear-to-r from-bg-deep/4 via-bg-deep/16 to-bg-deep/50"></div>
          <div class="pointer-events-none absolute inset-0 z-2 bg-linear-to-t from-bg-deep/40 via-bg-deep/14 to-transparent"></div>
          <!-- 封面图片 -->
          <div v-if="selectedPreviewUrl" v-viewer.rebuild="imageViewerOptions" class="absolute left-0 top-0 z-3 h-full w-fit overflow-hidden pointer-events-auto" :style="headerPreviewWrapStyle" >
            <div class="relative inline-block h-full">
              <img :src="selectedPreviewUrl" :alt="selectedDisplayTitle || '工坊项目封面'" class="block h-full w-auto max-w-none cursor-zoom-in select-none" />
              <img :src="selectedPreviewUrl" aria-hidden="true" class="pointer-events-none absolute inset-0 block h-full w-auto max-w-none blur-[20px]" :style="headerPreviewBlurStyle" />
            </div>
          </div>
          <div v-else class="absolute left-0 top-0 z-3 h-full aspect-4/3 bg-bg-inset/50"></div>
          <!-- 项目名称及数据 -->
          <div class="absolute inset-y-0 left-[25%] right-0 z-4 flex flex-col justify-center gap-2 px-5 py-4 text-text-main">
            <!-- 原始名称（仅在翻译后出现） -->
            <span v-if="selectedShowsTranslatedTitle" class="flex items-center justify-start gap-2 -my-2 pl-3 text-text-dim">
              <button type="button" v-tooltip="'点击可复制项目名称'" class="hover:text-accent-primary scale-95 hover:scale-105 active:scale-95 transition-all duration-300"
                @click.stop="copyHeaderValue('原始名称', selectedOriginalTitle)">
                <Copy class="size-3" />
              </button> 
              <span class="min-w-0 text-xs font-black leading-tight text-balance text-shadow-md"  v-tooltip="selectedOriginalTitle">
                {{ selectedOriginalTitle }}
              </span>
            </span>
            <!-- 项目名称（优先显示翻译） -->
            <span class="flex items-center justify-start gap-2">
              <button type="button" v-tooltip="'点击可复制项目名称'" class="hover:text-accent-primary scale-95 hover:scale-105 active:scale-95 transition-all duration-300"
                @click.stop="copyHeaderValue('项目名称', selectedDisplayTitle)">
                <Copy class="size-6" />
              </button> 
              <h2 class="min-w-0 text-[1.75rem] font-black leading-tight text-balance text-shadow-lg" v-tooltip="selectedDisplayTitle">
                {{ selectedDisplayTitle }}
              </h2>
            </span>
            <!-- 项目信息 -->
            <div class="flex flex-wrap items-center gap-1.5 pointer-events-auto">
              <button type="button" v-tooltip="'Steam 工坊项目的唯一编号。单击可复制。'" class="group relative workshop-detail-chip border-accent-primary/20 bg-accent-primary/10 pr-7 text-left transition-colors hover:border-accent-primary/36 hover:bg-accent-primary/14 active:scale-[0.99]" @click.stop="copyHeaderValue('工坊 ID', selectedIdLabel)">
                <Hash class="workshop-detail-chip__icon text-accent-primary" />
                <span class="workshop-detail-chip__title">工坊 ID</span>
                <span class="workshop-detail-chip__value">{{ selectedIdLabel }}</span>
                <Copy class="size-3 text-text-dim " />
              </button>
              <button type="button" v-tooltip="'模组包标识。通常用于本地规则匹配和同模组识别。单击可复制。'" class="group relative workshop-detail-chip border-accent-cool/20 bg-accent-cool/10 pr-7 text-left transition-colors hover:border-accent-cool/30 hover:bg-accent-cool/12 active:scale-[0.99]" @click.stop="copyHeaderValue('包名', selectedPackageId)">
                <Package class="workshop-detail-chip__icon text-accent-cool" />
                <span class="workshop-detail-chip__title">包名</span>
                <span class="workshop-detail-chip__value">{{ selectedPackageId }}</span>
                <Copy class="size-3 text-text-dim " />
              </button>
              <button type="button" v-tooltip="'作者名称。增强模式下优先显示作者资料缓存中的公开名称。单击可复制。'" class="group relative workshop-detail-chip border-accent-success/20 bg-accent-success/10 pr-7 text-left transition-colors hover:border-accent-success/30 hover:bg-accent-success/12 active:scale-[0.99]" @click.stop="copyHeaderValue('作者', selectedAuthorLabel)">
                <UserRound class="workshop-detail-chip__icon text-accent-success" />
                <span class="workshop-detail-chip__title">作者</span>
                <span class="workshop-detail-chip__value">{{ selectedAuthorLabel }}</span>
                <Copy class="size-3 text-text-dim " />
              </button>
            </div>
            <div class="flex flex-wrap items-center gap-1.5 pointer-events-auto">
              <span v-tooltip="'当前 Steam 工坊公开订阅人数。'" class="workshop-detail-chip border-accent-primary/20 bg-accent-primary/10">
                <Flag class="workshop-detail-chip__icon text-accent-primary" />
                <span class="workshop-detail-chip__title">订阅数</span>
                <strong class="workshop-detail-chip__value">{{ selectedSubscriptionLabel }}</strong>
              </span>
              <span v-tooltip="'Steam 返回的综合评分。适合快速判断整体用户反馈。'" class="workshop-detail-chip border-accent-tip/22 bg-accent-tip/10">
                <Star class="workshop-detail-chip__icon text-accent-tip" />
                <span class="workshop-detail-chip__title">评分</span>
                <strong class="workshop-detail-chip__value">{{ selectedVoteScoreLabel }}</strong>
              </span>
              <span v-tooltip="'公开点赞数量。适合结合评分一起看口碑。'" class="workshop-detail-chip border-accent-success/20 bg-accent-success/10">
                <ThumbsUp class="workshop-detail-chip__icon text-accent-success" />
                <span class="workshop-detail-chip__title">点赞</span>
                <strong class="workshop-detail-chip__value">{{ selectedVoteUpLabel }}</strong>
              </span>
              <span v-tooltip="'公开点踩数量。'" class="workshop-detail-chip border-accent-danger/20 bg-accent-danger/10">
                <ThumbsDown class="workshop-detail-chip__icon text-accent-danger" />
                <span class="workshop-detail-chip__title">点踩</span>
                <strong class="workshop-detail-chip__value">{{ selectedVoteDownLabel }}</strong>
              </span>
              <span v-tooltip="'被加入收藏的次数。适合判断长期关注度。'" class="workshop-detail-chip border-accent-cool/20 bg-accent-cool/10">
                <Heart class="workshop-detail-chip__icon text-accent-cool" />
                <span class="workshop-detail-chip__title">收藏</span>
                <strong class="workshop-detail-chip__value">{{ selectedFavoriteLabel }}</strong>
              </span>
              <span v-tooltip="'Steam 工坊公开评论数量。'" class="workshop-detail-chip border-border-base/16 bg-bg-deep/38">
                <MessageSquareMore class="workshop-detail-chip__icon text-text-dim" />
                <span class="workshop-detail-chip__title">评论</span>
                <strong class="workshop-detail-chip__value">{{ selectedCommentLabel }}</strong>
              </span>
              <span v-tooltip="'Steam 返回的文件体积，可用来粗略判断下载耗时和磁盘占用。'" class="workshop-detail-chip border-border-base/16 bg-bg-deep/38">
                <HardDrive class="workshop-detail-chip__icon text-text-dim" />
                <span class="workshop-detail-chip__title">大小</span>
                <strong class="workshop-detail-chip__value">{{ selectedFileSizeLabel }}</strong>
              </span>
              <span v-tooltip="'项目首次发布到 Steam 工坊的时间。'" class="workshop-detail-chip border-border-base/16 bg-bg-deep/38">
                <CalendarPlus class="workshop-detail-chip__icon text-text-dim" />
                <span class="workshop-detail-chip__title">创建</span>
                <strong class="workshop-detail-chip__value">{{ selectedCreatedLabel }}</strong>
              </span>
              <span v-tooltip="'项目最近一次在 Steam 工坊更新的时间。'" class="workshop-detail-chip border-border-base/16 bg-bg-deep/38">
                <CalendarArrowUp class="workshop-detail-chip__icon text-text-dim" />
                <span class="workshop-detail-chip__title">更新</span>
                <strong class="workshop-detail-chip__value">{{ selectedUpdatedLabel }}</strong>
              </span>
              <span v-if="selectedStatusLabel" v-tooltip="'项目当前状态异常。通常表示该项目已被 Steam 限制或封禁。'" class="workshop-detail-chip border-accent-danger/20 bg-accent-danger/10">
                <ShieldAlert class="workshop-detail-chip__icon text-accent-danger" />
                <span class="workshop-detail-chip__title">状态</span>
                <strong class="workshop-detail-chip__value">{{ selectedStatusLabel }}</strong>
              </span>
              <span v-if="selectedContentWarningLabel" v-tooltip="'项目被 Steam 标记为可能含有敏感内容，展示前建议自行确认。'" class="workshop-detail-chip border-accent-warn/24 bg-accent-warn/12">
                <TriangleAlert class="workshop-detail-chip__icon text-accent-warn" />
                <span class="workshop-detail-chip__title">内容</span>
                <strong class="workshop-detail-chip__value">{{ selectedContentWarningLabel }}</strong>
              </span>
              <span v-for="tag in selectedDisplayTags" :key="`${selectedId}-${tag}`"
                v-tooltip="`工坊标签：${tag}`" class="workshop-detail-chip border-accent-cool/20 bg-accent-cool/10">
                <Tag class="workshop-detail-chip__icon text-accent-cool" />
                <span class="workshop-detail-chip__title">标签</span>
                <strong class="workshop-detail-chip__value">{{ tag }}</strong>
              </span>
              <span v-if="!selectedDisplayTags.length" v-tooltip="'该项目没有返回可展示的工坊标签。'" class="workshop-detail-chip border-accent-cool/20 bg-accent-cool/10">
                <Tag class="workshop-detail-chip__icon text-accent-cool" />
                <span class="workshop-detail-chip__title">标签</span>
                <strong class="workshop-detail-chip__value">-</strong>
              </span>
              <span v-if="selectedHiddenTagCount > 0" v-tooltip="selectedHiddenTagTooltip" class="workshop-detail-chip border-border-base/16 bg-bg-deep/38">
                <Plus class="workshop-detail-chip__icon text-text-dim" />
                <strong class="workshop-detail-chip__value">+{{ selectedHiddenTagCount }}</strong>
              </span>
              <span v-tooltip="'该项目标注的 RimWorld 适用版本。这里会合并后端缓存和标签中的版本信息。'" class="workshop-detail-chip border-accent-tip/22 bg-accent-tip/10">
                <Layers class="workshop-detail-chip__icon text-accent-tip" />
                <span class="workshop-detail-chip__title">版本</span>
                <strong class="workshop-detail-chip__value">{{ selectedVersionSummary }}</strong>
              </span>
            </div>
          </div>
          <!-- 操作按钮 -->
          <WorkshopItemActions :workshop-id="selectedId" class="absolute right-3 top-3 z-5 pointer-events-none group-hover:pointer-events-auto opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
        </div>

        <!-- 内容区 -->
        <div ref="detailScrollRef" class="content-surface custom-scrollbar flex-1 overflow-y-auto p-5">
          <!-- 依赖提示框 (如果是解析得到的) -->
          <div v-if="relatedDependencies.length > 0 || (workspaceStore.workshopSearch.relatedLoading.dependencies && selectedMod?.item_type !== 'collection')" data-tour="workspace-workshop-dependencies"
            class="mb-4 rounded-2xl border border-accent-warn/25 bg-accent-warn/8 py-2 px-3">
            <div class="mb-3 flex items-center justify-between gap-3">
              <h4 class="flex items-center gap-1.5 text-[0.72rem] font-black text-accent-warn">
                <Link class="size-3" /> 依赖项目
              </h4>
              <span v-if="workspaceStore.workshopSearch.relatedLoading.dependencies" class="text-[0.65rem] text-text-dim">加载中...</span>
              <div class="flex flex-wrap justify-end gap-1.5">
                <button @click="handleUnsubscribe(dependencyIds)" :disabled="isDependencyActionPending('unsubscribe')" :class="isDependencyActionPending('unsubscribe') ? 'app-action-disabled' : ''"
                  class="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-accent-danger/30 bg-accent-danger/15 px-2.5 py-1.5 text-[0.65rem] font-extrabold text-accent-danger transition-all hover:bg-accent-danger hover:text-on-accent-danger active:scale-[0.98]">
                  <LoaderCircle v-if="isDependencyActionPending('unsubscribe')" class="size-3 animate-spin" />
                  {{ isDependencyActionPending('unsubscribe') ? '取消中' : '取消订阅全部依赖' }}
                </button>
                <button @click="handleSubscribe(dependencyIds)" :disabled="isDependencyActionPending('subscribe')" :class="isDependencyActionPending('subscribe') ? 'app-action-disabled' : ''"
                  class="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-accent-primary/30 bg-accent-primary/15 px-2.5 py-1.5 text-[0.65rem] font-extrabold text-accent-primary transition-all hover:bg-accent-primary hover:text-on-accent-primary active:scale-[0.98]">
                  <LoaderCircle v-if="isDependencyActionPending('subscribe')" class="size-3 animate-spin" />
                  {{ isDependencyActionPending('subscribe') ? '订阅中' : '订阅全部依赖' }}
                </button>
                <button @click="handleDownload(dependencyIds)" :disabled="isDependencyActionPending('download')" :class="isDependencyActionPending('download') ? 'app-action-disabled' : ''"
                  class="inline-flex cursor-pointer items-center gap-1 rounded-lg border border-accent-success/30 bg-accent-success/15 px-2.5 py-1.5 text-[0.65rem] font-extrabold text-accent-success transition-all hover:bg-accent-success hover:text-on-accent-success active:scale-[0.98]">
                  <LoaderCircle v-if="isDependencyActionPending('download')" class="size-3 animate-spin" />
                  {{ isDependencyActionPending('download') ? '下载中' : '下载全部依赖' }}
                </button>
              </div>
            </div>
            <!-- 依赖项目列表 -->
            <div class="flex gap-2 overflow-x-auto custom-scrollbar snap-x">
              <MiniModCard v-for="mod in relatedDependencies" :key="mod.workshop_id" :mod="mod" class="snap-start" @navigate="handleNavigateInside" />
            </div>
          </div>

          <!-- 游戏截图画廊 (Horizontal Scroll) -->
          <div v-if="selectedMod?.screenshots?.length > 0" class="mb-4 space-y-3 rounded-2xl border border-border-base/10 bg-bg-inset/45 p-4">
            <h4 class="flex items-center gap-1.5 text-[0.72rem] font-black text-text-dim">
              <Image class="size-3" /> 截图
            </h4>
            <!-- 使用 flex nowrap 和 overflow-x-auto 实现横向滚动 -->
            <div v-viewer.rebuild="imageViewerOptions" class="flex gap-3 overflow-x-auto custom-scrollbar pb-2 snap-x">
              <div v-for="(img, idx) in selectedMod.screenshots" :key="idx"
                class="relative h-36 w-64 shrink-0 snap-start overflow-hidden rounded-xl border border-border-base/10 bg-bg-inset/80" >
                <div v-if="!loadedScreenshotMap[img]" class="absolute inset-0 flex items-center justify-center bg-bg-inset/90" >
                  <svg viewBox="0 0 160 96" class="h-12 w-20 text-text-disabled" fill="none" aria-hidden="true">
                    <rect x="10" y="10" width="140" height="76" rx="10" stroke="currentColor" stroke-width="4" stroke-dasharray="6 6" />
                    <circle cx="48" cy="38" r="10" fill="currentColor" class="opacity-60" />
                    <path d="M24 72L58 48L80 66L106 42L136 72" stroke="currentColor" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" class="opacity-70" />
                  </svg>
                </div>
                <img class="h-full w-full object-cover transition-transform hover:scale-[1.02] cursor-zoom-in"
                  :src="appStore.getRemoteUrl(img)" :alt="`${selectedDisplayTitle || '工坊项目'}截图`" @load="markScreenshotLoaded(img)" @error="markScreenshotLoaded(img)" />
              </div>
            </div>
          </div>
          <!-- 描述内容 -->
          <div v-if="selectedMod" class="mb-2 flex justify-end">
            <TranslationFeatureControls feature="workshop_detail" :button-label="selectedTranslationLanguageLabel" :settings-tooltip="translationSettingsTooltip"
              :language-options="translationLanguageOptions" :display-language="workspaceStore.workshopSearch.detailTranslationLanguage" :display-language-options="translationDisplayOptions"
              show-display-language show-quick :quick-label="translationQuickLabel" :quick-tooltip="translationQuickTooltip"
              :is-translated="!!selectedTranslationEntry" :is-translating="workspaceStore.workshopSearch.isTranslating" :is-stale="selectedTranslationStale"
              :can-retranslate="!!selectedResolvedTranslationLanguage" :can-clear="!!selectedTranslationEntry"
              @update:display-language="selectTranslationDisplayLanguage" @toggle="handleToggleWorkshopTranslation" @retranslate="handleRetranslateCurrentLanguage" @clear="handleClearCurrentTranslation" />
          </div>
          <div v-viewer.rebuild="imageViewerOptions" class="prose prose-invert prose-sm md:prose-base max-w-none select-text px-2 prose-a:text-accent-primary prose-img:rounded-xl">
            <div v-if="parsedDescription" v-html="parsedDescription"></div>
            <div v-else class="text-text-dim italic">该模组没有提供详细描述。</div>
          </div>
          <!-- Steam 详情数据 -->
          <div v-if="hasRichSteamDetails" class="mt-4 space-y-2 rounded-2xl border border-border-base/10 bg-bg-inset/45 p-4">
            <h4 class="flex items-center gap-1.5 text-[0.72rem] font-black text-accent-tip">
              <SlidersHorizontal class="size-3" /> Steam 详情数据
            </h4>
            <div class="grid grid-cols-2 gap-2 text-xs">
              <div v-if="selectedMod?.kv_tags?.length" class="col-span-2 flex flex-wrap gap-1.5 rounded-xl border border-border-base/10 bg-bg-inset/70 p-2">
                <span v-for="tag in selectedMod.kv_tags" :key="`${tag.key || tag.name}-${tag.value}`"
                  class="rounded border border-border-base/10 bg-bg-overlay/20 px-1.5 py-0.5 text-[0.65rem] text-text-dim">
                  {{ tag.key || tag.name }}={{ tag.value }}
                </span>
              </div>
            </div>
          </div>
          <!-- 合集子项 -->
          <div v-if="relatedCollectionChildren.length > 0 || (selectedMod?.item_type === 'collection' && workspaceStore.workshopSearch.relatedLoading.dependencies)" class="mt-4 space-y-3 rounded-2xl border border-border-base/10 bg-bg-inset/45 p-4">
            <div class="flex items-center justify-between gap-2">
              <h4 class="flex items-center gap-1.5 text-[0.72rem] font-black text-accent-tip">
                <Link class="size-3" /> 合集子项
              </h4>
              <span v-if="workspaceStore.workshopSearch.relatedLoading.dependencies" class="text-[0.65rem] text-text-dim">加载中...</span>
            </div>
            <div class="flex flex-wrap gap-2">
              <button v-for="child in relatedCollectionChildren" :key="child.workshop_id" v-tooltip="buildResultTooltip(child)"
                class="rounded-lg border border-border-base/10 bg-bg-inset/80 px-2.5 py-1.5 text-xs text-text-soft transition-colors hover:border-accent-primary/40 hover:text-accent-primary"
                @click="handleNavigateInside(child.workshop_id)" >
                {{ child.display_title || child.title || child.name || child.workshop_id }}
              </button>
            </div>
          </div>

          <!-- 反向依赖推荐 (有谁依赖了我) -->
          <div v-if="relatedDependents.length > 0 || workspaceStore.workshopSearch.relatedLoading.dependents || workspaceStore.workshopSearch.relatedErrors.dependents" class="mt-4 space-y-3 rounded-2xl border border-border-base/10 bg-bg-inset/45 p-4">
            <div class="flex items-center justify-between gap-2">
              <h4 class="flex items-center gap-1.5 text-[0.72rem] font-black text-accent-primary">
                <Network class="size-3" /> 生态关联
              </h4>
              <button v-if="workspaceStore.workshopSearch.relatedMeta.dependents.total > relatedDependents.length"
                @click="showRelatedList('dependents')" class="rounded-lg border border-border-base/10 bg-bg-inset px-2 py-1 text-[0.65rem] font-bold text-text-dim hover:text-accent-primary">
                查看全部
              </button>
              <span v-else-if="workspaceStore.workshopSearch.relatedLoading.dependents" class="text-[0.65rem] text-text-dim">加载中...</span>
            </div>
            <div v-if="workspaceStore.workshopSearch.relatedErrors.dependents" class="text-xs text-accent-danger">{{ workspaceStore.workshopSearch.relatedErrors.dependents }}</div>
            <div class="flex gap-3 overflow-x-auto custom-scrollbar pb-2 snap-x">
              <MiniModCard v-for="mod in relatedDependents" :key="mod.workshop_id" :mod="mod" class="snap-start" 
                @navigate="handleNavigateInside" />
            </div>
          </div>

          <!-- 同作者作品 -->
          <div v-if="relatedSameAuthor.length > 0 || workspaceStore.workshopSearch.relatedLoading.same_author || workspaceStore.workshopSearch.relatedErrors.same_author" class="mt-4 space-y-3 rounded-2xl border border-border-base/10 bg-bg-inset/45 p-4">
            <div class="flex items-center justify-between gap-2">
              <h4 class="flex items-center gap-1.5 text-[0.72rem] font-black text-accent-success">
                <User class="size-3" /> 同作者作品
              </h4>
              <button v-if="workspaceStore.workshopSearch.relatedMeta.same_author.total > relatedSameAuthor.length"
                @click="showRelatedList('same_author')" class="rounded-lg border border-border-base/10 bg-bg-inset px-2 py-1 text-[0.65rem] font-bold text-text-dim hover:text-accent-success">
                查看全部
              </button>
              <span v-else-if="workspaceStore.workshopSearch.relatedLoading.same_author" class="text-[0.65rem] text-text-dim">加载中...</span>
            </div>
            <div v-if="workspaceStore.workshopSearch.relatedErrors.same_author" class="text-xs text-accent-danger">{{ workspaceStore.workshopSearch.relatedErrors.same_author }}</div>
            <div class="flex gap-3 overflow-x-auto custom-scrollbar pb-2 snap-x">
              <MiniModCard v-for="mod in relatedSameAuthor" :key="mod.workshop_id" :mod="mod" class="snap-start" @navigate="handleNavigateInside" />
            </div>
          </div>

        </div>
      </template>

      <!-- 加载遮罩 -->
      <div v-if="workspaceStore.workshopSearch.isDetailLoading && !selectedMod" class="absolute inset-0 bg-bg-deep flex flex-col items-center justify-center z-50">
        <div class="relative flex items-center justify-center">
          <div class="size-16 border-2 border-border-base/10 rounded-full"></div>
          <div class="absolute size-16 border-2 border-accent-primary border-t-transparent rounded-full animate-spin"></div>
          <Globe class="size-6 text-accent-primary absolute animate-pulse" />
        </div>
        <span class="text-xs font-mono text-text-dim mt-6 tracking-widest">从 Steam 获取详情中...</span>
      </div>
      <div v-else-if="!selectedMod" class="flex h-full flex-col items-center justify-center px-8 text-center text-text-disabled">
        <Globe class="mb-4 size-16 opacity-35" />
        <div class="text-base font-bold text-text-dim">选择一个工坊项目查看详情</div>
        <div class="mt-2 max-w-sm text-xs leading-5 text-text-subtle">左侧结果会保留搜索和排序状态，点击项目后可查看说明、依赖、截图和关联项目。</div>
      </div>

    </section>

  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css' // 确保引入 CSS
import { Search, Globe, Cpu, Download, Link, Flag, FlagOff, LoaderCircle, Network, User, Image, Layers, UserRound, SlidersHorizontal, Star, ThumbsUp, ThumbsDown, HardDrive, ShieldAlert, TriangleAlert, Heart, Hash, Copy, Tag, Plus, MessageSquareMore, Package, CalendarPlus, CalendarArrowUp } from 'lucide-vue-next'
import { useAppStore } from '../../../app/stores/appStore'
import { useTaskStore } from '../../../app/stores/taskStore'
import { toast } from '../../../shared/lib/common'
import { cleanRichText, parseUnityRichText } from '../../../shared/lib/text'
import { imageViewerOptions } from '../../../shared/lib/domEffects'
import { useWorkspaceStore } from '../workspaceStore'
import MiniModCard from '../components/MiniModCard.vue'
import CommonSwitch from '../../../shared/components/input/CommonSwitch.vue'
import CommonSelect from '../../../shared/components/input/CommonSelect.vue'
import FixedPopover from '../../../shared/components/popover/FixedPopover.vue'
import TranslationFeatureControls from '../../../shared/components/translation/TranslationFeatureControls.vue'
import WorkshopItemActions from '../../../shared/components/WorkshopItemActions.vue'
import TagSearchInput from '../../../shared/components/tag-search/TagSearchInput.vue'
import { createTagSearchController, TAG_FIELD_TYPES } from '../../../shared/components/tag-search/tagSearchEngine'
import {
  WORKSHOP_DAY_RANGE_OPTIONS, WORKSHOP_SORT_OPTIONS, WORKSHOP_TEXT_TARGET_OPTIONS,
  allowsWorkshopUntilNow, formatWorkshopSortStateLabel, hasWorkshopSearchText, resolveWorkshopSortSelection, supportsWorkshopDayRange,
} from '../workshopSearchOptions'

const appStore = useAppStore()
const taskStore = useTaskStore()
const workspaceStore = useWorkspaceStore()

const workshopSearchInputRef = ref(null)
const advancedButtonRef = ref(null)
const advancedPanelRef = ref(null)
const scrollerRef = ref(null)
const detailScrollRef = ref(null)
const isLocalFetching = ref(false)  // 局部硬锁，绝对同步，防穿透
const loadedScreenshotMap = ref({})
const dependencyActionPending = ref(new Set())
const isDependencyActionPending = (action) => dependencyActionPending.value.has(action)
const setDependencyActionPending = (action, pending) => {
  const next = new Set(dependencyActionPending.value)
  if (pending) next.add(action)
  else next.delete(action)
  dependencyActionPending.value = next
}
const versionTagPattern = /^\d+(?:\.\d+)+$/
const normalSortOptions = [
  { label: '最近更新', value: 'latest' },
  { label: '最多订阅', value: 'subscriptions' },
  { label: '名称排序', value: 'name' },
  { label: '作者排序', value: 'author' },
]
const languageOptions = computed(() => workspaceStore.workshopSearch.languageOptions)
const translationLanguageOptions = computed(() => languageOptions.value
  .map(item => ({ label: item.label, value: item.code || item.value }))
  .filter(item => item.value))
const translationDisplayOptions = computed(() => [
  { label: workspaceStore.getTranslationLanguageLabel('follow_ui'), value: 'follow_ui' },
  { label: '原文', value: '' },
  ...translationLanguageOptions.value,
])
const translationProviderOptions = computed(() => (
  appStore.translationProviders.map(item => ({ label: item.label || item.id, value: item.id }))
))
const workshopSearchReady = computed(() => !!workspaceStore.workshopSearch.isModeReady)
const workshopSourceTitle = computed(() => {
  if (!workshopSearchReady.value) return '读取工坊设置'
  return workspaceStore.workshopSearch.isEnhancedMode ? '增强工坊搜索' : '缓存工坊搜索'
})
const workshopSortPanelOptions = computed(() => (
  workspaceStore.workshopSearch.isEnhancedMode ? WORKSHOP_SORT_OPTIONS : normalSortOptions
))
const knownTagOptions = computed(() => ([
  { label: 'Mod（普通模组）', value: 'Mod' },
  { label: 'Translation（翻译）', value: 'Translation' },
  { label: 'Scenario（剧本）', value: 'Scenario' },
  ...['1.6', '1.5', '1.4', '1.3', '1.2', '1.1', '1.0'].map(version => ({ label: version, value: version })),
]))
const workshopSearchPlaceholder = computed(() => (
  workspaceStore.workshopSearch.isEnhancedMode
    ? '搜索工坊，支持 t:标签 d:DLC_AppID m:依赖工坊ID'
    : '搜索缓存，支持 t:标签 d:DLC_AppID m:依赖工坊ID a:作者'
))
const workshopTokenSchema = computed(() => {
  const schema = {
    text: { type: TAG_FIELD_TYPES.STRING, label: '搜索文本', alias: ['q', 'text'], suggest: true, defaultSearch: true },
    tag: { type: TAG_FIELD_TYPES.LIST, label: '标签', alias: ['t', 'tag'], suggest: true },
    dlc: { type: TAG_FIELD_TYPES.STRING, label: 'DLC依赖', alias: ['d', 'dlc'], suggest: true },
    dependency: { type: TAG_FIELD_TYPES.STRING, label: '模组依赖', alias: ['m', 'mod', 'dep'], suggest: false },
  }
  if (!workspaceStore.workshopSearch.isEnhancedMode) {
    schema.author = { type: TAG_FIELD_TYPES.STRING, label: '作者', alias: ['a', 'author'], suggest: false }
  }
  return schema
})
const workshopTokenValueOptions = computed(() => ({
  tag: knownTagOptions.value,
  dlc: workspaceStore.workshopSearch.dlcOptions.map(item => ({ label: item.label, value: String(item.appid) })),
}))
const workshopSearchController = computed(() => createTagSearchController({
  schema: workshopTokenSchema.value,
  valueOptions: workshopTokenValueOptions.value,
}))
const workshopInputHelpText = [
  '**输入关键词并回车确认**',
  '可直接输入关键词，或使用 类别:关键词 格式',
  '搜索文本支持用英文括号约束内部条件，可使用 [[+]]、^^|^^、!!-!! 表示[[必须包含]]、^^任意匹配^^、!!排除匹配!!。',
  '例如：(红色 ^^|^^ !!-!!蓝色) 表示：匹配红色或排除蓝色。',
  '\n[[(使用 Tab 键应用输入建议)]]',
].join('\n')

// 仅在用户真正打开工坊页且当前没有任何结果时，才触发默认搜索。
onMounted(async () => {
  await workspaceStore.ensureWorkshopSearchReady()
  void workspaceStore.loadSteamLanguageOptions()
  void workspaceStore.loadTranslationProviders()
  void workspaceStore.loadWorkshopDlcOptions()
  if (workspaceStore.workshopSearch.results.length === 0) {
    void workspaceStore.doWorkshopSearch('')
  }
})

const itemMinHeight = computed(() => appStore.scalePx(72))

const selectedMod = computed(() => {
  return workspaceStore.workshopSearch.detailData
})
const selectedId = computed(() => {
  return workspaceStore.workshopSearch.selectedId
})
const workshopActiveList = computed(() => (
  workspaceStore.workshopSearch.transientList.active
    ? workspaceStore.workshopSearch.transientList
    : workspaceStore.workshopSearch
))
const workshopDisplayResults = computed(() => Array.isArray(workshopActiveList.value.items) ? workshopActiveList.value.items : (workshopActiveList.value.results || []))
const workshopDisplayTotal = computed(() => Number(workshopActiveList.value.total || 0))
const workshopDisplayLoading = computed(() => !workshopSearchReady.value || !!(workshopActiveList.value.isLoading || workshopActiveList.value.isLoadMore))
const workshopLoadingText = computed(() => (workshopSearchReady.value ? '正在检索...' : '正在读取工坊设置...'))
const workshopDisplayHasMore = computed(() => !!workshopActiveList.value.hasMore)
const workshopDisplayBanner = computed(() => (
  workspaceStore.workshopSearch.transientList.active
    ? workspaceStore.workshopSearch.transientList.title
    : ''
))
const headerPreviewWrapMask = 'linear-gradient(to right, rgba(255,255,255,1) 30%, rgba(255,255,255,1) 35%, rgba(255,255,255,0) 100%)'
const headerPreviewBlurMask = 'linear-gradient(to right, transparent 30%, transparent 35%, #000 100%)'
const headerPreviewWrapStyle = {
  WebkitMaskImage: headerPreviewWrapMask,
  maskImage: headerPreviewWrapMask,
}
const headerPreviewBlurStyle = {
  WebkitMaskImage: headerPreviewBlurMask,
  maskImage: headerPreviewBlurMask,
}
const selectedPreviewUrl = computed(() => (
  selectedMod.value?.preview_url ? appStore.getRemoteUrl(selectedMod.value.preview_url) : ''
))
const normalizeHeaderText = (value) => {
  const text = String(value ?? '').trim()
  return text && text !== '0' ? text : '-'
}
const formatHeaderCount = (value) => {
  const num = Number(value || 0)
  return Number.isFinite(num) && num > 0 ? formatCount(num) : '-'
}
const formatHeaderDate = (value) => {
  const num = Number(value || 0)
  return Number.isFinite(num) && num > 0 ? formatDate(num) : '-'
}
const formatVotePercent = (value) => {
  const score = Number(value || 0)
  if (!Number.isFinite(score) || score <= 0) return '-'
  const percent = score <= 1 ? score * 100 : score
  return `${percent >= 10 ? percent.toFixed(0) : percent.toFixed(1)}%`
}
const selectedTags = computed(() => {
  return (selectedMod.value?.tags || [])
    .filter(tag => tag && !versionTagPattern.test(String(tag)))
    .slice(0, 12)
})
const selectedIdLabel = computed(() => normalizeHeaderText(selectedId.value))
const selectedPackageId = computed(() => normalizeHeaderText(selectedMod.value?.package_id))
const selectedAuthorLabel = computed(() => normalizeHeaderText(selectedMod.value?.author || selectedMod.value?.author_steam_id))
const selectedVersionSummary = computed(() => {
  const versions = Array.isArray(selectedMod.value?.game_versions) ? selectedMod.value.game_versions.filter(Boolean) : []
  return versions.length ? versions.join(' / ') : '-'
})
const selectedFileSizeLabel = computed(() => {
  const fileSize = Number(selectedMod.value?.file_size || 0)
  return fileSize > 0 ? `${(fileSize / 1024 / 1024).toFixed(1)} MB` : '-'
})
const selectedUpdatedLabel = computed(() => formatHeaderDate(selectedMod.value?.time_updated))
const selectedCreatedLabel = computed(() => formatHeaderDate(selectedMod.value?.time_created))
const selectedSubscriptionLabel = computed(() => {
  const stats = selectedMod.value?.stats || {}
  return formatHeaderCount(stats.subscriptions)
})
const selectedVoteScoreLabel = computed(() => {
  const stats = selectedMod.value?.stats || {}
  return formatVotePercent(stats.vote_score)
})
const selectedVoteUpLabel = computed(() => {
  const stats = selectedMod.value?.stats || {}
  return formatHeaderCount(stats.votes_up)
})
const selectedVoteDownLabel = computed(() => {
  const stats = selectedMod.value?.stats || {}
  return formatHeaderCount(stats.votes_down)
})
const selectedFavoriteLabel = computed(() => {
  const stats = selectedMod.value?.stats || {}
  return formatHeaderCount(stats.favorited)
})
const selectedCommentLabel = computed(() => {
  const stats = selectedMod.value?.stats || {}
  return formatHeaderCount(stats.num_comments_public)
})
const selectedStatusLabel = computed(() => (
  selectedMod.value?.status?.banned ? '已封禁' : ''
))
const selectedOriginalTitle = computed(() => String(selectedMod.value?.original_title || selectedMod.value?.title || selectedMod.value?.name || '').trim())
const selectedOriginalDescription = computed(() => String(selectedMod.value?.original_description || selectedMod.value?.description || selectedMod.value?.short_description || '').trim())
const selectedResolvedTranslationLanguage = computed(() => (
  workspaceStore.getResolvedTranslationLanguage(workspaceStore.workshopSearch.detailTranslationLanguage)
))
const selectedTranslationEntry = computed(() => (
  workspaceStore.workshopSearch.detailTranslationLanguage
    ? workspaceStore.getWorkshopTranslationEntry(selectedMod.value?.translations, selectedResolvedTranslationLanguage.value)
    : null
))
const selectedDisplayTitle = computed(() => String(selectedTranslationEntry.value?.title || selectedOriginalTitle.value || selectedMod.value?.name || '未知模组').trim())
const selectedDisplayDescription = computed(() => String(selectedTranslationEntry.value?.description || selectedOriginalDescription.value || '').trim())
const selectedShowsTranslatedTitle = computed(() => (
  !!selectedTranslationEntry.value?.title
  && selectedDisplayTitle.value
  && selectedOriginalTitle.value
  && selectedDisplayTitle.value !== selectedOriginalTitle.value
))
const selectedTranslationLanguageLabel = computed(() => (
  workspaceStore.getTranslationLanguageLabel(workspaceStore.workshopSearch.detailTranslationLanguage)
))
const workshopTranslationSettings = computed(() => appStore.getTranslationFeatureSettings('workshop_detail'))
const selectedTranslationProviderLabel = computed(() => {
  const provider = String(workshopTranslationSettings.value.provider || 'ai.default')
  return translationProviderOptions.value.find(item => item.value === provider)?.label || provider
})
const selectedTranslationStale = computed(() => (
  !!(
    selectedTranslationEntry.value
    && selectedMod.value?.translation_source_hash
    && selectedTranslationEntry.value.source_hash
    && selectedTranslationEntry.value.source_hash !== selectedMod.value.translation_source_hash
  )
))
const translationSettingsTooltip = computed(() => (
  `${selectedTranslationStale.value ? '^^原文已更新，可重新翻译。^^\n' : ''}当前显示：${selectedTranslationLanguageLabel.value}\n当前翻译器：${selectedTranslationProviderLabel.value}\n\n点击可切换显示语言和翻译器，也可以重新翻译或清理当前译文。`
))
const translationQuickLabel = computed(() => {
  if (workspaceStore.workshopSearch.isTranslating) return '翻译'
  return selectedTranslationEntry.value ? '原文' : '翻译'
})
const translationQuickTooltip = computed(() => (
  selectedTranslationEntry.value
    ? '点击切换回工坊原文\n长按可重新翻译当前语言'
    : `点击按当前翻译目标语言显示或生成译文：${workspaceStore.getTranslationLanguageLabel(workspaceStore.getDefaultTranslationSelection())}\n长按可重新翻译当前语言`
))
const selectedContentWarningLabel = computed(() => (
  selectedMod.value?.maybe_inappropriate_sex || selectedMod.value?.maybe_inappropriate_violence ? '含敏感标记' : ''
))
const selectedDisplayTags = computed(() => selectedTags.value.slice(0, 4))
const selectedHiddenTagCount = computed(() => Math.max(0, selectedTags.value.length - selectedDisplayTags.value.length))
const selectedHiddenTagTooltip = computed(() => (
  selectedTags.value.length > selectedDisplayTags.value.length
    ? `其余标签：${selectedTags.value.slice(selectedDisplayTags.value.length).join(' / ')}`
    : ''
))
const hasRichSteamDetails = computed(() => {
  const mod = selectedMod.value || {}
  return !!(mod.kv_tags?.length || mod.playtime_stats)
})
const relatedDependencies = computed(() => selectedMod.value?.related?.dependencies || [])
const relatedDependents = computed(() => selectedMod.value?.related?.dependents || [])
const relatedSameAuthor = computed(() => selectedMod.value?.related?.same_author || [])
const relatedCollectionChildren = computed(() => selectedMod.value?.related?.collection_children || [])
const dependencyIds = computed(() => relatedDependencies.value.map(item => item.workshop_id).filter(Boolean))
// 解析富文本描述
const parsedDescription = computed(() => {
  if (!selectedDisplayDescription.value) return ''
  return parseUnityRichText(
    selectedDisplayDescription.value,
    false,
    (url) => appStore.getRemoteUrl(url),
  )
})

const formatCount = (value) => {
  const num = Number(value || 0)
  if (!num) return '0'
  if (num >= 10000) return `${(num / 10000).toFixed(1)}w`
  if (num >= 1000) return `${(num / 1000).toFixed(1)}k`
  return String(num)
}

const buildResultTooltip = (item = {}) => {
  const summary = String(item.display_description || item.short_description || item.description || '').trim()
  if (!summary) return ''
  return cleanRichText(summary, 260).replace(/\n+/g, '\n').trim()
}

const getWorkshopItemStatus = (workshopId) => workspaceStore.getModStatus(workshopId)
const isSubscribed = (workshop_ids) => {
  if (!workshop_ids.length) return false
  return workshop_ids.every(id => workspaceStore.subscribedWorkshopIds.has(id))
}
const isInstalled = (workshop_ids) => {
  if (!workshop_ids.length) return false
  return workshop_ids.every(id => workspaceStore.installedAllIds.has(id))
}
const workshopHasSearchText = computed(() => hasWorkshopSearchText(workspaceStore.workshopSearch.queryTokens))
const workshopActiveSortValue = computed(() => (
  workspaceStore.workshopSearch.isEnhancedMode
    ? resolveWorkshopSortSelection(workspaceStore.workshopSearch.sort, workshopHasSearchText.value)
    : workspaceStore.workshopSearch.sort
))
const workshopSortStateLabel = computed(() => (
  workspaceStore.workshopSearch.isEnhancedMode
    ? formatWorkshopSortStateLabel(workspaceStore.workshopSearch.sort, workspaceStore.workshopSearch.days, workshopHasSearchText.value)
    : normalSortOptions.find(option => option.value === workspaceStore.workshopSearch.sort)?.label || '最近更新'
))
const isWorkshopSortOptionDisabled = (option) => (
  workspaceStore.workshopSearch.isEnhancedMode
  && option?.value === 'relevance'
  && !workshopHasSearchText.value
)
const isWorkshopDayOptionDisabled = (option) => {
  if (!workspaceStore.workshopSearch.isEnhancedMode) return true
  if (!supportsWorkshopDayRange(workspaceStore.workshopSearch.sort, workshopHasSearchText.value)) return true
  return option.value === 0 && !allowsWorkshopUntilNow(workspaceStore.workshopSearch.sort, workshopHasSearchText.value)
}
const selectWorkshopSort = (value) => {
  if (isWorkshopSortOptionDisabled({ value })) return
  workspaceStore.workshopSearch.sort = value
}
const selectWorkshopDays = (value) => {
  workspaceStore.workshopSearch.days = value
}
const buildWorkshopAdvancedSnapshot = () => JSON.stringify({
  isEnhancedMode: workspaceStore.workshopSearch.isEnhancedMode,
  language: workspaceStore.workshopSearch.language,
  searchTextTarget: workspaceStore.workshopSearch.searchTextTarget,
  sort: workspaceStore.workshopSearch.sort,
  days: workspaceStore.workshopSearch.days,
})
const workshopAdvancedSnapshot = ref('')

const triggerSearchNow = () => {
  // 搜索时滚动条回滚到顶部
  if (scrollerRef.value) {
    scrollerRef.value.$el.scrollTop = 0
  }
  workspaceStore.closeWorkshopTransientList()
  workspaceStore.doWorkshopSearch('', false)
}
const submitWorkshopSearch = async () => {
  workshopSearchInputRef.value?.addTag?.()
  await nextTick()
  triggerSearchNow()
}
const toggleAdvancedPanel = () => {
  if (workspaceStore.workshopSearch.advancedOpen) {
    closeAdvancedPanel()
    return
  }
  // 打开时记录参数快照；关闭时只有高级参数真的改变才重新检索。
  // 这样用户只是查看面板或点外部关闭时，不会触发一次多余的 Steam 请求。
  workshopAdvancedSnapshot.value = buildWorkshopAdvancedSnapshot()
  workspaceStore.workshopSearch.advancedOpen = true
}
const closeAdvancedPanel = () => {
  if (!workspaceStore.workshopSearch.advancedOpen) return
  const hasChanged = workshopAdvancedSnapshot.value && workshopAdvancedSnapshot.value !== buildWorkshopAdvancedSnapshot()
  workspaceStore.workshopSearch.advancedOpen = false
  workshopAdvancedSnapshot.value = ''
  if (hasChanged) triggerSearchNow()
}
const selectTranslationDisplayLanguage = async (language) => {
  const displayLanguage = String(language || '').trim()
  workspaceStore.setWorkshopDetailTranslationLanguage(displayLanguage)
  const targetLanguage = workspaceStore.getResolvedTranslationLanguage(displayLanguage)
  if (
    workshopTranslationSettings.value.auto_translate_missing
    && displayLanguage
    && targetLanguage
    && !workspaceStore.shouldSkipWorkshopAutoTranslate(selectedMod.value)
    && !workspaceStore.getWorkshopTranslationEntry(selectedMod.value?.translations, targetLanguage)
  ) {
    await workspaceStore.translateWorkshopDetail({ language: targetLanguage, displayLanguage })
  }
}
const handleToggleWorkshopTranslation = async () => {
  await workspaceStore.toggleWorkshopDetailTranslation()
}
const handleRetranslateCurrentLanguage = async () => {
  const displayLanguage = String(workspaceStore.workshopSearch.detailTranslationLanguage || '').trim() || workspaceStore.getDefaultTranslationSelection()
  const targetLanguage = workspaceStore.getResolvedTranslationLanguage(displayLanguage)
  if (!targetLanguage) return
  await workspaceStore.translateWorkshopDetail({ language: targetLanguage, displayLanguage, force: true })
}
const handleClearCurrentTranslation = async () => {
  const displayLanguage = String(workspaceStore.workshopSearch.detailTranslationLanguage || '').trim()
  const targetLanguage = workspaceStore.getResolvedTranslationLanguage(displayLanguage)
  if (!targetLanguage || !selectedTranslationEntry.value) return
  await workspaceStore.clearWorkshopDetailTranslation({ language: targetLanguage, displayLanguage })
}
// 以图片地址为键记录加载完成状态，避免切换详情时旧状态串到新截图。
const markScreenshotLoaded = (url) => {
  if (!url) return
  loadedScreenshotMap.value = {
    ...loadedScreenshotMap.value,
    [url]: true
  }
}

const toggleEnhancedMode = async (event) => {
  const enabled = !!event?.target?.checked
  const switched = await workspaceStore.setWorkshopSearchMode(enabled)
  if (!switched && event?.target) {
    event.target.checked = workspaceStore.workshopSearch.isEnhancedMode
  }
}

// 选中查看详情, 点击左侧主列表 (会清空历史栈)
const selectMod = (item) => {
  loadedScreenshotMap.value = {}
  workspaceStore.fetchWorkshopDetails(item.workshop_id, false)
}
// 点击详情页内的推荐卡片 (会压入历史栈)
const handleNavigateInside = (workshop_id) => {
  // 滚动条回到顶部 (可选，提升体验)
  if (detailScrollRef.value) detailScrollRef.value.scrollTop = 0
  loadedScreenshotMap.value = {}
  workspaceStore.fetchWorkshopDetails(workshop_id, true)
}
const showRelatedList = async (kind) => {
  loadedScreenshotMap.value = {}
  await workspaceStore.openWorkshopTransientList(kind, selectedMod.value || {})
  if (scrollerRef.value) {
    scrollerRef.value.$el.scrollTop = 0
  }
}

const closeTransientList = () => {
  workspaceStore.closeWorkshopTransientList()
}

// 核心：处理无限滚动
// RecycleScroller 原生触发滚动事件
const handleScroll = async (event) => {
  const target = event.target;
  // 2. 修复精度问题：使用 Math.ceil 向上取整，兼容高分屏和缩放导致的小数 scrollTop
  const isBottom = Math.ceil(target.scrollTop + target.clientHeight) >= target.scrollHeight - 150;
  // 1. 拦截条件
  if (
    !isBottom || 
    !workshopDisplayHasMore.value ||
    workshopDisplayLoading.value ||
    isLocalFetching.value // 改为 .value
  ) {
    return;
  }
  // 2. 瞬间开启局部硬锁
  isLocalFetching.value = true;
  try {
    // 3. 等待后端请求完成
    if (workspaceStore.workshopSearch.transientList.active) {
      await workspaceStore.loadWorkshopTransientList(true);
    } else {
      await workspaceStore.doWorkshopSearch('', true);
    }
    // 4. 极其关键：nextTick 对 RecycleScroller 不够！
    // 虚拟列表依赖 ResizeObserver 或内置 watcher，需要给它一点物理时间去生成新 DOM 并撑开容器。
    // 使用 100ms 延时可以完美避免高度瞬间缩水引发的二次触发。
    await new Promise(resolve => setTimeout(resolve, 100));
  } catch (error) {
    console.error("加载下一页失败:", error);
  } finally {
    // 5. 确保虚拟DOM完全撑开后，再释放局部硬锁
    isLocalFetching.value = false;
  }
}


const formatDate = (ts) => ts ? new Date(ts).toLocaleDateString() : '未知'
const copyHeaderValue = async (label, value) => {
  const text = String(value || '').trim()
  if (!text || text === '-' || !navigator?.clipboard?.writeText) return
  try {
    await navigator.clipboard.writeText(text)
    toast.success(`${label}已复制`, { timeout: 1000 })
  } catch (error) {
    toast.error(`${label}复制失败`)
  }
}

// 打开网页
const openWebUrl = (url, on_steam=true) => {
  if(!url) return
  workspaceStore.openSteamWorkshopUrl(url, on_steam)
}
// 订阅模组
const getTaskIdFromResult = (result) => String(result?.taskId || result?.task_id || result?.data?.task_id || '')
const waitForDependencyTask = async (types, startedAt, result) => {
  const taskId = getTaskIdFromResult(result)
  if (taskId) {
    await taskStore.waitForTaskCompletion(taskId).catch(() => null)
    return
  }
  if (!types) return
  await taskStore.waitForLatestTaskByType(types, { since: startedAt, startTimeout: 5000 }).catch(() => null)
}
const runDependencyAction = async (action, runner, taskTypes = null) => {
  if (isDependencyActionPending(action)) return
  const startedAt = Date.now()
  setDependencyActionPending(action, true)
  try {
    const result = await runner?.()
    await waitForDependencyTask(taskTypes, startedAt, result)
    return result
  } finally {
    setDependencyActionPending(action, false)
  }
}
const handleSubscribe = async (workshop_ids) => {
  await runDependencyAction('subscribe', () => appStore.subscribeWorkshopIds(workshop_ids), 'steam-subscribe')
}
// 取消订阅
const handleUnsubscribe = async (workshop_ids) => {
  await runDependencyAction('unsubscribe', () => appStore.unsubscribeWorkshopIds(workshop_ids), 'steam-unsubscribe')
}
// 下载模组
const handleDownload = async (workshop_ids) => {
  await runDependencyAction('download', () => appStore.downloadWorkshopItems(workshop_ids), 'steamcmd-download')
}
const handleDownloadSingle = (workshop_ids) => {
  handleDownload(workshop_ids)
}
</script>

<style scoped>
.workshop-detail-chip {
  display: inline-flex;
  min-width: 0;
  max-width: 100%;
  align-items: center;
  gap: 0.3rem;
  border-radius: 0.5rem;
  border-width: 1px;
  padding: 0.25rem 0.375rem;
  color: var(--color-text-main);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(4px);
}

.workshop-detail-chip__icon {
  flex-shrink: 0;
  width: 0.75rem;
  height: 0.75rem;
}

.workshop-detail-chip__title {
  flex-shrink: 0;
  font-size: 0.7rem;
  color: var(--color-text-subtle);
}

.workshop-detail-chip__value {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: -0.1rem;
  font-size: 0.8rem;
  font-weight: 800;
  color: var(--color-text-main);
}
</style>
