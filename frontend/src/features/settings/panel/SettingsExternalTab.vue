<template>
              <section class="animate-in fade-in slide-in-from-right-4">
                <h3 class="text-lg font-bold text-text-main mb-6 flex items-center justify-between">外部依赖
                  <button @click="resetToDefaultExternalPaths" :disabled="isPending('reset-default-paths')" :class="isPending('reset-default-paths') ? 'app-action-disabled' : ''"
                    v-tooltip="isPending('reset-default-paths') ? '正在读取默认路径' : '将外部依赖相关路径重置为默认值'" class="inline-flex items-center gap-1 px-3 py-1 bg-accent-warn/10 hover:bg-accent-warn/20 border border-accent-warn/30 rounded text-xs font-bold text-accent-warn transition-all">
                    <LoaderCircle v-if="isPending('reset-default-paths')" class="size-3 animate-spin" />
                    {{ isPending('reset-default-paths') ? '读取中' : '重置为默认路径' }}
                  </button>
                </h3>
                <div class="space-y-6">
                  <div class="modal-section space-y-4 p-5">
                    <div class="flex items-center justify-between gap-3">
                      <div> <h4 class="text-sm font-bold text-text-main">外部工具</h4><p class="text-xs text-text-dim mt-1">SteamCMD、贴图工具等由管理器调用的外部程序配置与状态检查。</p></div>
                      <button @click="handleCheckTools" :disabled="isPending('check-tools')" :class="isPending('check-tools') ? 'app-action-disabled' : ''"
                        class="inline-flex items-center gap-1 px-3 py-1.5 bg-accent-tip/10 hover:bg-accent-tip/25 border border-accent-tip/20 rounded-lg text-xs font-bold transition-all">
                        <LoaderCircle v-if="isPending('check-tools')" class="size-3 animate-spin" />
                        {{ isPending('check-tools') ? '检查中' : '检查外部工具' }}
                      </button>
                    </div>
                    <div class="grid grid-cols-2 gap-4">
                      <CommonPathInput class="col-span-2" label="模组下载工具目录" v-model="formData.steamcmd_path" @browse="handleBrowse('steamcmd_path')" @blur="checkPath('steamcmd_path', formData.steamcmd_path)" :check="formData.check_info?.steamcmd_path" :description="'管理器下载和更新工坊模组使用的 SteamCMD 目录，应选择包含 steamcmd.exe 的文件夹。'" />
                      <CommonPathInput class="col-span-2" label="文本搜索工具目录" v-model="formData.ripgrep_path" @browse="handleBrowse('ripgrep_path')" @blur="checkPath('ripgrep_path', formData.ripgrep_path)" :check="formData.check_info?.ripgrep_path" :description="'文件内容搜索优先使用的 ripgrep 工具目录，应选择包含 rg.exe 的文件夹。'" />
                      <CommonPathInput class="col-span-2" label="贴图优化工具目录" v-model="formData.texture_opt.texture_tools_path" @browse="handleBrowse('texture_opt.texture_tools_path', null, 'texture_tools_path')" @blur="checkPath('texture_tools_path', formData.texture_opt.texture_tools_path)" :check="formData.check_info?.texture_tools_path" :description="'贴图优化使用的 todds 工具目录，应选择包含 todds.exe 的文件夹。'" />
                      <CommonSwitch class="col-span-1" label="自动检查外部工具" v-model="formData.enable_auto_tool_check" description="按设定间隔检查 SteamCMD、todds 等外部工具是否缺失或未就绪。" />
                      <CommonNumber class="col-span-1" label="检查间隔（天）" v-model="formData.tool_check_interval_days" :step="1" :min="1" :max="365" />
                    </div>
                  </div>

                  <div class="modal-section space-y-4 p-5">
                    <div class="flex items-center justify-between gap-3">
                      <div> <h4 class="text-sm font-bold text-text-main">外部库与规则</h4><p class="text-xs text-text-dim mt-1">规则库、工坊数据库、替代库等外部数据文件的来源、路径和更新检查。</p></div>
                      <button @click="handleCheckExternalData" :disabled="isPending('check-external-data')" :class="isPending('check-external-data') ? 'app-action-disabled' : ''"
                        class="inline-flex items-center gap-1 px-3 py-1.5 bg-accent-primary/10 hover:bg-accent-primary/25 border border-accent-primary/20 rounded-lg text-xs font-bold transition-all">
                        <LoaderCircle v-if="isPending('check-external-data')" class="size-3 animate-spin" />
                        {{ isPending('check-external-data') ? '检查中' : '检查外部库更新' }}
                      </button>
                    </div>

                    <CommonPathInput label="用户规则路径" v-model="formData.user_rules_path" @browse="handleBrowse('user_rules_path', ['JSON Files (*.json)'])" :check="formData.check_info?.user_rules_path" description="本地用户规则文件，用来保存自定义排序、依赖和冲突规则。" />
                    <div class="flex items-end gap-1.5">
                        <CommonInput label="社区规则库 URL" v-model="formData.community_rules_url" description="RimSort 维护的规则库文件，用来补充排序、依赖和冲突规则。" />
                      <button @click="ruleStore.updateCommunity()" :disabled="ruleStore.isLoading" v-tooltip="ruleStore.isLoading ? '正在下载更新社区规则' : '下载更新 社区规则'" :class="ruleStore.isLoading ? 'app-action-disabled' : ''"
                        class="shrink-0 h-9 w-9 bg-accent-tip/10 hover:bg-accent-tip text-accent-tip hover:text-text-main border border-accent-tip/30 rounded-lg flex items-center justify-center transition-colors">
                        <LoaderCircle v-if="ruleStore.isLoading" class="size-5 animate-spin" />
                        <Download v-else class="size-5" />
                      </button>
                    </div>
                    <CommonPathInput label="社区规则库路径" v-model="formData.community_rules_path" @browse="handleBrowse('community_rules_path', ['JSON Files (*.json)'])" :check="formData.check_info?.community_rules_path" description="社区规则库的本地缓存文件。" />
                    
                    <div class="py-2 pt-2 place-self-center w-[90%] border-b border-border-base/10"></div>
                    <div class="flex items-end gap-1.5">
                      <CommonInput label="工坊数据库 URL" v-model="formData.community_workshop_db_url" description="工坊信息数据库，用来补充模组名称、作者和简介。来源：社区缓存文件。" />
                      <button @click="updateExternalDB('workshop_db')" :disabled="downloadState['workshop_db']" v-tooltip="downloadState['workshop_db'] ? '正在下载更新社区工坊数据库' : '下载更新 社区工坊数据库'" :class="downloadState['workshop_db'] ? 'app-action-disabled' : ''"
                        class="shrink-0 h-9 w-9 bg-accent-tip/10 hover:bg-accent-tip text-accent-tip hover:text-text-main border border-accent-tip/30 rounded-lg flex items-center justify-center transition-colors">
                        <LoaderCircle v-if="downloadState['workshop_db']" class="size-5 animate-spin" />
                        <Download v-else class="size-5" />
                      </button>
                    </div>
                    <CommonPathInput label="工坊数据库路径" v-model="formData.community_workshop_db_path" @browse="handleBrowse('community_workshop_db_path', ['JSON Files (*.json)'])" :check="formData.check_info?.community_workshop_db_path" description="工坊信息数据库的本地缓存文件。" />
                    <div class="py-2 pt-2 place-self-center w-[90%] border-b border-border-base/10"></div>
                    <div class="flex items-end gap-1.5">
                      <CommonInput label="替代 Mod 数据库 URL" v-model="formData.community_instead_db_url" description="替代 Mod 数据库，用来提示失效、重制或推荐替代项。来源：社区缓存文件。" />
                      <button @click="updateExternalDB('instead_db')" :disabled="downloadState['instead_db']" v-tooltip="downloadState['instead_db'] ? '正在下载更新社区替代 Mod 数据库' : '下载更新 社区替代 Mod 数据库'" :class="downloadState['instead_db'] ? 'app-action-disabled' : ''"
                        class="shrink-0 h-9 w-9 bg-accent-tip/10 hover:bg-accent-tip text-accent-tip hover:text-text-main border border-accent-tip/30 rounded-lg flex items-center justify-center transition-colors">
                        <LoaderCircle v-if="downloadState['instead_db']" class="size-5 animate-spin" />
                        <Download v-else class="size-5" />
                      </button>
                    </div>
                    <CommonPathInput label="替代 Mod 数据库路径" v-model="formData.community_instead_db_path" @browse="handleBrowse('community_instead_db_path', ['JSON Files (*.json;*.gz)'])" :check="formData.check_info?.community_instead_db_path" description="替代 Mod 数据库的本地缓存文件。" />
                    <div class="py-2 pt-2 place-self-center w-[90%] border-b border-border-base/10"></div>
                    <div class="flex items-center gap-1.5">
                      <div class="w-full">
                        <div class="flex justify-between items-center px-1 mb-1">
                          <label class="text-xs text-text-dim uppercase font-bold tracking-widest">
                            Git 推荐清单来源
                            <span v-tooltip="'每行一个来源，格式：名称|URL。留空时使用默认推荐清单。'" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</span>
                          </label>
                        </div>
                        <textarea v-model="formData.git_provider_catalog_url" rows="3"
                          class="input-glass w-full resize-y px-3 py-2 font-mono text-sm text-text-main focus:outline-none"
                          placeholder="RJW|https://example.invalid/providers.json"></textarea>
                        <p class="text-xs text-text-dim mt-1 px-1">Git 模组推荐清单，用来提供可订阅的仓库来源。</p>
                      </div>
                      <button @click="updateExternalDB('git_provider_catalog')" :disabled="downloadState['git_provider_catalog']" v-tooltip="downloadState['git_provider_catalog'] ? '正在刷新 Git 推荐清单' : '刷新 Git 推荐清单'" :class="downloadState['git_provider_catalog'] ? 'app-action-disabled' : ''"
                        class="shrink-0 mb-0.5 h-9 w-9 bg-accent-tip/10 hover:bg-accent-tip text-accent-tip hover:text-text-main border border-accent-tip/30 rounded-lg flex items-center justify-center transition-colors">
                        <LoaderCircle v-if="downloadState['git_provider_catalog']" class="size-5 animate-spin" />
                        <Download v-else class="size-5" />
                      </button>
                    </div>
                    <div class="py-2 pt-2 place-self-center w-[90%] border-b border-border-base/10"></div>
                    <div class="flex items-end gap-1.5">
                      <CommonInput label="联机模组兼容表 URL" v-model="formData.multiplayer_compatibility_url" description="Multiplayer 的兼容等级表，用来显示联机兼容状态。来源：官方接口。" />
                      <button @click="updateExternalDB('multiplayer_compatibility')" :disabled="downloadState['multiplayer_compatibility']" v-tooltip="downloadState['multiplayer_compatibility'] ? '正在刷新 Multiplayer 兼容表' : '刷新 Multiplayer 兼容表'" :class="downloadState['multiplayer_compatibility'] ? 'app-action-disabled' : ''"
                        class="shrink-0 h-9 w-9 bg-accent-tip/10 hover:bg-accent-tip text-accent-tip hover:text-text-main border border-accent-tip/30 rounded-lg flex items-center justify-center transition-colors">
                        <LoaderCircle v-if="downloadState['multiplayer_compatibility']" class="size-5 animate-spin" />
                        <Download v-else class="size-5" />
                      </button>
                    </div>
                    <CommonPathInput label="联机模组兼容表路径" v-model="formData.multiplayer_compatibility_path" @browse="handleBrowse('multiplayer_compatibility_path', ['JSON Files (*.json)'])" :check="formData.check_info?.multiplayer_compatibility_path" description="联机模组兼容表的本地缓存文件。" />
                    <div class="flex items-end gap-1.5">
                      <CommonInput label="联机兼容修正模组支持表 URL" v-model="formData.mp_compat_package_ids_url" description="Multiplayer Compatibility 的修正支持表，用来标记可由辅助模组修正的模组。来源：源码解析。" />
                      <button @click="updateExternalDB('mp_compat_package_ids')" :disabled="downloadState['mp_compat_package_ids']" v-tooltip="downloadState['mp_compat_package_ids'] ? '正在刷新 Multiplayer Compatibility 支持表' : '刷新 Multiplayer Compatibility 支持表'" :class="downloadState['mp_compat_package_ids'] ? 'app-action-disabled' : ''"
                        class="shrink-0 h-9 w-9 bg-accent-tip/10 hover:bg-accent-tip text-accent-tip hover:text-text-main border border-accent-tip/30 rounded-lg flex items-center justify-center transition-colors">
                        <LoaderCircle v-if="downloadState['mp_compat_package_ids']" class="size-5 animate-spin" />
                        <Download v-else class="size-5" />
                      </button>
                    </div>
                    <CommonPathInput label="联机兼容修正模组支持表路径" v-model="formData.mp_compat_package_ids_path" @browse="handleBrowse('mp_compat_package_ids_path', ['JSON Files (*.json)'])" :check="formData.check_info?.mp_compat_package_ids_path" description="联机兼容修正模组支持表的本地缓存文件。" />
                    <div class="grid grid-cols-2 gap-4 pt-1">
                      <CommonSwitch class="col-span-1" label="自动检查外部库更新" v-model="formData.enable_auto_external_data_update_check" description="按设定间隔检查规则库、工坊数据库、替代库、联机兼容数据和 Git 推荐清单是否有更新。" />
                      <CommonSwitch class="col-span-1" label="静默更新外部库" :disabled="!formData.enable_auto_external_data_update_check" :model-value="silentExternalDataUpdateEnabled" @update:modelValue="updateSilentExternalDataUpdate"
                        :description="formData.enable_auto_external_data_update_check ? '开启后，自动检查发现外部库更新时会直接刷新，不再弹窗询问；手动检查仍会让你确认。' : '需要先开启自动检查外部库更新。'" />
                      <CommonNumber class="col-span-1" label="检查间隔（天）" v-model="formData.external_data_update_check_interval_days" :step="1" :min="1" :max="365" />
                    </div>
                  </div>
                </div>
              </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Download, LoaderCircle } from 'lucide-vue-next'
import CommonPathInput from '../../../shared/components/input/CommonPathInput.vue'
import CommonSwitch from '../../../shared/components/input/CommonSwitch.vue'
import CommonInput from '../../../shared/components/input/CommonInput.vue'
import CommonNumber from '../../../shared/components/input/CommonNumber.vue'
import { useAppStore } from '../../../app/stores/appStore'
import { useRuleStore } from '../../rules/ruleStore'

const props = defineProps({
  formData: { type: Object, required: true },
  handleBrowse: { type: Function, required: true },
  checkPath: { type: Function, required: true },
})

const appStore = useAppStore()
const ruleStore = useRuleStore()

const downloadState = ref({
  workshop_db: false,
  instead_db: false,
  multiplayer_compatibility: false,
  mp_compat_package_ids: false,
  git_provider_catalog: false,
})
const pendingAction = ref('')
const silentExternalDataUpdateEnabled = computed(() => (
  !!props.formData.enable_auto_external_data_update_check && !!props.formData.enable_silent_external_data_update
))

const resetToDefaultExternalPaths = async () => {
  await runPendingAction('reset-default-paths', async () => {
    // 默认路径按后端当前运行环境生成；贴图工具配置是嵌套对象，需要合并而不是整段覆盖。
    const paths = await appStore.getDefaultExternalPaths()
    if (!paths) return
    const { texture_opt, ...rest } = paths
    Object.assign(props.formData, rest)
    if (texture_opt && typeof texture_opt === 'object') {
      props.formData.texture_opt = {
        ...(props.formData.texture_opt || {}),
        ...texture_opt,
      }
    }
  })
}

const handleCheckTools = async () => {
  await runPendingAction('check-tools', () => appStore.checkToolMaintenance({
    manual: true,
    prompt: true,
    overrides: {
      steamcmd_path: props.formData.steamcmd_path,
      ripgrep_path: props.formData.ripgrep_path,
      texture_opt: props.formData.texture_opt,
    },
  }))
}

const handleCheckExternalData = async () => {
  await runPendingAction('check-external-data', () => appStore.checkExternalDataUpdates({
    manual: true,
    prompt: true,
    overrides: {
      user_rules_path: props.formData.user_rules_path,
      community_rules_url: props.formData.community_rules_url,
      community_rules_path: props.formData.community_rules_path,
      community_workshop_db_url: props.formData.community_workshop_db_url,
      community_workshop_db_path: props.formData.community_workshop_db_path,
      community_instead_db_url: props.formData.community_instead_db_url,
      community_instead_db_path: props.formData.community_instead_db_path,
      multiplayer_compatibility_url: props.formData.multiplayer_compatibility_url,
      multiplayer_compatibility_path: props.formData.multiplayer_compatibility_path,
      mp_compat_package_ids_url: props.formData.mp_compat_package_ids_url,
      mp_compat_package_ids_path: props.formData.mp_compat_package_ids_path,
      git_provider_catalog_url: props.formData.git_provider_catalog_url,
    },
  }))
}

const updateExternalDB = async (dbType) => {
  if (downloadState.value[dbType]) return
  // 每个外部库独立维护下载状态，避免一个按钮下载时锁住其它更新入口。
  downloadState.value[dbType] = true
  try {
    await appStore.updateExternalDB(dbType)
  } finally {
    downloadState.value[dbType] = false
  }
}
const updateSilentExternalDataUpdate = (value) => {
  props.formData.enable_silent_external_data_update = !!props.formData.enable_auto_external_data_update_check && !!value
}
const isPending = (action) => pendingAction.value === action
const runPendingAction = async (action, runner) => {
  if (pendingAction.value) return
  pendingAction.value = action
  try {
    await runner?.()
  } finally {
    pendingAction.value = ''
  }
}
</script>
