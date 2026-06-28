<template>
  <transition name="fade">
    <div v-if="visible" class="fixed inset-0 z-100 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div
        class="w-5/7 max-h-9/10 flex flex-col bg-bg-deep border border-accent-danger/30 rounded-xl shadow-2xl overflow-hidden">

        <!-- Header -->
        <div class="px-6 py-4 bg-accent-danger/10 border-b border-accent-danger/20 flex items-center justify-between shrink-0">
          <div class="flex items-center gap-3">
            <div class="p-2 rounded-full bg-accent-danger/20 text-accent-danger animate-pulse">
              <svg class="size-6" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3" /><path d="M12 9v4" /><path d="M12 17h.01" /></svg>
            </div>
            <div>
              <h2 class="text-lg font-bold text-white">发现模组冲突</h2>
              <p class="text-sm text-text-dim">检测到 {{ localConflicts.length }} 组重复的包ID。请为每一组选择一个<span
                  class="text-accent-success font-bold">保留版本</span>。</p>
            </div>
          </div>
          <common-switch v-model="appStore.settings.show_coexistence_message" @click="appStore.saveSetting('show_coexistence_message', appStore.settings.show_coexistence_message)"
            label="显示共存问题" mini description="关闭后，仅显示冲突的包ID，不显示版本共存问题"
            class="w-45 text-xs text-text-dim peer-disabled:cursor-not-allowed hover:text-white transition-colors"
          />
        </div>

        <!-- 滚动列表区 -->
        <div class="flex-1 overflow-y-auto p-6 space-y-6">

          <!-- 循环每一组冲突：key 改为 package_id -->
          <div v-for="group in localConflicts" :key="group.package_id"
            class="bg-white/5 rounded-xl border border-white/10 overflow-hidden">

            <!-- 组标题 -->
            <div class="flex-1 bg-black/20 px-4 py-2 border-b border-white/5 flex justify-between items-center">
              <div class="flex items-center gap-2 min-w-0">
                <span class="font-mono text-sm font-bold text-accent-highlight truncate">{{ group.package_id }}</span>
                <!-- 增加类型标签提示 -->
                <span v-if="group._type === 'hard'" v-tooltip="'!!在同一个目录下发现重复文件，这可能会引起冲突，需要处理!!'"
                  class="px-1.5 py-0.5 rounded bg-accent-danger/20 cursor-help text-accent-danger text-[10px] font-black uppercase border border-accent-danger/30">同级冲突</span>
                <span v-else v-tooltip="'不同目录下发现重复文件，这是正常现象，可选择处理，游戏会默认使用本地版本'"
                  class="px-1.5 py-0.5 rounded bg-blue-500/20 cursor-help text-blue-400 text-[10px] font-black uppercase border border-blue-500/30">版本共存</span>
              </div>
              <div class="text-xs text-text-dim shrink-0">发现 {{ group.items.length }} 个副本</div>
            </div>

            <!-- 版本选项列表 -->
            <div class="p-3 grid gap-2 grid-cols-1">
              <!-- key 改为 mod.path，选中判断改为 selections[group.package_id] -->
              <div v-for="mod in group.items" :key="mod.path" @click="selectVersion(group.package_id, mod.path)"
                class="relative flex items-center p-3 rounded-lg border transition-all cursor-pointer group/item"
                :class="selections[group.package_id] === mod.path
                  ? 'bg-accent-success/10 border-accent-success ring-1 ring-accent-success/50'
                  : 'bg-black/20 border-white/5 opacity-70 hover:opacity-100 hover:border-white/20'">
                <!-- 选中标记 -->
                <div class="w-5 h-5 rounded-full border flex items-center justify-center mr-4 shrink-0 transition-colors"
                  :class="selections[group.package_id] === mod.path ? 'border-accent-success bg-accent-success text-black' : 'border-white/30'">
                  <svg v-if="selections[group.package_id] === mod.path" class="size-4" viewBox="0 0 24 24" fill="none"
                    stroke="currentColor" stroke-width="4">
                    <path d="M20 6L9 17l-5-5" />
                  </svg>
                </div>

                <!-- Mod 信息 -->
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="font-bold text-sm text-white truncate">{{ mod.name }}</span>
                    <span class="px-1.5 py-0.5 rounded bg-white/10 text-xs font-mono text-accent-primary">
                      v{{ mod.version || '?' }}</span>
                    <!-- 来源高亮 -->
                    <span class="text-xs px-1 rounded"
                      :class="mod.source === 'local' ? 'text-accent-success border border-accent-success/30' : (mod.source === 'workshop' ? 'text-accent-primary border border-accent-primary/10' : 'text-text-dim border border-text-dim/10')">
                      {{ mod.source }}</span>
                  </div>
                  <div class="text-xs text-text-dim mt-1 truncate font-mono" :title="mod.path">{{ mod.path }}</div>
                </div>

                <!-- 未选中时的操作配置 (禁用/删除) -->
                <!-- 只有当此项未被选中时才显示 -->
                <div v-if="selections[group.package_id] !== mod.path" @click.stop
                  class="ml-4 flex items-center gap-3 px-3 py-1.5 rounded bg-black/40 border border-white/5">
                  <span class="text-xs text-text-dim">处理方式:</span>
                  <!-- radio 的 name 使用 mod.path 保证唯一性 -->
                  <label class="flex items-center gap-1 cursor-pointer hover:text-white transition-colors">
                    <input type="radio" :name="`act-${mod.path}`" value="disable" v-model="actionMap[mod.path]"
                      class="accent-accent-primary w-3 h-3">
                    <span class="text-xs">禁用</span>
                  </label>
                  <label class="flex items-center gap-1 cursor-pointer hover:text-accent-danger transition-colors">
                    <input type="radio" :name="`act-${mod.path}`" value="delete" v-model="actionMap[mod.path]"
                      class="accent-accent-danger w-3 h-3">
                    <span class="text-xs">删除</span>
                  </label>
                </div>

                <!-- 选中状态文字 -->
                <div v-else
                  class="ml-4 px-3 py-1.5 rounded bg-accent-success/20 text-accent-success text-xs font-bold border border-accent-success/20">
                  将保留并使用
                </div>

              </div>
            </div>
          </div>

        </div>

        <!-- Footer -->
        <div class="py-4 px-6 bg-black/20 border-t border-white/5 flex justify-between items-center shrink-0">
          <div class="text-sm text-text-dim">
            <span class="text-accent-warn">注意：</span> 选择删除将直接移除文件至回收站，操作不可逆。<br>禁用则会通过修改加载文件(About.xml)名称，让游戏无法检测，保留文件。
          </div>
          <div class="flex gap-3">
            <div @click.stop class="ml-4 flex items-center gap-3 px-3 py-1.5 rounded bg-black/40 border border-white/5">
              <span class="text-xs text-text-dim">一键批量:</span>
              <!-- radio 的 name 使用 mod.path 保证唯一性 -->
              <label class="flex items-center gap-1 cursor-pointer hover:text-white transition-colors">
                <input type="radio" name="allActionState" value="disable" v-model="allActionState"
                  class="accent-accent-primary w-3 h-3">
                <span class="text-xs">禁用</span>
              </label>
              <label class="flex items-center gap-1 cursor-pointer hover:text-accent-danger transition-colors">
                <input type="radio" name="allActionState" value="delete" v-model="allActionState"
                  class="accent-accent-danger w-3 h-3">
                <span class="text-xs">删除</span>
              </label>
            </div>
            <button @click="submit" :disabled="processing"
              class="px-8 py-2.5 rounded-lg bg-accent-primary hover:bg-accent-primary/80 text-black text-sm font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 shadow-lg shadow-accent-primary/20">
              <span v-if="processing" class="animate-spin">⟳</span>
              {{ processing ? '处理中...' : '确认解决所有冲突' }}
            </button>
          </div>
        </div>

      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, watch, reactive, computed } from 'vue'
import { useModStore } from '../stores/modStore'
import { useAppStore } from '../stores/appStore'
import { useToast } from "vue-toastification"
import CommonSwitch from './common/input/CommonSwitch.vue'

const appStore = useAppStore()
const modStore = useModStore()
const toast = useToast()

const visible = ref(false)
const processing = ref(false)
const localConflicts = ref([]) // 本地副本，避免直接操作 store 引用

// 状态管理：使用 package_id 做键，而非索引
// selections: { groupIndex: selectedPath }  记录每组选了哪个
const selections = reactive({})
// actionMap: { path: 'disable' | 'delete' } 记录每个路径的具体操作
const actionMap = reactive({})

watch(
  // 增加对设置项的监听，这样用户在设置中切换开关时，UI 能即时反应
  [
    () => modStore.conflictList,
    () => modStore.coexistenceList,
    () => appStore.settings.show_coexistence_message
  ],
  ([conflictsVal, coexistencesVal, showCoexistence]) => {
    // console.log('处理冲突', showCoexistence, coexistencesVal, conflictsVal)
    // 1. 汇总最终需要显示的列表
    const totalList = [];

    // --- 处理硬冲突 (同目录重复) ---
    // 逻辑：这类冲突会导致系统混乱，无论设置如何，通常都建议显示并让用户处理
    if (conflictsVal?.length > 0) {
      // 给每个组标记类型，方便在模板中显示不同的 UI 样式或标签
      totalList.push(...conflictsVal.map(g => ({ ...g, _type: 'hard' })));
      // console.log('conflictsVal', conflictsVal)
    }

    // --- 处理共存/软冲突 (跨目录重复) ---
    // 逻辑：仅当用户开启了“显示共存提示”开关时，才加入处理列表
    if (showCoexistence && coexistencesVal?.length > 0) {
      totalList.push(...coexistencesVal.map(g => ({ ...g, _type: 'soft' })));
      // console.log('coexistencesVal', coexistencesVal)
    }

    // 2. 更新 UI 绑定的冲突列表数据
    // 注意：这里将过滤后的汇总列表赋值给 conflicts.value 供模板遍历
    localConflicts.value = totalList;

    // 3. 执行初始化逻辑
    if (totalList.length > 0) {
      // 清空旧的选择和映射（防止数据残留）
      Object.keys(selections).forEach(key => delete selections[key]);
      Object.keys(actionMap).forEach(key => delete actionMap[key]);
      totalList.forEach((group) => {
        const pid = group.package_id;

        // 智能默认选择：优先保留 Local 来源的 Mod
        const localVersion = group.items.find(m => m.source === 'workshop');
        const defaultWinner = localVersion || group.items[0];

        selections[pid] = defaultWinner.path;

        // 初始化该组内所有项的操作状态
        group.items.forEach(mod => {
          // 默认操作为 disable (禁用 About.xml)
          // 这里的逻辑可以优化：如果是 winner，UI 上可以禁用操作选择
          actionMap[mod.path] = 'disable';
        });
      });

      // 显示冲突解决弹窗
      visible.value = true;
    } else {
      // 如果没有需要处理的项，确保弹窗关闭
      visible.value = false;
    }
  },
  { deep: true, immediate: true }
);

// 所有操作状态
const allActionState = computed({
    get() {
      // 返回操作状态合集结果，只有所有项都为True 或者所有项都为False 才返回True 或False，否则返回null
      const states = Object.values(actionMap)
      if (states.every(state => state === 'disable')) {
          return 'disable'
      } else if (states.every(state => state === 'delete')) {
          return 'delete'
      } else {
          return ''
      }
    },
    set(val) {
      if (val !== '') {
          // 遍历所有路径，根据 val 统一设置状态
          Object.keys(actionMap).forEach(key => {
              actionMap[key] = val;
          });
      }
    }
})

// 修改选择函数
const selectVersion = (packageId, path) => {
  selections[packageId] = path
}

const submit = async () => {
  processing.value = true

  // 构造操作列表
  const operations = []

  localConflicts.value.forEach((group) => {
    const pid = group.package_id;
    const keepPath = selections[pid];

    // 这一组的 package_id

    // 遍历该组所有项
    group.items.forEach(mod => {
      if (mod.path !== keepPath) {
        // 只有非保留项才产生操作指令
        operations.push({
          action: actionMap[mod.path],
          target_path: mod.path,
          keep_id: pid
        })
      }
    })
  })

  if (operations.length === 0) {
    toast.info("未检测到需要执行的操作");
    visible.value = false;
    processing.value = false;
    return;
  }
  try {
    const res = await window.pywebview.api.resolve_scan_conflicts(operations)
    if (res.status === 'success') {
      toast.success("冲突已解决，正在刷新列表...")
      // 关键：先清理 Store 中的状态，防止弹窗逻辑因异步扫描再次触发
      modStore.conflictList = []
      modStore.coexistenceList = []
      visible.value = false
      // 强制重置扫描状态，确保重新开始
      await appStore.refreshData() // 这会读取数据库，但数据库里现在还没有新Mod
      // 关键：必须重新触发一次扫描，让保留下来的那个Mod（因为没有竞争者了）正常入库
      modStore.scanMods()
    } else {
      toast.error("处理失败: " + res.message)
    }
  } catch (e) {
    toast.error("API 调用异常")
    console.error(e)
  } finally {
    processing.value = false
  }
}
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>