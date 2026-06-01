<template>
              <section class="animate-in fade-in slide-in-from-right-4">
                <h3 class="text-lg font-bold text-text-main mb-6 flex items-center justify-between">界面与布局
                  <button @click="guideStore.resetAllGuides()" v-tooltip="'重置界面引导，将界面引导重置为默认值'" class="px-3 py-1 bg-accent-warn/10 hover:bg-accent-warn/20 border border-accent-warn/30 rounded text-xs font-bold text-accent-warn transition-all">
                    重置界面引导
                  </button>
                </h3>
                <div class="space-y-6">
                  <div class="grid grid-cols-2 gap-4">
                    <CommonSelect class="pointer-events-none opacity-50" label="界面语言" v-model="formData.language" :options="[{label:'简体中文', value:'zh-CN'}, {label:'English', value:'en'}]" />
                    <ThemeSelect v-if="formData.ui" :model-value="currentThemeId" :themes="appStore.themes"
                      @update:model-value="emit('update:currentThemeId', $event)"
                      @create="emit('open-theme-create')" @edit="emit('open-theme-edit', $event)" @delete="emit('delete-theme', $event)"
                    />
                  </div>
                  <CommonSwitch label="在系统浏览器中打开 URL" v-model="formData.open_url_on_system" description="关闭则使用内置浏览器" />
                  <div class="grid grid-cols-2 gap-4">
                    <CommonNumber label="字体大小" description="控制界面字体大小，影响所有控件的内容显示" v-model="formData.ui.font_size" :step="1" :min="8" :max="40" />
                    <CommonNumber label="提示悬停时间" description="控制悬浮提示信息的等待时间，单位是毫秒" v-model="formData.ui.tooltip_hover_time" :step="100" :min="100" :max="5000" />
                    <CommonNumber label="拖动判定延迟" description="控制列表项拖动操作的判定延迟，单位是毫秒，默认值为 30 毫秒，为 0 时可能使点击操作出现抖动。" v-model="formData.ui.drag_delay" :step="10" :min="0" :max="500" />
                    <div></div>
                    
                    <div class="modal-section col-span-2 grid grid-cols-2 gap-2 p-2">
                      <span class="col-span-2 ml-2 mt-2 text-sm font-bold tracking-wide">列表设定
                        <label v-tooltip="'可调整列表的显示方式与辅助功能'" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
                      </span>
                      <CommonSwitch label="Mod 悬停面板" v-model="formData.ui.show_mod_hover_panel" description="控制 Mod 列表中悬停时的面板显示。" />
                      <CommonSwitch label="双击启用/停用 Mod" v-model="formData.ui.double_click_active_mod" description="控制 Mod 列表中双击启用/停用 Mod 动作。" />
                      <CommonSwitch label="依赖关系图" v-model="formData.ui.show_dependency_graph" description="控制启用列表中依赖关系图的显示。" />
                      <CommonSwitch label="列表索引" v-model="formData.ui.show_list_index" description="控制列表中索引列的显示。" />
                    </div>

                    <div class="modal-section col-span-2 grid grid-cols-2 gap-2 p-2">
                      <CommonSwitch class="col-span-2 px-2 pt-2" label="列表图标" v-model="formData.ui.show_list_icon" description="控制列表中的所有图标显示，包括简单视图和详细视图。" mini />
                      <CommonSwitch :disabled="!formData.ui.show_list_icon" label="列表 Mod 图标" v-model="formData.ui.show_list_mod_icon" description="控制列表中 Mod 图标显示，不影响详细视图。" />
                      <CommonSwitch :disabled="!formData.ui.show_list_icon" label="列表 Mod 类型图标" v-model="formData.ui.show_list_modtype_icon" description="控制列表中 Mod 类型图标显示，不影响详细视图。" />
                    </div>
                    <div class="modal-section col-span-2 grid grid-cols-2 gap-2 p-2">
                      <CommonSwitch class="col-span-2 px-2 pt-2" mini label="列表分类折叠" v-model="formData.ui.enable_active_section_collapse" description="仅在启用列表生效。名称或别名满足 `=标题=` 或 `/*标题*/` 的纯标题模组会被识别为可折叠分类标题；折叠后拖动标题即整组拖动。^^可工坊订阅 [[分类排列标签合集]] 配合使用。^^" />
                      <CommonSwitch :disabled="!formData.ui.enable_active_section_collapse" label="默认折叠" v-model="formData.ui.default_collapse_active_sections" description="开启后，启用列表中的标题分组会在初始显示时默认折叠。" />
                      <div class="flex items-center gap-1" :class="{'pointer-events-none opacity-50': !formData.ui.enable_active_section_collapse}">
                        <button @click="appStore.openSteamWorkshopById('2138932352')"
                          class="px-2 py-1.5 bg-bg-overlay/5 hover:bg-bg-overlay/10 border border-border-base/10 rounded-lg text-xs font-bold cursor-pointer transition-all">
                          <span class="flex items-center gap-2">
                            访问<p class="text-accent-cool">分类排列标签合集</p>工坊页面
                          </span>
                        </button>
                        <button @click="appStore.openSteamWorkshopById('3542535605')"
                          class="px-2 py-1.5 bg-bg-overlay/5 hover:bg-bg-overlay/10 border border-border-base/10 rounded-lg text-xs font-bold cursor-pointer transition-all">
                          <span class="flex items-center gap-2">
                            访问<p class="text-accent-cool">分类排序合集</p>工坊页面
                          </span>
                        </button>
                      </div>
                    </div>
                    
                    <div class="modal-section col-span-2 grid grid-cols-2 gap-2 p-2">
                      <span class="col-span-2 ml-2 mt-2 text-sm font-bold tracking-wide">分组设定
                        <label v-tooltip="'可调整分组列表的显示方式'" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
                      </span>
                      <CommonSwitch label="分组索引" v-model="formData.ui.show_group_index" description="控制分组列表中Mod索引的显示。" />
                      <CommonSwitch label="分组图标" v-model="formData.ui.show_group_icon" description="控制分组列表中Mod图标的显示。" />
                    </div>
                    <div class="modal-section col-span-2 grid grid-cols-2 gap-2 p-2">
                      <span class="col-span-2 ml-2 mt-2 text-sm font-bold tracking-wide">主页布局
                        <label v-tooltip="'可拖动切换布局顺序'" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
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
                      <CommonSwitch class="col-span-2 px-2 pt-2" mini label="Mod 详情面板" v-model="getDataById('details', formData.ui.main_layout).visible" description="可关闭Mod详情栏。" />
                      <CommonSwitch :disabled="!getDataById('details', formData.ui.main_layout).visible" label="动态图标云" v-model="formData.ui.show_icons_cloud" description="控制详情页闲置时的动态图标云显示。" />
                      <CommonNumber label="详情页加载延迟" description="控制 Mod 详情页加载的延迟时间，单位是毫秒，默认值为 200 毫秒。" v-model="formData.ui.detail_delay" :step="10" :min="0" :max="5000" />
                      <span class="col-span-2 text-xs ml-2 mt-2">Mod 详情布局
                        <label v-tooltip="'可拖动切换布局顺序'" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
                      </span>
                      <div class="col-span-2 flex flex-col gap-1 p-2 rounded-xl bg-bg-deep/10 border border-border-base/10"
                        :class="{ 'pointer-events-none opacity-50': !getDataById('details', formData.ui.main_layout).visible }">
                        <div v-for="item, index in formData.ui.mod_details_layout" :key="item.id"
                          class="flex items-center transition-transform duration-150"
                          :class="getLayoutDragClass('mod_details_layout', index)"
                          :draggable="getDataById('details', formData.ui.main_layout).visible"
                          @dragstart="handleLayoutDragStart('mod_details_layout', index, $event)"
                          @dragover.prevent="handleLayoutDragOver('mod_details_layout', index)"
                          @drop.prevent="handleLayoutDrop('mod_details_layout', index)"
                          @dragend="handleLayoutDragEnd">
                          <span class="p-1 mr-1 rounded-md bg-accent-primary/30">{{ index }}</span>
                          <CommonSwitch class="flex-1 cursor-move" :disabled="!getDataById('details', formData.ui.main_layout).visible" :key="item.id" :label="appStore.DETAILS_LAYOUT_MAPS[item.id].label" v-model="item.visible" :description="appStore.DETAILS_LAYOUT_MAPS[item.id].desc" />
                        </div>
                      </div>
                      
                    </div>
                    
                  </div>
                </div>
              </section>
</template>

<script setup>
import CommonSwitch from '../../../shared/components/input/CommonSwitch.vue'
import CommonNumber from '../../../shared/components/input/CommonNumber.vue'
import CommonSelect from '../../../shared/components/input/CommonSelect.vue'
import ThemeSelect from '../theme/ThemeSelect.vue'

defineProps({
  formData: { type: Object, required: true },
  appStore: { type: Object, required: true },
  guideStore: { type: Object, required: true },
  currentThemeId: { type: String, required: true },
  getDataById: { type: Function, required: true },
  getLayoutDragClass: { type: Function, required: true },
  handleLayoutDragStart: { type: Function, required: true },
  handleLayoutDragOver: { type: Function, required: true },
  handleLayoutDrop: { type: Function, required: true },
  handleLayoutDragEnd: { type: Function, required: true },
})
const emit = defineEmits(['update:currentThemeId', 'open-theme-create', 'open-theme-edit', 'delete-theme'])
</script>
