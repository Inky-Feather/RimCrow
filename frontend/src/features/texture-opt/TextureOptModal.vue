<template>
  <CommonModalShell :show="appStore.uiState.showTextureOptModal" :show-header="false" size="page" :z-index="100" accent="highlight" content-class="h-full flex flex-col"
    @close="closeModal" >
      <div data-tour="texture-opt-modal" class="flex h-full w-full flex-col overflow-hidden">
        <header class="shrink-0 border-b border-border-base/5 bg-[linear-gradient(135deg,rgba(var(--rgb-bg-deep),0.88),rgba(var(--rgb-bg-inset),0.96))] px-6 py-2">
          <div class="flex items-center justify-between">

            <h2 data-tour="texture-opt-title" class="shrink-0 flex items-center gap-3 min-w-0 text-2xl font-black tracking-wider text-text-main">
              <Images class="w-6 h-6 text-accent-highlight" />
              <span>贴图优化</span>
              <span v-tooltip="textureOptHelpText" class="inline-flex size-5 cursor-help items-center justify-center text-lg font-bold text-text-dim hover:text-text-main hover:border-border-base/18">?</span>
            </h2>

            <div data-tour="texture-opt-summary" class="bg-bg-surface/80 mx-5 min-w-0 flex-1 rounded-xl px-4 py-2 text-xs">
              <div class="grid grid-cols-4 gap-x-4 gap-y-2">
                <div class="min-w-0">
                  <span class="text-accent-tip/80">PNG</span>
                  <span class="ml-1 text-text-dim">{{ summary.source_total_count || 0 }} 张</span>
                  <span class="ml-1 font-mono font-bold text-accent-tip">{{ formatFileSize(summary.source_total_bytes || 0) }}</span>
                </div>
                <div class="min-w-0">
                  <span class="text-accent-primary/80">DDS</span>
                  <span class="ml-1 text-text-dim">{{ summary.dds_output_count || 0 }} 张</span>
                  <span class="ml-1 font-mono font-bold text-accent-primary">{{ formatFileSize(summary.dds_output_bytes || 0) }}</span>
                  <span v-if="summary.zstd_output_count" class="ml-2 text-accent-secondary/80">ZSTD</span>
                  <span v-if="summary.zstd_output_count" class="ml-1 text-text-dim">{{ summary.zstd_output_count }} 张</span>
                  <span v-if="summary.zstd_output_count" class="ml-1 font-mono font-bold text-accent-secondary">{{ formatFileSize(summary.zstd_output_bytes || 0) }}</span>
                </div>
                <div class="min-w-0 truncate text-accent-highlight">
                  显存占用预估
                  <span class="ml-1 line-through opacity-50">{{ formatFileSize(summary.source_vram_bytes_est || 0) }}</span>
                  <span class="mx-1">→</span>
                  <span class="font-mono font-bold">{{ formatFileSize(summary.output_vram_bytes_est || 0) }}</span>
                </div>
                <div class="min-w-0 text-text-dim">
                  模组 <span class="ml-1 font-mono font-bold text-text-main">{{ summary.mod_count || 0 }}</span>
                </div>

                <div class="min-w-0 text-accent-warning/80">
                  待生成 <span class="ml-1 font-mono font-bold text-text-main">{{ summary.generate_required_count || 0 }}</span>
                </div>
                <div class="col-span-3 min-w-0 flex items-center gap-4">
                  <span class="shrink-0 text-accent-tip/80">
                    当前比例 <span class="ml-1 font-mono font-bold text-text-main">{{ summary.scaled_count || 0 }}</span>
                  </span>
                  <span class="shrink-0 text-accent-secondary/80">
                    自动回退 <span class="ml-1 font-mono font-bold text-text-main">{{ summary.fallback_scaled_count || 0 }}</span>
                  </span>
                  <span class="shrink-0 text-text-dim">
                    保留原尺寸 <span class="ml-1 font-mono font-bold text-text-main">{{ summary.keep_original_count || 0 }}</span>
                  </span>
                  <div class="min-w-0 text-text-dim">
                    超范围未缩放 <span class="ml-1 font-mono font-bold text-text-main">{{ summary.skip_small_count || 0 }}</span>
                  </div>
                  <span v-if="summary.unsupported_source_count" class="shrink-0 cursor-help text-accent-warning" v-tooltip="unsupportedSummaryTooltip">
                    无效 PNG <span class="ml-1 font-mono font-bold text-text-main">{{ summary.unsupported_source_count }}</span>
                  </span>
                  <div class="min-w-0 text-accent-danger/80">
                    已排除 <span class="ml-1 font-mono font-bold text-text-main">{{ summary.excluded_count || 0 }}</span>
                  </div>
                </div>
              </div>
            </div>

            <div class="flex justify-end">
              <button @click="closeModal" class="modal-close-button" aria-label="关闭">
                <X class="w-5 h-5" />
              </button>
            </div>

          </div>
        </header>

        <div class="relative flex flex-1 min-h-0">
          <section class="flex min-w-0 flex-1 flex-col border-r border-border-base/5">
            <div data-tour="texture-opt-list-toolbar" class="toolbar-surface shrink-0 px-6 py-3">
              <div class="flex items-center gap-2">

                <div class="flex items-center gap-1 rounded-lg bg-bg-overlay/5 p-1">
                  <button v-for="mode in viewModes" :key="mode.value" @click="textureStore.viewMode = mode.value" class="px-3 py-1 rounded-md text-xs font-bold transition-all"
                    :class="textureStore.viewMode === mode.value ? 'bg-bg-overlay/10 text-text-main shadow-sm' : 'text-text-dim hover:text-text-main'" >
                    {{ mode.label }}
                  </button>
                </div>
                <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 px-1 py-2 text-xs font-bold text-text-dim transition-colors hover:text-text-main"
                  @click="textureStore.isResultDrawerOpen = !textureStore.isResultDrawerOpen" >
                  {{ textureStore.isResultDrawerOpen ? '隐藏结果面板' : '显示结果面板' }}
                </button>

                <div class="input-glass flex items-center gap-1 px-2 py-2.5 min-w-0">
                  <Search class="w-4 h-4 text-text-dim" />
                  <input v-model.trim="searchQuery" type="text" class="flex-1 min-w-0 bg-transparent text-xs text-text-main outline-none"
                    placeholder="筛选模组名称或路径" >
                </div>
                <CommonSelect class="w-44" v-model="sortMetric" :options="sortOptions" />
                <div class="text-xs italic text-text-dim shrink-0">共 {{ displayRows.length }} 个结果</div>
              </div>

            </div>

            <!-- 结果列表 -->
            <div data-tour="texture-opt-list" class=" relative min-h-0 flex-1 overflow-hidden">
              <div v-if="displayRows.length === 0" class="absolute inset-0 flex flex-col items-center justify-center text-text-disabled" >
                <Inbox class="mb-4 w-16 h-16 opacity-50" />
                <p>暂无数据，请先扫描统计或直接开始生成。</p>
              </div>

              <DynamicScroller v-else :items="displayRows" :min-item-size="textureListMinItemSize" key-field="mod_instance_key"
                class="h-full min-h-0 px-3 py-2" v-slot="{ item, index, active }" >
                <DynamicScrollerItem :item="item" :active="active" :data-index="index" :size-dependencies="getRowSizeDependencies(item)" >
                    <div class="pb-1">
                    <TextureModCard :mod="item" :view-mode="textureStore.viewMode" :max-bytes="maxBytesInCurrentView"
                      :is-excluded="textureStore.isModExcluded(item.package_id)"
                      @toggle-mod-exclusion="handleToggleModExclusion"
                      @open-mod-menu="openTextureModMenu"
                    />
                  </div>
                </DynamicScrollerItem>
              </DynamicScroller>
            </div>

            <!-- 状态栏 -->
            <footer class="min-h-16 shrink-0 border-t border-border-base/5 bg-bg-inset/80 px-6 py-3">
              <div v-if="showProgressBlock" class="space-y-2">
                <div class="flex items-center gap-3">
                  <component :is="progressStatusIcon" class="w-4 h-4 shrink-0" :class="progressStatusIconClass" />
                  <div class="min-w-0 flex-1 overflow-hidden rounded-full bg-bg-overlay/10 h-2">
                    <div class="h-full transition-all duration-300" :class="progressBarClass" :style="{ width: `${progressDisplayPercent}%` }"></div>
                  </div>
                  <span class="shrink-0 text-xs font-mono" :class="progressPercentClass">{{ progressDisplayPercent }}%</span>
                  <span class="shrink-0 text-xs font-mono text-text-dim">{{ progressElapsedLabel }}</span>
                </div>
                <div class="flex items-center justify-between gap-3 text-xs">
                  <span class="min-w-0 truncate text-text-dim" v-tooltip="progressFullMessage">
                    {{ progressFullMessage }}
                  </span>
                  <div class="shrink-0 whitespace-nowrap text-text-dim">
                    <span v-if="progressCountLabel">{{ progressCountLabel }}</span>
                  </div>
                </div>
              </div>

              <div v-else class="flex items-center gap-2 text-xs text-text-dim">
                <CheckCircle2 class="w-4 h-4 text-accent-success" />
                就绪
              </div>
            </footer>
          </section>

          <!-- 选项面板 -->
          <aside class="flex w-96 shrink-0 flex-col bg-bg-surface">
            <div data-tour="texture-opt-options"  class="min-h-0 flex-1 overflow-y-auto custom-scrollbar p-4">
              <div class="space-y-2">
                <div class="rounded-lg border p-3 text-xs"
                  :class="toolStatus.available ? 'bg-accent-success/10 border-accent-success/20 text-accent-success' : 'bg-accent-danger/10 border-accent-danger/20 text-accent-danger'">
                  <div class="font-bold">{{ toolStatus.available ? '工具已就绪' : '工具未就绪' }}</div>
                  <div class="mt-1 break-all opacity-90">{{ toolStatus.message || '正在检测环境...' }}</div>
                  <div v-if="toolStatus.resolved_path" class="mt-2 break-all text-xs opacity-70">{{ toolStatus.resolved_path }}</div>
                </div>

                <button v-if="!toolStatus.available && !isBusy" @click="textureStore.downloadTool()"
                  class="w-full rounded-xl bg-bg-overlay/10 py-2 text-sm font-bold transition-colors hover:bg-bg-overlay/10" >
                  下载 todds
                </button>

                <section class="modal-section space-y-3 p-3">
                  <h3 class="text-xs font-black uppercase tracking-widest text-text-main">处理范围</h3>
                  <CommonSelect v-model="targetScope"
                    :options="[
                      { label: '仅当前启用的模组', value: 'active' },
                      { label: '全部已安装模组', value: 'all' }
                    ]"
                  />
                </section>

                <section class="modal-section space-y-2 p-3">
                  <h3 class="text-xs font-black uppercase tracking-widest text-text-main">生成选项</h3>
                  <CommonSelect label="生成范围" v-model="config.process_mode" @change="saveConfig"
                    description="全部处理（完全覆盖重新生成所有贴图），只补缺失的贴图（增量处理，不重新生成已存在的优化贴图），只处理需要缩放的图片（已经存在的无法缩放的优化贴图不用重新生成，可缩放的覆盖生成）。"
                    :options="[
                      { label: '处理全部贴图（覆盖）', value: 'all_overwrite' },
                      { label: '只处理新增贴图（增量）', value: 'all_skip_existing' },
                      { label: '只处理可缩放图片（覆盖）', value: 'scaled_only_overwrite' }
                    ]"
                  />
                  <CommonSelect label="输出格式" v-model="config.output_format" @change="saveConfig"
                    :description="'DDS：RimWorld 1.6 起游戏可原生读取；1.6 以前通常需要搭配 Graphics Settings+ 才能加载 .dds。\nZSTD：先生成 DDS，再额外压缩成 .dds.zstd，主要节省磁盘空间；需要搭配 Image Opt 后游戏才能读取。'"
                    :options="[
                      { label: 'DDS', value: 'dds' },
                      { label: 'ZSTD（Image Opt）', value: 'zstd' }
                    ]"
                  />
                  <div v-if="isZstdMode && !isImageOptEnabled" class="rounded-lg border border-accent-warning/25 bg-accent-warning/10 p-2 text-xs text-accent-warning">
                    <div class="flex items-start gap-2">
                      <AlertTriangle class="mt-0.5 size-4 shrink-0" />
                      <div class="min-w-0 flex-1">
                        <div class="font-bold">{{ isImageOptInstalled ? 'Image Opt 未在当前列表启用' : '未安装 Image Opt' }}</div>
                        <div class="mt-1 text-text-dim">{{ imageOptWarningText }}</div>
                      </div>
                      <button v-if="!isImageOptInstalled" class="shrink-0 rounded-md border border-accent-warning/30 px-2 py-1 font-bold text-accent-warning hover:bg-accent-warning/10"
                        @click="openImageOptWorkshop">
                        打开工坊
                      </button>
                    </div>
                  </div>
                  <CommonSwitch v-if="isZstdMode" label="生成后清理旧 DDS" description="ZSTD 生成后自动删除同名旧 DDS。"
                    v-model="config.zstd_clean_old_dds" @change="saveConfig" mini />
                  <CommonSwitch label="生成 Mipmap" description="Mipmap 是给远距离显示准备的缩小层级。开启后远看更平滑、闪烁更少，但生成时间和文件体积会增加一些。" v-model="config.generate_mipmaps"
                    @change="saveConfig" mini />
                </section>

                <section class="modal-section space-y-3 p-3">
                  <h3 class="text-xs font-black uppercase tracking-widest text-text-main">缩放选项（进一步节省显存）</h3>
                  <CommonSelect label="缩放比例" v-model.number="config.scale_factor" @change="saveConfig"
                    description="优先按当前选定的比例处理；如果某些图片不适合这个比例，会自动回退到更稳妥的比例，必要时保持原尺寸。"
                    :options="[
                      { label: '不缩放', value: 1.0 },
                      { label: '80%', value: 0.8 },
                      { label: '75%', value: 0.75 },
                      { label: '60%', value: 0.6 },
                      { label: '50%', value: 0.5 },
                      { label: '40%', value: 0.4 },
                      { label: '25%', value: 0.25 },
                      { label: '20%', value: 0.2 }
                    ]"
                  />
                  <CommonSelect label="最小清晰度" v-model.number="config.max_size" @change="saveConfig"
                    :disabled="isNoCompressionMode"
                    :description="maxSizeDescription"
                    :options="[
                      { label: '256 px', value: 256 },
                      { label: '128 px', value: 128 }
                    ]"
                  />
                  <CommonSwitch label="超范围图片不参与缩放" description="太小或太大的图片仍会生成 DDS，但会保留原尺寸，不参与缩放比例计算。"
                    v-model="config.skip_small_textures" @change="saveConfig" mini />
                </section>

                <section class="modal-section space-y-2 p-3">
                  <h3 class="text-xs font-black uppercase tracking-widest text-text-main">清理说明</h3>
                  <div class=" text-xs text-text-dim">
                    {{ cleanDescription }}
                  </div>
                  <CommonSwitch label="清理 ZSTD" description="关闭时只清理 DDS；开启时只清理 .dds.zstd，两种输出不会混合清理。"
                    v-model="cleanZstdMode" @change="saveConfig" mini />
                  <div class="grid grid-cols-2 gap-2">
                    <button type="button" class="inline-flex min-w-0 items-center justify-center gap-1 rounded-md border border-accent-warning/25 px-2 py-1 text-xs font-bold text-accent-warning transition-colors hover:bg-accent-warning/10 disabled:cursor-not-allowed disabled:opacity-50"
                      :disabled="!toolStatus.available || isBusy" @click="handleCleanResidue" v-tooltip="residueCleanButtonLabel">
                      <BrushCleaning class="size-3.5 shrink-0" />
                    <span class="truncate">{{ residueCleanButtonLabel }}</span>
                  </button>
                  <button type="button" class="inline-flex min-w-0 items-center justify-center gap-1 rounded-md border border-accent-danger/25 px-2 py-1 text-xs font-bold text-accent-danger transition-colors hover:bg-accent-danger/10 disabled:cursor-not-allowed disabled:opacity-50"
                    :disabled="isBusy" @click="handleCleanWithoutSource" v-tooltip="orphanCleanButtonLabel">
                      <Trash2 class="size-3.5 shrink-0" />
                      <span class="truncate">{{ orphanCleanButtonLabel }}</span>
                    </button>
                  </div>
                </section>
              </div>
            </div>

            <!-- 操作按钮 -->
            <div class="modal-footer shrink-0 p-4">
              <div data-tour="texture-opt-actions" class="space-y-2">
                <div class="flex gap-2">
                  <button data-tour="texture-opt-analyze" @click="handleAnalyze" :disabled="isBusy"
                    class="flex min-w-0 flex-1 basis-0 @container items-center justify-center gap-2 rounded-xl border border-accent-secondary/30 bg-accent-secondary/10 py-2.5 font-bold text-accent-secondary transition-all hover:scale-102 active:scale-95 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
                    v-tooltip="'扫描统计'">
                    <ScanSearch class="w-4 h-4 shrink-0" />
                    <span class="min-w-0 truncate whitespace-nowrap text-[clamp(0.7rem,9cqw,1rem)]">扫描统计</span>
                  </button>
                  <button data-tour="texture-opt-clean" @click="handleCleanGenerated" :disabled="!toolStatus.available || isBusy"
                    class="flex min-w-0 flex-1 basis-0 @container items-center justify-center gap-2 rounded-xl border border-accent-warning/30 bg-accent-warning/10 py-2.5 font-bold text-accent-warning transition-all hover:scale-102 active:scale-95 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
                    v-tooltip="cleanButtonLabel">
                    <BrushCleaning class="w-4 h-4 shrink-0" />
                    <span class="min-w-0 truncate whitespace-nowrap text-[clamp(0.7rem,9cqw,1rem)]">{{ cleanButtonLabel }}</span>
                  </button>
                </div>

                <button v-if="!isBusy" data-tour="texture-opt-generate" @click="handleOptimize" :disabled="!toolStatus.available"
                  class="flex min-w-0 w-full @container items-center justify-center gap-2 rounded-xl bg-accent-primary py-3 font-black text-on-accent-primary shadow-[0_0_15px_rgba(var(--rgb-accent-cool),0.3)] transition-all hover:scale-102 active:scale-95 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
                  v-tooltip="processModeLabel">
                  <Rocket class="w-5 h-5 shrink-0" />
                  <span class="min-w-0 truncate whitespace-nowrap text-[clamp(0.8rem,8cqw,1.15rem)]">{{ processModeLabel }}</span>
                </button>

                <button v-else @click="handleCancel" class="flex w-full items-center justify-center gap-2 rounded-xl bg-accent-danger py-3 font-black text-on-accent-danger shadow-[0_0_15px_rgba(var(--rgb-accent-danger),0.3)] transition-all hover:scale-102 active:scale-95 cursor-pointer">
                  <Ban class="w-5 h-5" /> 停止当前任务
                </button>
              </div>
            </div>
          </aside>

          <!-- 结果面板 -->
          <transition name="panel-slide">
            <aside v-if="textureStore.isResultDrawerOpen" class="absolute inset-y-0 right-0 z-20 flex w-md flex-col border-l border-border-base/10 bg-[linear-gradient(180deg,rgba(var(--rgb-bg-inset),0.98),rgba(var(--rgb-bg-deep),0.98))] shadow-2xl" >
              <div class="flex items-center justify-between border-b border-border-base/10 px-4 py-3">
                <div>
                  <div class="text-sm font-black tracking-wider text-text-main">结果面板</div>
                  <div class="text-xs text-text-dim">当前任务、最近 3 次任务历史和排除规则</div>
                </div>
                <button class="rounded-lg p-1.5 text-text-dim hover:bg-bg-overlay/10 hover:text-text-main" @click="textureStore.isResultDrawerOpen = false">
                  <X class="w-4 h-4" />
                </button>
              </div>

              <div class="flex-1 space-y-4 overflow-y-auto custom-scrollbar p-4 text-xs">
                <section class="modal-section space-y-2 p-3">
                  <h3 class="font-black uppercase tracking-widest text-text-main">当前状态</h3>
                  <div class="text-text-dim">{{ progressFullMessage }}</div>
                  <div class="flex items-center gap-3 text-text-dim">
                    <span>{{ progressCountLabel || '暂无任务进度' }}</span>
                    <span>{{ progressElapsedLabel }}</span>
                  </div>
                </section>

                <section class="modal-section space-y-2 p-3">
                  <div class="flex items-center justify-between gap-2">
                    <h3 class="font-black uppercase tracking-widest text-text-main">最近结果</h3>
                    <button class="text-text-dim hover:text-text-main" @click="textureStore.loadResultHistory()">刷新</button>
                  </div>
                  <div v-if="resultHistory.length === 0" class="text-text-dim">暂无历史结果</div>
                  <button v-for="item in resultHistory" :key="item.result_path" class="w-full rounded-lg border px-3 py-2 text-left transition-colors"
                    :class="textureStore.selectedResultPath === item.result_path ? 'border-accent-primary/30 bg-accent-primary/10 text-text-main' : 'border-border-base/10 bg-bg-overlay/5 text-text-dim hover:text-text-main'"
                    @click="textureStore.selectedResultPath = item.result_path" >
                    <div class="flex items-center justify-between gap-3">
                      <span class="font-bold">{{ item.action === 'clean_generated' ? '清理任务' : '生成任务' }}</span>
                      <span class="font-mono">{{ formatDateTime(item.updated_at) }}</span>
                    </div>
                    <div class="mt-1 text-[0.8rem] opacity-80">
                      成功 {{ item.summary?.current_output_count || 0 }} / 失败 {{ item.failed_items?.length || 0 }}
                    </div>
                  </button>
                </section>

                <section class="modal-section space-y-2 p-3">
                  <div class="flex items-center justify-between gap-2">
                    <h3 class="font-black uppercase tracking-widest text-text-main">失败项</h3>
                    <input v-model.trim="failedSearchQuery" type="text" placeholder="筛选失败项"
                      class="input-glass w-40 px-2 py-1 text-xs text-text-main outline-none" >
                  </div>
                  <div v-if="filteredFailedItems.length === 0" class="text-text-dim">当前结果没有失败项</div>
                  <div v-for="item in filteredFailedItems" :key="`${item.mod_path}-${item.rel_path}-${item.error}`" class="modal-section-subtle p-2"
                    @contextmenu.prevent="openTextureFailedItemMenu($event, item)">
                    <div class="font-bold text-text-main">{{ item.mod_name || item.package_id || '未知模组' }}</div>
                    <div class="mt-1 break-all font-mono text-text-dim">{{ item.rel_path }}</div>
                    <div class="mt-1 text-accent-warning">{{ item.error }}</div>
                    <div class="mt-2 flex justify-end gap-2">
                      <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 p-1.5 text-text-dim transition-colors hover:text-text-main"
                        @click="handleOpenTextureFile(item)" v-tooltip="'打开文件'" >
                        <FileText class="w-4 h-4" />
                      </button>
                      <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 p-1.5 text-text-dim transition-colors hover:text-text-main"
                        @click="handleOpenTextureFolder(item)" v-tooltip="'打开所在目录'" >
                        <FolderOpen class="w-4 h-4" />
                      </button>
                      <button v-if="getFailedItemLogPath(item)" v-tooltip="'打开 todds 日志'"
                        class="rounded-lg border border-border-base/10 bg-bg-overlay/5 p-1.5 text-text-dim transition-colors hover:text-text-main"
                        @click="handleOpenToddsLog(item)" >
                        <ScrollText class="w-4 h-4" />
                      </button>
                      <button class="inline-flex items-center gap-1 rounded-lg border border-accent-warning/20 bg-accent-warning/10 px-2 py-1 font-bold text-accent-warning transition-colors hover:bg-accent-warning/20"
                        @click="handleAddFailedItemExclusion(item)" v-tooltip="'添加文件到排除列表'" >
                        <Plus class="w-3.5 h-3.5" />
                        排除文件
                      </button>
                    </div>
                  </div>
                </section>

                <section class="modal-section space-y-2 p-3">
                  <div class="flex items-center justify-between gap-2">
                    <h3 class="font-black uppercase tracking-widest text-text-main">模组排除</h3>
                    <input v-model.trim="excludeModQuery" type="text" placeholder="筛选已排除"
                      class="input-glass w-40 px-2 py-1 text-xs text-text-main outline-none" >
                  </div>
                  <div v-if="filteredExcludedModRows.length === 0" class="text-text-dim">
                    {{ excludedModRows.length === 0 ? '暂无模组排除' : '没有匹配的已排除模组' }}
                  </div>
                  <div class="max-h-48 space-y-2 overflow-y-auto custom-scrollbar">
                    <div v-for="item in filteredExcludedModRows" :key="item.package_id"
                      class="modal-section-subtle flex items-center justify-between gap-3 px-2 py-2" >
                      <div class="min-w-0">
                        <div class="truncate font-bold text-text-main">{{ item.mod_name }}</div>
                        <div class="truncate font-mono text-text-dim">{{ item.package_id }}</div>
                        <div v-if="item.mod_path" class="truncate text-[0.8rem] text-text-dim">{{ item.mod_path }}</div>
                      </div>
                      <button class="shrink-0 rounded-lg border border-accent-danger/20 bg-accent-danger/10 p-1.5 text-accent-danger transition-colors hover:bg-accent-danger/20"
                        @click="handleRemoveModExclusion(item)" v-tooltip="'移除模组排除'" >
                        <Trash2 class="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </section>

                <section class="modal-section space-y-2 p-3">
                  <div class="flex items-center justify-between gap-2">
                    <h3 class="font-black uppercase tracking-widest text-text-main">文件排除</h3>
                    <input v-model.trim="excludeFileQuery" type="text" placeholder="筛选已排除"
                      class="input-glass w-40 px-2 py-1 text-xs text-text-main outline-none" >
                  </div>
                  <div class="flex gap-2">
                    <textarea v-model.trim="pathExclusionInput" rows="2" placeholder="粘贴完整文件路径，可多行"
                      class="input-glass min-h-12 flex-1 resize-none px-2 py-1 text-xs text-text-main outline-none" >
                    </textarea>
                    <button class="inline-flex items-center gap-1 rounded-lg border border-border-base/10 bg-bg-overlay/5 px-3 py-1 font-bold text-text-dim hover:text-text-main" @click="handleAddPathExclusion">
                      <Plus class="w-3.5 h-3.5" />
                      识别
                    </button>
                  </div>
                  <div v-if="filteredFileExclusionRows.length === 0" class="text-text-dim">
                    {{ fileExclusionRows.length === 0 ? '暂无文件排除' : '没有匹配的已排除文件' }}
                  </div>
                  <div v-for="item in filteredFileExclusionRows" :key="`${item.mod_path}:${item.rel_path}`" class="modal-section-subtle p-2"
                    @contextmenu.prevent="openTextureFileExclusionMenu($event, item)">
                    <div class="font-bold text-text-main">{{ item.mod_name }}</div>
                    <div class="mt-1 break-all font-mono text-text-main">{{ item.rel_path }}</div>
                    <div class="mt-1 break-all text-text-dim">{{ item.mod_path }}</div>
                    <div class="mt-2 flex justify-end gap-2">
                      <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 p-1.5 text-text-dim transition-colors hover:text-text-main"
                        @click="handleOpenTextureFile(item)" v-tooltip="'打开文件'" >
                        <FileText class="w-4 h-4" />
                      </button>
                      <button class="rounded-lg border border-border-base/10 bg-bg-overlay/5 p-1.5 text-text-dim transition-colors hover:text-text-main"
                        @click="handleOpenTextureFolder(item)" v-tooltip="'打开所在目录'" >
                        <FolderOpen class="w-4 h-4" />
                      </button>
                      <button class="rounded-lg border border-accent-danger/20 bg-accent-danger/10 p-1.5 text-accent-danger transition-colors hover:bg-accent-danger/20"
                        @click="handleRemoveFileExclusion(item)" v-tooltip="'移除文件排除'" >
                        <Trash2 class="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </section>
              </div>
            </aside>
          </transition>
        </div>
      </div>
  </CommonModalShell>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller'
import { useNow } from '@vueuse/core'
import { AlertTriangle, Ban, BrushCleaning, CheckCircle2, Copy, Cpu, FileText, FolderOpen, Images, Inbox, Loader2, Plus, Rocket, ScanSearch, ScrollText, Search, Trash2, X } from 'lucide-vue-next'
import { useAppStore } from '../../app/stores/appStore'
import { useTextureStore } from './textureStore'
import { useModStore } from '../mod/stores/modStore'
import CommonSwitch from '../../shared/components/input/CommonSwitch.vue'
import CommonSelect from '../../shared/components/input/CommonSelect.vue'
import CommonModalShell from '../../shared/components/modal/CommonModalShell.vue'
import { useConfirmStore } from '../../shared/components/modal/confirmStore'
import { useContextMenuStore } from '../../shared/components/context-menu/contextMenuStore'
import TextureModCard from './TextureModCard.vue'
import { formatFileSize } from '../../shared/lib/format'
import { toast } from '../../shared/lib/common'
import { copyTextToClipboard } from '../mod/lib/modContextMenuItems'

const appStore = useAppStore()
const textureStore = useTextureStore()
const modStore = useModStore()
const confirmStore = useConfirmStore()
const contextMenuStore = useContextMenuStore()

const IMAGE_OPT_PACKAGE_ID = 'dev.soeur.imageopt'
const IMAGE_OPT_WORKSHOP_ID = '3543873568'

const config = computed(() => appStore.settings.texture_opt)
const summary = computed(() => textureStore.globalSummary || {})
const progressState = computed(() => textureStore.progressState)
const toolStatus = computed(() => textureStore.toolStatus)
const isBusy = computed(() => textureStore.isAnalyzing || textureStore.isOptimizing)
const isNoCompressionMode = computed(() => Math.abs(Number(config.value?.scale_factor || 1) - 1) <= 1e-6)
const isZstdMode = computed(() => String(config.value?.output_format || 'dds') === 'zstd')
const isImageOptInstalled = computed(() => (
  getInstalledMods().some(mod => String(mod?.package_id || '').trim().toLowerCase() === IMAGE_OPT_PACKAGE_ID)
))
const isImageOptEnabled = computed(() => (
  modStore.activeIds.some(id => {
    const mod = modStore.takeModById(id)
    return String(mod?.package_id || id || '').trim().toLowerCase() === IMAGE_OPT_PACKAGE_ID
  })
))
const imageOptWarningText = computed(() => (
  isImageOptInstalled.value
    ? 'ZSTD 压缩贴图需要当前已启用 Image Opt 才会生效；未启用时仍可生成，但游戏可能不会读取这些文件。'
    : 'ZSTD 压缩贴图需要 Image Opt 才能被游戏读取；未安装时仍可生成，但游戏会继续使用原图或其它可读取的输出。'
))
const maxSizeDescription = computed(() => (
  isNoCompressionMode.value
    ? '当前为不缩放，最小清晰度不会参与处理。'
    : '缩放时会尽量保证最短边不低于这个目标，避免图片被压得过小。'
))
const cleanZstdMode = computed({
  get: () => String(config.value?.clean_output_format || 'dds') === 'zstd',
  set: value => {
    config.value.clean_output_format = value ? 'zstd' : 'dds'
  },
})
const cleanOutputFormat = computed(() => cleanZstdMode.value ? 'zstd' : 'dds')
const cleanOutputLabel = computed(() => cleanZstdMode.value ? 'ZSTD' : 'DDS')
const cleanButtonLabel = computed(() => `清理已生成 ${cleanOutputLabel.value}`)
const residueCleanButtonLabel = computed(() => `清理卸载残留 ${cleanOutputLabel.value}`)
const orphanCleanButtonLabel = computed(() => `删除无对应源图 ${cleanOutputLabel.value}`)
const cleanDescription = computed(() => (
  `主清理会删除当前范围内、且能找到同名 PNG 源图的已生成 ${cleanOutputLabel.value}；卸载残留和无对应源图的输出需要单独处理。`
))
const resultHistory = computed(() => textureStore.resultHistory)
const textureExclusions = computed(() => textureStore.textureExclusions)
const now = useNow({ interval: 1000 })
const targetScope = ref('active')
const searchQuery = ref('')
const sortMetric = ref('impact')
const failedSearchQuery = ref('')
const excludeModQuery = ref('')
const excludeFileQuery = ref('')
const pathExclusionInput = ref('')
const textureOptHelpText = '把 PNG 贴图预先生成为更适合游戏读取的 DDS 贴图输出。\nDDS 主要用来减少显存压力、加快加载；通常情况下，DDS 能在大型模组环境下减少卡顿和爆显存风险；代价是生成比较耗时，DDS 也往往会比源 PNG 更占磁盘空间。\nRimWorld 1.6 起游戏可原生读取 DDS，1.6 以前通常需要[[ Graphics Settings+ ]]才能加载。\n\nZSTD 会生成 .dds.zstd，本质上相当于把已经生成好的 DDS 再打包压缩一层，主要作用是进一步节省磁盘空间，但需要[[ Image Opt ]]才能被游戏读取。\n\n缩放功能部分感谢贴吧老哥 ##贴吧用户_0CWt68M## 提供的帮助'
const textureListMinItemSize = computed(() => appStore.scalePx(101, 14))
const viewModes = [
  { label: '综合视图', value: 'ALL' },
  { label: '仅看 PNG', value: 'PNG' },
  { label: '仅看 DDS', value: 'DDS' },
  { label: '仅看 ZSTD', value: 'ZSTD' },
]

const sortOptions = [
  { label: '按总体积占比', value: 'impact' },
  { label: '按待生成数量', value: 'pending' },
  { label: '按预估显存', value: 'vram' },
  { label: '按节省显存', value: 'vram_saved' },
  { label: '按名称', value: 'name' },
]

const resolvedRows = computed(() => (
  textureStore.modsData.map(item => ({
    ...item,
    mod_name: resolveModName(item),
    mod_path: item.mod_path || '',
    vram_saved: Math.max(0, Number(item.source_vram_bytes_est || 0) - Number(item.output_vram_bytes_est || 0)),
  }))
))

const getViewMetricBytes = (item) => {
  if (textureStore.viewMode === 'PNG') return Number(item.source_total_bytes || 0)
  if (textureStore.viewMode === 'DDS') return Number(item.dds_output_bytes || 0)
  if (textureStore.viewMode === 'ZSTD') return Number(item.zstd_output_bytes || 0)
  return Number(item.combined_total_bytes || 0)
}

const sortRows = (rows) => {
  rows.sort((a, b) => {
    if (sortMetric.value === 'name') {
      return a.mod_name.localeCompare(b.mod_name, 'zh-Hans-CN')
    }
    if (sortMetric.value === 'pending') {
      return (Number(b.generate_required_count || 0) - Number(a.generate_required_count || 0))
        || (Number(b.unsupported_source_count || 0) - Number(a.unsupported_source_count || 0))
        || (Number(b.combined_total_bytes || 0) - Number(a.combined_total_bytes || 0))
    }
    if (sortMetric.value === 'vram') {
      return Number(b.output_vram_bytes_est || 0) - Number(a.output_vram_bytes_est || 0)
    }
    if (sortMetric.value === 'vram_saved') {
      return Number(b.vram_saved || 0) - Number(a.vram_saved || 0)
    }
    const aMetric = getViewMetricBytes(a)
    const bMetric = getViewMetricBytes(b)
    return bMetric - aMetric
      || Number(b.generate_required_count || 0) - Number(a.generate_required_count || 0)
      || Number(b.unsupported_source_count || 0) - Number(a.unsupported_source_count || 0)
  })
  return rows
}

const displayRows = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  const rows = resolvedRows.value.filter(item => {
    if (!query) return true
    return item.mod_name.toLowerCase().includes(query) || item.mod_path.toLowerCase().includes(query)
  })

  return sortRows(rows)
})

const maxBytesInCurrentView = computed(() => {
  const list = displayRows.value
  if (list.length === 0) return 1
  return list.reduce((maxBytes, item) => {
    const currentBytes = getViewMetricBytes(item)
    return Math.max(maxBytes, currentBytes)
  }, 1)
})

const getRowSizeDependencies = (item) => [
  Number(appStore.settings.ui.font_size || 14),
  textureStore.viewMode,
  String(item?.mod_name || ''),
  Number(item?.generate_required_count || 0),
  Number(item?.unsupported_source_count || 0),
  JSON.stringify(item?.scale_breakdown || []),
  Number(item?.source_total_count || 0),
  Number(item?.output_total_count || 0),
  Number(item?.source_total_bytes || 0),
  Number(item?.output_total_bytes || 0),
  Number(item?.dds_output_bytes || 0),
  Number(item?.zstd_output_bytes || 0),
]
const unsupportedSummaryTooltip = computed(() => {
  const preview = Array.isArray(summary.value.engine_unsupported_preview) ? summary.value.engine_unsupported_preview : []
  if (!preview.length) return '有些文件看起来像图片，其实不是正常图片，已经自动跳过。'
  return [
    '以下伪装 PNG 已从任务中自动排除：',
    ...preview.map(item => `${item.mod_name} / ${item.rel_path}${item.reason ? ` - ${item.reason}` : ''}`),
  ].join('\n')
})

const processedCount = computed(() => {
  const details = progressState.value.details || {}
  return Number((details.phase_done ?? details.done ?? details.processed_mods) || 0)
})

const totalCount = computed(() => {
  const details = progressState.value.details || {}
  return Number((details.phase_total ?? details.total ?? details.total_mods) || 0)
})

const progressPhaseLabel = computed(() => {
  const details = progressState.value.details || {}
  return String(details.phase_label || '')
})

const processModeLabel = computed(() => {
  if (config.value.process_mode === 'all_overwrite') return '完全覆盖生成'
  if (config.value.process_mode === 'all_skip_existing') return '增量生成'
  return '只处理需缩放图片'
})

const progressCountLabel = computed(() => {
  if (!totalCount.value) return ''
  const details = progressState.value.details || {}
  const unit = String(details.phase_unit || (details.total_mods != null || details.processed_mods != null ? '模组' : '项'))
  const phase = progressPhaseLabel.value ? `${progressPhaseLabel.value} ` : ''
  return `${phase}${processedCount.value}/${totalCount.value} ${unit}`
})

const progressFullMessage = computed(() => String(progressState.value.message || '处理中...'))
const showProgressBlock = computed(() => isBusy.value || showFinishedProgress.value)
const progressDisplayPercent = computed(() => {
  if (showFinishedProgress.value) return 100
  const details = progressState.value.details || {}
  return Number((progressState.value.percent ?? details.phase_percent) || 0)
})
const progressStatusIcon = computed(() => (showFinishedProgress.value ? CheckCircle2 : Loader2))
const progressStatusIconClass = computed(() => (showFinishedProgress.value ? 'text-accent-success' : 'text-accent-primary animate-spin'))
const progressBarClass = computed(() => (showFinishedProgress.value ? 'bg-accent-success' : 'bg-accent-primary'))
const progressPercentClass = computed(() => (showFinishedProgress.value ? 'text-accent-success' : 'text-accent-primary'))

const progressElapsedLabel = computed(() => {
  const details = progressState.value.details || {}
  const startedAt = Number(details.local_started_at || 0)
  if (!startedAt) return '--:--'
  const totalElapsed = Number(details.local_total_elapsed_ms || 0)
  const isTerminal = ['success', 'failed', 'cancelled'].includes(String(details.local_status || ''))
  if (isTerminal && totalElapsed > 0) {
    return `总用时 ${formatDuration(totalElapsed)}`
  }
  return `已用时 ${formatDuration(Math.max(0, Number(now.value) - startedAt))}`
})

const showFinishedProgress = computed(() => {
  const status = String(progressState.value.details?.local_status || '')
  return ['success', 'failed', 'cancelled'].includes(status)
})

const selectedHistoryResult = computed(() => (
  resultHistory.value.find(item => item.result_path === textureStore.selectedResultPath) || resultHistory.value[0] || null
))

const currentFailedItems = computed(() => {
  const liveItems = Array.isArray(progressState.value.details?.failed_items) ? progressState.value.details.failed_items : []
  if (isBusy.value) return liveItems
  if (selectedHistoryResult.value) return selectedHistoryResult.value.failed_items || []
  return liveItems
})

const filteredFailedItems = computed(() => {
  const query = failedSearchQuery.value.trim().toLowerCase()
  return currentFailedItems.value.filter(item => {
    if (!query) return true
    return (
      String(item.mod_name || '').toLowerCase().includes(query)
      || String(item.rel_path || '').toLowerCase().includes(query)
      || String(item.error || '').toLowerCase().includes(query)
    )
  })
})

const normalizePackageKey = (value) => String(value || '').trim().toLowerCase()
const normalizePathKey = (value) => String(value || '').trim().replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()
const stripPathQuotes = (value) => String(value || '').trim().replace(/^[\s"'`“”‘’]+|[\s"'`“”‘’]+$/g, '')
const getInstalledMods = () => Array.from(modStore.allModsMap instanceof Map ? modStore.allModsMap.values() : [])

const resolvedRowByPackageId = computed(() => {
  const map = new Map()
  for (const row of resolvedRows.value) {
    const key = normalizePackageKey(row.package_id)
    if (key && !map.has(key)) map.set(key, row)
  }
  return map
})

const resolvedRowByModPath = computed(() => {
  const map = new Map()
  for (const row of resolvedRows.value) {
    const key = normalizePathKey(row.mod_path)
    if (key && !map.has(key)) map.set(key, row)
  }
  return map
})

const installedModByPackageId = computed(() => {
  const map = new Map()
  for (const mod of getInstalledMods()) {
    const key = normalizePackageKey(mod?.package_id)
    if (key && !map.has(key)) map.set(key, mod)
  }
  return map
})

const installedModByPath = computed(() => {
  const map = new Map()
  for (const mod of getInstalledMods()) {
    const key = normalizePathKey(mod?.path)
    if (key && !map.has(key)) map.set(key, mod)
  }
  return map
})

const pathExclusionCandidates = computed(() => {
  const rows = []
  const seen = new Set()
  const pushCandidate = (item) => {
    const modPath = String(item?.mod_path || item?.path || '').trim()
    const key = normalizePathKey(modPath)
    if (!key || seen.has(key)) return
    seen.add(key)
    rows.push({
      mod_path: modPath,
      package_id: item?.package_id || '',
      mod_name: item?.mod_name || item?.alias_name || item?.display_name || item?.name || item?.package_id || '未知模组',
    })
  }
  resolvedRows.value.forEach(pushCandidate)
  getInstalledMods().forEach(pushCandidate)
  return rows.sort((left, right) => normalizePathKey(right.mod_path).length - normalizePathKey(left.mod_path).length)
})

const excludedModRows = computed(() => {
  const rows = []
  const seen = new Set()
  for (const item of textureExclusions.value.mods || []) {
    const packageId = String(item?.package_id || '').trim()
    const key = normalizePackageKey(packageId)
    if (!key || seen.has(key)) continue
    seen.add(key)
    const statsRow = resolvedRowByPackageId.value.get(key)
    const installedMod = installedModByPackageId.value.get(key)
    rows.push({
      ...item,
      package_id: packageId,
      mod_name: statsRow?.mod_name || installedMod?.alias_name || installedMod?.display_name || installedMod?.name || packageId,
      mod_path: statsRow?.mod_path || installedMod?.path || '',
    })
  }
  return rows.sort((left, right) => String(left.mod_name || '').localeCompare(String(right.mod_name || ''), 'zh-Hans-CN'))
})

const filteredExcludedModRows = computed(() => {
  const query = excludeModQuery.value.trim().toLowerCase()
  return excludedModRows.value.filter(item => {
    if (!query) return true
    return (
      String(item.mod_name || '').toLowerCase().includes(query)
      || String(item.package_id || '').toLowerCase().includes(query)
      || String(item.mod_path || '').toLowerCase().includes(query)
    )
  })
})

const fileExclusionRows = computed(() => {
  const rows = []
  const seen = new Set()
  for (const item of textureExclusions.value.files || []) {
    const modPath = String(item?.mod_path || '').trim()
    const relPath = String(item?.rel_path || '').trim().replace(/\\/g, '/').replace(/^\/+/, '')
    const key = `${normalizePathKey(modPath)}:${relPath.toLowerCase()}`
    if (!modPath || !relPath || seen.has(key)) continue
    seen.add(key)
    const modKey = normalizePathKey(modPath)
    const statsRow = resolvedRowByModPath.value.get(modKey)
    const installedMod = installedModByPath.value.get(modKey)
    rows.push({
      ...item,
      mod_path: modPath,
      rel_path: relPath,
      file_path: buildTextureFilePath(modPath, relPath),
      mod_name: statsRow?.mod_name || installedMod?.alias_name || installedMod?.display_name || installedMod?.name || installedMod?.package_id || '未知模组',
    })
  }
  return rows.sort((left, right) => (
    String(left.mod_name || '').localeCompare(String(right.mod_name || ''), 'zh-Hans-CN')
    || String(left.rel_path || '').localeCompare(String(right.rel_path || ''), 'zh-Hans-CN')
  ))
})

const filteredFileExclusionRows = computed(() => {
  const query = excludeFileQuery.value.trim().toLowerCase()
  return fileExclusionRows.value.filter(item => {
    if (!query) return true
    return (
      String(item.mod_name || '').toLowerCase().includes(query)
      || String(item.rel_path || '').toLowerCase().includes(query)
      || String(item.mod_path || '').toLowerCase().includes(query)
    )
  })
})

const closeModal = () => {
  appStore.uiState.showTextureOptModal = false
}

const saveConfig = async () => {
  await appStore.saveSetting('texture_opt', config.value)
  await textureStore.checkToolStatus()
}

const getTargetIds = () => {
  if (targetScope.value === 'active') {
    return modStore.activeIds
  }
  return Array.from(modStore.allModsMap.values())
    .filter(mod => !mod.isMissing && mod.path)
    .map(mod => mod.package_id)
}

const warnImageOptIfNeeded = () => {
  if (isZstdMode.value && !isImageOptEnabled.value) {
    toast.warning('当前启用模组里未检测到 Image Opt。ZSTD 贴图仍会生成，但游戏可能不会读取这些文件。')
  }
}

const handleAnalyze = async () => {
  const ids = getTargetIds()
  await textureStore.startAnalysis(ids, targetScope.value)
}

const handleOptimize = async () => {
  warnImageOptIfNeeded()
  const ids = getTargetIds()
  await textureStore.startOptimization(ids, 'optimize', targetScope.value)
}

const handleCleanGenerated = async () => {
  const ids = getTargetIds()
  await textureStore.startOptimization(ids, 'clean_generated', targetScope.value, {
    clean_output_format: cleanOutputFormat.value,
  })
}

const handleCleanResidue = async () => {
  const ids = getTargetIds()
  await textureStore.startOptimization(ids, 'clean_generated', targetScope.value, {
    clean_uninstalled_residue_only: true,
    clean_output_format: cleanOutputFormat.value,
  })
}

const handleCleanWithoutSource = async () => {
  const ok = await confirmStore.confirmAction(
    `删除无对应源图 ${cleanOutputLabel.value}`,
    `将删除当前范围内找不到同名 PNG 源图的 ${cleanOutputLabel.value} 输出文件。部分模组本来就会直接提供 DDS 或 ZSTD 贴图，这类文件也可能被误删；建议确认目标范围后再继续。`,
    {
      type: 'error',
      confirmText: '确认删除',
      cancelText: '取消',
    },
  )
  if (!ok) return
  const ids = getTargetIds()
  await textureStore.startOptimization(ids, 'clean_generated', targetScope.value, {
    clean_output_format: cleanOutputFormat.value,
    clean_without_source: true,
  })
}

const buildSingleModTarget = (item) => ({
  mod_path: String(item?.mod_path || ''),
  mod_name: String(item?.mod_name || ''),
  package_id: String(item?.package_id || ''),
  store: String(item?.store || ''),
  path_hash: String(item?.path_hash || ''),
  mod_instance_key: String(item?.mod_instance_key || item?.path_hash || item?.mod_path || ''),
})

const getSingleTargetIds = (item) => {
  const packageId = String(item?.package_id || '').trim()
  return packageId ? [packageId] : []
}

const handleOptimizeSingleMod = async (item) => {
  if (!item?.mod_path) return
  warnImageOptIfNeeded()
  await textureStore.startOptimization(getSingleTargetIds(item), 'optimize', 'single', {
    single_mod_target: buildSingleModTarget(item),
  })
}

const handleAnalyzeSingleMod = async (item) => {
  if (!item?.mod_path) return
  await textureStore.startAnalysis(getSingleTargetIds(item), 'single', {
    single_mod_target: buildSingleModTarget(item),
  })
}

const handleCleanSingleMod = async (item, outputFormat = cleanOutputFormat.value) => {
  if (!item?.mod_path) return
  await textureStore.startOptimization(getSingleTargetIds(item), 'clean_generated', 'single', {
    clean_uninstalled_residue_only: false,
    clean_output_format: outputFormat,
    single_mod_target: buildSingleModTarget(item),
  })
}

const handleCleanSingleModWithoutSource = async (item, outputFormat = cleanOutputFormat.value) => {
  if (!item?.mod_path) return
  const outputLabel = outputFormat === 'zstd' ? 'ZSTD' : 'DDS'
  const ok = await confirmStore.confirmAction(
    `删除无对应源图 ${outputLabel}`,
    `将删除「${item.mod_name || '当前模组'}」中找不到同名 PNG 源图的 ${outputLabel} 输出文件。部分模组本来就会直接提供 DDS 或 ZSTD 贴图，这类文件也可能被误删。`,
    { type: 'error', confirmText: '确认删除', cancelText: '取消' },
  )
  if (!ok) return
  await textureStore.startOptimization(getSingleTargetIds(item), 'clean_generated', 'single', {
    clean_output_format: outputFormat,
    clean_without_source: true,
    single_mod_target: buildSingleModTarget(item),
  })
}

const openTextureModMenu = (event, item) => {
  contextMenuStore.open(event, [
    { label: '刷新该模组统计', icon: ScanSearch, disabled: isBusy.value || !item?.mod_path, action: () => handleAnalyzeSingleMod(item) },
    { label: `生成${isZstdMode.value ? ' ZSTD' : ' DDS'}（当前配置）`, icon: Rocket, disabled: isBusy.value || !toolStatus.value.available || !item?.mod_path, action: () => handleOptimizeSingleMod(item) },
    {
      label: '清理已生成',
      icon: BrushCleaning,
      disabled: isBusy.value || !toolStatus.value.available || !item?.mod_path,
      children: [
        { label: '只清理 DDS', icon: BrushCleaning, action: () => handleCleanSingleMod(item, 'dds') },
        { label: '只清理 ZSTD', icon: BrushCleaning, action: () => handleCleanSingleMod(item, 'zstd') },
      ],
    },
    {
      label: '删除无对应源图',
      icon: Trash2,
      level: 'danger',
      disabled: isBusy.value || !item?.mod_path,
      children: [
        { label: '只删除无对应源图 DDS', icon: Trash2, level: 'danger', action: () => handleCleanSingleModWithoutSource(item, 'dds') },
        { label: '只删除无对应源图 ZSTD', icon: Trash2, level: 'danger', action: () => handleCleanSingleModWithoutSource(item, 'zstd') },
      ],
    },
    { divider: true },
    { label: textureStore.isModExcluded(item?.package_id) ? '取消排除模组' : '排除模组', icon: Ban, disabled: !item?.package_id, action: () => handleToggleModExclusion(item) },
    { label: '打开模组目录', icon: FolderOpen, disabled: !item?.mod_path, action: () => appStore.openPath(item.mod_path) },
  ], item)
}

const buildTextureFileCopyItems = (item) => {
  const fullPath = item?.file_path || buildTextureFilePath(item?.mod_path, item?.rel_path)
  const relPath = String(item?.rel_path || '').trim()
  return [
    { label: '复制完整路径', icon: Copy, disabled: !fullPath, action: () => copyTextToClipboard(fullPath, '完整路径') },
    { label: '复制相对路径', icon: Copy, disabled: !relPath, action: () => copyTextToClipboard(relPath, '相对路径') },
  ]
}

const openTextureFailedItemMenu = (event, item) => {
  contextMenuStore.open(event, [
    { label: '打开文件', icon: FileText, disabled: !(item?.file_path || (item?.mod_path && item?.rel_path)), action: () => handleOpenTextureFile(item) },
    { label: '打开所在目录', icon: FolderOpen, disabled: !(item?.file_path || (item?.mod_path && item?.rel_path)), action: () => handleOpenTextureFolder(item) },
    { label: '打开 todds 日志', icon: ScrollText, disabled: !getFailedItemLogPath(item), action: () => handleOpenToddsLog(item) },
    { divider: true },
    { label: '加入文件排除', icon: Plus, disabled: !item?.mod_path || !item?.rel_path, action: () => handleAddFailedItemExclusion(item) },
    { divider: true },
    ...buildTextureFileCopyItems(item),
  ], item)
}

const openTextureFileExclusionMenu = (event, item) => {
  contextMenuStore.open(event, [
    { label: '打开文件', icon: FileText, disabled: !(item?.file_path || (item?.mod_path && item?.rel_path)), action: () => handleOpenTextureFile(item) },
    { label: '打开所在目录', icon: FolderOpen, disabled: !(item?.file_path || (item?.mod_path && item?.rel_path)), action: () => handleOpenTextureFolder(item) },
    { divider: true },
    { label: '移除文件排除', icon: Trash2, level: 'danger', disabled: !item?.mod_path || !item?.rel_path, action: () => handleRemoveFileExclusion(item) },
    { divider: true },
    ...buildTextureFileCopyItems(item),
  ], item)
}

const openImageOptWorkshop = () => {
  appStore.openSteamWorkshopById(IMAGE_OPT_WORKSHOP_ID)
}

const handleCancel = async () => {
  await textureStore.cancelCurrentTask()
}

watch(() => appStore.uiState.showTextureOptModal, (visible) => {
  if (visible) {
    textureStore.checkToolStatus()
    textureStore.loadResultHistory()
    textureStore.loadExclusions()
  }
})

const handleToggleModExclusion = async (item) => {
  if (!item?.package_id) return
  await textureStore.toggleModExclusion(item.package_id, !textureStore.isModExcluded(item.package_id))
}

const handleRemoveModExclusion = async (item) => {
  if (!item?.package_id) return
  await textureStore.toggleModExclusion(item.package_id, false)
}

const handleAddFailedItemExclusion = async (item) => {
  if (!item?.mod_path || !item?.rel_path) return
  await textureStore.toggleFileExclusion(item.mod_path, item.rel_path, true)
}

const handleRemoveFileExclusion = async (item) => {
  if (!item?.mod_path || !item?.rel_path) return
  await textureStore.toggleFileExclusion(item.mod_path, item.rel_path, false)
}

const handleOpenTextureFile = async (item) => {
  const filePath = item?.file_path || buildTextureFilePath(item?.mod_path, item?.rel_path)
  if (!filePath) return
  await appStore.openFile(filePath)
}

const handleOpenTextureFolder = async (item) => {
  const filePath = item?.file_path || buildTextureFilePath(item?.mod_path, item?.rel_path)
  if (!filePath) return
  await appStore.openPath(filePath)
}

const handleOpenToddsLog = async (item) => {
  const logPath = getFailedItemLogPath(item)
  if (!logPath) return
  await appStore.openFile(logPath)
}

const handleAddPathExclusion = async () => {
  const rawPaths = String(pathExclusionInput.value || '')
    .split(/\r?\n/)
    .map(stripPathQuotes)
    .filter(Boolean)
  if (rawPaths.length === 0) return

  let addedCount = 0
  let unmatchedCount = 0
  for (const rawPath of rawPaths) {
    const matched = resolvePastedTexturePath(rawPath)
    if (!matched) {
      unmatchedCount += 1
      continue
    }
    const ok = await textureStore.toggleFileExclusion(matched.mod_path, matched.rel_path, true)
    if (ok) addedCount += 1
  }

  if (addedCount > 0) {
    pathExclusionInput.value = ''
  }
  if (unmatchedCount > 0) {
    toast.warning(`有 ${unmatchedCount} 条路径无法匹配到已安装模组目录`)
  }
}

function getFailedItemLogPath(item) {
  return String(
    item?.todds_log_path
    || progressState.value.details?.todds_log_path
    || selectedHistoryResult.value?.todds_log_path
    || ''
  ).trim()
}

function resolveModName(item) {
  const match = Array.from(modStore.allModsMap.values()).find(mod => mod?.path === item.mod_path)
  return match?.alias_name || match?.display_name || match?.name || item.mod_name || '未知模组'
}

function buildTextureFilePath(modPath, relPath) {
  const root = String(modPath || '').trim().replace(/\\/g, '/').replace(/\/+$/, '')
  const rel = String(relPath || '').trim().replace(/\\/g, '/').replace(/^\/+/, '')
  if (!root) return rel
  if (!rel) return root
  return `${root}/${rel}`
}

function resolvePastedTexturePath(rawPath) {
  const normalizedPath = normalizePathKey(rawPath)
  const matchedMod = pathExclusionCandidates.value.find(item => {
    const root = normalizePathKey(item.mod_path)
    return root && (normalizedPath === root || normalizedPath.startsWith(`${root}/`))
  })
  if (!matchedMod?.mod_path) return null

  const normalizedRoot = String(matchedMod.mod_path || '').trim().replace(/\\/g, '/').replace(/\/+$/, '')
  const normalizedRaw = String(rawPath || '').trim().replace(/\\/g, '/')
  const relPath = normalizedRaw.slice(normalizedRoot.length).replace(/^\/+/, '')
  if (!relPath) return null
  return {
    mod_path: matchedMod.mod_path,
    rel_path: relPath,
  }
}


function formatDuration(ms) {
  const totalSeconds = Math.max(0, Math.floor(Number(ms || 0) / 1000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

function formatDateTime(value) {
  const ts = Number(value || 0)
  if (!ts) return '--'
  return new Date(ts).toLocaleString()
}

</script>

<style scoped>
.panel-slide-enter-active,
.panel-slide-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}

.panel-slide-enter-from,
.panel-slide-leave-to {
  opacity: 0;
  transform: translateX(1.5rem);
}

.custom-scrollbar::-webkit-scrollbar {
  width: 0.375rem;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: var(--color-border-strong);
  border-radius: 0.625rem;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: var(--color-accent-primary);
}
</style>
