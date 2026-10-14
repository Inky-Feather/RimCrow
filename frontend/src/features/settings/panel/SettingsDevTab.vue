<template>
  <section class="animate-in fade-in slide-in-from-right-4">
    <h3 class="text-lg font-bold text-text-main mb-6">{{ t('ui.settings.dev.title', '开发与调试') }}</h3>
    <div class="grid grid-cols-2 gap-4">
      <CommonSwitch class="col-span-2" :label="t('ui.settings.dev.debug_mode', '调试模式')" v-model="formData.debug_mode" :description="t('ui.settings.dev.debug_mode_desc', '开启调试模式后重启软件将会出现开发者工具窗口，可查看问题详情。')" />
      <CommonSwitch class="col-span-2" :label="t('ui.settings.dev.browser_mode', '浏览器模式启动')" v-model="formData.browser_mode" :description="t('ui.settings.dev.browser_mode_desc', '默认仍使用内置 WebView。开启后，无启动参数时将改为在本机浏览器中启动；关闭浏览器主页面后程序会自动退出。')" />
      <div class="modal-section col-span-2 p-2">
        <CommonSwitch class="mb-2" :label="t('ui.settings.dev.auto_enter_silent_mode', '自动进入静默模式')" v-model="formData.auto_enter_silent_mode" mini :description="t('ui.settings.dev.auto_enter_silent_mode_desc', '开启后，检测到 RimWorld 运行时会自动切换到静默模式；关闭后仅保留手动进入能力。')" />
        <div class="grid grid-cols-3 items-center">
          <p class="col-span-2 text-xs ml-1 leading-relaxed text-text-dim">
            {{ t('ui.settings.dev.silent_mode_help', '游戏运行时可切到更轻量的界面，减少资源占用，并可直接查看游戏日志。') }}
          </p>
          <CommonSelect class="col-span-1 mr-2" :label="t('ui.settings.dev.default_silent_page', '默认页面')" mini v-model="formData.silent_mode_default_view"
            :options="silentModeViewOptions"
            :description="t('ui.settings.dev.default_silent_page_desc', '控制自动进入静默模式时，默认先显示主页还是直接进入日志页。')"
          />
        </div>
      </div>
      <CommonSelect :label="t('ui.settings.dev.log_level', '日志等级')" v-model="formData.log_level" :options="logLevelOptions" />
      <CommonNumber :label="t('ui.settings.dev.log_retention_days', '日志保留天数')" v-model="formData.log_retention_days" :step="1" :min="0" :max="365" />
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import CommonSwitch from '../../../shared/components/input/CommonSwitch.vue'
import CommonSelect from '../../../shared/components/input/CommonSelect.vue'
import CommonNumber from '../../../shared/components/input/CommonNumber.vue'
import { t } from '../../../shared/i18n.js'

defineProps({ formData: { type: Object, required: true } })

const silentModeViewOptions = computed(() => [
  { label: t('ui.settings.dev.silent_view.home', '静默主页'), value: 'home' },
  { label: t('ui.settings.dev.silent_view.logs', '游戏日志'), value: 'logs' },
])
const logLevelOptions = [
  { label: 'DEBUG', value: 'DEBUG' },
  { label: 'INFO', value: 'INFO' },
  { label: 'WARNING', value: 'WARNING' },
]
</script>
