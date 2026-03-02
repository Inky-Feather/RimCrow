<template>
  <transition name="panel-fade">
    <div v-if="appStore.uiState.showRuleDrawer" 
      class="fixed inset-0 z-100 flex items-center justify-center bg-bg-deep/60 backdrop-blur-md"
      @click.self="appStore.uiState.showRuleDrawer = false">

      <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/20 backdrop-blur-md p-10" @click.self="appStore.uiState.showRuleDrawer = false">
        
        <div class="flex w-full max-w-9/10 h-full max-h-[90vh] bg-bg-deep/95 border border-text-main/10 rounded-2xl shadow-3xl overflow-hidden animate-scale-in">
          
          <!-- ================= 左侧侧边栏 ================= -->
          <aside class="w-64 bg-black/20 border-r border-text-main/5 flex flex-col">
            <div class="p-6">
              <h2 class="text-xl font-bold text-text-main flex items-center gap-2" @click="ruleStore.fetchRules">
                <svg class="w-6 h-6 text-accent-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" /></svg>
                规则中心
              </h2>
              <p class="text-sm text-text-dim mt-2">管理排序逻辑与约束</p>
            </div>

            <nav class="flex-1 px-2 space-y-1">
              <button v-for="tab in tabs" :key="tab.id" @click="currentTab = tab.id"
                class="w-full flex items-center justify-between px-3 py-3 rounded-xl text-sm font-bold transition-all duration-200 group"
                :class="currentTab === tab.id ? 'bg-accent-primary/10 text-accent-primary border border-accent-primary/20' : 'text-text-dim hover:bg-text-main/5 border border-transparent'">
                <div class="flex items-center gap-2">
                  <component :is="tab.icon" class="w-4 h-4 transition-transform group-hover:scale-110" />
                  {{ tab.label }}
                </div>
                <span v-if="tab.count !== undefined" class="bg-black/30 px-2 py-0.5 rounded text-xs opacity-60">{{ tab.count }}</span>
              </button>
            </nav>

            <!-- ================= 优先级排序 (侧边栏) ================= -->
            <div class="px-4 py-4 bg-bg-highlight/25 border-text-main/5">
              <div class="flex items-center justify-between mb-3 px-2">
                <span class="text-xs font-bold text-text-dim uppercase tracking-widest">
                  生效优先级
                  <label v-tooltip="'规则生效优先级，影响自动排序和问题检测的判定。'" class="text-xs text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
                </span>
                <div class="flex gap-2">
                  <button v-if="isPriorityDirty" @click="resetPriority" v-tooltip="'重置'"
                    class="text-text-dim hover:text-text-main transition-colors">
                    <RotateCcw class="w-3.5 h-3.5" />
                  </button>
                  <button @click="savePriority" v-tooltip="isPriorityDirty ? '保存优先级修改' : '无变化'"
                    :class="[isPriorityDirty ? 'text-accent-success scale-110' : 'text-text-dim opacity-50']"
                    class="transition-all duration-300">
                    <Save class="w-4 h-4" />
                  </button>
                </div>
              </div>

              <div class="space-y-1 relative">
                <TransitionGroup name="flip-list">
                  <div v-for="(source, idx) in localPriority" :key="source"
                    draggable="true"
                    @dragstart="onDragStart($event, idx)"
                    @dragover="onDragOver($event, idx)" 
                    @dragend="onDragEnd"
                    class="drag-item flex items-center gap-2 px-3 py-2 bg-text-dim/10 border border-text-main/5 rounded-lg cursor-grab active:cursor-grabbing group transition-colors hover:border-accent-primary/30"
                    :class="{ 'opacity-20 bg-accent-primary/5 border-accent-primary/50': dragIndex === idx }">
                    <!-- 内部元素增加 pointer-events-none 防止干扰 dragenter -->
                    <GripVertical class="pointer-events-none w-3.5 h-3.5 text-text-dim group-hover:text-accent-primary transition-colors" />
                    <span class="pointer-events-none text-xs font-medium text-text-main/80 select-none">{{ sourceNames[source] }}</span>
                    <span class="pointer-events-none ml-auto text-[10px] font-mono text-text-dim bg-black/40 w-4 h-4 flex items-center justify-center rounded">
                      {{ idx + 1 }}
                    </span>
                  </div>
                </TransitionGroup>
              </div>
              <p class="text-[10px] text-text-dim/60 mt-2 px-2 leading-relaxed">
                * 生效优先级：从上到下，优先级从高到低。
              </p>
            </div>

            <div class="p-4 border-t border-text-main/5 space-y-2">
              <button @click="ruleStore.handleImport" class="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-text-main/5 hover:bg-text-main/10 text-sm text-text-dim transition-all border border-text-main/5">
                <Download class="w-3 h-3" /> 导入配置包
              </button>
              <button @click="ruleStore.handleExport" class="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-text-main/5 hover:bg-text-main/10 text-sm text-text-dim transition-all border border-text-main/5">
                <Share2 class="w-3 h-3" /> 导出配置包
              </button>
            </div>
          </aside>

          <!-- ================= 右侧主内容区 ================= -->
          <main class="flex-1 flex flex-col min-w-0 bg-text-main/1">
            
            <!-- 顶部工具栏 -->
            <header class="h-16 border-b border-text-main/5 flex items-center justify-between px-6 bg-black/10">
              <!-- 搜索 -->
              <div class="relative w-72 group">
                <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-dim group-focus-within:text-accent-primary transition-colors" />
                <input v-model="searchQuery" placeholder="搜索规则、Mod名称或ID..." 
                  class="w-full bg-black/20 border border-text-main/10 rounded-full pl-9 pr-4 py-1.5 text-sm text-text-main focus:border-accent-primary focus:bg-black/40 outline-none transition-all" />
              </div>

              <!-- 全局开关与操作 -->
              <div class="flex items-center gap-4">
                <label v-if="currentTab !== 'dynamic'" class="flex items-center gap-2 cursor-pointer select-none">
                  <div class="relative">
                    <input type="checkbox" v-model="filterInstalled" class="sr-only peer">
                    <div class="w-9 h-5 bg-text-main/10 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-text-main after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-text-main after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-accent-secondary"></div>
                  </div>
                  <span class="text-sm text-text-dim font-bold">仅显示已安装</span>
                </label>

                <button v-if="currentTab === 'dynamic'" @click="createDynamicRule"
                  class="flex items-center gap-2 px-4 py-2 bg-accent-primary hover:bg-accent-primary/80 text-black text-sm font-bold rounded-lg shadow-lg shadow-accent-primary/20 transition-all active:scale-95">
                  <Plus class="w-4 h-4" /> 新建规则
                </button>

                <label class="flex items-center gap-2 cursor-pointer select-none" :key="currentTab + 'Enable'">
                  <div class="relative">
                    <input type="checkbox" v-model="globalRulesEnable" class="sr-only peer" >
                    <div class="w-9 h-5 bg-text-main/10 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-text-main after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-text-main after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-accent-success"></div>
                  </div>
                  <span class="text-sm text-text-dim font-bold">启用规则</span>
                </label>
              </div>
            </header>

            <!-- 内容列表 -->
            <div class="flex-1 overflow-y-auto p-6 space-y-2 custom-scrollbar">
              
              <!-- 1. 动态规则列表 -->
              <template v-if="currentTab === 'dynamic'">
                <div v-for="rule in filteredDynamicRules" :key="rule.rule_id" 
                  class="group relative bg-text-main/5 border border-text-main/10 hover:border-accent-primary/30 rounded-xl p-4 transition-all duration-200">
                  
                  <div class="flex justify-between items-start ">
                    <div class="flex-1">
                      <div class="flex items-center gap-2">
                        <span class="text-sm font-bold text-text-main">{{ rule.name }}</span>
                        <span class="text-xs px-2 py-0.5 rounded bg-black/30 text-text-dim border border-text-main/5">Priority: {{ rule.priority }}</span>
                        <span v-if="!rule.enabled" class="text-xs px-2 py-0.5 rounded bg-red-500/10 text-red-400 border border-red-500/20">已禁用</span>
                        <span v-if="rule.description" :title="rule.description" class="flex-1 text-xs px-1 py-0.5 text-text-dim ">{{ rule.description }}</span>
                      </div>
                      
                      <!-- 逻辑可视化 -->
                      <div class="mt-3 flex flex-wrap gap-2 items-center text-sm">
                        <span class="text-accent-secondary font-bold font-mono">IF</span>
                        <div class="flex flex-wrap gap-1">
                          <span v-for="(f, i) in rule.filters" :key="i">
                            <span v-if="i>0" class="text-accent-cool mr-1">{{ rule.logic }}</span>
                            <span class="px-1.5 py-0.5 rounded bg-text-main/10 text-text-main border border-text-main/5">
                              {{ ruleStore.DYNAMIC_RULE_PROPS[f.field] }} {{ formatOperator(f.operator) }} <span class="text-accent-cool">{{ f.value }}</span>
                            </span>
                          </span>
                        </div>
                        <span class="text-accent-primary font-bold font-mono ml-2">THEN</span>
                        <span class="px-1.5 py-0.5 rounded bg-accent-primary/10 text-accent-primary border border-accent-primary/20">
                          {{ formatAction(rule.action) }}
                        </span>
                      </div>
                    </div>

                    <!-- 操作区 -->
                    <div class="flex items-center gap-2 opacity-60 group-hover:opacity-100 transition-opacity">
                      <button @click="ruleStore.toggleDynamicRule(rule)" v-tooltip="rule.enabled ? '禁用规则' : '启用规则'"
                        class="p-2 rounded-lg hover:bg-text-main/10" :class="rule.enabled ? 'text-accent-success' : 'text-accent-danger'">
                        <CircleCheckBig v-if="rule.enabled" class="w-4 h-4" />
                        <CircleOff v-else class="w-4 h-4" />
                      </button>
                      <button @click="editDynamicRule(rule)" v-tooltip="'编辑'" class="p-2 rounded-lg hover:bg-text-main/10 text-text-dim hover:text-text-main">
                        <Edit3 class="w-4 h-4" />
                      </button>
                      <button @click="deleteDynamicRule(rule, $event)" v-tooltip="'删除'" class="p-2 rounded-lg hover:bg-red-500/10 text-text-dim hover:text-red-400">
                        <Trash2 class="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
                
                <div v-if="filteredDynamicRules.length === 0" class="flex flex-col items-center justify-center h-64 text-text-dim/30">
                  <Zap class="w-12 h-12 mb-2" />
                  <p class="text-sm">暂无动态规则</p>
                </div>
              </template>

              <!-- 2. 用户规则 & 社区规则列表 (共用结构) -->
              <template v-else>
                <div v-if="currentTab === 'community'" class="mb-4 p-4 rounded-xl bg-accent-secondary/10 border border-accent-secondary/20 flex justify-between items-center">
                  <div class="text-sm text-accent-secondary">
                    <p class="font-bold mb-1">社区规则库 (RimSort)</p>
                    <p class="opacity-80">包含众多由社区维护的排序建议。此处仅展示与已安装模组相关的条目。</p>
                  </div>
                  <div class="flex flex-col items-center gap-2">
                    <button @click="ruleStore.updateCommunity" class="px-3 py-1.5 bg-accent-secondary/20 hover:bg-accent-secondary/40 text-accent-secondary rounded-lg text-sm font-bold transition-all border border-accent-secondary/30">
                      手动更新库
                    </button>
                    <span class="text-xs px-2 py-0.5 rounded bg-text-main/5 text-text-dim border border-text-main/5">
                      更新时间: {{ ruleStore.communityRulesUpdateTime? new Date(ruleStore.communityRulesUpdateTime).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '无' }}
                      <!-- 更新时间: {{ ruleStore.communityRulesUpdateTime }} -->
                    </span>
                  </div>
                </div>

                <div v-for="item in filteredStaticRules" :key="item.id" 
                  class="flex gap-2 p-2 rounded-xl bg-text-main/2 border border-text-main/5 hover:bg-text-main/5 transition-colors">
                  
                  <!-- Mod 信息 -->
                  <div class="w-64 shrink-0 flex gap-3 items-start" v-preview="modStore.takeModById(item.id)">
                    <div class="w-10 h-10 rounded-lg bg-black/30 border border-text-main/10 flex items-center justify-center overflow-hidden shrink-0">
                      <img v-if="item.icon" :src="item.icon" class="w-full h-full object-cover">
                      <div v-else class="text-xs text-text-dim">{{ item.id.substring(0,2) }}</div>
                    </div>
                    <div class="min-w-0 flex flex-col gap-1"> 
                      <div class="text-sm font-bold text-text-main truncate">{{ item.name }}</div>
                      <div class="text-xs text-text-dim font-mono truncate opacity-60">{{ item.id }}</div>

                      <span v-if="item.rules.loadTop?.value"
                        v-tooltip="formatTooltip(item.id, item.rules.loadTop?.comment)"
                        class="px-1.5 py-0.5 rounded max-w-[49%] min-w-0 w-fit bg-accent-tip/10 text-text-main text-[0.8rem] border border-accent-tip/20 truncate cursor-help">
                        强制置顶
                      </span>
                      <span v-else-if="item.rules.loadBottom?.value"
                        v-tooltip="formatTooltip(item.id, item.rules.loadBottom?.comment)"
                        class="px-1.5 py-0.5 rounded max-w-[49%] min-w-0 w-fit bg-accent-highlight/10 text-text-main text-[0.8rem] border border-accent-highlight/20 truncate cursor-help">
                        强制置底
                      </span>

                    </div>

                  </div>

                  <!-- 规则详情 -->
                  <div class="flex-1 min-w-0 space-y-2 border-l border-text-main/5 pl-4">
                    <!-- Load After -->
                    <div v-if="item.rules.loadAfter && Object.keys(item.rules.loadAfter).length" class="flex flex-wrap gap-2 w-full min-w-0 items-start">
                      <span class="text-xs font-bold text-accent-warn uppercase mt-0.5">前置:</span>
                      <div class="flex flex-wrap gap-1 w-full min-w-0">
                        <span v-for="(info, targetId) in item.rules.loadAfter" :key="targetId" 
                          v-tooltip="formatTooltip(targetId, info)"
                          class="px-1.5 py-0.5 rounded max-w-[49%] min-w-0 bg-accent-warn/10 text-text-main text-[0.8rem] border border-accent-warn/20 truncate cursor-help">
                          {{ getDisplayName(targetId, info.name) }}
                        </span>
                      </div>
                    </div>
                    <!-- Load Before -->
                    <div v-if="item.rules.loadBefore && Object.keys(item.rules.loadBefore).length" class="flex flex-wrap gap-2 w-full min-w-0 items-start">
                      <span class="text-xs font-bold text-accent-primary uppercase mt-0.5">后置:</span>
                      <div class="flex flex-wrap gap-1 w-full min-w-0 ">
                        <span v-for="(info, targetId) in item.rules.loadBefore" :key="targetId"
                          v-tooltip="formatTooltip(targetId, info)" 
                          class="px-1.5 py-0.5 rounded max-w-[49%] min-w-0 bg-accent-primary/10 text-text-main text-[0.8rem] border border-accent-primary/20 truncate cursor-help">
                          {{ getDisplayName(targetId, info.name) }}
                        </span>
                      </div>
                    </div>
                    <!-- Incompatible -->
                    <div v-if="item.rules.incompatibleWith && Object.keys(item.rules.incompatibleWith).length" class="flex flex-wrap gap-2 w-full min-w-0 items-start">
                      <span class="text-xs font-bold text-accent-danger uppercase mt-0.5">冲突:</span>
                      <div class="flex flex-wrap gap-1 w-full min-w-0 ">
                        <span v-for="(info, targetId) in item.rules.incompatibleWith" :key="targetId"
                          v-tooltip="formatTooltip(targetId, info)"
                          class="px-1.5 py-0.5 rounded max-w-[49%] min-w-0 bg-accent-danger/10 text-text-main text-[0.8rem] border border-accent-danger/20 truncate cursor-help">
                          {{ getDisplayName(targetId, info.name) }}
                        </span>
                      </div>
                    </div>
                  </div>

                  <!-- 操作 (仅用户规则有删除) -->
                  <div class="shrink-0 flex items-center flex-col">
                    <button @click="toggleModRule(item.id)" v-tooltip="isModExcluded(item.id) ? '启用规则' : '禁用规则'"
                      class="p-2 rounded-lg hover:bg-text-main/10" :class="!isModExcluded(item.id) ? 'text-accent-success' : 'text-accent-danger'">
                      <CircleCheckBig v-if="!isModExcluded(item.id)" class="w-4 h-4" />
                      <CircleOff v-else class="w-4 h-4" />
                    </button>

                    <button v-if="currentTab === 'user'" @click="deleteUserModRule(item.id, $event)" class="p-2 text-text-dim hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors">
                      <Trash2 class="w-4 h-4" />
                    </button>
                  </div>

                </div>
                
                <div v-if="filteredStaticRules.length === 0" class="flex flex-col items-center justify-center h-64 text-text-dim/30">
                  <Shield class="w-12 h-12 mb-2" />
                  <p class="text-sm">没有找到相关规则</p>
                </div>
              </template>

            </div>
          </main>
        </div>

        <!-- ================= 3. 规则编辑器 (Modal) ================= -->
        <Transition name="fade">
          <div v-if="editingRule" class="fixed inset-0 z-60 flex items-center justify-center bg-bg-deep/30 backdrop-blur-sm p-4">
            <div class="w-full max-w-[70%] bg-bg-surface border border-text-main/10 rounded-2xl shadow-3xl flex flex-col max-h-[90%] animate-scale-in">
              
              <header class="px-6 py-4 border-b border-text-main/5 flex justify-between items-center bg-text-main/2">
                <div class="flex items-center gap-3">
                  <div class="w-8 h-8 rounded-lg bg-accent-primary/20 flex items-center justify-center">
                    <Zap class="w-4 h-4 text-accent-primary" />
                  </div>
                  <h2 class="text-lg font-bold text-text-main">{{ editingRule.rule_id.startsWith('new_') ? '新建动态规则' : '编辑规则' }}</h2>
                </div>
                <button @click="editingRule = null" class="text-text-dim hover:text-text-main"><X class="w-6 h-6"/></button>
              </header>
              
              <div class="flex-1 overflow-y-auto p-6 space-y-6">
                
                <!-- 基础设置 -->
                <div class="grid grid-cols-12 gap-4">
                  <CommonInput v-model="editingRule.name" label="规则名称" placeholder="例如: 汉化包置底" class="col-span-8" />
                  <CommonNumber v-model.number="editingRule.priority" label="优先级 (Priority)" placeholder="例如: 100" class="col-span-4" :step=1 :min="0" :max="1000" />
                  <CommonInput v-model="editingRule.description" label="描述 (可选)" placeholder="规则的备注说明..." class="col-span-12" />
                </div>

                <!-- 条件构建器 -->
                <div class="space-y-3">
                  <div class="flex items-center justify-between">
                    
                    <CommonSelect class="min-w-45" v-model="editingRule.logic" label="触发条件" mini :options="[{label:'满足所有 (AND)',value:'AND'}, {label:'满足任一 (OR)',value:'OR'}]"></CommonSelect>
                    
                    <button @click="addFilter" class="text-accent-primary text-sm hover:underline flex items-center gap-1"><Plus class="w-3 h-3"/>添加条件</button>
                  </div>
                  
                  <div class="space-y-2 bg-black/20 rounded-xl p-3 border border-text-main/5">
                    <div v-for="(filter, idx) in editingRule.filters" :key="idx" class="flex gap-2 items-center group">
                      
                      <CommonSelect class="min-w-20" v-model="filter.field" :options="Object.entries(ruleStore.DYNAMIC_RULE_PROPS).map(([key, value]) => ({label: value, value: key}))"></CommonSelect>
                      
                      <CommonSelect class="min-w-30" v-model="filter.operator" :options="Object.entries(ruleStore.DYNAMIC_RULE_OPERATORS).map(([key, value]) => ({label: value, value: key}))"></CommonSelect>
                      
                      <div v-if="filter.field === 'package_id'" class="flex-1">
                        <CommonSelect v-model="filter.value" :options="modIdList" editable ></CommonSelect>
                      </div>
                      <CommonInput v-else v-model="filter.value" placeholder="值..." class="flex-1" />
                      
                      <button @click="editingRule.filters.splice(idx, 1)" class="p-1.5 text-text-dim hover:text-red-400 opacity-50 group-hover:opacity-100 transition-opacity"><Trash2 class="w-3.5 h-3.5"/></button>
                    </div>
                    <div v-if="editingRule.filters.length === 0" class="text-center py-2 text-sm text-text-dim italic">点击右上角添加筛选条件</div>
                  </div>
                </div>

                <!-- 动作设置 -->
                <div class="space-y-3">
                  <label class="text-xs uppercase font-bold text-text-dim tracking-wider mb-1">执行动作</label>
                  <div class="bg-accent-primary/5 border border-accent-primary/20 rounded-xl p-3 flex gap-2 items-center">
                    <CommonSelect class="min-w-40" v-model="editingRule.action.type" :options="Object.entries(ruleStore.DYNAMIC_RULE_ACTIONS).map(([key, value]) => ({label: value, value: key}))"></CommonSelect>
                    
                    <!-- 根据动作类型显示输入框 -->
                    <div v-if="editingRule.action.type.includes('weight')" class="flex items-center gap-2 flex-1">
                      <!-- <input type="number" v-model.number="editingRule.action.value" class="bg-bg-deep border border-text-main/10 rounded-lg px-3 py-2 text-sm w-32 text-text-main outline-none focus:border-accent-primary" /> -->
                      <CommonNumber v-model.number="editingRule.action.value" :step=1 :min="editingRule.action.type === 'weight_shift' ? -1000 : 0" :max="1000" />
                      <span class="text-sm text-text-dim">
                        {{ editingRule.action.type === 'weight_shift' ? '(负数向前，正数向后)' : '(0-1000，越小越靠前)' }}
                      </span>
                      <label class="text-sm text-text-dim italic hover:text-text-main cursor-help" v-tooltip="weightTooltip">?</label>
                    </div>
                    <div v-else-if="editingRule.action.type.includes('load_')" class="flex-1">
                      <!-- <CommonInput v-model="editingRule.action.value" placeholder="目标 Mod 的 PackageID" class="w-full" /> -->
                      <CommonSelect v-model="editingRule.action.value" :options="modIdList" editable ></CommonSelect>
                    </div>
                    <div v-else class="text-sm text-text-dim flex-1">
                      无需参数，匹配项将被移至列表最{{ editingRule.action.type === 'top' ? '前' : '后' }}端。
                    </div>
                  </div>
                </div>

              </div>

              <footer class="p-4 border-t border-text-main/5 bg-text-main/2 flex justify-end gap-3">
                <button @click="editingRule = null" class="px-5 py-2 rounded-lg hover:bg-text-main/5 text-sm font-bold text-text-dim transition-colors">取消</button>
                <button @click="saveDynamicRule" class="px-6 py-2 bg-accent-primary hover:bg-accent-primary/90 text-black rounded-lg text-sm font-bold shadow-lg transition-transform active:scale-95">保存规则</button>
              </footer>
            </div>
          </div>
        </Transition>

      </div>

    </div>
  </transition>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Edit3, Trash2, X, Shield, User, Zap, Share2, Search, Plus, Power, Download, Waypoints, CircleCheckBig, CircleOff, GripVertical, Save, RotateCcw } from 'lucide-vue-next'
import { useToast } from "vue-toastification"
import { useAppStore } from '../stores/appStore'
import { useModStore } from '../stores/modStore'
import { useRuleStore } from '../stores/ruleStore'
import { useConfirmStore } from '../stores/confirmStore'
import CommonInput from './common/input/CommonInput.vue'
import CommonNumber from './common/input/CommonNumber.vue'
import CommonSelect from './common/input/CommonSelect.vue'



const emit = defineEmits(['close'])
const toast = useToast()
const appStore = useAppStore()
const modStore = useModStore()
const ruleStore = useRuleStore()
const confirmStore = useConfirmStore()


// --- 状态管理 ---
const currentTab = ref('dynamic')
const searchQuery = ref('')
const filterInstalled = ref(true) // 默认开启“仅显示已安装”


const editingRule = ref(null)

const tabs = computed(() => [
  { id: 'dynamic', label: '动态群组规则', icon: Zap, count: allRules.value.user_dynamic_rules.length },
  { id: 'user', label: '用户Mod规则', icon: User, count: Object.keys(allRules.value.user_mod_rules).length },
  { id: 'community', label: '社区Mod规则', icon: Waypoints, count: Object.keys(allRules.value.community_mod_rules).length },
])

const allRules = computed(() => ({
  user_mod_rules: ruleStore.userModRules,
  community_mod_rules: ruleStore.communityModRules,
  user_dynamic_rules: ruleStore.userDynamicRules,
  excluded_user_mods_set: new Set(ruleStore.settings?.excluded_user_mods || []),
  excluded_community_mods_set: new Set(ruleStore.settings?.excluded_community_mods || []),
}))

const modIdList = computed(() => Array.from(modStore.allModsMap.values(), mod => ({label: modStore.displayModName(mod)+' ('+mod.package_id+')', value: mod.package_id})))

const isModExcluded = (modId) => {
  if (currentTab.value === 'user') return allRules.value.excluded_user_mods_set.has(modId)
  if (currentTab.value === 'community') return allRules.value.excluded_community_mods_set.has(modId)
}

// 规则是否启用
const globalRulesEnable = computed({
    get() {
      if (currentTab.value === 'dynamic') return !!ruleStore.settings?.dynamic_rules_enabled
      if (currentTab.value === 'user') return !!ruleStore.settings?.user_mod_rules_enabled
      if (currentTab.value === 'community') return !!ruleStore.settings?.community_mod_rules_enabled
    },
    set(val) {
      if (currentTab.value === 'dynamic') ruleStore.setGlobalEnable('dynamic', val)
      if (currentTab.value === 'user') ruleStore.setGlobalEnable('user', val)
      if (currentTab.value === 'community') ruleStore.setGlobalEnable('community', val)
    }
})


// --- 核心过滤逻辑 ---

// 1. 动态规则过滤
const filteredDynamicRules = computed(() => {
  let rules = [...(allRules.value.user_dynamic_rules || [])]
  const q = searchQuery.value.toLowerCase().trim()
  
  if (q) {
    rules = rules.filter(r => 
      r.name.toLowerCase().includes(q) || 
      (r.description && r.description.toLowerCase().includes(q))
    )
  }
  return rules.sort((a, b) => a.priority - b.priority)
})

// 2. 静态规则过滤 (用户单项 & 社区)
const filteredStaticRules = computed(() => {
  const q = searchQuery.value.toLowerCase().trim()
  const source = currentTab.value === 'user' ? allRules.value.user_mod_rules : allRules.value.community_mod_rules
  
  // 转换为数组方便渲染: [{ id: 'package_id', rules: {...}, name: 'Mod Name', icon: '...' }]
  let list = Object.entries(source).map(([id, rules]) => {
    const mod = modStore.takeModById(id) // 从 store 获取 Mod 信息
    return {
      id: id,
      rules: rules,
      name: mod?.name || id,
      icon: mod?.thumb_url || null,
      isInstalled: mod && !!mod.path // 判断是否安装
    }
  })

  // 过滤器 1: 仅显示已安装
  if (filterInstalled.value) {
    list = list.filter(item => item.isInstalled)
  }

  // 过滤器 2: 搜索文本
  if (q) {
    list = list.filter(item => 
      item.id.toLowerCase().includes(q) || 
      item.name.toLowerCase().includes(q)
    )
  }

  // 排序：已安装的排前面，然后按名字
  return list.sort((a, b) => {
    if (a.isInstalled !== b.isInstalled) return b.isInstalled - a.isInstalled
    return a.name.localeCompare(b.name)
  })
})

// --- 辅助显示方法 ---
const formatOperator = (op) => {
  const map = { contains: '包含', equals: '等于', not_contains: '不含', regex: '正则', starts_with: '开头是', ends_with: '结尾是' }
  return map[op] || op
}
// 格式化操作指令
const formatAction = (act) => {
  if (act.type === 'weight_shift') return `权重 ${act.value > 0 ? '+' : ''}${act.value}`
  else if (act.type === 'weight_set') return `权重设为 ${act.value}`
  else if (act.type.includes('load_')) return `在 ${modStore.displayModName(act.value)} ${act.type === 'load_after' ? '之后' : '之前'}`
  else return act.type === 'top' ? '置顶' : '置底'
}
// 获取 Mod 显示名称
const getDisplayName = (id, defaultName) => modStore.displayModName(id, defaultName)
// 格式化动态规则的提示信息
const formatTooltip = (targetId, info) => {
  let text = `ID: ${targetId}`
  if (info.name) text += `\nName: ${Array.isArray(info.name) ? info.name[0] : info.name}`
  if (info.comment) text += `\n\n说明:\n${Array.isArray(info.comment) ? info.comment.join('\n') : info.comment}`
  return text
}
// 权重说明
const weightTooltip = `**MOD权重设置规则**
权重取值范围为 0-1000，数值越低，加载优先级越高（越靠前） 。其中，普通 MOD 的默认权重为 500，若设置权重偏移，将以当前已设定的权重为基准进行偏移调整。

建议按照以下权重区间对 MOD 进行分类设置，具体如下：

[[权重区间]]		[[类别描述]]						[[典型例子]]
0 - 50			绝对底层框架				Harmony, Prepatcher
51 - 100		官方内容						Core, Royalty, Ideology, Anomaly
101 - 200		通用基础库					Vanilla Expanded Framework
201 - 700		普通功能/内容模组		大多数内容 Mod (物品、种族、派系)
701 - 800		UI与界面增强				RimHUD, Numbers, InventoryTab
801 - 950		视觉/汉化/补丁			汉化包 (LanguagePack), 纹理替换
951 - 1000	末端优化/逻辑处理		Rocketman, Performance Optimize
`

// --- 操作逻辑 ---
// 创建新的动态规则
const createDynamicRule = () => {
  editingRule.value = {
    rule_id: 'new_' + Date.now(),
    name: '',
    description: '',
    enabled: true,
    priority: 100,
    logic: 'AND',
    filters: [{ field: 'package_id', operator: 'contains', value: '' }],
    action: { type: 'weight_shift', value: -10 }
  }
}
// 编辑动态规则
const editDynamicRule = (rule) => {
  editingRule.value = JSON.parse(JSON.stringify(rule)) // Deep clone
}
// 添加检查条件
const addFilter = () => {
  editingRule.value.filters.push({ field: 'package_id', operator: 'contains', value: '' })
}
// 保存动态规则
const saveDynamicRule = async () => {
  if (!window.pywebview) return
  if (!editingRule.value.name) {
    toast.warning("请输入规则名称")
    return
  }
  // 如果是新建，生成正式ID
  if (editingRule.value.rule_id.startsWith('new_')) {
    editingRule.value.rule_id = 'dyn_' + Date.now()
  }
  const res = await ruleStore.saveDynamicRules(editingRule.value)
  if (res) { editingRule.value = null }
}
// 删除动态规则
const deleteDynamicRule = async (rule, event) => {
  const confirm = await confirmStore.open({
    title: '确认删除',
    message: '确定删除该动态规则吗？',
    type: 'error',
    mode: 'confirm',
  },event.target)
  if (confirm) {
    ruleStore.deleteDynamicRule(rule)
  }
}


// 删除用户 Mod 规则
const deleteUserModRule = async (ruleId, event) => {
  const confirm = await confirmStore.open({
    title: '确认删除',
    message: '确定删除该 Mod 规则吗？',
    type: 'error',
    mode: 'confirm',
  },event.target)
  if (confirm) {
    ruleStore.deleteUserModRule(ruleId)
  }
}
// 切换 Mod 规则状态
const toggleModRule = (modId) => {
  if (currentTab.value === 'community') {
    ruleStore.toggleCommunityModRule(modId)
  } else if (currentTab.value === 'user') {
    ruleStore.toggleUserModRule(modId)
  }
}

// --- 优先级排序逻辑 ---
const sourceNames = {
  user: '用户规则',
  native: '原版规则',
  community: '社区规则',
  dynamic: '动态规则'
}

// 本地优先级列表，用于拖拽展示
const localPriority = ref([])
const dragIndex = ref(null)

// 监听 store 数据变化，初始化本地列表
watch(() => ruleStore.settings?.rule_source_priority, (newVal) => {
  if (newVal) localPriority.value = [...newVal]
}, { immediate: true })

// 是否发生变动（用于保存按钮变色）
const isPriorityDirty = computed(() => {
  const original = ruleStore.settings?.rule_source_priority || []
  return JSON.stringify(localPriority.value) !== JSON.stringify(original)
})

// 拖拽逻辑
const onDragStart = (e, index) => {
  dragIndex.value = index;
  // 设置拖拽效果，这会固定光标为 "move"
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.dropEffect = 'move';
  
  // 兼容火狐：必须设置 setData 才能触发拖拽
  e.dataTransfer.setData('text/plain', index);
  
  // 增加一个类名，用于 CSS 优化
  e.target.classList.add('is-dragging');
};

const onDragOver = (e, index) => {
  e.preventDefault(); // 必须保留，允许投放
  
  if (dragIndex.value === null || dragIndex.value === index) return;

  // 获取目标元素的空间信息
  const targetRect = e.currentTarget.getBoundingClientRect();
  
  // 计算目标元素的中点高度
  const midpoint = targetRect.top + targetRect.height / 2;
  
  // 鼠标当前的 Y 坐标
  const mouseY = e.clientY;

  /**
   * 缓冲区逻辑：
   * 1. 如果向上拖拽 (dragIndex > index)，鼠标必须滑过目标项的中点以上
   * 2. 如果向下拖拽 (dragIndex < index)，鼠标必须滑过目标项的中点以下
   */
  const draggingDown = dragIndex.value < index;
  const draggingUp = dragIndex.value > index;

  if (draggingDown && mouseY < midpoint) return;
  if (draggingUp && mouseY > midpoint) return;

  // 只有通过了中点判定，才执行交换
  const list = [...localPriority.value];
  const item = list.splice(dragIndex.value, 1)[0];
  list.splice(index, 0, item);
  
  localPriority.value = list;
  dragIndex.value = index;
};

const onDragEnter = (index) => {
  // 如果进入的是自身，或者目标索引没变，直接返回
  if (index === dragIndex.value) return;

  // 核心逻辑：直接操作数组，Vue 的 flip-list 会处理平滑动画
  const list = [...localPriority.value];
  const draggedItem = list.splice(dragIndex.value, 1)[0];
  list.splice(index, 0, draggedItem);
  
  localPriority.value = list;
  dragIndex.value = index; // 更新当前索引，防止抖动
};

const onDragEnd = (e) => {
  dragIndex.value = null;
  e.target.classList.remove('is-dragging');
};

const savePriority = async () => {
  if (!isPriorityDirty.value) return
  const success = await ruleStore.changeRuleSourcePriority(localPriority.value)
  if (success) {
  }
}

const resetPriority = () => {
  localPriority.value = [...(ruleStore.settings?.rule_source_priority || [])]
}
</script>

<style scoped>
.animate-scale-in {
  animation: scaleIn 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
@keyframes scaleIn {
  from { opacity: 0; transform: scale(0.95); }
  to { opacity: 1; transform: scale(1); }
}

/* 页面切换动画 */
.panel-fade-enter-active, .panel-fade-leave-active { transition: opacity 0.4s ease; }
.panel-fade-enter-from, .panel-fade-leave-to { opacity: 0; }


/* 1. 核心：当处于拖拽状态时，禁用列表中所有子元素的鼠标事件 */
/* 这能防止鼠标进入图标或文字时，意外触发 dragenter 导致抖动 */
.drag-item * {
  pointer-events: none;
}

/* 2. 移除正在拖拽的元素在列表中的视觉干扰，但保留占位 */
.is-dragging {
  /* 也可以设置 visibility: hidden 或极低不透明度 */
  opacity: 0.1; 
}

/* 3. 修正光标 */
.cursor-grab {
  cursor: grab !important;
}
.cursor-grabbing {
  cursor: grabbing !important;
}

/* 4. Flip List 动画保持平滑 */
/* 1. 交换时的动画曲线：建议使用 out-expo 或 out-quart，前快后慢有助于视觉对齐 */
.flip-list-move {
  transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

/* 2. 关键优化：被拖拽的源节点在占位时，不应接收任何 Pointer 事件 */
/* 这能防止被拖拽的“影子”干扰鼠标判定 */
.is-dragging {
  opacity: 0.1;
  pointer-events: none; 
}

/* 3. 防止拖拽时文字选中干扰 */
.drag-item {
  user-select: none;
  -webkit-user-drag: element;
}

/* 确保交换时没有多余的布局跳动 */
.flip-list-enter-active,
.flip-list-leave-active {
  transition: none;
}
</style>