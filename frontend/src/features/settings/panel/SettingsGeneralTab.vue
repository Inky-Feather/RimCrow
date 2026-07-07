<template>
              <section class="animate-in fade-in slide-in-from-right-4">
                <h3 class="text-lg font-bold text-text-main mb-6 flex items-center justify-between">{{ t('ui.settings.general.title', '界面与布局') }}
                  <button @click="guideStore.resetAllGuides()" v-tooltip="t('tooltip.settings.general.reset_guides', '重置界面引导，将界面引导重置为默认值')" class="px-3 py-1 bg-accent-warn/10 hover:bg-accent-warn/20 border border-accent-warn/30 rounded text-xs font-bold text-accent-warn transition-all">
                    {{ t('ui.settings.general.reset_guides', '重置界面引导') }}
                  </button>
                </h3>
                <div class="space-y-6">
                  <div class="grid grid-cols-2 gap-4">
                    <CommonSelect :label="t('ui.settings.general.interface_language', '界面语言')" v-model="formData.language" :options="languageOptions" />
                    <ThemeSelect v-if="formData.ui" v-model="currentThemeId" :themes="appStore.themes"
                      @create="openThemeCreate" @edit="openThemeEdit" @delete="handleThemeDelete"
                    />
                    <CommonSwitch :label="t('ui.settings.general.translation_mode', '翻译模式')" v-model="translationMode" :description="t('ui.settings.general.translation_mode_desc', '开启后显示翻译辅助浮窗，也可按 Ctrl + Shift + L 快速开关。')" />
                  </div>
                  <CommonSwitch :label="t('ui.settings.general.open_url_in_system_browser', '在系统浏览器中打开 URL')" v-model="formData.open_url_on_system" :description="t('ui.settings.general.open_url_in_system_browser_desc', '关闭则使用内置浏览器')" />
                  <div class="grid grid-cols-2 gap-4">
                    <CommonNumber :label="t('ui.settings.general.font_size', '字体大小')" :description="t('ui.settings.general.font_size_desc', '控制界面字体大小，影响所有控件的内容显示')" v-model="formData.ui.font_size" :step="1" :min="8" :max="40" />
                    <CommonNumber :label="t('ui.settings.general.tooltip_hover_time', '提示悬停时间')" :description="t('ui.settings.general.tooltip_hover_time_desc', '控制悬浮提示信息的等待时间，单位是毫秒')" v-model="formData.ui.tooltip_hover_time" :step="100" :min="100" :max="5000" />
                    <CommonNumber :label="t('ui.settings.general.drag_delay', '拖动判定延迟')" :description="t('ui.settings.general.drag_delay_desc', '控制列表项拖动操作的判定延迟，单位是毫秒，默认值为 30 毫秒，为 0 时可能使点击操作出现抖动。')" v-model="formData.ui.drag_delay" :step="10" :min="0" :max="500" />
                    <div></div>
                    
                    <div class="modal-section col-span-2 grid grid-cols-2 gap-2 p-2">
                      <span class="col-span-2 ml-2 mt-2 text-sm font-bold tracking-wide">{{ t('ui.settings.general.list_settings', '列表设定') }}
                        <label v-tooltip="t('tooltip.settings.general.list_settings', '可调整列表的显示方式与辅助功能')" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
                      </span>
                      <CommonSwitch :label="t('ui.settings.general.mod_hover_panel', 'Mod 悬停面板')" v-model="formData.ui.show_mod_hover_panel" :description="t('ui.settings.general.mod_hover_panel_desc', '控制 Mod 列表中悬停时的面板显示。')" />
                      <CommonSwitch :label="t('ui.settings.general.double_click_toggle_mod', '双击启用/停用 Mod')" v-model="formData.ui.double_click_active_mod" :description="t('ui.settings.general.double_click_toggle_mod_desc', '控制 Mod 列表中双击启用/停用 Mod 动作。')" />
                      <CommonSwitch :label="t('ui.settings.general.dependency_graph', '依赖关系图')" v-model="formData.ui.show_dependency_graph" :description="t('ui.settings.general.dependency_graph_desc', '控制启用列表中依赖关系图的显示。')" />
                      <CommonSwitch :label="t('ui.settings.general.smooth_target_scroll', '平滑定位滚动')" v-model="formData.ui.smooth_list_target_scroll" :description="t('ui.settings.general.smooth_target_scroll_desc', '开启后，搜索定位或移动后定位会平滑滚动到目标项；关闭后直接跳到目标位置。')" />
                      <CommonSwitch :label="t('ui.settings.general.list_index', '列表索引')" v-model="formData.ui.show_list_index" :description="t('ui.settings.general.list_index_desc', '控制列表中索引列的显示。')" />
                    </div>

                    <div class="modal-section col-span-2 grid grid-cols-2 gap-2 p-2">
                      <CommonSwitch class="col-span-2 px-2 pt-2" :label="t('ui.settings.general.list_icons', '列表图标')" v-model="formData.ui.show_list_icon" :description="t('ui.settings.general.list_icons_desc', '控制列表中的所有图标显示，包括简单视图和详细视图。')" mini />
                      <CommonSwitch :disabled="!formData.ui.show_list_icon" :label="t('ui.settings.general.list_mod_icon', '列表 Mod 图标')" v-model="formData.ui.show_list_mod_icon" :description="t('ui.settings.general.list_mod_icon_desc', '控制列表中 Mod 图标显示，不影响详细视图。')" />
                      <CommonSwitch :disabled="!formData.ui.show_list_icon" :label="t('ui.settings.general.list_mod_type_icon', '列表 Mod 类型图标')" v-model="formData.ui.show_list_modtype_icon" :description="t('ui.settings.general.list_mod_type_icon_desc', '控制列表中 Mod 类型图标显示，不影响详细视图。')" />
                    </div>
                    <div class="modal-section col-span-2 grid grid-cols-2 gap-2 p-2">
                      <span class="col-span-2 ml-2 mt-2 text-sm font-bold tracking-wide">{{ t('ui.settings.general.section_collapse', '列表分割组功能') }}
                        <label v-tooltip="t('tooltip.settings.general.section_collapse', '为列表支持分割线折叠分组的功能，需要安装了分割线模组才能启用。开启后，列表会识别名称或别名满足 `=标题=`、`/*标题*/` 的纯分割线模组，并支持折叠、整组拖动和右键分割组移动。')" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
                      </span>
                      <CommonSwitch :label="t('ui.settings.general.active_section_support', '“启用列表”分割组支持')" v-model="formData.ui.enable_active_section_collapse" :description="t('ui.settings.general.active_section_support_desc', '开启后，启用列表会支持分割组折叠、整组拖动和右键分割组移动。')" />
                      <CommonSwitch :label="t('ui.settings.general.inactive_section_support', '“停用列表”分割组支持')" v-model="formData.ui.enable_inactive_section_collapse" :description="t('ui.settings.general.inactive_section_support_desc', '开启后，停用列表会支持分割组折叠、整组拖动和右键分割组移动。')" />
                      <CommonSwitch :disabled="!formData.ui.enable_active_section_collapse" :label="t('ui.settings.general.default_collapse_active_sections', '启用列表默认折叠分割组')" v-model="formData.ui.default_collapse_active_sections" :description="t('ui.settings.general.default_collapse_active_sections_desc', '开启后，启用列表中的分割组会在初始显示时默认折叠。')" />
                      <CommonSwitch :disabled="!formData.ui.enable_inactive_section_collapse" :label="t('ui.settings.general.default_collapse_inactive_sections', '停用列表默认折叠分割组')" v-model="formData.ui.default_collapse_inactive_sections" :description="t('ui.settings.general.default_collapse_inactive_sections_desc', '开启后，停用列表中的分割组会在初始显示时默认折叠。')" />
                      <div class="flex items-center gap-1">
                        <button @click="appStore.openSteamWorkshopById('2138932352', false)"
                          class="px-2 py-1.5 bg-bg-overlay/5 hover:bg-bg-overlay/10 border border-border-base/10 rounded-lg text-xs font-bold cursor-pointer transition-all">
                          <span class="flex items-center gap-2">
                            {{ t('ui.settings.general.visit', '访问') }}<p class="text-accent-cool">{{ t('ui.settings.general.section_label_collection', '分类排列标签合集') }}</p>{{ t('ui.settings.general.workshop_page', '工坊页面') }}
                          </span>
                        </button>
                        <button @click="appStore.openSteamWorkshopById('3542535605', false)"
                          class="px-2 py-1.5 bg-bg-overlay/5 hover:bg-bg-overlay/10 border border-border-base/10 rounded-lg text-xs font-bold cursor-pointer transition-all">
                          <span class="flex items-center gap-2">
                            {{ t('ui.settings.general.visit', '访问') }}<p class="text-accent-cool">{{ t('ui.settings.general.section_sort_collection', '分类排序合集') }}</p>{{ t('ui.settings.general.workshop_page', '工坊页面') }}
                          </span>
                        </button>
                      </div>
                    </div>
                    
                    <div class="modal-section col-span-2 grid grid-cols-2 gap-2 p-2">
                      <span class="col-span-2 ml-2 mt-2 text-sm font-bold tracking-wide">{{ t('ui.settings.general.group_settings', '分组设定') }}
                        <label v-tooltip="t('tooltip.settings.general.group_settings', '可调整分组列表的显示方式')" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
                      </span>
                      <CommonSwitch :label="t('ui.settings.general.group_index', '分组索引')" v-model="formData.ui.show_group_index" :description="t('ui.settings.general.group_index_desc', '控制分组列表中 Mod 索引的显示。')" />
                      <CommonSwitch :label="t('ui.settings.general.group_icon', '分组图标')" v-model="formData.ui.show_group_icon" :description="t('ui.settings.general.group_icon_desc', '控制分组列表中 Mod 图标的显示。')" />
                    </div>
                    <div class="modal-section col-span-2 grid grid-cols-2 gap-2 p-2">
                      <span class="col-span-2 ml-2 mt-2 text-sm font-bold tracking-wide">{{ t('ui.settings.general.home_layout', '主页布局') }}
                        <label v-tooltip="t('tooltip.settings.general.drag_layout_order', '可拖动切换布局顺序')" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
                      </span>
                      <div class="col-span-2 flex gap-1">
                        <div v-for="item, index in formData.ui.main_layout" :key="item.id"
                          class="flex items-center transition-transform duration-150"
                          :class="getLayoutDragClass('main_layout', index)"
                          draggable="true"
                          @dragstart="handleLayoutDragStart('main_layout', index, $event)"
                          @dragover.prevent="handleLayoutDragOver('main_layout', index)"
                          @drop.prevent="handleLayoutDrop('main_layout', index)"
                          @dragend="handleLayoutDragEnd">
                          <CommonSwitch class="flex-1 cursor-move" :key="item.id" :label="appStore.MAIN_LAYOUT_MAPS[item.id].label" v-model="item.visible" :description="appStore.MAIN_LAYOUT_MAPS[item.id].desc" />
                        </div>
                      </div>
                      
                    </div>

                    <div class="modal-section col-span-2 grid grid-cols-2 gap-2 p-2">
                      <CommonSwitch class="col-span-2 px-2 pt-2" mini :label="t('ui.settings.general.mod_details_panel', 'Mod 详情面板')" v-model="detailsPanelVisible" :description="t('ui.settings.general.mod_details_panel_desc', '可关闭 Mod 详情栏。')" />
                      <CommonSwitch :disabled="!detailsPanelVisible" :label="t('ui.settings.general.icons_cloud', '动态图标云')" v-model="formData.ui.show_icons_cloud" :description="t('ui.settings.general.icons_cloud_desc', '控制详情页闲置时的动态图标云显示。')" />
                      <CommonNumber :label="t('ui.settings.general.detail_delay', '详情页加载延迟')" :description="t('ui.settings.general.detail_delay_desc', '控制 Mod 详情页加载的延迟时间，单位是毫秒，默认值为 200 毫秒。')" v-model="formData.ui.detail_delay" :step="10" :min="0" :max="5000" />
                      <span class="col-span-2 text-xs ml-2 mt-2">{{ t('ui.settings.general.mod_details_layout', 'Mod 详情布局') }}
                        <label v-tooltip="t('tooltip.settings.general.drag_layout_order', '可拖动切换布局顺序')" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
                      </span>
                      <div class="col-span-2 flex flex-col gap-1 p-2 rounded-xl bg-bg-deep/10 border border-border-base/10"
                        :class="{ 'pointer-events-none opacity-50': !detailsPanelVisible }">
                        <div v-for="item, index in formData.ui.mod_details_layout" :key="item.id"
                          class="flex items-center transition-transform duration-150"
                          :class="getLayoutDragClass('mod_details_layout', index)"
                          :draggable="detailsPanelVisible"
                          @dragstart="handleLayoutDragStart('mod_details_layout', index, $event)"
                          @dragover.prevent="handleLayoutDragOver('mod_details_layout', index)"
                          @drop.prevent="handleLayoutDrop('mod_details_layout', index)"
                          @dragend="handleLayoutDragEnd">
                          <span class="p-1 mr-1 rounded-md bg-accent-primary/30">{{ index }}</span>
                          <CommonSwitch class="flex-1 cursor-move" :disabled="!detailsPanelVisible" :key="item.id" :label="appStore.DETAILS_LAYOUT_MAPS[item.id].label" v-model="item.visible" :description="appStore.DETAILS_LAYOUT_MAPS[item.id].desc" />
                        </div>
                      </div>
                      
                    </div>
                    
                  </div>
                </div>
              </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import CommonSwitch from '../../../shared/components/input/CommonSwitch.vue'
import CommonNumber from '../../../shared/components/input/CommonNumber.vue'
import CommonSelect from '../../../shared/components/input/CommonSelect.vue'
import ThemeSelect from '../theme/ThemeSelect.vue'
import { DEFAULT_THEME_ID, applyTheme, createEditableThemeFrom, findThemeById, normalizeTheme } from '../theme/themeManager'
import { useAppStore } from '../../../app/stores/appStore'
import { useConfirmStore } from '../../../shared/components/modal/confirmStore'
import { useGuideStore } from '../../guide/guideStore'
import { t } from '../../../shared/i18n'

const props = defineProps({
  formData: { type: Object, required: true },
})

const appStore = useAppStore()
const guideStore = useGuideStore()
const confirmStore = useConfirmStore()

const layoutDragState = ref({ key: '', fromIndex: -1, overIndex: -1 })

const languageOptions = computed(() => [
  { label: t('ui.settings.general.language.zh_cn', '简体中文'), value: 'zh-CN' },
  { label: t('ui.settings.general.language.en', 'English'), value: 'en' },
])

const translationMode = computed({
  get: () => !!appStore.translationModeEnabled,
  set: (enabled) => { appStore.translationModeEnabled = !!enabled },
})

const selectedFormTheme = computed(() => {
  return findThemeById(appStore.themes, currentThemeId.value)
})

// 主题选择需要立即生效，保存按钮只负责提交设置表单里的其它改动。
const currentThemeId = computed({
  get: () => appStore.settings.ui?.theme_id || DEFAULT_THEME_ID,
  set: async (themeId) => {
    if (!appStore.settings.ui) appStore.settings.ui = {}
    appStore.settings.ui.theme_id = themeId || DEFAULT_THEME_ID
    applyTheme(findThemeById(appStore.themes, appStore.settings.ui.theme_id))
    await appStore.saveSetting('ui', appStore.settings.ui)
  },
})

const openThemeCreate = () => {
  appStore.themeEditor.theme = createEditableThemeFrom(selectedFormTheme.value)
  appStore.themeEditor.isOpen = true
}

const openThemeEdit = (theme) => {
  if (!theme || theme.builtin) return
  appStore.themeEditor.theme = normalizeTheme(theme)
  appStore.themeEditor.isOpen = true
}

const handleThemeDelete = async (theme) => {
  if (!theme || theme.builtin) return
  const ok = await confirmStore.confirmAction(
    t('confirm.settings.general.delete_theme.title', '删除主题'),
    t('confirm.settings.general.delete_theme.message', '确定要删除自定义主题「{name}」吗？此操作不可撤销。', { name: theme.name }),
    { type: 'error' }
  )
  if (!ok) return
  const deleted = await appStore.deleteUserTheme(theme.id)
  if (deleted && currentThemeId.value === theme.id) {
    currentThemeId.value = DEFAULT_THEME_ID
  }
}

const findLayoutItem = (id, datas) => Array.isArray(datas) ? datas.find(item => item?.id === id) : null
const detailsPanelVisible = computed({
  get: () => findLayoutItem('details', props.formData?.ui?.main_layout)?.visible !== false,
  set: (visible) => {
    if (!props.formData.ui || typeof props.formData.ui !== 'object') props.formData.ui = {}
    if (!Array.isArray(props.formData.ui.main_layout)) props.formData.ui.main_layout = []
    let item = findLayoutItem('details', props.formData.ui.main_layout)
    if (!item) {
      item = { id: 'details', visible: true }
      props.formData.ui.main_layout.unshift(item)
    }
    item.visible = !!visible
  },
})

// 布局排序只修改当前设置表单副本，最终仍由设置面板的保存流程统一提交。
const getLayoutList = (layoutKey) => {
  const list = props.formData?.ui?.[layoutKey]
  return Array.isArray(list) ? list : []
}

const handleLayoutDragStart = (layoutKey, index, event) => {
  const list = getLayoutList(layoutKey)
  if (!list[index]) return
  layoutDragState.value = { key: layoutKey, fromIndex: index, overIndex: index }
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', `${layoutKey}:${index}`)
}

const handleLayoutDragOver = (layoutKey, index) => {
  if (layoutDragState.value.key !== layoutKey) return
  layoutDragState.value = { ...layoutDragState.value, overIndex: index }
}

const handleLayoutDrop = (layoutKey, toIndex) => {
  const { key, fromIndex } = layoutDragState.value
  const list = getLayoutList(layoutKey)
  if (key !== layoutKey || fromIndex < 0 || toIndex < 0 || fromIndex === toIndex || !list[fromIndex]) {
    handleLayoutDragEnd()
    return
  }
  const nextList = [...list]
  const [moving] = nextList.splice(fromIndex, 1)
  nextList.splice(toIndex, 0, moving)
  props.formData.ui[layoutKey] = nextList
  handleLayoutDragEnd()
}

const handleLayoutDragEnd = () => {
  layoutDragState.value = { key: '', fromIndex: -1, overIndex: -1 }
}

const getLayoutDragClass = (layoutKey, index) => {
  if (layoutDragState.value.key !== layoutKey) return ''
  if (layoutDragState.value.fromIndex === index) return 'opacity-50 scale-[0.98]'
  if (layoutDragState.value.overIndex === index) return 'translate-y-0 ring-1 ring-accent-primary/60 rounded-xl'
  return ''
}
</script>
