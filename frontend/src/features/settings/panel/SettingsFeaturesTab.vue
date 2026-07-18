<template>
              <section class="animate-in fade-in slide-in-from-right-4">
                <h3 class="text-lg font-bold text-text-main mb-6">{{ t('ui.settings.features.title', '功能设置') }}</h3>
                <div class="space-y-6">
                  <div class="modal-section space-y-4 p-5">
                    <div>
                      <h4 class="text-sm font-bold text-text-main">{{ t('ui.settings.features.scan_maintenance', '扫描与数据维护') }}</h4>
                      <p class="text-xs text-text-dim mt-1">{{ t('ui.settings.features.scan_maintenance_desc', '控制 Mod 列表刷新、文件变动识别和缺失数据处理。') }}</p>
                    </div>
                    <div class="grid grid-cols-2 gap-4">
                      <CommonSwitch class="col-span-1" :label="t('ui.settings.features.auto_scan_on_startup', '启动时自动扫描 Mod 目录')" v-model="formData.enable_auto_scan" :description="t('ui.settings.features.auto_scan_on_startup_desc', '关闭后，需要手动点击扫描按钮才能更新 Mod 列表。')" />
                      <CommonSwitch class="col-span-1" :label="t('ui.settings.features.launch_profile_quick_scan', '环境直启前检查同步')" v-model="formData.enable_launch_profile_quick_scan" :description="t('ui.settings.features.launch_profile_quick_scan_desc', '从环境列表直接启动非当前环境时，会先检查并同步运行前所需的链接。开启后会先做一次轻量扫描再同步；关闭后只按当前数据库缓存和环境配置强制同步。')" />
                      <CommonSwitch class="col-span-1" :label="t('ui.settings.features.file_size_scan', '检查文件大小')" v-model="formData.enable_file_size_scan" :description="t('ui.settings.features.file_size_scan_desc', '开启后，扫描会检查 Mod 文件大小，更容易发现文件变化，但会更慢。')" />
                      <CommonSwitch class="col-span-1" :label="t('ui.settings.features.mod_residue_scan', '扫描后检查残留')" v-model="formData.enable_mod_residue_scan" :description="t('ui.settings.features.mod_residue_scan_desc', '开启后，全量扫描结束会在后台检查卸载后留下的文件夹和设置文件；关闭后只在手动打开残留清理时检查。')" />
                      <CommonSwitch class="col-span-1" :label="t('ui.settings.features.startup_prompt_new_only', '启动时只提醒新异常')" v-model="formData.startup_inventory_prompt_new_only" :description="t('ui.settings.features.startup_prompt_new_only_desc', '开启后，启动库存提醒只显示新发现的变更、缺失和已删除项；关闭后，只要问题仍存在就会继续提醒。')" />
                      <CommonSwitch class="col-span-1" :label="t('ui.settings.features.strict_disabled_mode', '严格禁用模式')" v-model="formData.strict_disabled_mode" :description="t('ui.settings.features.strict_disabled_mode_desc', '开启后，扫描时会按管理器记录保持禁用状态；被外部恢复启用的 Mod 会自动重新禁用。手动解除禁用不受影响。')" />
                      <CommonSwitch class="col-span-1" :label="t('ui.settings.features.delete_missing_mods_data', '自动清理缺失的 Mod 数据')" v-model="formData.delete_missing_mods_data" :description="t('ui.settings.features.delete_missing_mods_data_desc', '关闭后，缺失的 Mod 数据将保留在数据库中，列表内可以重新订阅。')" />
                      <CommonNumber class="col-span-1" :label="t('ui.settings.features.backup_retention_days', '自动备份保留天数')" :description="t('ui.settings.features.backup_retention_days_desc', '管理自动备份的最长保留时间，手动备份不受影响。')" v-model="formData.backup_retention_days" :step="1" :min="0" :max="365" />
                    </div>
                  </div>

                  <div class="modal-section space-y-4 p-5">
                    <div class="flex items-center justify-between gap-3">
                      <div>
                        <h4 class="text-sm font-bold text-text-main">{{ t('ui.settings.features.list_action_checks', '列表功能与检查提示') }}</h4>
                        <p class="text-xs text-text-dim mt-1">{{ t('ui.settings.features.list_action_checks_desc', '控制列表保存、运行、显示提示和重置预设。') }}</p>
                      </div>
                      <button type="button" v-tooltip="t('ui.settings.features.reset_active_preset_desc', '管理预设的基底启用列表，重置列表时会直接按预设列表重置。')"
                        class="inline-flex items-center gap-1 rounded-lg border border-accent-warn/25 bg-accent-warn/10 px-3 py-1.5 text-xs font-bold text-accent-warn transition-all hover:bg-accent-warn/20"
                        @click="appStore.uiState.showResetActiveListManager = true">
                        {{ t('ui.settings.features.reset_active_preset_manager', '预设列表管理') }}
                      </button>
                    </div>
                    <div class="grid grid-cols-2 gap-4">
                      <CommonSwitch class="col-span-1" :label="t('ui.settings.features.persist_temp_mod_list', '保存临时列表')" v-model="formData.ui.persist_temp_mod_list" :description="t('ui.settings.features.persist_temp_mod_list_desc', '开启后，临时列表会按当前环境保存，下次进入该环境时自动恢复；关闭后，保存时会把临时列表里的 Mod 放回停用列表顶部。')" />
                      <CommonSwitch class="col-span-1" :label="t('ui.settings.features.action_prechecks', '关键动作前必要检查')" v-model="formData.enable_action_prechecks" :description="t('ui.settings.features.action_prechecks_desc', '开启后，保存、运行、自动排序前会检查未安装项和未启用项；关闭后将直接执行，不再弹出检查窗口。')" />
                      <CommonSwitch class="col-span-1" :label="t('ui.settings.features.show_coexistence_message', '显示共存冲突提示')" v-model="formData.show_coexistence_message" :description="t('ui.settings.features.show_coexistence_message_desc', '关闭后，将不会显示共存 Mod 的冲突提示信息。')" />
                      <CommonSwitch class="col-span-1" :label="t('ui.settings.features.check_language_support', '检查语言支持')" v-model="formData.check_language_support" :description="t('ui.settings.features.check_language_support_desc', '开启后，将会在 Mod 问题提示增加“语言支持”警告，提示 Mod 是否支持当前语言。')" />
                      <CommonSwitch class="col-span-1" :label="t('ui.settings.features.wide_language_pack_detection', '宽泛识别语言包')" v-model="formData.wide_language_pack_detection" :description="t('ui.settings.features.wide_language_pack_detection_desc', '开启后，带翻译文件和补丁、但没有程序集、贴图、音频或普通定义的 Mod，也会按语言包参与归属判断。')" />
                      <CommonSwitch class="col-span-1" :label="t('ui.settings.features.multiplayer_compatibility_check', '检查 Multiplayer 联机兼容性')" v-model="formData.enable_multiplayer_compatibility_check" :description="t('ui.settings.features.multiplayer_compatibility_check_desc', '开启后，在库存中检测到 Multiplayer 时，会为 Mod 列表显示联机兼容等级和辅助修正提示。')" />
                      <CommonSwitch class="col-span-1" :label="t('ui.settings.features.skip_language_pack_alias_generation', '别名备注时跳过语言包')" v-model="formData.skip_language_pack_alias_generation" :description="t('ui.settings.features.skip_language_pack_alias_generation_desc', '开启后，批量生成别名和备注时不处理语言包；单个模组手动生成不受影响。')" />
                      <CommonSwitch class="col-span-1" :label="t('ui.settings.features.enable_tool_mods', '使用辅助工具模组')" v-model="formData.enable_tool_mods" :description="t('ui.settings.features.enable_tool_mods_desc', '开启后，将在保存或自动排序时自动启用辅助工具模组，如提供日志获取等功能。')" />
                    </div>
                  </div>

                  <div class="modal-section space-y-4 p-5">
                    <div>
                      <h4 class="text-sm font-bold text-text-main">{{ t('ui.settings.features.auto_sort_logic', '自动排序逻辑') }}</h4>
                      <p class="text-xs text-text-dim mt-1">{{ t('ui.settings.features.auto_sort_logic_desc', '控制自动排序的整体策略、同档顺序和依赖贴靠效果。') }}</p>
                    </div>
                    <div class="grid grid-cols-2 gap-4">
                      <CommonSwitch class="col-span-1" :label="t('ui.settings.features.regular_mods_follow_dependencies', '普通模组贴紧依赖')" v-model="formData.regular_mods_follow_dependencies" :description="t('ui.settings.features.regular_mods_follow_dependencies_desc', '开启后，自动排序会尽量让普通 Mod 紧跟在同权重内已启用的最后一个依赖后方，让同一系列的模组更聚拢。')" />
                      <CommonSwitch class="col-span-1" :label="t('ui.settings.features.language_packs_follow_targets', '语言包贴紧前置')" v-model="formData.language_packs_follow_targets" :description="t('ui.settings.features.language_packs_follow_targets_desc', '开启后，自动排序会尽量让语言包紧跟在它已启用的最后一个前置/依赖模组后方；如果找不到目标，就保持原来的默认底层位置。')" />
                      <CommonSelect class="col-span-1" :label="t('ui.settings.features.auto_sort_strategy_label', '自动排序策略')" v-model="formData.auto_sort_strategy" showBottom
                        :description="t('ui.settings.features.auto_sort_strategy_desc', '旧版更保守、更接近传统手工整理结果，但对带有置顶/置底倾向的模组及其关联链的处理效果较差；新版会更积极地把带有置顶/置底倾向的模组及其关联链推向列表两端。')"
                        :options="autoSortStrategyOptions" />
                      <CommonSelect class="col-span-1" :label="t('ui.settings.features.sort_mods_by', '排序顺序')" v-model="formData.sort_mods_by" showBottom
                        :description="t('ui.settings.features.sort_mods_by_desc', '影响自动排序时同档次的 Mod 顺序，处理优先级是 别名>原名>包名，所以即使 Mod 没有别名，也能按原名参与排序。')"
                        :options="modNameSortOptions" />
                    </div>
                  </div>

                  <div class="modal-section space-y-4 p-5">
                    <div>
                      <h4 class="text-sm font-bold text-text-main">{{ t('ui.settings.features.file_generation_deploy', '文件生成与部署') }}</h4>
                      <p class="text-xs text-text-dim mt-1">{{ t('ui.settings.features.file_generation_deploy_desc', '控制共存 Mod 的文件夹命名，以及运行前链接部署方式。') }}</p>
                    </div>
                    <div class="grid grid-cols-2 gap-4">
                      <CommonSelect class="col-span-1" :label="t('ui.settings.features.coexist_folder_name_type', '共存 Mod 文件夹生成方式')" v-model="formData.coexist_mod_folder_name_type" showBottom
                        :description="t('ui.settings.features.coexist_folder_name_type_desc', '影响创建共存 Mod 时的文件夹名称，处理优先级是 别名>原名>包名>工坊 ID，所以即使 Mod 没有别名，也能按原名创建文件夹。')"
                        :options="coexistFolderNameOptions" />
                      <CommonSelect class="col-span-1" :label="t('ui.settings.features.link_deployment_mode', '链接部署模式')" v-model="formData.link_deployment_mode_full" showBottom
                        :description="t('ui.settings.features.link_deployment_mode_desc', '影响启用管理器 Mod 或多环境下使用创意工坊 Mod 时的链接部署行为模式，增量部署会尽量保留已正确的链接，只处理变化项；完全重建会先移除全部旧链接，再按当前扫描结果重新部署。')"
                        :options="linkDeploymentOptions" />
                    </div>
                  </div>

                  <div v-if="formData.translation" class="modal-section space-y-4 p-5">
                    <div>
                      <h4 class="text-sm font-bold text-text-main">{{ t('ui.settings.features.translation', '翻译') }}</h4>
                      <p class="text-xs text-text-dim mt-1">{{ t('ui.settings.features.translation_desc', '设置默认翻译偏好，以及工坊说明翻译的单独策略。') }}</p>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                      <TranslationFeatureControls class="col-span-2" mode="panel" feature="default" :settings="formData.translation.default" :show-feature-switches="false"
                        :title="t('ui.settings.features.default_translation_settings', '默认翻译设置')" :description="t('ui.settings.features.default_translation_settings_desc', '没有单独指定语言或翻译器的翻译功能，会使用这里的设置。')" />
                      <button type="button" class="col-span-2 mt-2 flex items-center justify-between rounded-lg border border-border-base/10 bg-bg-inset/70 px-3 py-2 text-left transition-colors hover:border-accent-primary/30 hover:text-accent-primary"
                        @click="showWorkshopTranslationSettings = !showWorkshopTranslationSettings">
                        <span>
                          <span class="block text-xs font-black text-text-main">{{ t('ui.settings.features.workshop_description_translation', '工坊说明翻译') }}</span>
                          <span class="block text-[0.68rem] text-text-dim">{{ t('ui.settings.features.workshop_description_translation_desc', '设置工坊详情页说明翻译的语言、翻译器和自动翻译策略。') }}</span>
                        </span>
                        <span class="text-xs font-bold text-text-dim">{{ showWorkshopTranslationSettings ? t('common.action.collapse', '收起') : t('ui.settings.features.configure', '设置') }}</span>
                      </button>
                      <TranslationFeatureControls v-if="showWorkshopTranslationSettings" class="col-span-2" mode="panel" feature="workshop_detail" :settings="formData.translation.workshop_detail"
                        :title="t('ui.settings.features.workshop_description_translation', '工坊说明翻译')" :description="t('ui.settings.features.workshop_description_translation_only_desc', '只影响工坊详情页的标题和说明翻译。')" />
                    </div>
                  </div>
                </div>
              </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import CommonSwitch from '../../../shared/components/input/CommonSwitch.vue'
import CommonSelect from '../../../shared/components/input/CommonSelect.vue'
import CommonNumber from '../../../shared/components/input/CommonNumber.vue'
import TranslationFeatureControls from '../../../shared/components/translation/TranslationFeatureControls.vue'
import { useAppStore } from '../../../app/stores/appStore'
import { t } from '../../../shared/i18n.js'

defineProps({ formData: { type: Object, required: true } })
const showWorkshopTranslationSettings = ref(false)
const appStore = useAppStore()

const autoSortStrategyOptions = computed(() => [
  { label: t('ui.settings.features.auto_sort_strategy.classic', '经典自动排序（旧版）'), value: 'classic_sort_logic' },
  { label: t('ui.settings.features.auto_sort_strategy.edge_enhanced', '两端强化排序（新版）'), value: 'edge_enhanced_sort_logic' },
])
const modNameSortOptions = computed(() => [
  { label: t('ui.mod.option.by_alias', '按别名'), value: 'alias_name' },
  { label: t('ui.mod.option.by_name_short', '按原名'), value: 'name' },
  { label: t('ui.mod.option.by_package_id', '按包名'), value: 'id' },
])
const coexistFolderNameOptions = computed(() => [
  { label: t('ui.mod.option.by_workshop_id', '按工坊 ID'), value: 'workshop_id' },
  { label: t('ui.mod.option.by_package_id', '按包名'), value: 'package_id' },
  { label: t('ui.mod.option.by_name_short', '按原名'), value: 'name' },
  { label: t('ui.mod.option.by_alias', '按别名'), value: 'alias_name' },
])
const linkDeploymentOptions = computed(() => [
  { label: t('ui.settings.features.link_deployment.incremental', '增量部署（默认）'), value: 'incremental' },
  { label: t('ui.settings.features.link_deployment.full', '完全重建'), value: 'full' },
])
</script>
