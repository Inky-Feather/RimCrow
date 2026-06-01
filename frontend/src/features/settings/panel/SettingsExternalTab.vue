<template>
              <section class="animate-in fade-in slide-in-from-right-4">
                <h3 class="text-lg font-bold text-text-main mb-6 flex items-center justify-between">外部依赖
                  <button @click="resetToDefaultExternalPaths" v-tooltip="'将外部依赖相关路径重置为默认值'" class="px-3 py-1 bg-accent-warn/10 hover:bg-accent-warn/20 border border-accent-warn/30 rounded text-xs font-bold text-accent-warn transition-all">
                    重置为默认路径
                  </button>
                </h3>
                <div class="space-y-6">
                  <div class="modal-section space-y-4 p-5">
                    <div class="flex items-center justify-between gap-3">
                      <div> <h4 class="text-sm font-bold text-text-main">外部工具</h4><p class="text-xs text-text-dim mt-1">SteamCMD、贴图工具等由管理器调用的外部程序配置与状态检查。</p></div>
                      <button @click="handleCheckTools" class="px-3 py-1.5 bg-accent-tip/10 hover:bg-accent-tip/25 border border-accent-tip/20 rounded-lg text-xs font-bold transition-all">
                        检查外部工具
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
                      <button @click="handleCheckExternalData" class="px-3 py-1.5 bg-accent-primary/10 hover:bg-accent-primary/25 border border-accent-primary/20 rounded-lg text-xs font-bold transition-all">
                        检查外部库更新
                      </button>
                    </div>

                    <CommonPathInput label="用户规则路径" v-model="formData.user_rules_path" @browse="handleBrowse('user_rules_path', ['JSON Files (*.json)'])" :check="formData.check_info?.user_rules_path" />
                    <div class="flex items-end gap-1.5">
                        <CommonInput label="社区规则库 URL" v-model="formData.community_rules_url" />
                      <button @click="ruleStore.updateCommunity()" v-tooltip="'下载更新 社区规则'" :class="{'opacity-50 cursor-not-allowed pointer-events-none' :ruleStore.isLoading }"
                        class="shrink-0 h-9 w-9 bg-accent-tip/10 hover:bg-accent-tip text-accent-tip hover:text-text-main border border-accent-tip/30 rounded-lg flex items-center justify-center transition-colors">
                        <Download class="size-5" :class="{'animate-bounce': ruleStore.isLoading}" />
                      </button>
                    </div>
                    <CommonPathInput label="社区规则库路径" v-model="formData.community_rules_path" @browse="handleBrowse('community_rules_path', ['JSON Files (*.json)'])" :check="formData.check_info?.community_rules_path" />
                    <div class="py-2 pt-2 place-self-center w-[90%] border-b border-border-base/10"></div>
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
                    </div>
                    <div class="py-2 pt-2 place-self-center w-[90%] border-b border-border-base/10"></div>
                    <div class="flex items-end gap-1.5">
                      <CommonInput label="工坊数据库 URL" v-model="formData.community_workshop_db_url" />
                      <button @click="updateExternalDB('workshop_db')" v-tooltip="'下载更新 社区工坊数据库'" :class="{'opacity-50 cursor-not-allowed pointer-events-none' : downloadState['workshop_db'] }"
                        class="shrink-0 h-9 w-9 bg-accent-tip/10 hover:bg-accent-tip text-accent-tip hover:text-text-main border border-accent-tip/30 rounded-lg flex items-center justify-center transition-colors">
                        <Download class="size-5" :class="{'animate-bounce': downloadState['workshop_db']}" />
                      </button>
                    </div>
                    <CommonPathInput label="工坊数据库路径" v-model="formData.community_workshop_db_path" @browse="handleBrowse('community_workshop_db_path', ['JSON Files (*.json)'])" :check="formData.check_info?.community_workshop_db_path" />
                    <div class="py-2 pt-2 place-self-center w-[90%] border-b border-border-base/10"></div>
                    <div class="flex items-end gap-1.5">
                      <CommonInput label="替代 Mod 数据库 URL" v-model="formData.community_instead_db_url" />
                      <button @click="updateExternalDB('instead_db')" v-tooltip="'下载更新 社区替代 Mod 数据库'" :class="{'opacity-50 cursor-not-allowed pointer-events-none' : downloadState['instead_db'] }"
                        class="shrink-0 h-9 w-9 bg-accent-tip/10 hover:bg-accent-tip text-accent-tip hover:text-text-main border border-accent-tip/30 rounded-lg flex items-center justify-center transition-colors">
                        <Download class="size-5" :class="{'animate-bounce': downloadState['instead_db']}" />
                      </button>
                    </div>
                    <CommonPathInput label="替代 Mod 数据库路径" v-model="formData.community_instead_db_path" @browse="handleBrowse('community_instead_db_path', ['JSON Files (*.json;*.gz)'])" :check="formData.check_info?.community_instead_db_path" />
                    <div class="grid grid-cols-2 gap-4 pt-1">
                      <CommonSwitch class="col-span-1" label="自动检查外部库更新" v-model="formData.enable_auto_external_data_update_check" description="按设定间隔检查社区规则库、工坊数据库、替代 Mod 数据库是否有新版本。" />
                      <CommonNumber class="col-span-1" label="检查间隔（天）" v-model="formData.external_data_update_check_interval_days" :step="1" :min="1" :max="365" />
                    </div>
                  </div>
                </div>
              </section>
</template>

<script setup>
import { Download } from 'lucide-vue-next'
import CommonPathInput from '../../../shared/components/input/CommonPathInput.vue'
import CommonSwitch from '../../../shared/components/input/CommonSwitch.vue'
import CommonInput from '../../../shared/components/input/CommonInput.vue'
import CommonNumber from '../../../shared/components/input/CommonNumber.vue'

defineProps({
  formData: { type: Object, required: true },
  ruleStore: { type: Object, required: true },
  downloadState: { type: Object, required: true },
  resetToDefaultExternalPaths: { type: Function, required: true },
  handleCheckTools: { type: Function, required: true },
  handleCheckExternalData: { type: Function, required: true },
  handleBrowse: { type: Function, required: true },
  checkPath: { type: Function, required: true },
  updateExternalDB: { type: Function, required: true },
})
</script>
