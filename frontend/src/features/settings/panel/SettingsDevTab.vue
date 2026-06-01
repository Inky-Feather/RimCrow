<template>
              <section class="animate-in fade-in slide-in-from-right-4">
                <h3 class="text-lg font-bold text-text-main mb-6">开发与调试</h3>
                <div class="space-y-6">
                  <div class="grid grid-cols-2 gap-4">
                    <CommonSwitch class="col-span-2" label="调试模式" v-model="formData.debug_mode" description="开启调试模式后重启软件将会出现开发者工具窗口，可查看问题详情。" />
                    <CommonSwitch class="col-span-2" label="浏览器模式启动" v-model="formData.browser_mode" description="默认仍使用内置 WebView。开启后，无启动参数时将改为在本机浏览器中启动；关闭浏览器主页面后程序会自动退出。" />
                    <div class="modal-section col-span-2 p-2">
                      <CommonSwitch class="mb-2" label="自动进入静默模式" v-model="formData.auto_enter_silent_mode" mini description="开启后，检测到 RimWorld 运行时会自动切换到静默模式；关闭后仅保留手动进入能力。" />
                      <div class="grid grid-cols-3 items-center">
                        <p class="col-span-2 text-xs ml-1 leading-relaxed text-text-dim">
                          游戏运行时可切到更轻量的界面，减少资源占用，并可直接查看游戏日志。
                        </p>
                        <CommonSelect class="col-span-1 mr-2" label="默认页面" mini v-model="formData.silent_mode_default_view"
                          :options="[
                            { label: '静默主页', value: 'home' },
                            { label: '游戏日志', value: 'logs' }
                          ]"
                          description="控制自动进入静默模式时，默认先显示主页还是直接进入日志页。"
                        />
                      </div>
                    </div>
                    <CommonSwitch class="col-span-1" label="自动检查更新" v-model="formData.enable_auto_update_check" description="关闭后，需要手动点击检查更新按钮才能更新 RimModManager。" />
                    <!-- 手动检查按钮 -->
                    <div class="modal-section flex items-center justify-between p-3">
                      <div class="flex flex-col">
                        <span class="text-sm font-bold text-text-main">软件版本</span>
                        <span class="text-xs text-text-dim">当前版本: v{{ appStore.appVersion }}</span>
                      </div>

                      <div class="flex items-center justify-between gap-1">
                        <button @click="appStore.showChangelog()"
                          class="px-3 py-1.5 bg-accent-tip/15 hover:bg-accent-tip/30 border border-accent-tip/10 rounded-lg text-xs font-bold cursor-pointer transition-all">
                          <span class="flex items-center gap-2">
                            更新日志
                          </span>
                        </button>
                        <button @click="appStore.checkUpdate(true)" :disabled="appStore.updateState.isChecking"
                          class="px-3 py-1.5 bg-accent-highlight/15 hover:bg-bg-overlay/10 border border-border-base/10 rounded-lg text-xs font-bold cursor-pointer transition-all">
                          <span v-if="appStore.updateState.isChecking" class="flex items-center gap-2">
                            <LoaderCircle class="animate-spin h-3 w-3" />
                            检查中
                          </span>
                          <span v-else>检查更新</span>
                        </button>
                      </div>

                    </div>
                    <CommonSelect label="日志等级" v-model="formData.log_level" :options="[{label:'DEBUG', value:'DEBUG'},{label:'INFO', value:'INFO'},{label:'WARNING', value:'WARNING'}]" />
                    <CommonNumber label="日志保留天数" v-model="formData.log_retention_days" :step="1" :min="0" :max="365" />
                  </div>
                  <div class="modal-section p-4">
                    <div class="flex items-center justify-between gap-4">
                      <div class="min-w-0">
                        <h4 class="text-sm font-bold text-text-main">网络图片缓存</h4>
                        <p class="mt-1 text-xs leading-relaxed text-text-dim">
                          远程封面图、截图和富文本图片会先写入本地缓存，再由前端通过本地资源服务读取。
                        </p>
                        <div class="mt-3 flex flex-wrap items-center gap-3 text-xs text-text-dim">
                          <span>已缓存 {{ appStore.remoteImageCache.file_count }} 张</span>
                          <span>占用 {{ formatFileSize(appStore.remoteImageCache.total_bytes) }}</span>
                        </div>
                      </div>
                      <button @click="handleClearRemoteImageCache" :disabled="appStore.isLoading"
                        class="shrink-0 px-4 py-1.5 bg-bg-overlay/5 hover:bg-bg-overlay/10 border border-border-base/10 rounded-lg text-xs font-bold transition-all disabled:cursor-not-allowed disabled:opacity-50">
                        清理缓存图片
                      </button>
                    </div>
                  </div>
                  <div class="p-4 rounded-2xl bg-accent-primary/5 border border-accent-primary/20">
                    <div class="flex items-center justify-between gap-4">
                      <div class="min-w-0">
                        <h4 class="text-sm font-bold text-text-main">软件数据迁移</h4>
                        <p class="text-xs text-text-dim leading-relaxed mt-1">
                          导入现有数据包，或打开导出面板选择要打包的软件数据。环境数据会包含对应环境的完整目录。
                        </p>
                      </div>
                      <div class="flex items-center gap-2 shrink-0">
                        <button @click="openDataBundleImportDialog"
                          class="px-3 py-1.5 rounded-lg bg-bg-overlay/5 hover:bg-bg-overlay/10 border border-border-base/10 text-xs font-bold transition-all" >
                          导入数据包
                        </button>
                        <button @click="openDataBundleModal"
                          class="px-4 py-1.5 rounded-lg bg-accent-primary hover:bg-accent-primary/85 text-on-accent-primary text-xs font-black shadow-[0_0_15px_rgba(var(--rgb-accent-primary),0.2)] transition-all" >
                          导出软件数据
                        </button>
                      </div>
                    </div>
                  </div>
                  <div class="p-4 rounded-2xl bg-accent-special/5 border border-accent-special/20">
                    <div class="flex items-center justify-between gap-4">
                      <div class="min-w-0">
                        <h4 class="text-sm font-bold text-text-main">环境与模组打包</h4>
                        <p class="text-xs text-text-dim leading-relaxed mt-1">
                          导入导出模组实体包。支持当前环境有效模组、当前启用模组导出，也支持附带环境数据的模组包导入。
                        </p>
                      </div>
                      <div class="flex items-center gap-2 shrink-0">
                        <button @click="openModPackageImportDialog"
                          class="px-3 py-1.5 rounded-lg bg-bg-overlay/5 hover:bg-bg-overlay/10 border border-border-base/10 text-xs font-bold transition-all" >
                          导入模组包
                        </button>
                        <button @click="openCurrentProfileExportDialog"
                          class="px-4 py-1.5 rounded-lg bg-accent-special hover:bg-accent-special/85 text-on-accent-special text-xs font-black shadow-[0_0_15px_rgba(var(--rgb-accent-cool),0.2)] transition-all" >
                          导出环境模组
                        </button>
                      </div>
                    </div>
                    <div class="mt-4 grid grid-cols-3 gap-4 items-center">
                      <div class="col-span-1 text-xs text-text-dim">
                        当前环境：<span class="font-bold text-text-main">{{ profileStore.currentProfile?.name || '未激活' }}</span>
                      </div>
                      <CommonSelect class="col-span-1" label="Mod文件夹重命名" v-model="formData.bundle_mod_folder_name_type" showBottom mini
                        description="影响打包Mod时的文件夹名称，默认原文件夹名称，处理优先级是 别名>模组名>默认，或者 工坊>ID包名>默认，所以即使Mod没有别名，也能按模组原名创建文件夹。"
                        :options="[{label:'默认', value:'default'},{label:'按别名', value:'alias_name'},{label:'按原模组名', value:'name'},{label:'按工坊ID', value:'workshop_id'},{label:'按包名', value:'package_id'}]" />
                      <CommonNumber class="col-span-1" label="打包压缩级别" v-model="formData.bundle_compress_level" :step="1" :min="0" :max="9" mini
                        description="0 最快，9 最省空间。默认 6。压缩级别越高，导出越慢，但包体通常更小。"  />
                    </div>
                  </div>
                  <div class="p-6 rounded-2xl bg-accent-danger/5 border border-accent-danger/20 space-y-4">
                    <h4 class="text-sm font-bold text-accent-danger uppercase">危险操作区</h4>
                    <p class="text-xs text-accent-danger/60 leading-relaxed">修复会尝试恢复当前的本地数据。修复成功后需要重启软件才能生效；如果修复失败，建议直接重置数据库。重置会清空分组、备注等本地数据，且无法撤销，请确认后再继续。</p>
                    <div class="grid grid-cols-2 gap-3">
                      <button @click="handleRepair" :disabled="appStore.isLoading"
                        class="w-full py-2 bg-accent-warn/10 hover:bg-accent-warn text-accent-warn hover:text-text-main border border-accent-warn/30 rounded-lg text-xs font-bold transition-all disabled:cursor-not-allowed disabled:opacity-50" >
                        强制修复本地数据库
                      </button>
                      <button @click="handleReset" :disabled="appStore.isLoading"
                        class="w-full py-2 bg-accent-danger/10 hover:bg-accent-danger text-accent-danger hover:text-text-main border border-accent-danger/30 rounded-lg text-xs font-bold transition-all disabled:cursor-not-allowed disabled:opacity-50" >
                        立即重置本地数据库
                      </button>
                    </div>
                  </div>
                </div>
              </section>
</template>

<script setup>
import { LoaderCircle } from 'lucide-vue-next'
import CommonSwitch from '../../../shared/components/input/CommonSwitch.vue'
import CommonSelect from '../../../shared/components/input/CommonSelect.vue'
import CommonNumber from '../../../shared/components/input/CommonNumber.vue'
import { formatFileSize } from '../../../shared/lib/format'

defineProps({
  formData: { type: Object, required: true },
  appStore: { type: Object, required: true },
  profileStore: { type: Object, required: true },
  handleClearRemoteImageCache: { type: Function, required: true },
  openDataBundleImportDialog: { type: Function, required: true },
  openDataBundleModal: { type: Function, required: true },
  openModPackageImportDialog: { type: Function, required: true },
  openCurrentProfileExportDialog: { type: Function, required: true },
  handleRepair: { type: Function, required: true },
  handleReset: { type: Function, required: true },
})
</script>
