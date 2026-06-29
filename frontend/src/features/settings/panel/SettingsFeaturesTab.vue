<template>
              <section class="animate-in fade-in slide-in-from-right-4">
                <h3 class="text-lg font-bold text-text-main mb-6">功能设置</h3>
                <div class="space-y-6">
                  <div class="modal-section space-y-4 p-5">
                    <div>
                      <h4 class="text-sm font-bold text-text-main">扫描与数据维护</h4>
                      <p class="text-xs text-text-dim mt-1">控制 Mod 列表刷新、文件变动识别和缺失数据处理。</p>
                    </div>
                    <div class="grid grid-cols-2 gap-4">
                      <CommonSwitch class="col-span-1" label="启动时自动扫描 Mod 目录" v-model="formData.enable_auto_scan" description="关闭后，需要手动点击扫描按钮才能更新 Mod 列表。" />
                      <CommonSwitch class="col-span-1" label="环境直启前检查同步" v-model="formData.enable_launch_profile_quick_scan" description="从环境列表直接启动非当前环境时，会先检查并同步运行前所需的链接。开启后会先做一次轻量扫描再同步；关闭后只按当前数据库缓存和环境配置强制同步。" />
                      <CommonSwitch class="col-span-1" label="扫描时检查文件大小" v-model="formData.enable_file_size_scan" description="开启后，扫描时会自动检查 Mod 的文件大小，以此识别新增或更新的内容。该功能会增加扫描耗时，但能显著提高文件变动的识别精度。" />
                      <CommonSwitch class="col-span-1" label="扫描后检查残留" v-model="formData.enable_mod_residue_scan" description="开启后，全量扫描结束会在后台检查卸载后留下的文件夹和设置文件；关闭后只在手动打开残留清理时检查。" />
                      <CommonSwitch class="col-span-1" label="启动时只提醒新异常" v-model="formData.startup_inventory_prompt_new_only" description="开启后，启动库存提醒只显示新发现的变更、缺失和已删除项；关闭后，只要问题仍存在就会继续提醒。" />
                      <CommonSwitch class="col-span-1" label="严格禁用模式" v-model="formData.strict_disabled_mode" description="开启后，扫描时会按管理器记录保持禁用状态；被外部恢复启用的 Mod 会自动重新禁用。手动解除禁用不受影响。" />
                      <CommonSwitch class="col-span-1" label="自动清理缺失的 Mod 数据" v-model="formData.delete_missing_mods_data" description="关闭后，缺失的 Mod 数据将保留在数据库中，列表内可以重新订阅。" />
                      <CommonNumber class="col-span-1" label="自动备份保留天数" description="管理自动备份的最长保留时间，手动备份不受影响。" v-model="formData.backup_retention_days" :step="1" :min="0" :max="365" />
                    </div>
                  </div>

                  <div class="modal-section space-y-4 p-5">
                    <div>
                      <h4 class="text-sm font-bold text-text-main">列表操作问题检查</h4>
                      <p class="text-xs text-text-dim mt-1">控制保存、运行和列表显示时的提醒与辅助行为。</p>
                    </div>
                    <div class="grid grid-cols-2 gap-4">
                      <CommonSwitch class="col-span-1" label="保存临时列表" v-model="formData.ui.persist_temp_mod_list" description="开启后，临时列表会按当前环境保存，下次进入该环境时自动恢复；关闭后，保存时会把临时列表里的 Mod 放回停用列表顶部。" />
                      <CommonSwitch class="col-span-1" label="关键动作前必要检查" v-model="formData.enable_action_prechecks" description="开启后，保存、运行、自动排序前会检查未安装项和未启用项；关闭后将直接执行，不再弹出检查窗口。" />
                      <CommonSwitch class="col-span-1" label="显示共存冲突提示" v-model="formData.show_coexistence_message" description="关闭后，将不会显示共存Mod的冲突提示信息。" />
                      <CommonSwitch class="col-span-1" label="检查语言支持" v-model="formData.check_language_support" description="开启后，将会在 Mod 问题提示增加“语言支持”警告，提示 Mod 是否支持当前语言。" />
                      <CommonSwitch class="col-span-1" label="检查 Multiplayer 联机兼容性" v-model="formData.enable_multiplayer_compatibility_check" description="开启后，在库存中检测到 Multiplayer 时，会为 Mod 列表显示联机兼容等级和辅助修正提示。" />
                      <CommonSwitch class="col-span-1" label="跳过语言包生成别名备注" v-model="formData.skip_language_pack_alias_generation" description="开启后，批量生成别名和备注时不处理语言包；单个模组手动生成不受影响。" />
                      <CommonSwitch class="col-span-1" label="使用辅助工具模组" v-model="formData.enable_tool_mods" description="开启后，将在保存或自动排序时自动启用辅助工具模组，如提供日志获取等功能。" />
                    </div>
                  </div>

                  <div class="modal-section space-y-4 p-5">
                    <div>
                      <h4 class="text-sm font-bold text-text-main">自动排序逻辑</h4>
                      <p class="text-xs text-text-dim mt-1">控制自动排序的整体策略、同档顺序和依赖贴靠效果。</p>
                    </div>
                    <div class="grid grid-cols-2 gap-4">
                      <CommonSwitch class="col-span-1" label="普通模组贴紧依赖" v-model="formData.regular_mods_follow_dependencies" description="开启后，自动排序会尽量让普通 Mod 紧跟在同权重内已启用的最后一个依赖后方，让同一系列的模组更聚拢。" />
                      <CommonSwitch class="col-span-1" label="语言包贴紧前置" v-model="formData.language_packs_follow_targets" description="开启后，自动排序会尽量让语言包紧跟在它已启用的最后一个前置/依赖模组后方；如果找不到目标，就保持原来的默认底层位置。" />
                      <CommonSelect class="col-span-1" label="自动排序策略" v-model="formData.auto_sort_strategy" showBottom
                        description="旧版更保守、更接近传统手工整理结果，但对带有置顶/置底倾向的模组及其关联链的处理效果较差；新版会更积极地把带有置顶/置底倾向的模组及其关联链推向列表两端。"
                        :options="[{label:'经典自动排序（旧版）', value:'classic_sort_logic'},{label:'两端强化排序（新版）', value:'edge_enhanced_sort_logic'}]" />
                      <CommonSelect class="col-span-1" label="排序顺序" v-model="formData.sort_mods_by" showBottom
                        description="影响自动排序时同档次的Mod顺序，处理优先级是 别名>原名>包名，所以即使Mod没有别名，也能按原名参与排序。"
                        :options="[{label:'按别名', value:'alias_name'},{label:'按原名', value:'name'},{label:'按包名', value:'id'}]" />
                    </div>
                  </div>

                  <div class="modal-section space-y-4 p-5">
                    <div>
                      <h4 class="text-sm font-bold text-text-main">文件生成与部署</h4>
                      <p class="text-xs text-text-dim mt-1">控制共存 Mod 的文件夹命名，以及运行前链接部署方式。</p>
                    </div>
                    <div class="grid grid-cols-2 gap-4">
                      <CommonSelect class="col-span-1" label="共存Mod文件夹生成方式" v-model="formData.coexist_mod_folder_name_type" showBottom
                        description="影响创建共存Mod时的文件夹名称，处理优先级是 别名>原名>包名>工坊ID，所以即使Mod没有别名，也能按原名创建文件夹。"
                        :options="[{label:'按工坊ID', value:'workshop_id'},{label:'按包名', value:'package_id'},{label:'按原名', value:'name'},{label:'按别名', value:'alias_name'}]" />
                      <CommonSelect class="col-span-1" label="链接部署模式" v-model="formData.link_deployment_mode_full" showBottom
                        description="影响启用管理器Mod或多环境下使用创意工坊Mod时的链接部署行为模式，增量部署会尽量保留已正确的链接，只处理变化项；完全重建会先移除全部旧链接，再按当前扫描结果重新部署。"
                        :options="[{label:'增量部署（默认）', value:'incremental'},{label:'完全重建', value:'full'}]" />
                    </div>
                  </div>

                  <div v-if="formData.translation" class="modal-section space-y-4 p-5">
                    <div>
                      <h4 class="text-sm font-bold text-text-main">翻译</h4>
                      <p class="text-xs text-text-dim mt-1">设置默认翻译偏好，以及工坊说明翻译的单独策略。</p>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                      <TranslationFeatureControls class="col-span-2" mode="panel" feature="default" :settings="formData.translation.default" :show-feature-switches="false"
                        title="默认翻译设置" description="没有单独指定语言或翻译器的翻译功能，会使用这里的设置。" />
                      <button type="button" class="col-span-2 mt-2 flex items-center justify-between rounded-lg border border-border-base/10 bg-bg-inset/70 px-3 py-2 text-left transition-colors hover:border-accent-primary/30 hover:text-accent-primary"
                        @click="showWorkshopTranslationSettings = !showWorkshopTranslationSettings">
                        <span>
                          <span class="block text-xs font-black text-text-main">工坊说明翻译</span>
                          <span class="block text-[0.68rem] text-text-dim">设置工坊详情页说明翻译的语言、翻译器和自动翻译策略。</span>
                        </span>
                        <span class="text-xs font-bold text-text-dim">{{ showWorkshopTranslationSettings ? '收起' : '设置' }}</span>
                      </button>
                      <TranslationFeatureControls v-if="showWorkshopTranslationSettings" class="col-span-2" mode="panel" feature="workshop_detail" :settings="formData.translation.workshop_detail"
                        title="工坊说明翻译" description="只影响工坊详情页的标题和说明翻译。" />
                    </div>
                  </div>
                </div>
              </section>
</template>

<script setup>
import { ref } from 'vue'
import CommonSwitch from '../../../shared/components/input/CommonSwitch.vue'
import CommonSelect from '../../../shared/components/input/CommonSelect.vue'
import CommonNumber from '../../../shared/components/input/CommonNumber.vue'
import TranslationFeatureControls from '../../../shared/components/translation/TranslationFeatureControls.vue'

defineProps({ formData: { type: Object, required: true } })
const showWorkshopTranslationSettings = ref(false)
</script>
