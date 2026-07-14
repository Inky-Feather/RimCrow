<template>
  <div v-tooltip="item.tooltip || t('tooltip.context_menu.color_custom', '自定义颜色')"
    class="context-color-picker relative flex items-center justify-center aspect-square w-[33px] rounded-md border border-border-base/10 bg-bg-overlay/5 hover:border-border-base/18 hover:bg-bg-overlay/10 transition-all duration-200"
    @click.stop @mousedown.stop>
    <!-- 弹层挂到 body，避免被子菜单滚动容器裁剪。父菜单关闭保护在 ContextMenuItem 里处理。 -->
    <ColorPicker v-model:pureColor="item.color" @pureColorChange="handleColorChange"
      :picker-container="pickerContainer || 'body'" :z-index="100020" format="hex" picker-type="fk" disable-alpha round-history />
  </div>
</template>

<script setup>
import { defineAsyncComponent } from 'vue'
import { t } from '../../i18n.js'

const ColorPicker = defineAsyncComponent(async () => {
  await import('vue3-colorpicker/style.css')
  const module = await import('vue3-colorpicker')
  return module.ColorPicker
})

const props = defineProps({
  item: { type: Object, required: true },
  pickerContainer: { type: [Object, String], default: 'body' }
})

const handleColorChange = (color) => {
  if (props.item.disabled || !props.item.action) return
  props.item.action(color)
}
</script>

<style scoped>
/* 菜单里的取色器只保留“方块触发器”外观，完整面板仍然使用库默认样式。 */
.context-color-picker :deep(.vc-color-wrap) {
  width: 100%;
  height: 100%;
  margin-right: 0;
  border-radius: 0.375rem;
  box-shadow: none;
  display: block;
}

/* 库默认触发器是 50x24 的长条，这里强制铺满菜单色块尺寸。 */
.context-color-picker :deep(.vc-color-wrap .current-color) {
  width: 100%;
  height: 100%;
  border-radius: inherit;
}

.context-color-picker :deep(.vc-color-wrap.transparent) {
  background-image: none;
}
</style>
