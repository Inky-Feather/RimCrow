<template>
  <Teleport to="body">
    <Transition name="slide-left">
      <div v-if="appStore.uiState.showProfileDrawer" class="fixed inset-y-8 top-18 left-0 w-100 z-100 flex flex-col" >
        <!-- 1. 上方内凹边角 (对称自 ListDiffView) -->
        <div class="absolute -top-[1.1rem] left-0 w-5 h-5 z-10 ">
          <div class="w-full h-full bg-bg-elevated/90 backdrop-blur-xl mask-[radial-gradient(circle_at_100%_0,transparent_1.25rem,black_1rem)]"></div>
          <svg class="absolute inset-0 w-full h-full text-border-default fill-none pointer-events-none" viewBox="0 0 20 20">
            <path d="M0,0 A20,20 0 0,0 20,20" stroke="currentColor" stroke-width="2" />
          </svg>
        </div>

        <!-- 2. 主体容器 -->
        <div class="flex-1 flex flex-col bg-bg-muted/80 backdrop-blur-xl rounded-l-none rounded-r-2xl border-y border-r transition-all duration-300 border-border-base/10 shadow-3xl overflow-hidden relative"
          :class="{'blur-sm pointer-events-none': profileStore.isLoading}">

          <!-- 头部：标题与快速新建 -->
          <header class="p-3 bg-bg-elevated/90 border-b border-border-base/5">
            <div class="flex items-center justify-between">
              <div>
                <h2 class="text-xl font-black italic text-text-main flex items-center gap-2">
                  <Database class="size-5 text-accent-primary" />
                  环境<span class="text-accent-primary">管理</span>
                </h2>
              </div>
              <button @click="openCreate" v-tooltip="'创建新环境'" data-tour="profile-create"
                class="p-2 rounded-xl bg-accent-primary/10 text-accent-primary hover:bg-accent-primary hover:text-on-accent-primary transition-all">
                <Plus class="size-5" />
              </button>
            </div>
          </header>

          <!-- 列表区 -->
          <div class="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar" data-tour="profile-list">
            <!-- 当前激活标识 -->
            <div class="px-2 text-[0.65rem] font-bold text-text-dim uppercase tracking-tighter opacity-60">已记录环境</div>

            <div v-for="p in profileStore.profiles" :key="p.id"
              @click="p.check ? profileStore.switchProfile(p.id) : null"
              class="group relative p-2 rounded-xl border transition-all duration-300 overflow-hidden profile-item"
              :class="[p.check ? (p.id === profileStore.currentProfileId
                ? 'bg-accent-primary/15 border-accent-primary/40 shadow-[0_0_15px_rgba(var(--rgb-accent-primary),0.15)] cursor-pointer'
                : 'bg-bg-overlay/5 border-border-base/5 hover:border-border-base/18 hover:bg-bg-overlay/10 cursor-pointer')
                : 'bg-accent-danger/15 border-accent-danger/40 shadow-[0_0_15px_rgba(var(--rgb-accent-danger),0.15)] cursor-not-allowed' ]"
            >
              <div v-if="!p.check" class="absolute bottom-2 right-2 z-100 text-accent-warn scale-100 cursor-help hover:scale-110 transition-transform">
                <AlertTriangle class="size-8 " v-tooltip="`^^${p.msg}^^`"></AlertTriangle>
              </div>

              <!-- 激活时的动态流光 -->
              <div v-if="p.id === profileStore.currentProfileId" class="absolute inset-0 bg-linear-to-r from-accent-primary/10 to-transparent animate-pulse-slow"></div>

              <div class="relative flex justify-between items-start w-full">
                <div class="flex flex-col min-w-0 flex-1 gap-1 w-full">

                  <div class="flex items-center justify-between w-full gap-1">
                    <!-- 环境名称 -->
                    <div class="flex items-center gap-2 min-w-0">
                      <div class="size-2 rounded-full ml-1"
                        :class="p.check ? (p.id === profileStore.currentProfileId ? 'bg-accent-primary animate-pulse shadow-[0_0_8px_rgba(var(--rgb-accent-primary),0.75)]'
                          : 'bg-bg-overlay/10'):'bg-accent-danger animate-pulse shadow-[0_0_8px_rgba(var(--rgb-accent-danger),0.75)]'">
                      </div>
                      <h4 class="shrink font-bold text-sm truncate min-w-0" v-tooltip="`[[${p.name}]]\n__${p.description}__`" :class="p.id === profileStore.currentProfileId ? 'text-text-main' : 'text-text-main'">{{ p.name }}</h4>
                    </div>
                    <!-- 操作组 -->
                    <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button @click.stop="openExportDialog(p)" v-tooltip="'导出环境模组包'" class="p-1.5 rounded-lg text-text-dim transition-all hover:text-accent-special hover:bg-accent-special/15"
                        :class="p.check ? '' : 'cursor-not-allowed pointer-events-none opacity-40'"><Package class="size-3.5" /></button>
                      <button v-if="p.id !== 'default'" @click.stop="handleCreateShortcut(p)" v-tooltip="p.check ? '创建桌面快捷方式' : '环境无效，无法创建快捷方式'" class="p-1.5 rounded-lg text-text-dim transition-all hover:text-accent-primary hover:bg-accent-primary/15"
                        :class="p.check ? '' : 'cursor-not-allowed pointer-events-none opacity-40'" ><SquareArrowOutUpRight class="size-3.5" /></button>
                      <button v-if="p.id !== 'default'" @click.stop="handleDelete(p)" v-tooltip="'删除环境'" class="p-1.5 rounded-lg hover:bg-accent-danger/20 text-text-dim hover:text-accent-danger transition-all"><Trash2 class="size-3.5" /></button>
                      <button @click.stop="handleEdit(p)" v-tooltip="'编辑环境'" class="p-1.5 rounded-lg hover:bg-bg-overlay/10 text-text-dim hover:text-text-main transition-all"><Settings2 class="size-3.5" /></button>
                      <button @click.stop="handlePlay(p)" v-tooltip="'运行环境'" class="p-1.5 rounded-lg text-text-dim  transition-all hover:text-accent-success hover:bg-accent-success/20"
                        :class="p.check ? '' : 'cursor-not-allowed pointer-events-none opacity-40'"><Play class="size-3.5" />
                      </button>
                    </div>
                  </div>

                  <!-- 标识 -->
                  <div class="flex items-center gap-1 min-w-0">
                    <span v-tooltip="'游戏版本'" class="text-[0.6rem] px-1.5 py-0.5 rounded bg-accent-secondary/20 text-accent-secondary border border-border-base/10 ">{{ p.game_version || '版本未知' }}</span>
                    <span v-if="showSteamVersionBadge(p)" v-tooltip="p.is_steam_managed ? '游戏由 Steam 管理。' : '这是一个 Steam 版环境。'" class="text-[0.6rem] px-1.5 py-0.5 rounded bg-accent-primary/10 text-accent-primary border border-border-base/10 ">Steam 版</span>
                    <span v-if="showWorkshopRuntimeBadge(p)" v-tooltip="'当前环境会使用创意工坊模组'" class="text-[0.6rem] px-1.5 py-0.5 rounded bg-accent-success/10 text-accent-success border border-border-base/10 ">工坊模组</span>
                    <span v-if="p.use_self_mods" v-tooltip="'当前环境会使用管理器模组'" class="text-[0.6rem] px-1.5 py-0.5 rounded bg-accent-success/10 text-accent-success border border-border-base/10 ">管理器模组</span>
                    <span v-if="p.id === 'default'" v-tooltip="'默认环境'" class="text-[0.6rem] px-1.5 py-0.5 rounded bg-accent-highlight/20 text-accent-highlight border border-border-base/10 ">默认</span>
                    <span v-if="p.id === runtimeProfileId && appStore.runtimeSession?.state === 'running'" v-tooltip="runtimeProfileLabel" class="text-[0.6rem] px-1.5 py-0.5 rounded bg-accent-primary/15 text-accent-primary border border-border-base/10 ">运行中</span>
                  </div>

                  <!-- 路径 -->
                  <span class="flex items-center" v-tooltip="'游戏安装路径:\n' + p.game_install_path">
                    <span class="text-[0.7rem] py-0.5 px-1 w-10 shrink-0 text-center bg-accent-cool/70 rounded-2xl">Game</span>
                    <span class="text-[0.7rem] px-1 text-text-dim font-mono opacity-50 truncate">{{ p.game_install_path }}</span>
                  </span>

                  <span class="flex items-center" v-tooltip="'用户数据路径:\n' + p.user_data_path">
                    <span class="text-[0.7rem] py-0.5 px-1 w-10 shrink-0 text-center bg-accent-tip/70 rounded-2xl">Data</span>
                    <span class="text-[0.7rem] px-1 text-text-dim font-mono opacity-50 truncate">{{ p.user_data_path }}</span>
                  </span>

                  <div class=" w-fit bg-accent-special/70 backdrop-blur-xl px-1 py-0.5 rounded-sm text-[0.65rem] text-text-main">
                    上次运行：{{ p.last_played_time ? formatDate(p.last_played_time) : '未运行' }}
                  </div>

                </div>

              </div>
            </div>

            <!-- 待恢复/孤立环境 -->
            <div v-if="profileStore.orphanedProfiles.length > 0" class="mt-8 space-y-3">
              <div class="px-2 text-[0.65rem] font-bold text-accent-warn uppercase tracking-tighter">待恢复环境</div>
              <div v-for="orphan in profileStore.orphanedProfiles" :key="orphan.id"
                class="p-4 rounded-xl border border-dashed border-accent-warn/30 bg-accent-warn/5 flex items-center justify-between group">
                <div class="min-w-0">
                  <div class="text-sm font-bold text-accent-warn/80">{{ orphan.name }}</div>
                  <div class="text-[0.7rem] text-text-dim truncate w-48 mt-1">{{ orphan._folder_path }}</div>
                </div>
                <button @click="profileStore.importOrphan(orphan)" class="px-3 py-1.5 rounded-lg bg-accent-warn/20 hover:bg-accent-warn text-accent-warn hover:text-on-accent-warn text-[0.7rem] font-black transition-all">
                  接入
                </button>
              </div>
            </div>
          </div>

          <!-- 底部工具栏 -->
          <footer class="bg-bg-elevated/90 flex items-center justify-between p-4">
            <div></div>
            <button @click="appStore.uiState.showProfileDrawer = false" class="px-4 py-1.5 rounded-lg bg-bg-overlay/5 hover:bg-bg-overlay/10 text-text-main text-xs font-bold transition-all">
              收起
            </button>
          </footer>

        </div>

        <!-- 3. 下方内凹边角 -->
        <div class="absolute -bottom-[1.2rem] left-0 w-5 h-5 z-10 rotate-90">
          <div class="w-full h-full bg-bg-elevated/90 mask-[radial-gradient(circle_at_100%_0,transparent_1.25rem,black_1rem)]"></div>
          <svg class="absolute inset-0 w-full h-full text-border-default fill-none pointer-events-none" viewBox="0 0 20 20">
            <path d="M0,0 A20,20 0 0,0 20,20" stroke="currentColor" stroke-width="2" />
          </svg>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- 4. 编辑/创建 模态框 (标准 RulePanel 风格) -->
  <Transition name="fade">
    <div v-if="showModal" class="fixed inset-0 z-150 flex items-center justify-center bg-bg-deep/40 backdrop-blur-md">
      <div class="modal-surface w-full max-w-[70%] overflow-hidden rounded-2xl bg-bg-highlight/90 animate-scale-in">
        <header class="modal-header flex items-center justify-between px-6 py-4">
          <h3 class="text-lg font-bold text-text-main">{{ isEditing ? '编辑环境属性' : '创建新环境快照' }}</h3>
          <button @click="showModal = false" class="text-text-dim hover:text-text-main"><X class="size-5" /></button>
        </header>

        <div class="p-6 space-y-3">
          <CommonInput label="显示名称" v-model="form.name" placeholder="例如: 1.5 中世纪" />
          <CommonInput label="环境描述" v-model="form.description" placeholder="这里可以写一些关于这个环境的说明..." />
          <CommonPathInput label="游戏执行目录" v-model="form.game_install_path" @browse="browsePath('game_install_path')"
            :check="form.check_info?.game_install_path" @blur="checkPath('game_install_path', form.game_install_path)"
            description="游戏安装目录，即游戏主程序所在的目录" />
          <CommonPathInput label="用户数据目录" v-model="form.user_data_path" @browse="browsePath('user_data_path')"
            :check="form.check_info?.user_data_path" @blur="checkPath('user_data_path', form.user_data_path)"
            description="游戏数据目录，可随意指定位置，或者留空自动生成，包含游戏配置及排序存档等用户信息。"
            :placeholder= '(!isEditing?"可空，默认在软件 data/profiles 目录下自动生成":"编辑模式下不可留空！")' />
          <CommonSwitch v-if="showWorkshopSwitch" :disabled="!canUseSteamLaunch" label="优先使用 Steam 启动" v-model="form.prefer_steam_launch" description="适用于 Steam 版游戏。开启后，管理器会优先通过 Steam 启动游戏，进而挂载创意工坊内容。（前提是账号正常使用该游戏和相关关创意工坊内容。）" />
          <CommonSwitch v-if="showWorkshopSwitch" :disabled="form.prefer_steam_launch" label="使用创意工坊 Mod" v-model="form.use_workshop_mods" description="适用于非 Steam 版环境。为当前环境使用创意工坊模组，启用后将通过链接方式自动为游戏添加创意工坊模组。（前提是账号正常使用该游戏和相关关创意工坊内容。）" />
          <CommonSwitch v-if="appStore.settings.self_mods_path" label="使用管理器 Mod" v-model="form.use_self_mods" description="启用后将通过链接方式自动为游戏添加管理器模组。" />
          <CommonSwitch v-if="!isEditing" label="继承当前配置" v-model="form.copy_current_data" description="自动复制当前的游戏配置到新环境" />
          <CommonTagInput label="游戏启动参数" v-model="form.run_commands" :allTags="RUN_COMMAND_TAGS" placeholder="请输入一个完整指令后回车确认……" description="注意不要使用 [[-savedatafolder]] 指令，多环境管理已经默认使用此指令，无需手动配置。" />

          <div class="text-[0.7rem] text-text-disabled leading-relaxed">
            * 每一个环境都拥有完全独立的存档、设置和 Mod 排序文件。系统将通过启动参数自动执行数据隔离。Mod 文件则会共用游戏本体所在的 Mods 目录。
            <p class="ml-2">游戏本体与环境无直接关联，同一个游戏本体可以与多个环境同时建立联系。</p>
            <p class="ml-2 text-accent-warning">注意：如果游戏执行目录不存在或游戏文件损坏，环境将无法正常启动。</p>
          </div>
        </div>

        <footer class="modal-footer flex justify-end gap-3 px-6 py-4">
          <button @click="showModal = false" class="px-4 py-2 text-sm text-text-dim hover:text-text-main">取消</button>
          <button @click="submitForm" class="px-6 py-2 rounded-xl bg-accent-primary text-on-accent-primary font-black text-sm shadow-lg shadow-accent-primary/20 transition-all hover:scale-105 active:scale-95">
            {{ isEditing ? '保存变更' : '确认创建' }}
          </button>
        </footer>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { Database, Plus, Trash2, Settings2, X, Play, AlertTriangle, SquareArrowOutUpRight, Package } from 'lucide-vue-next'
import { toast } from '../../shared/lib/common'
import { useProfileStore } from './profileStore'
import { useModStore } from '../mod/stores/modStore'
import { useAppStore } from '../../app/stores/appStore'
import { useConfirmStore } from '../../shared/components/modal/confirmStore'
import CommonInput from '../../shared/components/input/CommonInput.vue'
import CommonPathInput from '../../shared/components/input/CommonPathInput.vue'
import CommonSwitch from '../../shared/components/input/CommonSwitch.vue'
import CommonTagInput from '../../shared/components/input/CommonTagInput.vue'
import { RUN_COMMAND_TAGS } from '../../shared/lib/constants'
import { formatDate } from '../../shared/lib/format'

const profileStore = useProfileStore()
const modStore = useModStore()
const appStore = useAppStore()
const confirmStore = useConfirmStore()

// --- 状态 ---
const showModal = ref(false)
const isEditing = ref(false)
const gameInfo = ref('')
const form = reactive({
  id: '',
  name: '',
  description: '',
  game_install_path: '',
  user_data_path: '',
  prefer_steam_launch: false,
  use_workshop_mods: false,
  use_self_mods: false,
  copy_current_data: false,
  run_commands: [],
  check_info: {}
})
const detectedIsSteam = computed(() => {
  const checkedInstall = form.check_info?.game_install_path
  if (checkedInstall && Object.prototype.hasOwnProperty.call(checkedInstall, 'pass')) {
    if (checkedInstall.data && Object.prototype.hasOwnProperty.call(checkedInstall.data, 'is_steam')) {
      return !!checkedInstall.data.is_steam
    }
    return false
  }
  if (isEditing.value) {
    const editingProfile = profileStore.profiles.find(item => item.id === form.id)
    return !!editingProfile?.is_steam
  }
  return !!profileStore.activeContext?.is_steam
})
const canUseSteamLaunch = computed(() => detectedIsSteam.value)
const showWorkshopSwitch = computed(() => !!appStore.settings.workshop_mods_path)

const showSteamVersionBadge = (profile) => !!profile?.is_steam
const runtimeProfileId = computed(() => String(appStore.runtimeSession?.profile_id || '').trim())
const runtimeProfileLabel = computed(() => {
  if (appStore.runtimeSession?.source === 'external') {
    return '当前游戏由外部启动，后端已按 default 环境接管。'
  }
  return '当前游戏正在按这个环境运行。'
})
const showWorkshopRuntimeBadge = (profile) => {
  const caps = profile?.runtime_capabilities || {}
  // 这里的徽标语义不是“字段是否勾选”，而是“当前运行时 Workshop 会不会真正参与”：
  // - Steam 启动时，Workshop 由 Steam 自动挂载；
  // - 非 Steam 启动时，Workshop 只在链接部署生效时参与。
  return !!(caps.steam_launch_enabled || caps.workshop_deploy_enabled)
}

// --- 逻辑 ---
watch(() => appStore.uiState.showProfileDrawer, (val) => {
  if (val) profileStore.scanOrphans()
})
watch(() => form.prefer_steam_launch, (enabled) => {
  if (enabled) {
    form.use_workshop_mods = false
  }
})
watch(detectedIsSteam, (isSteam) => {
  if (!isSteam && form.prefer_steam_launch) {
    form.prefer_steam_launch = false
  }
})

const openCreate = () => {
  form.id = ''
  form.name = ''
  form.description = ''
  form.game_install_path = profileStore.activeContext.game_install_path
  form.user_data_path = ''
  form.prefer_steam_launch = !!profileStore.activeContext?.is_steam
  form.use_workshop_mods = false
  form.use_self_mods = false
  form.copy_current_data = false
  form.run_commands = []
  form.check_info = {}
  isEditing.value = false
  showModal.value = true
}

const handleEdit = async (p) => {
  form.id = p.id
  form.name = p.name
  form.description = p.description
  form.game_install_path = p.game_install_path
  form.user_data_path = p.user_data_path
  form.prefer_steam_launch = !!p.prefer_steam_launch
  form.use_workshop_mods = p.use_workshop_mods
  form.use_self_mods = p.use_self_mods
  form.run_commands = p.run_commands
  isEditing.value = true
  showModal.value = true

  await checkPath('user_data_path', form.user_data_path)
  await checkPath('game_install_path', form.game_install_path)
}

const browsePath = async (type) => {
  const path = await appStore.getFolderPath(form[type])
  if (path) form[type] = path
  if (type === 'game_install_path') {
    await checkPath('game_install_path', form.game_install_path)
  }
}

const submitForm = async () => {
  if (!form.name) {
    toast.warning('请输入显示名称')
    return
  }
  if (!form.game_install_path) {
    toast.warning('请选择游戏执行目录')
    return
  }
  if (!form.user_data_path && isEditing.value) {
    toast.warning('请输入用户数据目录')
    return
  }
  await checkPath('user_data_path', form.user_data_path)
  await checkPath('game_install_path', form.game_install_path)
  if (form['check_info']['game_install_path'] && !form['check_info']['game_install_path']['pass']) {
    toast.warning('请选择一个有效的游戏执行目录')
    return
  }
  if (form['check_info']['user_data_path'] && !form['check_info']['user_data_path']['pass'] && isEditing.value) {
    toast.warning('请输入一个有效的用户数据目录')
    return
  }
  if (isEditing.value) {
    const cleanForm = { ...form }
    delete cleanForm.copy_current_data
    await profileStore.updateProfile(form.id, cleanForm)
  } else {
    const cleanForm = { ...form }
    delete cleanForm.copy_current_data
    await profileStore.createProfile(cleanForm, form.copy_current_data)
  }
  showModal.value = false
}

// 检查游戏路径是否有效
const checkPath = async (type, path) => {
  const res = await appStore.checkPath(type, path)
  if (!form['check_info']) {
    form['check_info'] = {};
  }
  form['check_info'][type] = res
}

const handleDelete = async (p) => {
  const decision = await confirmStore.confirmDeleteAction(
    '危险操作',
    `确定要删除环境 "${p.name}" 吗？\n环境记录会被移除；其隔离区数据默认移入回收站，也可选择强制彻底删除。`,
    {
      trashOptionText: '移入回收站',
      forceOptionText: '强制删除隔离区数据',
    }
  )
  if (decision?.confirmed) {
    if (p.id === appStore.settings.current_profile_id) {
      profileStore.switchProfile('default')
    }
    await profileStore.deleteProfile(p.id, !!decision.force)
  }
}

const handlePlay = (p) => {
  appStore.launchGame(p.id)
}

const handleCreateShortcut = async (p) => {
  const ok = await confirmStore.confirmAction(
    '创建桌面快捷方式',
    `确定要为环境 "${p.name}" 创建桌面快捷方式吗？\n快捷方式会按当前环境的启动方式生成，并放到桌面。\n若当前环境优先使用 Steam 启动，且游戏本体路径不同于默认环境，管理器会改写 Steam 的非 Steam 游戏快捷方式配置并在桌面生成 Steam 协议入口；该流程需要 Steam 完全退出，并在写入后重启 Steam 才会生效。\n若多个环境共用同一个游戏目录，快捷方式只能保证启动目标和参数准确，不能保证目录中的链接状态始终与该环境完全一致。`,
    {
      confirmText: '创建',
      cancelText: '取消',
    }
  )
  if (!ok) return
  await profileStore.createDesktopShortcut(p.id)
}

const buildProfileExportScopeOptions = ({
  effectiveCount = null,
  activeCount = null,
  loading = false,
} = {}) => {
  const formatLabel = (title, count) => {
    if (loading) return `${title}（读取中）`
    return Number.isFinite(count) ? `${title}（${count}）` : title
  }
  return [
    { value: 'profile-effective', label: formatLabel('当前环境有效模组', effectiveCount), description: loading ? '正在读取这个环境里可导出的模组数量。' : '导出当前环境里能正常使用的模组。' },
    { value: 'profile-active', label: formatLabel('当前环境启用模组', activeCount), description: loading ? '正在读取这个环境里已启用的模组数量。' : '导出当前环境里已经启用的模组。' },
  ]
}

const openExportDialog = async (profile) => {
  const profileId = profile?.id || appStore.settings.current_profile_id || 'default'
  const isCurrentProfile = profileId === (appStore.settings.current_profile_id || 'default')
  const scopeOptions = isCurrentProfile
    ? buildProfileExportScopeOptions({
      effectiveCount: modStore.exportableVisibleCount,
      activeCount: modStore.exportableActiveCount,
    })
    : buildProfileExportScopeOptions({ loading: true })
  appStore.openPackageTransferDialog('mod-export', {
    title: `导出环境模组: ${profile?.name || '未命名环境'}`,
    description: '可选择导出当前环境有效模组或当前启用模组，并按需附带环境数据。',
    sourceProfile: true,
    profileId,
    profileName: profile?.name || '当前环境',
    scopeOptions,
    scopeOptionsLoading: !isCurrentProfile,
    export_scope: 'profile-effective',
  })
  if (isCurrentProfile) return

  const summary = await appStore.getModPackageProfileSummary(profileId)
  if (!appStore.uiState.showPackageTransferDialog) return
  if (appStore.packageTransferDialog.mode !== 'mod-export') return
  if (appStore.packageTransferDialog.preset.profileId !== profileId) return
  appStore.updatePackageTransferDialogPreset({
    scopeOptions: buildProfileExportScopeOptions({
      effectiveCount: summary?.effective_count ?? null,
      activeCount: summary?.active_count ?? null,
    }),
    scopeOptionsLoading: false,
  })
}



</script>

<style scoped>
.slide-left-enter-active, .slide-left-leave-active { transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1); }
.slide-left-enter-from, .slide-left-leave-to { transform: translateX(-100%); opacity: 0; }

.animate-scale-in { animation: scaleIn 0.2s ease-out; }
@keyframes scaleIn {
  from { opacity: 0; transform: scale(0.9); }
  to { opacity: 1; transform: scale(1); }
}

.custom-scrollbar::-webkit-scrollbar { width: 3px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: var(--color-border-subtle); border-radius: 10px; }
</style>
