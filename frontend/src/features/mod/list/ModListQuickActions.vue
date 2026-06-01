<template>
  <div class="absolute bottom-2 right-2 flex items-center justify-end gap-2"
    :data-tour="listId === 'active' ? 'list-quick-actions' : null">
    <button v-if="listId === 'active' && (missingInstallSummary.dangerTotal > 0 || missingInstallSummary.warnTotal > 0 || missingInstallSummary.unknownTotal > 0)"
      @click="openMissingInstallDialog"
      v-tooltip="missingInstallTooltip"
      class="px-1 py-1 rounded-md transition-all"
      :class="missingInstallButtonClass">
      <Download />
    </button>
    <button v-if="listId === 'active' && supplementSummary.visibleCount > 0"
      @click="openSupplementDialog"
      v-tooltip="supplementTooltip"
      class="px-1 py-1 rounded-md transition-all"
      :class="supplementButtonClass">
      <Megaphone />
    </button>
    <button v-if="invalidModsToRemove.length > 0"
      @click="removeInvalidMod"
      v-tooltip="`^^一键移除共计 ${invalidModsToRemove.length} 个无效Mod^^`"
      class="px-1 py-1 bg-accent-danger/80 text-text-disabled rounded-md hover:bg-accent-danger hover:text-text-main transition-all">
      <Trash2 />
    </button>
  </div>
</template>

<script setup>
import { Download, Megaphone, Trash2 } from 'lucide-vue-next'

defineProps({
  listId: { type: String, required: true },
  missingInstallSummary: { type: Object, required: true },
  missingInstallTooltip: { type: String, required: true },
  missingInstallButtonClass: { type: String, required: true },
  supplementSummary: { type: Object, required: true },
  supplementTooltip: { type: String, required: true },
  supplementButtonClass: { type: String, required: true },
  invalidModsToRemove: { type: Array, required: true },
  openMissingInstallDialog: { type: Function, required: true },
  openSupplementDialog: { type: Function, required: true },
  removeInvalidMod: { type: Function, required: true },
})
</script>
