<template>
              <section class="animate-in fade-in slide-in-from-right-4">
                <div class="flex items-center justify-between mb-6">
                  <h3 class="text-lg font-bold text-text-main">环境与路径配置
                    <label v-tooltip="'此处会直接修改当前环境的路径配置'" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
                    <label class="ml-5 text-xs py-0.5 px-2 text-accent-cool bg-accent-cool/20 rounded-md" v-tooltip="`当前环境：${profileStore?.currentProfile?.name}\n说明：${profileStore?.currentProfile?.description}`">
                      {{ profileStore?.currentProfile?.name }}
                    </label>
                  </h3>
                  <button @click="handleAutoDetect" :disabled="isPending('auto-detect')" :class="isPending('auto-detect') ? 'rmm-action-disabled' : ''"
                    v-tooltip="isPending('auto-detect') ? '正在自动搜索路径' : '尝试通过注册表自动搜索路径'" class="inline-flex items-center gap-1 px-3 py-1 bg-accent-success/10 hover:bg-accent-success/20 border border-accent-success/30 rounded text-xs font-bold text-accent-success transition-all">
                    <LoaderCircle v-if="isPending('auto-detect')" class="size-3 animate-spin" />
                    {{ isPending('auto-detect') ? '搜索中' : '自动搜索路径' }}
                  </button>
                </div>
                <div class="grid gap-6">
                  <CommonPathInput label="游戏安装目录" v-model="formData.game_install_path" @browse="handleGameBrowse"
                    :check="formData.check_info?.game_install_path"
                    :description="'游戏安装目录即游戏主程序所在的目录，默认安装目录一般位于：\nC:/Program Files (x86)/Steam/steamapps/common/RimWorld'" 
                    @blur="checkPath('game_install_path', formData.game_install_path)"/>
                  <CommonPathInput label="用户数据目录" v-model="formData.user_data_path" @browse="handleBrowse('user_data_path')" 
                    :check="formData.check_info?.user_data_path"
                    :description="'用户数据目录即游戏数据及存档所在的目录，默认配置目录一般位于：\nC:/Users/{用户名}/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios'" 
                    @blur="checkPath('user_data_path', formData.user_data_path)"/>
                  <!-- <CommonPathInput label="游戏配置目录" v-model="formData.game_config_path" @browse="handleBrowse('game_config_path')" 
                    :check="formData.check_info?.game_config_path"
                    :description="'游戏配置目录即排序文件（ModsConfig.xml）所在的目录，默认配置目录一般位于：\nC:/Users/{用户名}/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Config'" 
                    @blur="checkPath('game_config_path', formData.game_config_path)"/> -->
                  <CommonPathInput label="创意工坊目录" v-model="formData.workshop_mods_path" @browse="handleBrowse('workshop_mods_path')" 
                    :check="formData.check_info?.workshop_mods_path"
                    :description="'创意工坊目录即创意工坊下载的模组所在的目录，该设置所有环境通用'" 
                    @blur="checkPath('workshop_mods_path', formData.workshop_mods_path)"/>
                  <CommonPathInput label="本地模组目录" v-model="formData.local_mods_path" readOnly @browse="handleBrowse('local_mods_path')" description="根据游戏安装目录自动生成" />
                  <CommonTagInput label="游戏启动参数" v-model="formData.run_commands" :allTags="RUN_COMMAND_TAGS" placeholder="请输入一个完整指令后回车确认……" description="注意不要使用 [[-savedatafolder]] 指令，多环境管理已经默认使用此指令，无需手动配置。" />
                  <div class="modal-section grid grid-cols-1 gap-2 p-3">
                    <CommonPathInput label="Steam程序路径" :check="formData.check_info?.steam_path"
                      :description="'Steam程序路径即Steam.exe所在的目录，默认路径一般位于：\nC:/Program Files (x86)/Steam'" 
                      v-model="formData.steam_path" @browse="handleBrowse('steam_path')" @blur="checkPath('steam_path', formData.steam_path)"
                    />
                    <div class="grid grid-cols-2 gap-2">
                      <CommonSwitch label="优先使用 Steam 启动" :disabled="steamLaunchDisabled"
                        :model-value="formData.prefer_steam_launch" description="适用于 Steam 版游戏。开启后，管理器会优先通过 Steam 启动当前环境，并直接使用 Steam 中的创意工坊内容。"
                        @update:modelValue="handlePreferSteamLaunchUpdate" />
                      <CommonSwitch label="使用创意工坊 Mod" :disabled="workshopModsDisabled" v-model="formData.use_workshop_mods" description="适用于非 Steam 版环境。开启后，管理器会把创意工坊模组接入当前环境的本地模组目录，这样直接启动游戏本体时也能使用这些模组。" />
                    </div>
                  </div>
                  <div class="modal-section grid grid-cols-2 gap-2 p-3">
                    <h3 class="col-span-2 text-sm font-bold ml-1 text-text-main">管理器模组</h3>
                    <CommonPathInput class=" col-span-2" label="管理器下载模组路径" :check="formData.check_info?.self_mods_path"
                      :description="'由管理器下载的模组所在的目录，可自定义位置，如果将其设为游戏本地模组路径，请关闭该使用开关。'" 
                      v-model="formData.self_mods_path" @browse="handleBrowse('self_mods_path')" @blur="checkPath('self_mods_path', formData.self_mods_path)"
                    />
                    <CommonSwitch label="使用管理器模组" v-model="formData.use_self_mods" description="开启后将通过链接方式自动为游戏加载管理器Mod。" />
                    <CommonSwitch label="改变路径时移动模组" v-model="formData.move_old_self_mods" description="开启后，修改路径时会将原有模组移动到新路径；不开启则保留原有的文件结构。" />
                    <CommonSwitch class="col-span-1" label="自动检查管理器模组更新" v-model="formData.enable_auto_steamcmd_mod_update_check" description="按设定间隔检查管理器模组目录中由 SteamCMD 下载的工坊模组和 Git 仓库订阅模组更新。" />
                    <div class="col-span-1 grid grid-cols-2 gap-3 items-end">
                      <CommonNumber class="col-span-1" label="检查间隔（天）" v-model="formData.steamcmd_mod_update_check_interval_days" :step="1" :min="1" :max="365" />
                      <button @click="handleCheckSteamcmdMods" :disabled="isPending('steamcmd-mods')" :class="isPending('steamcmd-mods') ? 'rmm-action-disabled' : ''"
                        class="inline-flex items-center justify-center gap-1 px-3 py-1.5 mx-2 my-1 h-8 bg-accent-warn/10 hover:bg-accent-warn/25 border border-accent-warn/20 rounded-lg text-xs font-bold transition-all">
                        <LoaderCircle v-if="isPending('steamcmd-mods')" class="size-3 animate-spin" />
                        {{ isPending('steamcmd-mods') ? '检查中' : '检查更新' }}
                      </button>
                    </div>
                  </div>
                  <div class="modal-section grid grid-cols-2 gap-2 p-3">
                    <h3 class="col-span-2 text-sm font-bold ml-1 text-text-main">排序导入/导出 起始选择窗口配置</h3>
                    <CommonSelect class="col-span-1" label="导入起始目录" v-model="formData.load_order_import_dir_mode"
                      :description="'控制“导入加载序列”文件选择器的选择窗口初始目录。默认模式始终使用当前环境用户数据目录下的 ModLists；记忆模式使用上次成功导入的目录；自定义模式使用下方固定目录。'"
                      :options="LOAD_ORDER_DIR_MODE_OPTIONS"
                    />
                    <CommonSelect class="col-span-1" label="导出起始目录" v-model="formData.load_order_export_dir_mode"
                      :description="'控制“导出加载序列”文件选择器的选择窗口初始目录。默认模式保持当前环境备份目录的 other 子目录；记忆模式使用上次成功导出的目录；自定义模式使用下方固定目录。'"
                      :options="LOAD_ORDER_DIR_MODE_OPTIONS"
                    />
                    <CommonPathInput v-if="formData.load_order_import_dir_mode === 'custom'" class="col-span-2" label="自定义导入起始目录" v-model="formData.load_order_import_custom_path"
                      :check="formData.check_info?.load_order_import_custom_path" :description="'仅在导入目录模式为“自定义”时生效；若路径无效，运行时会自动回退到默认目录。'"
                      @browse="handleBrowse('load_order_import_custom_path')" @blur="checkPath('load_order_import_custom_path', formData.load_order_import_custom_path)"
                    />
                    <CommonPathInput v-if="formData.load_order_export_dir_mode === 'custom'" class="col-span-2" label="自定义导出起始目录" v-model="formData.load_order_export_custom_path"
                      :check="formData.check_info?.load_order_export_custom_path" :description="'仅在导出目录模式为“自定义”时生效；若路径无效，运行时会自动回退到默认目录。'"
                      @browse="handleBrowse('load_order_export_custom_path')" @blur="checkPath('load_order_export_custom_path', formData.load_order_export_custom_path)"
                    />
                  </div>
                  <!-- <CommonPathInput label="主目录" v-model="formData.home_path" @browse="handleBrowse('home_path')" /> -->
                </div>
              </section>
</template>

<script setup>
import { ref } from 'vue'
import { LoaderCircle } from 'lucide-vue-next'
import CommonPathInput from '../../../shared/components/input/CommonPathInput.vue'
import CommonSwitch from '../../../shared/components/input/CommonSwitch.vue'
import CommonSelect from '../../../shared/components/input/CommonSelect.vue'
import CommonNumber from '../../../shared/components/input/CommonNumber.vue'
import CommonTagInput from '../../../shared/components/input/CommonTagInput.vue'
import { RUN_COMMAND_TAGS } from '../../../shared/lib/constants'
import { useAppStore } from '../../../app/stores/appStore'
import { useProfileStore } from '../../profiles/profileStore'

const props = defineProps({
  formData: { type: Object, required: true },
  steamLaunchDisabled: Boolean,
  workshopModsDisabled: Boolean,
  markSteamLaunchTouched: Function,
  autoDetect: { type: Function, required: true },
  handleBrowse: { type: Function, required: true },
  checkPath: { type: Function, required: true },
})

const appStore = useAppStore()
const profileStore = useProfileStore()
const pendingAction = ref('')

const LOAD_ORDER_DIR_MODE_OPTIONS = [
  { label: '默认', value: 'default' },
  { label: '记忆', value: 'remember' },
  { label: '自定义', value: 'custom' },
]

const handleGameBrowse = async () => {
  // 游戏目录会影响 Steam 版判定和本地模组路径，选择后立即刷新校验结果。
  const res = await appStore.getFolderPath(props.formData.game_install_path)
  if (!res) return
  props.formData.game_install_path = res
  await props.checkPath('game_install_path', props.formData.game_install_path)
}

const handlePreferSteamLaunchUpdate = (value) => {
  props.markSteamLaunchTouched?.()
  props.formData.prefer_steam_launch = !!value
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
const handleAutoDetect = async () => {
  await runPendingAction('auto-detect', () => props.autoDetect())
}

const handleCheckSteamcmdMods = async () => {
  await runPendingAction('steamcmd-mods', () => appStore.checkSteamcmdModUpdates({ manual: true, prompt: true }))
}
</script>
