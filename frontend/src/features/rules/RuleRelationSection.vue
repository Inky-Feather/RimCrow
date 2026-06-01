<template>
  <div class="min-h-20 m-1 pb-2 rounded-lg relative transition-colors duration-200" :class="`bg-accent-${color}/10`">
    <div class="sticky top-0 z-30 px-2 py-1 text-sm font-bold backdrop-blur-2xl text-text-main rounded-t-lg" :class="`bg-accent-${color}/50`">
      {{ title }}
    </div>

    <div class="flex items-center text-xs text-text-dim px-2 py-1 gap-1">
      <div class="w-1 h-1 rounded-full bg-accent-tip shadow-[0_0_8px_var(--color-accent-tip)]"></div>
      <span class="text-accent-tip">原始规则 ({{ nativeRules.length || 0 }})</span>
      <div class="flex-1 h-px border-b border-accent-tip/30"></div>
    </div>
    <div class="px-2 relative">
      <div class="absolute top-0 left-0 h-full w-full bg-accent-tip/20 blur-lg"></div>
      <ModItem v-for="(mod, index) in nativeRules" :key="mod.package_id" :item_id="mod.package_id" :index="index" simple :showIndex="false" />
    </div>

    <div class="flex items-center text-xs text-text-dim px-2 py-1 gap-1">
      <div class="w-1 h-1 rounded-full bg-accent-cool shadow-[0_0_8px_var(--color-accent-cool)]"></div>
      <span class="text-accent-cool">社区规则 ({{ Object.keys(communityRules).length || 0 }})</span>
      <div class="flex-1 h-px border-b border-accent-cool/30"></div>
    </div>
    <div class="px-2 relative">
      <div class="absolute top-0 left-0 h-full w-full bg-accent-cool/20 blur-lg"></div>
      <div class="relative" v-for="(value, modId) in communityRules" :key="modId">
        <ModItem :item_id="modId" :index="0" simple :showIndex="false" list-color="cool" />
        <div v-if="formatRuleComment(value)" v-tooltip="formatRuleComment(value)" class="absolute right-2 top-0 h-full flex items-center justify-center">
          <svg class="w-5 h-5 opacity-50 text-accent-cool hover:text-text-main" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/></svg>
        </div>
      </div>
    </div>

    <template v-if="showWorkshop">
      <div class="flex items-center text-xs text-text-dim px-2 py-1 gap-1">
        <div class="w-1 h-1 rounded-full bg-accent-warning shadow-[0_0_8px_var(--color-accent-warning)]"></div>
        <span class="text-accent-warning">工坊规则 ({{ Object.keys(workshopRules).length || 0 }})</span>
        <div class="flex-1 h-px border-b border-accent-warning/30"></div>
      </div>
      <div class="px-2 relative">
        <div class="absolute top-0 left-0 h-full w-full bg-accent-warning/20 blur-lg"></div>
        <div class="relative" v-for="(value, modId) in workshopRules" :key="modId">
          <ModItem :item_id="modId" :index="0" simple :showIndex="false" list-color="warning" />
          <div v-if="formatRuleComment(value)" v-tooltip="formatRuleComment(value)" class="absolute right-2 top-0 h-full flex items-center justify-center">
            <svg class="w-5 h-5 opacity-50 text-accent-warning hover:text-text-main" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/></svg>
          </div>
        </div>
      </div>
    </template>

    <div class="flex items-center text-xs text-text-dim px-2 py-1 gap-1">
      <div class="w-1 h-1 rounded-full bg-accent-special shadow-[0_0_8px_var(--color-accent-special)]"></div>
      <span class="text-accent-special">用户规则 ({{ userRules.length || 0 }})</span>
      <div class="flex-1 h-px border-b border-accent-special/30"></div>
    </div>
    <div class="px-2 min-h-15 relative">
      <div class="absolute top-0 left-0 h-full w-full bg-accent-special/20 blur-lg select-none pointer-events-none"></div>
      <div v-show="userRules.length === 0" class="absolute flex rounded-lg top-0 bottom-0 left-0 right-0 m-1 items-center justify-center border-2 border-dashed text-text-dim text-xs select-none pointer-events-none">
        可拖拽模组到此
        <!-- 点阵背景 -->
        <div class="absolute inset-0 opacity-[0.05] pointer-events-none" style="background-image: radial-gradient(var(--color-text-main) 1px, transparent 1px); background-size: 20px 20px;"></div>
      </div>

      <SimpleDropList :model-value="userRules" dataKey="id" class="h-full min-h-15"
        :disabled="disabled"
        :group="{ name: 'rules', pull:false, put:['mods'], revertDrag: true }"
        @drop="$emit('drop', $event, ruleType)">
        <template v-slot:item="{ record, index, dataKey }">
          <div class="relative group">
            <ModItem :item_id="dataKey" :index="index" :key="dataKey" :show-index="false" :simple="true"></ModItem>
            <div class="absolute right-1 top-1/2 -translate-y-1/2 mr-1 overflow-visible gap-1 group text-sm font-medium flex flex-row-reverse items-center rtl:space-x-reverse">
              <button @click.stop="$emit('edit-comment', ruleType, dataKey, $event)" class="group z-50 h-5 px-2.5 relative rounded-md whitespace-nowrap cursor-pointer
                inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300
                text-text-dim bg-accent-primary/10
                hover:bg-accent-primary/60 hover:text-text-main hover:scale-110 active:scale-100
                group-hover:bg-accent-primary/40 group-hover:text-text-dim group-hover:shadow-2xl/20"
                v-tooltip="record.comment || '[[__点击添加说明__]]'">
                <span class="relative transition duration-300 only:-mx-6">
                  <svg class="size-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/></svg>
                </span>
              </button>
              <button @click.stop="$emit('remove-user-rule', ruleType, dataKey)" class="w-0 h-0 px-1 translate-x-3 opacity-0 overflow-hidden rounded-md whitespace-nowrap cursor-pointer
                inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300
                text-text-dim bg-accent-danger/10
                hover:bg-accent-danger/60 hover:text-text-main hover:scale-110 active:scale-100
                group-hover:bg-accent-danger/40 group-hover:text-text-dim group-hover:shadow-2xl/20
                group-hover:h-5 group-hover:w-5 group-hover:translate-x-0 group-hover:opacity-100"
                v-tooltip="'移除'">
                <span class="relative only:-mx-5">
                  <svg class="size-4" xmlns="http://www.w3.org/2000/svg"viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><circle cx="12" cy="12" r="10"/><path d="M8 12h8"/></svg>
                </span>
              </button>
            </div>
          </div>
        </template>
      </SimpleDropList>
    </div>
  </div>
</template>

<script setup>
import ModItem from '../mod/ModItem.vue'
import SimpleDropList from '../../shared/components/list/SimpleDropList.vue'

defineProps({
  title: { type: String, required: true },
  ruleType: { type: String, required: true },
  color: { type: String, default: 'primary' },
  nativeRules: { type: Array, default: () => [] },
  communityRules: { type: Object, default: () => ({}) },
  workshopRules: { type: Object, default: () => ({}) },
  showWorkshop: { type: Boolean, default: false },
  userRules: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
})

defineEmits(['drop', 'edit-comment', 'remove-user-rule'])

const formatRuleComment = (info) => {
  if (!info?.comment) return null
  return Array.isArray(info.comment) ? info.comment.join('\n') : info.comment
}
</script>
