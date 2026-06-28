<template>
  <div class="flex flex-col h-full bg-bg-surface/40 backdrop-blur-sm shadow-2xl"
    :class="`border-2 rounded-2xl border-accent-${listColor}/20`">
    <!-- 标题栏 -->
    <div :class="`px-3 h-8 border-b rounded-t-2xl border-text-main/5 flex justify-between items-center bg-accent-${listColor}/10`">
      <span :class="`text-sm font-bold text-accent-${listColor} uppercase tracking-wider flex items-center gap-2`">
        <div :class="`w-1.5 h-1.5 rounded-full bg-accent-${listColor} shadow-[0_0_8px_var(--color-accent-${listColor})]`"></div>
        {{ title }}
      </span>
      <button @click="ruleStore.currentId = null" class="text-xs font-bold text-text-dim/60 hover:text-text-dim transition-colors">关闭</button>
    </div>
    <!-- 当前选中的MOD -->
    <div class="px-2 py-2 w-full flex items-center gap-2 shadow-xl/10">
      <div class="w-13 h-13 shrink-0 rounded-lg bg-black/40 border border-text-main/30 flex items-center justify-center overflow-hidden shadow-lg">
        <img v-if="targetMod?.thumb_url" :src="targetMod.thumb_url" class="w-full h-full object-cover">
        <span v-else class="text-xs text-text-dim font-bold font-mono">MOD</span>
      </div>
      <div class="flex-1 truncate">
        <div class="font-bold text-text-main truncate">{{ modStore.displayModName(targetMod) }}</div>
        <div class="text-xs font-mono text-text-dim/60 truncate">{{ targetMod?.package_id }}</div>
      </div>
    </div>

    <!-- 列表区 -->
    <div class="overflow-y-auto flex-1 pb-0.5 after:pointer-events-none 
        after:content-[''] after:absolute after:bottom-0 after:w-full after:h-10 
        after:bg-linear-to-t after:from-bg-deep/80 after:to-transparent">

        <!-- 前置 -->
        <div class="min-h-20 m-1 pb-2 bg-accent-warn/10 rounded-lg relative">
          <div class="sticky top-0 z-30 px-2 py-1 text-sm font-bold bg-accent-warn/50 backdrop-blur-2xl text-text-main rounded-t-lg">前置</div>
          
          <div class="flex items-center text-xs text-text-dim px-2 py-1 gap-1">
            <div class="w-1 h-1 rounded-full bg-accent-tip shadow-[0_0_8px_var(--color-accent-tip)]"></div>
            <span class="text-accent-tip">原始规则 ({{ getNativeRules('loadAfter').length }})</span>
            <div class="flex-1 h-px border-b border-accent-tip/30"></div>
          </div>
          <div class="px-2 relative">
            <div class=" absolute top-0 left-0 h-full w-full bg-accent-tip/20 blur-lg"></div>
            <ModItem v-for="modId,index in getNativeRules('loadAfter')" :key="modId" :item_id="modId" :index="index" simple :showIndex="false" />
          </div>

          <div class="flex items-center text-xs text-text-dim px-2 py-1 gap-1">
            <div class="w-1 h-1 rounded-full bg-accent-cool shadow-[0_0_8px_var(--color-accent-cool)]"></div>
            <span class="text-accent-cool">社区规则 ({{ Object.keys(getCommunityRules('loadAfter')).length||0 }})</span>
            <div class="flex-1 h-px border-b border-accent-cool/30"></div>
          </div>
          <div class="px-2 relative">
            <div class="absolute top-0 left-0 h-full w-full bg-accent-cool/20 blur-lg"></div>
            <div class="relative" v-for="(value, modId) in getCommunityRules('loadAfter')">
              <ModItem :key="modId" :item_id="modId" :index="0" simple :showIndex="false" list-color="cool" />
              <div v-if="value.comment" v-tooltip="formatCommTooltip(value)" class="absolute right-2 top-0 h-full flex items-center justify-center">
                <svg class="w-5 h-5 opacity-50 text-accent-cool hover:text-text-main" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/></svg>
              </div>
            </div>
          </div>

          <div class="flex items-center text-xs text-text-dim px-2 py-1 gap-1">
            <div class="w-1 h-1 rounded-full bg-accent-special shadow-[0_0_8px_var(--color-accent-special)]"></div>
            <span class="text-accent-special">用户规则 ({{ userAfterRules.length }})</span>
            <div class="flex-1 h-px border-b border-accent-special/30"></div>
          </div>
          <div class="px-2 min-h-15 relative">
            <div class="absolute top-0 left-0 h-full w-full bg-accent-special/20 blur-lg select-none pointer-events-none"></div>
            <div v-show="userAfterRules.length === 0" class="absolute flex rounded-lg top-0 bottom-0 left-0 right-0 m-1 items-center justify-center border-2 border-dashed text-text-dim text-xs select-none pointer-events-none">
              可拖拽模组到此
              <!-- 点阵背景 -->
              <div class="absolute inset-0 opacity-[0.05] pointer-events-none" style="background-image: radial-gradient(#fff 1px, transparent 1px); background-size: 20px 20px;"></div>
            </div>

            <VirtualList v-model="userAfterRules" dataKey="id" :keeps="50" class="h-full min-h-15" handle="0"
              placeholderClass="ghost" wrapClass="" :fallbackOnBody="true" :appendToBody="true" :scrollSpeed="{ x: 0, y: 10 }"
              :sortable="false" :size="itemHeight" :delay="appStore.settings.ui.drag_delay"
              :group="{ name: '00', pull:false, put:['mods'], revertDrag: true }" :animation="150"
              @drop="onDrop($event,'loadAfter')">
              <template v-slot:item="{ record, index, dataKey }">
                <div class="relative group">
                  <ModItem :item_id="dataKey" :index="index" :key="dataKey":show-index="false" :simple="true"></ModItem>
                  <div class="absolute right-1 top-1/2 -translate-y-1/2 mr-1 overflow-visible gap-1 group text-sm font-medium flex flex-row-reverse items-center rtl:space-x-reverse">
                    <button @click.stop="addRuleComm('loadAfter', dataKey, $event)" class="group z-50 h-5 px-2.5 relative rounded-md whitespace-nowrap cursor-pointer 
                      inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300 
                      text-text-dim/70 bg-accent-primary/10 
                      hover:bg-accent-primary/60 hover:text-text-main hover:scale-110 active:scale-100 
                      group-hover:bg-accent-primary/40 group-hover:text-text-dim group-hover:shadow-2xl/20"
                      v-tooltip="record.comment || '[[__点击添加说明__]]'">
                      <span class="relative transition duration-300 only:-mx-6">
                        <svg class="size-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/></svg>
                      </span>
                    </button>
                    <button @click.stop="removeUserRule('loadAfter', dataKey)" class="w-0 h-0 px-1 translate-x-3 opacity-0 overflow-hidden rounded-md whitespace-nowrap cursor-pointer 
                      inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300 
                      text-text-dim/70 bg-accent-danger/10 
                      hover:bg-accent-danger/60 hover:text-text-main hover:scale-110 active:scale-100
                      group-hover:bg-accent-danger/40 group-hover:text-text-dim group-hover:shadow-2xl/20
                      group-hover:h-5 group-hover:w-5 group-hover:translate-x-0 group-hover:opacity-100"
                      v-tooltip="'移除'">
                      <span class="relative only:-mx-5">
                        <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><circle cx="12" cy="12" r="10"/><path d="M8 12h8"/></svg>
                      </span>
                    </button>
                  </div>

                </div>
              </template>
            </VirtualList>
          </div>

        </div>

        <!-- 后置 -->
        <div class="min-h-20 m-1 pb-2 bg-accent-primary/10 rounded-lg relative">
          <div class="sticky top-0 z-30 px-2 py-1 text-sm font-bold bg-accent-primary/50 backdrop-blur-2xl text-text-main rounded-t-lg">后置</div>
          
          <div class="flex items-center text-xs text-text-dim px-2 py-1 gap-1">
            <div class="w-1 h-1 rounded-full bg-accent-tip shadow-[0_0_8px_var(--color-accent-tip)]"></div>
            <span class="text-accent-tip">原始规则 ({{ getNativeRules('loadBefore').length||0 }})</span>
            <div class="flex-1 h-px border-b border-accent-tip/30"></div>
          </div>
          <div class="px-2 relative">
            <div class=" absolute top-0 left-0 h-full w-full bg-accent-tip/20 blur-lg"></div>
            <ModItem v-for="modId,index in getNativeRules('loadBefore')" :key="modId" :item_id="modId" :index="index" simple :showIndex="false" />
          </div>

          <div class="flex items-center text-xs text-text-dim px-2 py-1 gap-1">
            <div class="w-1 h-1 rounded-full bg-accent-cool shadow-[0_0_8px_var(--color-accent-cool)]"></div>
            <span class="text-accent-cool">社区规则 ({{ Object.keys(getCommunityRules('loadBefore')).length||0 }})</span>
            <div class="flex-1 h-px border-b border-accent-cool/30"></div>
          </div>
          <div class="px-2 relative">
            <div class="absolute top-0 left-0 h-full w-full bg-accent-cool/20 blur-lg"></div>
            <div class="relative" v-for="(value, modId) in getCommunityRules('loadBefore')">
              <ModItem :key="modId" :item_id="modId" :index="0" simple :showIndex="false" list-color="cool" />
              <div v-if="value.comment" v-tooltip="formatCommTooltip(value)" class="absolute right-2 top-0 h-full flex items-center justify-center">
                <svg class="w-5 h-5 opacity-50 text-accent-cool hover:text-text-main" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/></svg>
              </div>
            </div>
          </div>

          <div class="flex items-center text-xs text-text-dim px-2 py-1 gap-1">
            <div class="w-1 h-1 rounded-full bg-accent-special shadow-[0_0_8px_var(--color-accent-special)]"></div>
            <span class="text-accent-special">用户规则 ({{ userBeforeRules.length||0 }})</span>
            <div class="flex-1 h-px border-b border-accent-special/30"></div>
          </div>
          <div class="px-2 min-h-15 relative">
            <div class="absolute top-0 left-0 h-full w-full bg-accent-special/20 blur-lg select-none pointer-events-none"></div>
            <div v-show="userBeforeRules.length === 0" class="absolute flex rounded-lg top-0 bottom-0 left-0 right-0 m-1 items-center justify-center border-2 border-dashed text-text-dim text-xs select-none pointer-events-none">
              可拖拽模组到此
              <!-- 点阵背景 -->
              <div class="absolute inset-0 opacity-[0.05] pointer-events-none" style="background-image: radial-gradient(#fff 1px, transparent 1px); background-size: 20px 20px;"></div>
            </div>

            <VirtualList v-model="userBeforeRules" dataKey="id" :keeps="50" class="h-full min-h-15" handle="0"
              placeholderClass="ghost" wrapClass="" :fallbackOnBody="true" :appendToBody="true" :scrollSpeed="{ x: 0, y: 10 }"
              :sortable="false" :size="itemHeight" :delay="appStore.settings.ui.drag_delay"
              :group="{ name: '00', pull:false, put:['mods'], revertDrag: true }" :animation="150"
              @drop="onDrop($event,'loadBefore')">
              <template v-slot:item="{ record, index, dataKey }">
                <div class="relative group">
                  <ModItem :item_id="dataKey" :index="index" :key="dataKey":show-index="false" :simple="true"></ModItem>
                  <div class="absolute right-1 top-1/2 -translate-y-1/2 mr-1 overflow-visible gap-1 group text-sm font-medium flex flex-row-reverse items-center rtl:space-x-reverse">
                    <button @click.stop="addRuleComm('loadBefore', dataKey, $event)" class="group z-50 h-5 px-2.5 relative rounded-md whitespace-nowrap cursor-pointer 
                      inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300 
                      text-text-dim/70 bg-accent-primary/10 
                      hover:bg-accent-primary/60 hover:text-text-main hover:scale-110 active:scale-100 
                      group-hover:bg-accent-primary/40 group-hover:text-text-dim group-hover:shadow-2xl/20"
                      v-tooltip="record.comment || '[[__点击添加说明__]]'">
                      <span class="relative transition duration-300 only:-mx-6">
                        <svg class="size-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/></svg>
                      </span>
                    </button>
                    <button @click.stop="removeUserRule('loadBefore', dataKey)" class="w-0 h-0 px-1 translate-x-3 opacity-0 overflow-hidden rounded-md whitespace-nowrap cursor-pointer 
                      inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300 
                      text-text-dim/70 bg-accent-danger/10 
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
            </VirtualList>
          </div>

        </div>

        <!-- 冲突 -->
        <div class="min-h-20 m-1 pb-2 bg-accent-danger/10 rounded-lg relative">
          <div class="sticky top-0 z-30 px-2 py-1 text-sm font-bold bg-accent-danger/50 backdrop-blur-2xl text-text-main rounded-t-lg">冲突</div>
          
          <div class="flex items-center text-xs text-text-dim px-2 py-1 gap-1">
            <div class="w-1 h-1 rounded-full bg-accent-tip shadow-[0_0_8px_var(--color-accent-tip)]"></div>
            <span class="text-accent-tip">原始规则 ({{ getNativeRules('incompatibleWith').length||0 }})</span>
            <div class="flex-1 h-px border-b border-accent-tip/30"></div>
          </div>
          <div class="px-2 relative">
            <div class=" absolute top-0 left-0 h-full w-full bg-accent-tip/20 blur-lg"></div>
            <ModItem v-for="modId,index in getNativeRules('incompatibleWith')" :key="modId" :item_id="modId" :index="index" simple :showIndex="false" />
          </div>

          <div class="flex items-center text-xs text-text-dim px-2 py-1 gap-1">
            <div class="w-1 h-1 rounded-full bg-accent-cool shadow-[0_0_8px_var(--color-accent-cool)]"></div>
            <span class="text-accent-cool">社区规则 ({{ Object.keys(getCommunityRules('incompatibleWith')).length||0 }})</span>
            <div class="flex-1 h-px border-b border-accent-cool/30"></div>
          </div>
          <div class="px-2 relative">
            <div class="absolute top-0 left-0 h-full w-full bg-accent-cool/20 blur-lg"></div>
            <div class="relative" v-for="(value, modId) in getCommunityRules('incompatibleWith')">
              <ModItem :key="modId" :item_id="modId" :index="0" simple :showIndex="false" list-color="cool" />
              <div v-if="value.comment" v-tooltip="formatCommTooltip(value)" class="absolute right-2 top-0 h-full flex items-center justify-center">
                <svg class="w-5 h-5 opacity-50 text-accent-cool hover:text-text-main" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/></svg>
              </div>
            </div>
          </div>

          <div class="flex items-center text-xs text-text-dim px-2 py-1 gap-1">
            <div class="w-1 h-1 rounded-full bg-accent-special shadow-[0_0_8px_var(--color-accent-special)]"></div>
            <span class="text-accent-special">用户规则 ({{ userIncompatibleWithRules.length||0 }})</span>
            <div class="flex-1 h-px border-b border-accent-special/30"></div>
          </div>
          <div class="px-2 min-h-15 relative">
            <div class="absolute top-0 left-0 h-full w-full bg-accent-special/20 blur-lg select-none pointer-events-none"></div>
            <div v-show="userIncompatibleWithRules.length === 0" class="absolute flex rounded-lg top-0 bottom-0 left-0 right-0 m-1 items-center justify-center border-2 border-dashed text-text-dim text-xs select-none pointer-events-none">
              可拖拽模组到此
              <!-- 点阵背景 -->
              <div class="absolute inset-0 opacity-[0.05] pointer-events-none" style="background-image: radial-gradient(#fff 1px, transparent 1px); background-size: 20px 20px;"></div>
            </div>

            <VirtualList v-model="userIncompatibleWithRules" dataKey="id" :keeps="50" class="h-full min-h-15" handle="0"
              placeholderClass="ghost" wrapClass="" :fallbackOnBody="true" :appendToBody="true" :scrollSpeed="{ x: 0, y: 10 }"
              :sortable="false" :size="itemHeight" :delay="appStore.settings.ui.drag_delay"
              :group="{ name: '00', pull:false, put:['mods'], revertDrag: true }" :animation="150"
              @drop="onDrop($event,'incompatibleWith')">
              <template v-slot:item="{ record, index, dataKey }">
                <div class="relative group">
                  <ModItem :item_id="dataKey" :index="index" :key="dataKey":show-index="false" :simple="true"></ModItem>
                  <!-- 操作按钮 -->
                  <div class="absolute right-1 top-1/2 -translate-y-1/2 mr-1 overflow-visible gap-1 group text-sm font-medium flex flex-row-reverse items-center rtl:space-x-reverse">
                    <button @click.stop="addRuleComm('incompatibleWith', dataKey, $event)" class="group z-50 h-5 px-2.5 relative rounded-md whitespace-nowrap cursor-pointer 
                      inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300 
                      text-text-dim/70 bg-accent-primary/10 
                      hover:bg-accent-primary/60 hover:text-text-main hover:scale-110 active:scale-100 
                      group-hover:bg-accent-primary/40 group-hover:text-text-dim group-hover:shadow-2xl/20"
                      v-tooltip="record.comment || '[[__点击添加说明__]]'">
                      <span class="relative transition duration-300 only:-mx-6">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"/></svg>
                      </span>
                    </button>
                    <button @click.stop="removeUserRule('incompatibleWith', dataKey)" class="w-0 h-0 px-1 translate-x-3 opacity-0 overflow-hidden rounded-md whitespace-nowrap cursor-pointer 
                      inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300 
                      text-text-dim/70 bg-accent-danger/10 
                      hover:bg-accent-danger/60 hover:text-text-main hover:scale-110 active:scale-100
                      group-hover:bg-accent-danger/40 group-hover:text-text-dim group-hover:shadow-2xl/20
                      group-hover:h-5 group-hover:w-5 group-hover:translate-x-0 group-hover:opacity-100"
                      v-tooltip="'移除'">
                      <span class="relative only:-mx-5">
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-circle-minus-icon lucide-circle-minus"><circle cx="12" cy="12" r="10"/><path d="M8 12h8"/></svg>
                      </span>
                    </button>
                  </div>

                </div>
              </template>
            </VirtualList>
          </div>

        </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useModStore } from '../stores/modStore'
import { useRuleStore } from '../stores/ruleStore'
import { useConfirmStore } from '../stores/confirmStore'

import ModItem from './utils/ModItem.vue'
import VirtualList from 'vue-virtual-sortable';
import { useAppStore } from '../stores/appStore'

// 这里 modelValue 接收纯 ID 数组
const props = defineProps({
  title: { type: String, default: 'Rule' },
  listColor: { type: String, default: 'primary' } // danger/highlight/special/cool/primary/success/tip/warn/secondary/warning
})

const appStore = useAppStore()
const modStore = useModStore()
const ruleStore = useRuleStore()
const confirmStore = useConfirmStore()


const itemHeight = computed(() => appStore.scalePx(30)+4 )
const userAfterRules = computed({ get() { return getUserRules('loadAfter') }, set(val) {} })
const userBeforeRules = computed({ get() { return getUserRules('loadBefore') }, set(val) {} })
const userIncompatibleWithRules = computed({ get() { return getUserRules('incompatibleWith') }, set(val) {} })


// const targetMod = ref(null)
// watch(() => ruleStore.currentId, (newId) => {
//   if (newId) {
//     // 当选择的 Mod 变化时，更新显示的规则
//     targetMod.value = modStore.takeModById(newId)
//   }
// })

const targetMod = computed(() => modStore.takeModById(ruleStore.currentId))

// 1. Native
const getNativeRules = (type) => {
  if (!targetMod.value) return []
  if (type === 'loadAfter') return targetMod.value.load_after_mods || []
  if (type === 'loadBefore') return targetMod.value.load_before_mods || []
  if (type === 'incompatibleWith') return targetMod.value.incompatible_mods || []
  return []
}
// 2. Community
const getCommunityRules = (type) => {
  const rules = ruleStore.communityModRules[targetMod.value?.package_id]
  if (!rules || !rules[type]) return []
  return rules[type]
}
// 3. User
const getUserRules = (type) => {
  const rules = ruleStore.userModRules[targetMod.value?.package_id]
  if (!rules || !rules[type]) return []
  const userRules = Object.entries(rules[type]).map(([modId, info]) => {
    return {
      id: modId,
      comment: formatCommTooltip(info)
    }
  })
  return userRules
}
// 格式化注释为 Tooltip 格式
const formatCommTooltip = (info) => {
  if (!info.comment) return null
  return Array.isArray(info.comment) ? info.comment.join('\n') : info.comment
}
// 移除用户规则
const removeUserRule = async (ruleType, otherId) => {
  await ruleStore.removeUserModRuleItem(targetMod.value?.package_id, ruleType, otherId)
}
// 添加说明
const addRuleComm = async (ruleType, otherId, e) => {
  const comment = await confirmStore.open({
    title: '添加说明',
    placeholder: '请输入说明:',
    message: `为规则添加一段说明`,
    mode: 'prompt',
    type: 'info'
  }, e.target)
  // console.log(comment)
  if (!comment) return
  await ruleStore.updateComment(targetMod.value?.package_id, ruleType, otherId, comment)
}
// 从列表拖拽添加用户规则
const onDrop = async (e, ruleType) => {
  // console.log("更新子项排序:", e)
  const sourceId = e.item.id
  if (!sourceId || sourceId === targetMod.value?.package_id) return
  // 调用 RuleStore 添加规则
  await ruleStore.addUserModRule(targetMod.value?.package_id, ruleType, sourceId)
}
</script>

<style scoped>

</style>