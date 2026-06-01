<template>
  <CommonModalShell :show="appStore.uiState.showUpdateModal" :show-header="false"
    :close-on-backdrop="false" size="custom" :z-index="9999" accent="primary" panel-class="update-modal-box w-full max-w-2xl max-h-[85vh]" content-class="h-full flex flex-col"
    @backdrop="shakeComponent('.update-modal-box')"
    @close="closeModal"
  >
        
        <!-- 背景光效 -->
        <div class="absolute top-0 left-1/2 -translate-x-1/2 w-[120%] h-32 bg-accent-primary/20 blur-[60px] rounded-full pointer-events-none"></div>

        <!-- Header -->
        <header class="relative px-5 py-3 bg-bg-deep/40 border-b border-border-base/5 flex items-center justify-between shrink-0">
          <div class="flex items-center gap-4">
            <div class="p-2 bg-accent-primary/20 text-accent-primary rounded-xl shadow-[0_0_15px_rgba(var(--rgb-accent-primary),0.3)]">
              <svg class="size-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
            </div>
            <div>
              <h2 class="text-2xl font-black text-text-main tracking-wide">{{ modalTitle }}</h2>
              <p class="text-sm text-text-dim mt-1">
                <template v-if="isUpgradeView">
                  从 <span class="font-mono">{{ oldVersion }}</span> 跃升至 <span class="font-mono text-accent-primary font-bold">{{ currentVersion }}</span>
                </template>
                <template v-else>
                  查看当前版本线的完整变更记录
                </template>
              </p>
            </div>
          </div>
          
          <div class="flex items-center gap-2">
            <common-switch v-model="showFullHistory" mini label="完整历史" class="w-35" />
            <button class="modal-close-button" aria-label="关闭" @click="closeModal">
              <X class="size-4" />
            </button>
          </div>
        </header>

        <!-- 滚动时间线区域 -->
        <div class="flex-1 overflow-y-auto p-5 custom-scrollbar relative z-10">
          <div v-if="displayedLogs.length === 0" class="text-center text-text-dim py-10">
            没有找到更新记录...
          </div>
          <div v-else class="relative space-y-5 before:absolute before:inset-0 before:ml-3 before:h-full before:-left-[0.05rem] before:w-0.5 before:bg-linear-to-b before:from-transparent before:via-text-main/10 before:to-transparent">
            <!-- 每一版的记录 -->
            <div v-for="(log, idx) in displayedLogs" :key="log.version" 
                class="relative flex items-start gap-5 group">
              <!-- 圆点：固定在左侧线条上 -->
              <div class="flex self-center w-6 h-6 flex-none shrink-0 rounded-full border-4 border-bg-surface bg-bg-overlay/10 text-text-dim shadow z-10 transition-colors duration-300"
                  :class="{ 'bg-accent-primary border-accent-primary/30 ring-2 ring-accent-primary': idx === 0 }">
              </div>
              <!-- 内容卡片：占据右侧剩余空间 (flex-1) -->
              <div class="modal-section flex-1 rounded-xl p-4 backdrop-blur-sm transition-all hover:bg-bg-inset/80 hover:border-border-base/18 hover:shadow-lg">
                <div class="flex items-center justify-between mb-3">
                  <span class="text-lg font-black font-mono text-text-main" :class="{'text-accent-primary drop-shadow-[0_0_5px_rgba(var(--rgb-accent-primary),0.8)]': idx === 0}">
                    v{{ log.version }}
                  </span>
                  <span class="text-xs text-text-dim bg-bg-overlay/10 px-2 py-0.5 rounded-full">{{ log.date || '开发中' }}</span>
                </div>
                <div class="space-y-4">
                  <section
                    v-for="(entry, entryIdx) in log.entries || []"
                    :key="`${log.version}-${entryIdx}-${entry.title || 'entry'}`"
                    class="space-y-2.5"
                    :class="{ 'border-t border-border-base/10 pt-4': entryIdx > 0 }"
                  >
                    <div v-if="entry.title" class="text-xs font-bold uppercase tracking-[0.18em] text-text-dim">
                      {{ entry.title }}
                    </div>
                    <ul class="space-y-2.5">
                      <li v-for="(change, cIdx) in entry.changes || []" :key="cIdx" class="flex items-start gap-2 text-sm text-text-soft">
                        <span v-if="change.type === 'feature'" class="shrink-0 mt-0.5" ><CircleFadingPlus class="size-4 text-accent-tip"/></span>
                        <span v-else-if="change.type === 'optimize'" class="shrink-0 mt-0.5" ><Zap class="size-4 text-accent-special"/></span>
                        <span v-else-if="change.type === 'fix'" class="shrink-0 mt-0.5" ><Bug class="size-4 text-accent-warn"/></span>
                        <span v-else-if="change.type === 'breaking'" class="shrink-0 mt-0.5" ><Dna class="size-4 text-accent-highlight"/></span>
                        <span v-else class="shrink-0 mt-0.5"><Zap class="size-4 text-text-dim"/></span>
                        <span class="leading-relaxed">{{ change.text }}</span>
                      </li>
                    </ul>
                  </section>
                </div>
              </div>

            </div>
          </div>
        </div>

        <!-- Footer -->
        <footer class="px-8 py-4 border-t border-border-base/5 bg-bg-overlay/5 flex justify-end shrink-0 relative z-10">
          <button @click="closeModal" 
            class="px-8 py-2.5 bg-accent-primary hover:bg-accent-primary/90 text-on-accent-primary text-sm font-bold rounded-xl shadow-[0_0_15px_rgba(var(--rgb-accent-primary),0.4)] hover:scale-105 active:scale-95 transition-all">
            我知道了
          </button>
        </footer>
  </CommonModalShell>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useAppStore } from '../stores/appStore'
import { shakeComponent } from '../utils/domEffects'
import CommonSwitch from './common/input/CommonSwitch.vue'
import CommonModalShell from './common/CommonModalShell.vue'
import { Bug, CircleFadingPlus, Dna, Zap, X } from 'lucide-vue-next'
import { useToast } from 'vue-toastification'

const appStore = useAppStore()
const toast = useToast()



// 状态控制
const showFullHistory = ref(false)

// 获取上下文数据
const context = computed(() => appStore.upgradeContext || {})
const currentVersion = computed(() => context.value.new_version || '0.0.0')
const oldVersion = computed(() => context.value.old_version || '0.0.0')
const allLogs = computed(() => context.value.changelog || [])
const isUpgradeView = computed(() => !!context.value.version_changed && currentVersion.value !== oldVersion.value)
const modalTitle = computed(() => isUpgradeView.value ? '版本升级成功' : '更新日志')

// 监听弹窗打开动作
watch(() => appStore.uiState.showUpdateModal, (isOpen) => {
  if (isOpen) {
    // 逻辑判定：
    // 如果是版本升级（context.version_changed 为 true）且是刚打开，默认看增量
    // 如果是手动点击按钮（此时 version_changed 通常会被重置，或者版本号已一致），则强制看全量
    if (!context.value.version_changed || currentVersion.value === oldVersion.value) {
      showFullHistory.value = true
    } else {
      showFullHistory.value = false
    }
  }
})

// 简单的版本号比较器 (例如 '0.18.4' > '0.17.10' 返回 1)
const compareVersions = (v1, v2) => {
  const p1 = v1.split('.').map(Number);
  const p2 = v2.split('.').map(Number);
  for (let i = 0; i < Math.max(p1.length, p2.length); i++) {
    const n1 = p1[i] || 0;
    const n2 = p2[i] || 0;
    if (n1 > n2) return 1;
    if (n1 < n2) return -1;
  }
  return 0;
}

// 动态计算显示的日志
const displayedLogs = computed(() => {
  // 如果开启了“完整历史”，或者日志库里只有一条，直接全显示
  if (showFullHistory.value || allLogs.value.length <= 1) {
    return allLogs.value;
  }
  // 增量模式：只显示已发布、且位于升级区间内的版本
  const filtered = allLogs.value.filter(log => (
    !!log.date
    && compareVersions(log.version, oldVersion.value) > 0
    && compareVersions(log.version, currentVersion.value) <= 0
  ));
  // 兜底：如果增量过滤完啥都没了，还是显示全量吧
  return filtered.length > 0 ? filtered : allLogs.value;
})

// 关闭逻辑
const closeModal = () => {
  appStore.uiState.showUpdateModal = false
  // 可选：触发一个推荐扫描的通知
  if (context.value.pending_actions?.includes('recommend_scan')) {
    toast.info("建议执行一次全量扫描，以应用新版本的核心引擎特性！", { timeout: 5000 })
  }
}

</script>
