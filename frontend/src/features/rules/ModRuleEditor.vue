<template>
  <div class="flex flex-col h-full bg-bg-surface/40 backdrop-blur-sm shadow-2xl"
    :class="`border-2 rounded-2xl border-accent-${listColor}/20`">
    <!-- 标题栏 -->
    <div :class="`px-3 h-8 border-b rounded-t-2xl border-border-base/5 flex justify-between items-center bg-accent-${listColor}/10`">
      <span :class="`text-sm font-bold text-accent-${listColor} uppercase tracking-wider flex items-center gap-2`">
        <div :class="`w-1.5 h-1.5 rounded-full bg-accent-${listColor} shadow-[0_0_8px_var(--color-accent-${listColor})]`"></div>
        {{ title }}
      </span>
      <button @click="ruleStore.currentId = null" class="text-xs font-bold text-text-disabled hover:text-text-dim transition-colors">关闭</button>
    </div>
    <!-- 当前选中的MOD -->
    <div class="px-2 py-2 w-full flex items-center gap-2 shadow-xl/10">
      <div class="w-13 h-13 shrink-0 rounded-lg bg-bg-inset/80 border border-border-base/18 flex items-center justify-center overflow-hidden shadow-lg">
        <img v-if="targetMod?.preview_path" :src="appStore.getThumbUrl(targetMod.package_id, targetMod.preview_path)" class="w-full h-full object-cover">
        <span v-else class="text-xs text-text-dim font-bold font-mono">MOD</span>
      </div>
      <div class="flex-1 truncate">
        <div class="font-bold text-text-main truncate">{{ modStore.displayModName(targetMod) }}</div>
        <div class="text-xs font-mono text-text-disabled truncate">{{ targetMod?.package_id }}</div>
      </div>
    </div>

    <div class="px-1 pb-1">
      <!-- 绝对位置控制板 (Absolute Position) -->
      <div class="py-1 px-2 bg-bg-overlay/5 border border-border-base/10 rounded-lg flex flex-col items-center justify-center">
        <div class="flex items-center justify-between w-full">

          <span class="text-sm font-bold text-text-main flex items-center gap-2">
            加载位置
            <label v-tooltip="'强制让此 Mod 在启用列表中前置顶或置底。'" class="text-text-dim cursor-help italic underline hover:text-text-main">?</label>
            <span v-if="absPos.source === 'community'" class="text-[0.6rem] px-1.5 py-0.5 bg-accent-cool/20 text-accent-cool rounded border border-accent-cool/30">社区建议</span>
          </span>
          <!-- 开关组 (Segmented Control) -->
          <div class="flex items-center bg-bg-inset/80 rounded-lg p-1 border border-border-base/10 shadow-inner">
            <!-- 置顶 -->
            <button @click="handlePosChange('top')"
              class="px-1 py-1 text-xs font-bold rounded-md transition-all flex items-center gap-1"
              :class="absPos.pos === 'top' ? 'bg-accent-warn text-on-accent-warn shadow-lg' : 'text-text-dim hover:text-text-main'">
              <ArrowUpToLine class="size-3" /> 置顶
            </button>
            <!-- 默认 -->
            <button @click="handlePosChange('none')"
              class="px-1 py-1 text-xs font-bold rounded-md transition-all"
              :class="absPos.pos === 'none' ? 'bg-bg-overlay/10 text-text-main shadow-lg' : 'text-text-dim hover:text-text-main'">
              默认
            </button>
            <!-- 置底 -->
            <button @click="handlePosChange('bottom')"
              class="px-1 py-1 text-xs font-bold rounded-md transition-all flex items-center gap-1"
              :class="absPos.pos === 'bottom' ? 'bg-accent-primary text-on-accent-primary shadow-lg' : 'text-text-dim hover:text-text-main'">
              <ArrowDownToLine class="size-3" /> 置底
            </button>
          </div>
        </div>
        <span class="text-xs text-text-dim mt-0.5" v-if="absPos.comment">"{{ absPos.comment }}"</span>
      </div>
    </div>

    <!-- 列表区 -->
    <div class="overflow-y-auto flex-1 pb-0.5 after:pointer-events-none
      after:content-[''] after:absolute after:bottom-0 after:w-full after:h-10
      after:bg-linear-to-t after:from-bg-deep/80 after:to-transparent">

      <div v-if="isLanguagePackMod" class="min-h-20 m-1 pb-2 bg-accent-highlight/10 rounded-lg relative">
        <div class="sticky top-0 z-30 px-2 py-1 text-sm font-bold bg-accent-highlight/50 backdrop-blur-2xl text-text-main rounded-t-lg flex items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <span>语言包所属</span>
            <label v-tooltip="'默认分析所属来自后端统一判定。用户可以指定所属，右侧按钮切换覆盖或并入模式，开启覆盖后，用户指定所属将替代默认分析所属，关闭时则并入默认分析所属。'" class="text-text-dim cursor-help italic underline hover:text-text-main">?</label>
          </div>
          <label class="flex items-center gap-2 cursor-pointer select-none">
            <div class="relative">
              <input type="checkbox" class="sr-only peer" :checked="isLanguagePackOwnerReplaceEnabled" :disabled="!canToggleLanguagePackOwnerOverride"
                @change="toggleLanguagePackOwnerOverrideMode($event.target.checked)"
              >
              <div class="w-9 h-5 bg-bg-overlay/10 rounded-full transition-all after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-bg-contrast after:border-border-base/18 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-full peer-checked:after:border-bg-contrast peer-checked:bg-accent-special peer-disabled:opacity-40"></div>
            </div>
            <span class="text-xs font-bold text-text-dim">
              {{ isLanguagePackOwnerReplaceEnabled ? '覆盖默认分析' : '并入默认分析' }}
            </span>
          </label>
        </div>

        <div class="flex items-center text-xs text-text-dim px-2 py-1 gap-1">
          <div class="w-1 h-1 rounded-full bg-accent-tip shadow-[0_0_8px_var(--color-accent-tip)]"></div>
          <span class="text-accent-tip">默认分析所属 ({{ analyzedLanguagePackOwnerRows.length }})</span>
          <div class="flex-1 h-px border-b border-accent-tip/30"></div>
          <span class="text-[0.65rem] text-text-dim">{{ analyzedLanguagePackOwnerSummary }}</span>
        </div>
        <div class="px-2 relative">
          <div class="absolute top-0 left-0 h-full w-full bg-accent-tip/20 blur-lg pointer-events-none"></div>
          <div v-if="analyzedLanguagePackOwnerRows.length === 0" class="px-2 py-3 text-xs text-text-dim">
            当前未分析出可靠所属
          </div>
          <ModItem v-for="(owner, index) in analyzedLanguagePackOwnerRows" :key="owner.id" :item_id="owner.id" :index="index" simple :showIndex="false" />
        </div>

        <div class="flex items-center text-xs text-text-dim px-2 py-1 gap-1">
          <div class="w-1 h-1 rounded-full bg-accent-special shadow-[0_0_8px_var(--color-accent-special)]"></div>
          <span class="text-accent-special">用户指定所属 ({{ languagePackOwnerOverrideRows.length }})</span>
          <div class="flex-1 h-px border-b border-accent-special/30"></div>
        </div>
        <div class="px-2 min-h-15 relative">
          <div class="absolute top-0 left-0 h-full w-full bg-accent-special/20 blur-lg select-none pointer-events-none"></div>
          <div v-show="languagePackOwnerOverrideRows.length === 0" class="absolute flex rounded-lg top-0 bottom-0 left-0 right-0 m-1 items-center justify-center border-2 border-dashed text-text-dim text-xs select-none pointer-events-none">
            可拖拽模组到此
            <div class="absolute inset-0 opacity-[0.05] pointer-events-none" style="background-image: radial-gradient(var(--color-text-main) 1px, transparent 1px); background-size: 20px 20px;"></div>
          </div>

          <SimpleDropList :model-value="languagePackOwnerOverrideRows" dataKey="id" class="h-full min-h-15"
            :disabled="appStore.isLoading"
            :group="{ name: 'rules', pull:false, put:['mods'], revertDrag: true }"
            @drop="onDropLanguagePackOwner">
            <template v-slot:item="{ record, index, dataKey }">
              <div class="relative group">
                <ModItem :item_id="dataKey" :index="index" :key="dataKey" :show-index="false" :simple="true"></ModItem>
                <div class="absolute right-1 top-1/2 -translate-y-1/2 mr-1 overflow-visible gap-1 group text-sm font-medium flex flex-row-reverse items-center rtl:space-x-reverse">
                  <button @click.stop="removeLanguagePackOwner(dataKey)" class="w-0 h-0 px-1 translate-x-3 opacity-0 overflow-hidden rounded-md whitespace-nowrap cursor-pointer
                    inline-flex items-center self-center justify-center justify-self-center tracking-wide transition-all duration-300
                    text-text-dim bg-accent-danger/10
                    hover:bg-accent-danger/60 hover:text-text-main hover:scale-110 active:scale-100
                    group-hover:bg-accent-danger/40 group-hover:text-text-dim group-hover:shadow-2xl/20
                    group-hover:h-5 group-hover:w-5 group-hover:translate-x-0 group-hover:opacity-100"
                    v-tooltip="'移除'">
                    <span class="relative only:-mx-5">
                      <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M8 12h8"/></svg>
                    </span>
                  </button>
                </div>
              </div>
            </template>
          </SimpleDropList>
        </div>
      </div>

      <RuleRelationSection
        title="前置"
        rule-type="loadAfter"
        color="warn"
        :native-rules="getNativeRules('loadAfter')"
        :community-rules="getCommunityRules('loadAfter')"
        :workshop-rules="getWorkshopRules('loadAfter')"
        :show-workshop="true"
        :user-rules="userAfterRules"
        :disabled="appStore.isLoading"
        @drop="onDrop"
        @edit-comment="addRuleComm"
        @remove-user-rule="removeUserRule"
      />

      <RuleRelationSection
        title="后置"
        rule-type="loadBefore"
        color="primary"
        :native-rules="getNativeRules('loadBefore')"
        :community-rules="getCommunityRules('loadBefore')"
        :user-rules="userBeforeRules"
        :disabled="appStore.isLoading"
        @drop="onDrop"
        @edit-comment="addRuleComm"
        @remove-user-rule="removeUserRule"
      />

      <RuleRelationSection
        title="冲突"
        rule-type="incompatibleWith"
        color="danger"
        :native-rules="getNativeRules('incompatibleWith')"
        :community-rules="getCommunityRules('incompatibleWith')"
        :user-rules="userIncompatibleWithRules"
        :disabled="appStore.isLoading"
        @drop="onDrop"
        @edit-comment="addRuleComm"
        @remove-user-rule="removeUserRule"
      />

    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useModStore } from '../mod/stores/modStore'
import { useRuleStore } from './ruleStore'
import { useConfirmStore } from '../../shared/components/modal/confirmStore'
import { ArrowUpToLine, ArrowDownToLine } from 'lucide-vue-next'

import ModItem from '../mod/ModItem.vue'
import SimpleDropList from '../../shared/components/list/SimpleDropList.vue'
import RuleRelationSection from './RuleRelationSection.vue'
import { useAppStore } from '../../app/stores/appStore'

// 这里 modelValue 接收纯 ID 数组
const props = defineProps({
  title: { type: String, default: 'Rule' },
  listColor: { type: String, default: 'primary' } // danger/highlight/special/cool/primary/success/tip/warn/secondary/warning
})

const appStore = useAppStore()
const modStore = useModStore()
const ruleStore = useRuleStore()
const confirmStore = useConfirmStore()


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
// 获取当前位置状态
const absPos = computed(() => {
  return ruleStore.getAbsolutePosition(targetMod.value?.package_id) || { pos: 'none' }
})

const targetMod = computed(() => modStore.takeModById(ruleStore.currentId))
const isLanguagePackMod = computed(() => {
  const modType = String(targetMod.value?.user_mod_type || targetMod.value?.mod_type || '').trim()
  return modType === 'LanguagePack'
})
const resolvedLanguagePackOwnerResult = computed(() => targetMod.value?.language_pack_owner_result || null)
const analyzedLanguagePackOwnerRows = computed(() => (
  (resolvedLanguagePackOwnerResult.value?.analyzed_owners || resolvedLanguagePackOwnerResult.value?.owners || [])
    .map(owner => ({ id: String(owner?.package_id || '').trim().toLowerCase() }))
    .filter(owner => !!owner.id)
))
const analyzedLanguagePackOwnerSummary = computed(() => {
  const relationType = String(
    resolvedLanguagePackOwnerResult.value?.analyzed_relation_type ||
    resolvedLanguagePackOwnerResult.value?.relation_type ||
    'unknown'
  )
  const confidence = String(
    resolvedLanguagePackOwnerResult.value?.analyzed_summary_confidence ||
    resolvedLanguagePackOwnerResult.value?.summary_confidence ||
    'unknown'
  )
  return `${relationType} / ${confidence}`
})
const languagePackOwnerOverrideState = computed(() => (
  ruleStore.getLanguagePackOwnerOverride(targetMod.value?.package_id)
))
const languagePackOwnerReplaceEnabled = computed(() => !!languagePackOwnerOverrideState.value.replace)
const canToggleLanguagePackOwnerOverride = computed(() => languagePackOwnerOverrideRows.value.length > 0)
const isLanguagePackOwnerReplaceEnabled = computed(() => (
  canToggleLanguagePackOwnerOverride.value && languagePackOwnerReplaceEnabled.value
))
const languagePackOwnerOverrideRows = computed({
  get() {
    return (languagePackOwnerOverrideState.value.ownerIds || []).map(id => ({ id }))
  },
  set() {}
})

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
// 3. Workshop
const getWorkshopRules = (type) => {
  const rules = ruleStore.workshopModRules[targetMod.value?.package_id]
  if (!rules || !rules[type]) return []
  return rules[type]
}
// 4. User
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
  // 规则列表是小型投放区，不做虚拟排序；这里复用全局选中态支持多选拖入。
  const sourceId = e.item.id
  const selectedIds = (modStore.selectedIds || []).map(id => String(id || '').toLowerCase()).filter(Boolean)
  const sourceIds = selectedIds.includes(String(sourceId || '').toLowerCase()) ? selectedIds : [sourceId]
  for (const id of sourceIds) {
    if (!id || id === targetMod.value?.package_id) continue
    // 调用 RuleStore 添加规则
    await ruleStore.addUserModRule(targetMod.value?.package_id, ruleType, id)
  }
}

const persistLanguagePackOwnerOverride = async (ownerIds, replace = languagePackOwnerReplaceEnabled.value) => {
  await ruleStore.setLanguagePackOwnerOverride(targetMod.value?.package_id, ownerIds, replace)
}

const toggleLanguagePackOwnerOverrideMode = async (enabled) => {
  const normalizedEnabled = canToggleLanguagePackOwnerOverride.value ? !!enabled : false
  if (languagePackOwnerReplaceEnabled.value === normalizedEnabled) return
  await persistLanguagePackOwnerOverride(
    languagePackOwnerOverrideRows.value.map(item => item.id),
    normalizedEnabled
  )
}

const onDropLanguagePackOwner = async (e) => {
  const sourceId = e.item.id
  const selectedIds = (modStore.selectedIds || []).map(id => String(id || '').toLowerCase()).filter(Boolean)
  const sourceIds = selectedIds.includes(String(sourceId || '').toLowerCase()) ? selectedIds : [sourceId]
  const nextIds = [...new Set([
    ...languagePackOwnerOverrideRows.value.map(item => item.id),
    ...sourceIds
      .map(id => String(id || '').toLowerCase())
      .filter(id => id && id !== targetMod.value?.package_id)
  ])]
  await persistLanguagePackOwnerOverride(nextIds, languagePackOwnerReplaceEnabled.value)
}

const removeLanguagePackOwner = async (otherId) => {
  const nextIds = languagePackOwnerOverrideRows.value
    .map(item => item.id)
    .filter(id => id !== String(otherId || '').toLowerCase())
  const nextReplace = nextIds.length > 0 ? languagePackOwnerReplaceEnabled.value : false
  await persistLanguagePackOwnerOverride(nextIds, nextReplace)
}

// 改变位置
const handlePosChange = async (pos) => {
  if (absPos.value.pos === pos) return // 无变化

  let comment = ''
  if (pos !== 'none') {
    // 弹出输入框要求写个备注（可选）
    comment = await confirmStore.open({
      title: pos === 'top' ? '设为置顶' : '设为置底',
      placeholder: '选填：为什么要强制放到这？',
      mode: 'prompt'
    })
    if (comment === null) return // 用户点击了取消
  }

  await ruleStore.setAbsolutePosition(targetMod.value?.package_id, pos, comment)
}
</script>

<style scoped>

</style>
