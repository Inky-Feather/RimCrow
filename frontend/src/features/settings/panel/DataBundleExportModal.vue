<template>
  <CommonModalShell :show="show" size="default" :z-index="120" accent="primary" panel-class="border-accent-primary/20" content-class="min-h-0 flex flex-col"
    title="导出软件数据" description="勾选要打包的数据；如果选择环境数据，会打包对应环境的完整目录。"
    @close="emit('close')"
  >
    <div class="absolute -top-20 -left-16 w-56 h-56 rounded-full bg-accent-primary/10 blur-3xl pointer-events-none"></div>
    <div class="absolute -bottom-20 -right-16 w-56 h-56 rounded-full bg-accent-special/10 blur-3xl pointer-events-none"></div>

    <div class="relative z-10 flex-1 overflow-y-auto px-5 py-4 custom-scrollbar">
      <div class="grid grid-cols-3 gap-3">
        <label v-for="module in bundleModuleDefs" :key="module.key" class="rounded-xl border px-3 py-2.5 transition-all"
          :class="dataBundleModuleSelection[module.key] ? 'border-accent-primary/40 bg-accent-primary/10' : 'modal-section-subtle hover:border-border-base/18'"
        >
          <div class="flex items-center gap-2">
            <input :checked="!!dataBundleModuleSelection[module.key]" type="checkbox" class="accent-accent-primary"
              @change="toggleDataBundleModule(module.key, $event.target.checked)"
            >
            <span class="text-sm font-bold text-text-main">{{ module.label }}</span>
            <button v-if="buildBundleModuleTooltip(module)" type="button" v-tooltip="buildBundleModuleTooltip(module)" @click.prevent
              class="ml-auto size-5 rounded-full border border-border-base/10 text-xs font-bold text-text-dim hover:text-text-main hover:border-border-base/18 transition-all"
            >?
            </button>
          </div>
        </label>
      </div>

      <div v-if="isBundleProfileModuleSelected" class="modal-section mt-4">
        <button @click="showBundleProfilePicker = !showBundleProfilePicker" class="w-full flex items-center justify-between gap-3 px-4 py-3 text-left" >
          <div>
            <div class="text-sm font-bold text-text-main">环境数据</div>
            <div class="text-xs text-text-dim mt-1">选择要打包的环境。</div>
          </div>
          <span class="text-xs font-bold text-accent-primary">
            {{ showBundleProfilePicker ? '收起' : '展开' }}
          </span>
        </button>

        <div v-if="showBundleProfilePicker" class="px-4 pb-4">
          <div class="grid grid-cols-2 gap-3">
            <label v-for="profile in bundleProfileDefs" :key="profile.id" class="rounded-xl border p-3 transition-all"
              :class="profile.has_user_data ? 'border-border-base/10 bg-bg-inset/55 hover:border-border-base/18' : 'border-accent-danger/20 bg-accent-danger/8 opacity-60'"
            >
              <div class="flex items-start gap-3">
                <input :checked="dataBundleProfileSelection.includes(profile.id)" @change="toggleDataBundleProfile(profile.id, $event.target.checked)" :disabled="!profile.has_user_data" :value="profile.id" type="checkbox" class="mt-0.5 accent-accent-primary"  >
                <div class="min-w-0">
                  <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-sm font-bold text-text-main">{{ profile.name }}</span>
                    <span v-if="profile.is_default" class="text-[0.7rem] px-1.5 py-0.5 rounded bg-accent-highlight/20 text-accent-highlight">默认</span>
                    <span v-if="profile.game_version" class="text-[0.7rem] px-1.5 py-0.5 rounded bg-accent-secondary/20 text-accent-secondary">{{ profile.game_version }}</span>
                  </div>
                  <p class="text-xs text-text-dim mt-1">
                    {{ profile.has_user_data ? (profile.description || '将打包整个环境目录') : '未检测到可打包的用户数据目录' }}
                  </p>
                </div>
              </div>
            </label>
          </div>
        </div>
      </div>
    </div>

    <footer class="modal-footer relative z-10 flex items-center justify-between gap-4 px-5 py-4">
      <p class="text-xs leading-relaxed text-text-dim">
        <span class="text-accent-primary font-bold">环境数据</span> 会打包整个环境目录；
        <span class="text-accent-tip font-bold">路径绑定、敏感信息、当前激活环境 ID</span> 不会导出。
        <span class="text-accent-warn font-bold">环境导入冲突</span> 会在导入面板统一处理新建/覆盖。
      </p>
      <button @click="handleExportDataBundle"
        class="shrink-0 px-5 py-2 rounded-xl bg-accent-primary hover:bg-accent-primary/85 text-on-accent-primary text-sm font-black shadow-[0_0_18px_rgba(var(--rgb-accent-primary),0.24)] transition-all"
      >
        导出当前选择
      </button>
    </footer>
  </CommonModalShell>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import CommonModalShell from '../../../shared/components/modal/CommonModalShell.vue'
import { toast } from '../../../shared/lib/common'
import { useAppStore } from '../../../app/stores/appStore'

const props = defineProps({
  show: Boolean,
  schema: { type: Object, default: () => ({ modules: [], profiles: [] }) },
})
const emit = defineEmits(['close'])

const appStore = useAppStore()

const showBundleProfilePicker = ref(false)
const dataBundleModuleSelection = ref({})
const dataBundleProfileSelection = ref([])

const bundleModuleDefs = computed(() => props.schema?.modules || [])
const bundleProfileDefs = computed(() => props.schema?.profiles || [])
const selectedBundleModuleKeys = computed(() => (
  bundleModuleDefs.value
    .filter(module => !!dataBundleModuleSelection.value?.[module.key])
    .map(module => module.key)
))
const isBundleProfileModuleSelected = computed(() => !!dataBundleModuleSelection.value?.profiles)

// 每次打开弹窗都重新初始化选择，避免上一次导出残留影响本次打包。
const resetDataBundleSelections = () => {
  dataBundleModuleSelection.value = Object.fromEntries(
    bundleModuleDefs.value.map(module => [module.key, false])
  )
  dataBundleProfileSelection.value = []
  showBundleProfilePicker.value = false
}

// 选择模块时递归勾选依赖项，保证导出的数据包结构完整。
const ensureModuleEnabled = (moduleKey, selection) => {
  const target = bundleModuleDefs.value.find(module => module.key === moduleKey)
  if (!target) return
  selection[moduleKey] = true
  for (const dependencyKey of target.dependencies || []) {
    ensureModuleEnabled(dependencyKey, selection)
  }
}

// 取消模块时同步取消依赖它的模块，避免产生缺少前置数据的导出组合。
const disableModuleAndDependents = (moduleKey, selection) => {
  selection[moduleKey] = false
  const dependentKeys = bundleModuleDefs.value
    .filter(module => (module.dependencies || []).includes(moduleKey))
    .map(module => module.key)
  for (const dependentKey of dependentKeys) {
    disableModuleAndDependents(dependentKey, selection)
  }
}

const toggleDataBundleModule = (moduleKey, enabled) => {
  const nextSelection = { ...(dataBundleModuleSelection.value || {}) }
  if (enabled) {
    ensureModuleEnabled(moduleKey, nextSelection)
  } else {
    disableModuleAndDependents(moduleKey, nextSelection)
  }
  dataBundleModuleSelection.value = nextSelection
  if (!nextSelection.profiles) {
    dataBundleProfileSelection.value = []
    showBundleProfilePicker.value = false
  } else if (moduleKey === 'profiles' && enabled) {
    showBundleProfilePicker.value = true
  }
}

const toggleDataBundleProfile = (profileId, enabled) => {
  dataBundleProfileSelection.value = enabled
    ? [...dataBundleProfileSelection.value, profileId]
    : dataBundleProfileSelection.value.filter(id => id !== profileId)
}

const buildBundleModuleTooltip = (module) => {
  const lines = []
  if (module?.description) {
    lines.push(module.description)
  }
  const dependencyLabels = (module?.dependencies || [])
    .map(key => bundleModuleDefs.value.find(item => item.key === key)?.label || key)
  if (dependencyLabels.length) {
    lines.push(`依赖：${dependencyLabels.join('、')}`)
  }
  return lines.join('\n')
}

const handleExportDataBundle = async () => {
  // 导出前只校验用户当前选择，实际打包规则仍由后端 schema 和导出接口决定。
  const moduleKeys = selectedBundleModuleKeys.value
  if (moduleKeys.length === 0) {
    toast.warning('请至少勾选一个要导出的数据模块')
    return
  }
  if (moduleKeys.includes('profiles') && dataBundleProfileSelection.value.length === 0) {
    toast.warning('已勾选环境数据，请至少选择一个环境')
    return
  }

  const exported = await appStore.exportDataBundle({
    preset: 'custom',
    module_keys: moduleKeys,
    profile_ids: dataBundleProfileSelection.value,
  })
  if (exported) {
    emit('close')
  }
}

watch(() => props.show, (visible) => {
  if (visible) resetDataBundleSelections()
})
</script>
