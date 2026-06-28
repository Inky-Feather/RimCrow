<template>
  <transition name="panel-fade">
    <div v-show="appStore.uiState.showSettingsPanel" 
      class="fixed inset-0 z-100 flex items-center justify-center bg-bg-deep/60 backdrop-blur-md"
      @click.self="shakeComponent('#btn-cancel')">
      
      <!-- 主容器 -->
      <div class="relative w-[75%] h-[80%] flex bg-bg-deep/95 border border-text-dim/20 rounded-4xl shadow-[0_0_50px_rgba(0,0,0,0.8)] overflow-hidden animate-in zoom-in-95 duration-300">
        
        <!-- A. 装饰光效 -->
        <div class="absolute -top-24 -left-24 w-64 h-64 bg-accent-primary/10 blur-[80px] rounded-full pointer-events-none"></div>
        <div class="absolute -bottom-24 -right-24 w-64 h-64 bg-accent-special/10 blur-[80px] rounded-full pointer-events-none"></div>

        <!-- B. 左侧导航栏 -->
        <aside class="w-45 border-r border-text-main/5 flex flex-col p-6 relative z-10">
          <div class="mb-10 px-2">
            <h2 class="text-xl font-black text-text-main tracking-tighter italic">系统 <span class="text-accent-primary">设置</span></h2>
          </div>

          <!-- 动态 Glider 导航 -->
          <nav class="flex flex-col relative space-y-1" :style="{ '--total-tabs': tabs.length }">
            <button v-for="(tab, index) in tabs" :key="tab.id"
              @click="currentTab = tab.id"
              class="relative z-10 flex items-center gap-3 px-4 py-3 text-md font-bold transition-all duration-300 group"
              :class="currentTab === tab.id ? 'text-accent-primary' : 'text-text-dim hover:text-text-main/70'"
            >
              <component :is="tab.icon" class="size-4" />
              <span>{{ tab.label }}</span>
            </button>

            <!-- 物理 Glider 滑块 -->
            <div class="glider-container absolute left-0 top-0 w-full h-full pointer-events-none">
              <div class="glider absolute -left-6 w-1 h-11 bg-accent-primary shadow-[0_0_15px_#06b6d4] transition-transform duration-500 cubic-bezier"
                :style="{ transform: `translateY(${tabs.findIndex(t => t.id === currentTab) * 2.85}rem)` }">
                <!-- 侧边发光层 -->
                <div class="absolute left-0 top-0 w-40 h-full bg-linear-to-r from-accent-primary/10 to-transparent"></div>
              </div>
            </div>
          </nav>

          <!-- 底部版本号 -->
          <div class="mt-auto px-4 py-2 border-t border-text-main/5 opacity-30">
             <p class="text-xs font-mono text-text-dim">V{{ appStore.appVersion }}</p>
          </div>
        </aside>

        <!-- C. 右侧主内容区 -->
        <main class="flex-1 flex flex-col min-w-0 bg-black/20 relative z-10">
          <!-- 顶部状态条 -->
          <header class="h-14 flex items-center justify-between px-8 border-b border-text-main/5">
            <span class="text-xs font-mono text-text-dim/60 uppercase tracking-[0.3em]">
              / root / {{ currentTab }}
            </span>
            <div class="flex gap-1.5 text-text-dim/20 relative">
              <Settings class="absolute size-23 -top-16 -right-13" />
            </div>
          </header>

          <!-- 内容滚动容器 -->
          <div class="flex-1 overflow-y-auto p-8 custom-scrollbar">
            <div class=" mx-auto space-y-10">

              <!-- 路径设置 (Paths) -->
              <section v-if="currentTab === 'paths'" class="animate-in fade-in slide-in-from-right-4">
                <div class="flex items-center justify-between mb-6">
                  <h3 class="text-lg font-bold text-text-main">路径配置
                    <label v-tooltip="'此处会直接修改当前环境的路径配置'" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
                  </h3>
                  <button @click="autoDetect" v-tooltip="'尝试通过注册表自动搜索路径'" class="px-3 py-1 bg-accent-success/10 hover:bg-accent-success/20 border border-accent-success/30 rounded text-xs font-bold text-accent-success transition-all">
                    自动搜索路径
                  </button>
                </div>
                <div class="grid gap-6">
                  <CommonPathInput label="游戏安装目录" v-model="formData.game_install_path" @browse="handleGameBrowse('game_install_path')" :description="formData.game_info" @blur="checkGamePath"/>
                  <CommonPathInput label="游戏配置目录" v-model="formData.game_config_path" @browse="handleBrowse('game_config_path')" />
                  <CommonPathInput label="创意工坊目录" v-model="formData.workshop_mods_path" @browse="handleBrowse('workshop_mods_path')" description="该设置所有环境通用" />
                  <CommonPathInput label="本地模组目录" v-model="formData.local_mods_path" readOnly @browse="handleBrowse('local_mods_path')" description="根据游戏安装目录自动生成" />
                  <CommonTagInput label="游戏启动参数" v-model="formData.run_commands" :allTags="RUN_COMMAND_TAGS" placeholder="请输入一个完整指令后回车确认……" description="注意不要使用 [[-savedatafolder]] 指令，多环境管理已经默认使用此指令，无需手动配置。" />
                  <div class="p-2 rounded-2xl bg-text-main/2 border border-text-main/5 grid grid-cols-1 gap-2">
                    <CommonSwitch label="优先使用Steam启动游戏" v-model="formData.prefer_steam_launch" mini description="开启后将优先使用Steam启动Steam版游戏。该设置所有环境通用" />
                    <CommonPathInput :class="{' pointer-events-none opacity-50':!formData.prefer_steam_launch}" label="Steam程序路径" v-model="formData.steam_exe_path" @browse="handleBrowse('steam_exe_path')" />
                  </div>
                  <!-- <CommonPathInput label="主目录" v-model="formData.home_path" @browse="handleBrowse('home_path')" /> -->
                </div>
              </section>

              <!-- 常规设置 (General) -->
              <section v-if="currentTab === 'general'" class="animate-in fade-in slide-in-from-right-4">
                <h3 class="text-lg font-bold text-text-main mb-6">界面与环境</h3>
                <div class="space-y-6">
                  <div class="grid grid-cols-2 gap-4 aria-disabled:pointer-events-none aria-disabled:opacity-50" :aria-disabled="true">
                    <CommonSelect label="界面语言" v-model="formData.language" :options="[{label:'简体中文', value:'ZH-cn'}, {label:'English', value:'EN'}]" />
                    <CommonSelect label="配色方案" v-model="formData.theme" :options="[{label:'自动同步系统', value:'system'}, {label:'黑曜石', value:'dark'}]" />
                  </div>
                  <!-- <div class="grid grid-cols-2 gap-4">
                    <CommonNumber label="窗口宽度" v-model="formData.window_width" :step="10" />
                    <CommonNumber label="窗口高度" v-model="formData.window_height" :step="10" />
                  </div> -->
                  <CommonSwitch label="在系统浏览器中打开 URL" v-model="formData.open_url_on_system" description="关闭则使用内置科幻浏览器" />
                  <div class="grid grid-cols-2 gap-4">
                    <CommonNumber label="字体大小" description="控制界面字体大小，影响所有控件的内容显示" v-model="formData.ui.font_size" :step="1" :min="8" :max="40" />
                    <CommonNumber label="提示悬停时间" description="控制悬浮提示信息的等待时间，单位是毫秒" v-model="formData.ui.tooltip_hover_time" :step="100" :min="100" :max="5000" />
                    <CommonSwitch label="Mod 悬停面板" v-model="formData.ui.show_mod_hover_panel" description="控制 Mod 列表中悬停时的面板显示。" />
                    <CommonSwitch label="双击启用/停用 Mod" v-model="formData.ui.double_click_active_mod" description="控制 Mod 列表中双击启用/停用 Mod 动作。" />
                    <div class="col-span-2 p-2 rounded-2xl bg-text-main/2 border border-text-main/5 grid grid-cols-2 gap-2">
                      <CommonSwitch class="col-span-2" mini label="Mod 详情面板" v-model="formData.ui.show_mod_details_panel" description="可关闭Mod详情栏。" />
                      <CommonSwitch class="col-span-2" :disabled="!formData.ui.show_mod_details_panel" label="动态图标云" v-model="formData.ui.show_icons_cloud" description="控制详情页闲置时的动态图标云显示。" />
                      
                      <span class="col-span-2 text-xs ml-2 mt-2">Mod 详情布局
                        <label v-tooltip="'可拖动切换布局顺序'" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
                      </span>
                      <VueDraggable class="col-span-2 flex flex-col gap-1 p-2 rounded-xl bg-text-main/5 border border-text-main/10" 
                        ref="el" v-model="formData.ui.mod_details_layout" :animation="150" :disabled="!formData.ui.show_mod_details_panel">
                        <div v-for="item, index in formData.ui.mod_details_layout" class="flex items-center ">
                          <span class="p-1 mr-1 rounded-md bg-accent-primary/30">{{ index }}</span>
                          <CommonSwitch class="flex-1 cursor-move" :disabled="!formData.ui.show_mod_details_panel" :key="item.id" :label="appStore.DETAILS_LAYOUT_MAPS[item.id].label" v-model="item.visible" :description="appStore.DETAILS_LAYOUT_MAPS[item.id].desc" />
                        </div>
                      </VueDraggable>
                      
                    </div>
                    <CommonSwitch label="依赖关系图" v-model="formData.ui.show_dependency_graph" description="控制启用列表中依赖关系图的显示。" />
                    <CommonSwitch label="列表索引" v-model="formData.ui.show_list_index" description="控制列表中索引列的显示。" />
                    <CommonNumber label="拖动判定延迟" description="控制列表项拖动操作的判定延迟，单位是毫秒，默认值为 30 毫秒，为 0 时可能使点击操作出现抖动。" v-model="formData.ui.drag_delay" :step="10" :min="0" :max="500" />
                    <div class="col-span-2 p-2 rounded-2xl bg-text-main/2 border border-text-main/5 grid grid-cols-2 gap-2">
                      <CommonSwitch class="col-span-2" label="列表图标" v-model="formData.ui.show_list_icon" description="控制列表中的所有图标显示，包括简单视图和详细视图。" mini />
                      <CommonSwitch :disabled="!formData.ui.show_list_icon" label="列表 Mod 图标" v-model="formData.ui.show_list_mod_icon" description="控制列表中 Mod 图标显示，不影响详细视图。" />
                      <CommonSwitch :disabled="!formData.ui.show_list_icon" label="列表 Mod 类型图标" v-model="formData.ui.show_list_modtype_icon" description="控制列表中 Mod 类型图标显示，不影响详细视图。" />
                    </div>

                    <CommonSwitch label="分组索引" v-model="formData.ui.show_group_index" description="控制分组列表中Mod索引的显示。" />
                    <CommonSwitch label="分组图标" v-model="formData.ui.show_group_icon" description="控制分组列表中Mod图标的显示。" />
                  </div>
                </div>
              </section>

              <!-- 功能设置 -->
              <section v-if="currentTab === 'features'" class="animate-in fade-in slide-in-from-right-4">
                <h3 class="text-lg font-bold text-text-main mb-6">功能设置</h3>
                <div class="space-y-6">
                  <div class="grid grid-cols-2 gap-4">
                    <CommonSwitch class="col-span-1" label="启动时自动扫描 Mod 目录" v-model="formData.enable_auto_scan" description="关闭后，需要手动点击扫描按钮才能更新 Mod 列表。" />
                    <CommonSwitch class="col-span-1" label="扫描时检查文件大小" v-model="formData.enable_file_size_scan" description="开启后，扫描时会自动检查 Mod 的文件大小，以此识别新增或更新的内容。该功能会增加扫描耗时，但能显著提高文件变动的识别精度。" />
                    <CommonSwitch class="col-span-1" label="自动清理缺失的 Mod 数据" v-model="formData.delete_missing_mods_data" description="关闭后，缺失的 Mod 数据将保留在数据库中，列表内可以重新订阅。" />
                    <CommonSwitch class="col-span-1" label="自动激活依赖项" v-model="formData.auto_activate_dependencies" description="开启后，自动排序时将会自动激活停用的依赖项。" />
                    <CommonSwitch class="col-span-1" label="检查语言支持" v-model="formData.check_language_support" description="开启后，将会在 Mod 问题提示增加“语言支持”警告，提示 Mod 是否支持当前语言。" />
                    <CommonSwitch class="col-span-1" label="显示共存冲突提示" v-model="formData.show_coexistence_message" description="关闭后，将不会显示共存Mod的冲突提示信息。" />
                    <CommonSelect class="col-span-1" label="排序顺序" v-model="formData.sort_mods_by" showBottom
                      description="影响自动排序时同档次的Mod顺序，处理优先级是 别名>原名>包名，所以即使Mod没有别名，也能按原名参与排序。" 
                      :options="[{label:'按别名', value:'alias_name'},{label:'按原名', value:'name'},{label:'按包名', value:'id'}]" />
                    <CommonSelect class="col-span-1" label="共存Mod文件夹生成方式" v-model="formData.coexist_mod_folder_name_type" showBottom
                      description="影响创建共存Mod时的文件夹名称，处理优先级是 别名>原名>包名>工坊ID，所以即使Mod没有别名，也能按原名创建文件夹。" 
                      :options="[{label:'按工坊ID', value:'workshop_id'},{label:'按包名', value:'package_id'},{label:'按原名', value:'name'},{label:'按别名', value:'alias_name'}]" />
                    <CommonNumber class="col-span-1" label="自动备份保留天数" description="管理自动备份的最长保留时间，手动备份不受影响。" v-model="formData.backup_retention_days" :step="1" :min="0" :max="365" />
                  </div>
                </div>
              </section>

              <!-- 社区设置 -->
              <section v-if="currentTab === 'community'" class="animate-in fade-in slide-in-from-right-4">
                <h3 class="text-lg font-bold text-text-main mb-6">社区配置管理</h3>
                <div class="space-y-6">
                  <CommonPathInput label="SteamCMD 路径" v-model="formData.steam.steamcmd_path" @browse="handleBrowse('steamcmd_path')" />
                  <!-- <CommonSwitch label="优先使用 Steam 客户端浏览工坊内容" v-model="formData.steam.use_steam_client" description="开启此项以通过本地 Steam 客户端浏览工坊内容" /> -->
                  <CommonInput label="社区规则 URL" v-model="formData.community_rules_url" />
                  <CommonPathInput label="社区规则路径" v-model="formData.community_rules_path" @browse="handleBrowse('community_rules_path')" />
                  <CommonPathInput label="用户规则路径" v-model="formData.user_rules_path" @browse="handleBrowse('user_rules_path')" />
                </div>
              </section>

              <!-- 网络设置 (Network) -->
              <section v-if="currentTab === 'network'" class="animate-in fade-in slide-in-from-right-4">
                <h3 class="text-lg font-bold text-text-main mb-6">网络协议与代理</h3>
                <div class="space-y-8">
                   <div class="p-4 rounded-2xl bg-text-main/2 border border-text-main/5 space-y-6">
                      <CommonSwitch label="启用代理服务" v-model="formData.network.proxy.enabled" />
                      <div v-if="formData.network.proxy.enabled" class="grid grid-cols-6 gap-3 animate-in zoom-in-95">
                        <CommonSelect class="col-span-2" label="协议" v-model="formData.network.proxy.type" :options="[{label:'HTTP', value:'http'},{label:'SOCKS5', value:'socks5'}]" />
                        <CommonInput class="col-span-3" label="主机地址" v-model="formData.network.proxy.host" placeholder="127.0.0.1" />
                        <CommonNumber class="col-span-1" label="端口" v-model="formData.network.proxy.port" :step="1" :min="1" :max="65535" />
                        <CommonInput class="col-span-3" label="用户名" v-model="formData.network.proxy.username" />
                        <CommonInput class="col-span-3" label="密码" v-model="formData.network.proxy.password" is-password />
                        <div class="col-span-6">
                           <CommonTagInput label="不走代理的域名 (Bypass)" v-model="formData.network.proxy.bypass_list" />
                        </div>
                      </div>
                   </div>
                   <CommonKVEditor label="自定义 Hosts 映射" v-model="formData.network.hosts" />
                </div>
              </section>

              <!-- AI 设置 (AI) -->
              <section v-if="currentTab === 'ai'" class="animate-in fade-in slide-in-from-right-4">
                <div class="mb-6 flex items-center justify-between">
                  <h3 class="text-lg font-bold text-text-main flex items-center gap-2">
                    人工智能
                    <span class="px-2 py-0.5 rounded bg-accent-special/20 text-accent-special text-xs font-black uppercase">实验性</span>
                  </h3>

                  <button v-if="formData.ai.enabled" @click="appStore.uiState.showPromptManager = true"
                    class="px-4 py-1.5 rounded-lg bg-accent-special/10 hover:bg-accent-special/20 text-accent-special border border-accent-special/30 text-xs font-bold transition-colors flex items-center gap-2">
                    <Drama class="size-4" /> 提示词管理
                  </button>
                </div>
                <div class="space-y-6">
                  <CommonSwitch label="启用 AI 辅助" v-model="formData.ai.enabled" description="用于日志分析、概述模组等功能" />
                  <div v-if="formData.ai.enabled" class="space-y-6 animate-in slide-in-from-top-2">
                      
                    <!-- 2. 动态表单区 -->
                    <div class="p-4 rounded-xl bg-text-main/5 border border-text-main/10 space-y-5">
                      <!-- 1. API 模式切换器 -->
                      <div class="flex bg-black/40 p-1.5 rounded-lg border border-text-main/10 w-fit gap-1">
                        <button @click="handleApiTypeChange('official')" 
                          class="px-4 py-1 rounded-md text-sm font-bold transition-all duration-300"
                          :class="formData.ai.api_type === 'official' ? 'bg-accent-special text-black shadow-[0_0_15px_rgba(var(--color-accent-special),0.4)]' : 'text-text-dim hover:text-text-main'">
                          官方原生 API
                        </button>
                        <button @click="handleApiTypeChange('custom')" 
                          class="px-4 py-1 rounded-md text-sm font-bold transition-all duration-300"
                          :class="formData.ai.api_type === 'custom' ? 'bg-accent-special text-black shadow-[0_0_15px_rgba(var(--color-accent-special),0.4)]' : 'text-text-dim hover:text-text-main'">
                          自定义代理 / 本地部署
                        </button>
                      </div>
                      <div class="grid grid-cols-2 gap-3">
                        <!-- 厂商/协议选择 -->
                        <CommonSelect :label="formData.ai.api_type === 'official' ? '服务提供商' : '接口协议标准'" 
                          v-model="formData.ai.provider" :options="currentAiProviders" @change="handleProviderChange"/>
                        <!-- 模型选择 (带刷新动作) -->
                        <div class="relative flex items-end gap-2">
                          <div class="flex-1">
                            <!-- 加上 editable 允许用户手输未被探测到的模型名 -->
                            <CommonSelect label="选择模型"  editable v-model="formData.ai.model" :options="currentAiModels" 
                              placeholder="下拉选择或手动输入模型名" @visible-change="(val) => val && fetchAiModels()"/>
                          </div>
                          <!-- 对于自定义模式，提供显式的刷新按钮让用户主动拉取 -->
                          <button v-if="formData.ai.api_type === 'custom'" @click="fetchAiModels" v-tooltip="'重新从 Base URL 获取模型列表'" 
                            class="h-9 px-3 bg-black/30 hover:bg-accent-special/20 text-accent-special border border-accent-special/30 rounded-lg flex items-center justify-center transition-colors">
                            <svg class="size-4" :class="{'animate-spin': appStore.aiState.isLoading}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 21v-5h5"/></svg>
                          </button>
                        </div>

                        <!-- Base URL (自定义必填，官方高级选填) -->
                        <CommonInput label="Base URL" v-model="formData.ai.base_url" class="col-span-2" 
                          :placeholder="formData.ai.api_type === 'custom' ? '例如: http://127.0.0.1:11434 或 https://api.deepseek.com/v1' : '默认官方地址，除非使用反代否则留空'" 
                          :description="formData.ai.api_type === 'custom' ? '填写代理服务器或本地工具(如 LM Studio/Ollama)的地址。' : '高级选项：如果您使用了 Cloudflare Worker 等进行反代，请填入。'"
                        />
                        <!-- API Key -->
                        <CommonInput label="API Key" v-model="formData.ai.api_key" is-password class="col-span-2" 
                        :placeholder="formData.ai.api_type === 'custom' ? '本地部署通常留空，中转 API 必填' : 'sk-...'" 
                        />
                      </div>

                    </div>

                    <!-- 3. 测试与高级参数区 -->
                    <div class="grid grid-cols-2 gap-4">
                      <CommonNumber label="最大 Token 限制" v-model="formData.ai.max_tokens" :step="100" :min="500" />
                      <CommonNumber label="最大并发限制" v-model="formData.ai.max_concurrency" :step="1" :min="1" :max="100" description="同时处理的请求数，建议根据 API 限制设为 3-5 之间。" />
                      <CommonNumber label="输出随机性" v-model="formData.ai.temperature" :step="0.1" :min="0" :max="2.0" description="值 (Temperature) 越高创造性越强，越低越严谨。推荐0.7左右。" />
                      
                      <!-- 测试区 -->
                      <div class="col-span-2 pt-2 border-t border-text-main/5 flex gap-3">
                        <CommonInput label="测试输入" class="flex-1" v-model="testPrompt" placeholder="简单输入一句话测试连接 (如：你是谁？)" @keydown.enter="testModel"></CommonInput>
                        <button class="mt-[1.3rem] flex items-center justify-center bg-accent-special/70 hover:bg-accent-special hover:text-text-main text-text-dim px-6 py-2 rounded-lg font-bold transition-all" 
                          :class="[appStore.aiState.isLoading?'cursor-not-allowed pointer-events-none opacity-50':'cursor-pointer']"
                          @click="testModel">
                          <svg v-if="appStore.aiState.isLoading" class="animate-spin size-4 mr-2" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                          发起测试
                        </button>
                      </div>
                      <div v-if="testResponse" class="col-span-2 p-4 rounded-xl text-text-main/80 bg-accent-special/10 border border-text-main/10 relative">
                        <button @click="testResponse=''" class="absolute top-2 right-2 text-text-dim hover:text-text-main">×</button>
                        <div class="text-xs text-text-dim mb-1 font-bold">AI 响应结果：</div>
                        <div class="text-sm whitespace-pre-wrap leading-relaxed">{{ testResponse }}</div>
                      </div>
                    </div>
                  </div>
                </div>
              </section>

              <!-- 开发与调试 -->
              <section v-if="currentTab === 'dev'" class="animate-in fade-in slide-in-from-right-4">
                <h3 class="text-lg font-bold text-text-main mb-6">开发与调试</h3>
                <div class="space-y-6">
                  <div class="grid grid-cols-2 gap-4">
                    <CommonSwitch class="col-span-2" label="调试模式" v-model="formData.debug_mode" description="开启调试模式后重启软件将会出现开发者工具窗口，可查看问题详情。" />
                    <CommonSwitch class="col-span-1" label="自动检查更新" v-model="formData.enable_auto_update_check" description="关闭后，需要手动点击检查更新按钮才能更新 RimModManager。" />
                    <!-- 手动检查按钮 -->
                    <div class="flex items-center justify-between p-3 input-glass">
                      <div class="flex flex-col">
                        <span class="text-sm font-bold text-text-main">软件版本</span>
                        <span class="text-xs text-text-dim">当前版本: v{{ appStore.appVersion }}</span>
                      </div>
                      <button 
                        @click="appStore.checkUpdate(true)" 
                        :disabled="appStore.updateState.isChecking"
                        class="px-4 py-1.5 bg-text-main/5 hover:bg-text-main/10 border border-text-main/10 rounded-lg text-xs font-bold transition-all"
                      >
                        <span v-if="appStore.updateState.isChecking" class="flex items-center gap-2">
                          <svg class="animate-spin h-3 w-3" viewBox="0 0 24 24">...</svg>检查中
                        </span>
                        <span v-else>立即检查更新</span>
                      </button>
                    </div>
                    <CommonSelect label="日志等级" v-model="formData.log_level" :options="[{label:'DEBUG', value:'DEBUG'},{label:'INFO', value:'INFO'},{label:'WARNING', value:'WARNING'}]" />
                    <CommonNumber label="日志保留天数" v-model="formData.log_retention_days" :step="1" :min="0" :max="365" />
                  </div>
                  <div class="p-6 rounded-2xl bg-accent-danger/5 border border-accent-danger/20 space-y-4">
                    <h4 class="text-sm font-bold text-accent-danger uppercase">危险操作区</h4>
                    <p class="text-xs text-accent-danger/60 leading-relaxed">重置操作将清空所有本地数据库缓存、分组信息和自定义备注。该操作不可撤销，请确保已备份您的 Mod 列表。</p>
                    <button @click="handleReset" class="w-full py-2 bg-accent-danger/10 hover:bg-accent-danger text-accent-danger hover:text-text-main border border-accent-danger/30 rounded-lg text-xs font-bold transition-all">
                      立即重置本地数据库
                    </button>
                  </div>
                </div>
              </section>

            </div>
          </div>

          <!-- D. 底部操作栏 -->
          <footer class="h-20 flex items-center justify-end px-10 gap-4 border-t border-text-main/5 bg-text-main/2">
             <button id="btn-cancel" @click="appStore.closeSettingsPanel()" class="text-sm font-bold text-text-dim hover:text-text-main transition-colors">放弃修改</button>
             <button @click="save" class="relative overflow-hidden px-8 py-2.5 bg-accent-primary rounded-xl text-black font-black text-sm shadow-[0_0_20px_rgba(6,182,212,0.3)] hover:scale-105 active:scale-95 transition-all group">
                <div class="absolute inset-0 bg-text-main/20 -translate-x-full group-hover:translate-x-full transition-transform duration-500 skew-x-12"></div>
                应用并保存配置
             </button>
          </footer>
        </main>

      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, watch, onMounted, nextTick, h } from 'vue'
import { FolderTree, AppWindow, Globe, Cpu, Terminal, Search, Component, Settings, Drama } from 'lucide-vue-next'
import { useAppStore } from '../stores/appStore'
import { useConfirmStore } from '../stores/confirmStore'
import { createToastInterface } from 'vue-toastification'
import { flashComponent, shakeComponent } from '../utils/uiHelper'
import { VueDraggable } from 'vue-draggable-plus'

// 导入 Common UI
import CommonPathInput from './common/input/CommonPathInput.vue'
import CommonSwitch from './common/input/CommonSwitch.vue'
import CommonInput from './common/input/CommonInput.vue'
import CommonNumber from './common/input/CommonNumber.vue'
import CommonSelect from './common/input/CommonSelect.vue'
import CommonTagInput from './common/input/CommonTagInput.vue'
import CommonKVEditor from './common/input/CommonKVEditor.vue'
import { color } from 'motion-v'
import { RUN_COMMAND_TAGS } from '../utils/constants'

const toast = createToastInterface()
const appStore = useAppStore()
const confirmStore = useConfirmStore()

const currentTab = ref('paths')
const formData = ref({})

const Steam = h('svg', { viewBox: "0 0 448 512", fill: "currentColor" }, 
  [ h('path', { d: "M273.5 177.5a61 61 0 1 1 122 0 61 61 0 1 1 -122 0zm174.5 .2c0 63-51 113.8-113.7 113.8L225 371.3c-4 43-40.5 76.8-84.5 76.8-40.5 0-74.7-28.8-83-67L0 358 0 250.7 97.2 290c15.1-9.2 32.2-13.3 52-11.5l71-101.7C220.7 114.5 271.7 64 334.2 64 397 64 448 115 448 177.7zM203 363c0-34.7-27.8-62.5-62.5-62.5-4.5 0-9 .5-13.5 1.5l26 10.5c25.5 10.2 38 39 27.7 64.5-10.2 25.5-39.2 38-64.7 27.5-10.2-4-20.5-8.3-30.7-12.2 10.5 19.7 31.2 33.2 55.2 33.2 34.7 0 62.5-27.8 62.5-62.5zM410.5 177.7a76.4 76.4 0 1 0 -152.8 0 76.4 76.4 0 1 0 152.8 0z" })]
)

const tabs = [
  { id: 'paths', label: '路径配置', icon: FolderTree },
  { id: 'general', label: '界面设置', icon: AppWindow },
  { id: 'features', label: '功能设置', icon: Component },
  { id: 'community', label: '社区配置', icon: Steam },
  { id: 'network', label: '网络连接', icon: Globe },
  { id: 'ai', label: 'AI 集成', icon: Cpu },
  { id: 'dev', label: '开发调试', icon: Terminal },
]

const currentAiProviders = ref([])  // AI厂商或代理协议列表
const currentAiModels = ref([])     // 当前AI的模型列表

// 数据同步：打开时深度拷贝
watch(() => appStore.uiState.showSettingsPanel, (val) => {
  if (val) {
    // 利用 requestAnimationFrame 或 setTimeout
    // 让浏览器先渲染出弹窗的“背景”和“动画第一帧”，然后再去塞数据
    requestAnimationFrame(async () => {
      // 使用 structuredClone (Node 17+ / 现代浏览器均支持，速度更快)
      // 如果环境不支持，保留原来的 JSON 方式，但放在 requestAnimationFrame 里依然能解决卡顿
      try {
        formData.value = structuredClone(appStore.settings)
      } catch (e) {
        // 降级兼容
        formData.value = JSON.parse(JSON.stringify(appStore.settings))
      }

      // 如果 AI 已启用，且面板刚打开，加载初始的厂商和模型列表
      if (formData.value.ai) {
        await loadAiProviders(formData.value.ai.api_type)
        if (formData.value.ai.provider) {
          await fetchAiModels()
        }
      }

    })
  }
})


const autoDetect = async () => {
  const paths = await appStore.autoDetectPaths(false)
  if (paths) Object.assign(formData.value, paths)
  // 自动获取游戏信息
  checkGamePath()
}

const checkGamePath = async () => {
  const gameInfo = await appStore.getGameInfo(formData.value.game_install_path)
  if (!gameInfo || !gameInfo.exe) {
    // 游戏版本为空时
    formData.value['game_info'] = `^^未找到游戏可执行文件，请检查路径是否正确！^^`
    return
  }
  formData.value['local_mods_path'] = formData.value.game_install_path + '\\Mods'
  formData.value['game_info'] = `游戏版本: ${gameInfo.version}\n游戏路径: ${gameInfo.exe}`
}

const handleGameBrowse = async () => {
  let current = formData.value
  const res = await appStore.getFolderPath(current['game_install_path'])
  if (res) {
    current['game_install_path'] = res
    // 自动获取游戏信息
    checkGamePath()
  }

}
const handleBrowse = async (pathKey) => {
  // 处理嵌套路径 (如 'steam.steamcmd_path')
  const keys = pathKey.split('.')
  let current = formData.value
  for (let i = 0; i < keys.length - 1; i++) {
    current = current[keys[i]]
  }
  const lastKey = keys[keys.length - 1]
  
  const res = await appStore.getFolderPath(current[lastKey])
  if (res) {
    current[lastKey] = res
  }

}

// ======= AI 集成 ======
// 测试提示词
const testPrompt = ref("介绍一下自己")
const testResponse = ref("")
// 测试模型
const testModel = async () => {
  const res = await appStore.chatWithAI(testPrompt.value, formData.value.ai)
  if (res) {
    testResponse.value = res
    // console.log("模型测试结果:", res)
    toast.success("模型测试成功")
  }
}

// 切换 API 模式 (Official <-> Custom)
const handleApiTypeChange = async (type) => {
  formData.value.ai.api_type = type
  formData.value.ai.provider = '' // 清空原厂选择
  formData.value.ai.model = ''    // 清空原模型
  currentAiModels.value = []
  await loadAiProviders(type)
}
// 切换厂商/协议时，如果是官方模式，立即获取模型；若是代理模式，清空让用户重新获取
const handleProviderChange = async () => {
  formData.value.ai.model = ''
  if (formData.value.ai.api_type === 'official') {
    await fetchAiModels()
  } else {
    currentAiModels.value = [] // 代理模式需要base_url，等用户填好自己点下拉框获取
  }
}
// 加载厂商列表
const loadAiProviders = async (api_type) => {
  const providers = await appStore.getAiProviders(api_type)
  currentAiProviders.value = providers || []
}
// 拉取模型列表 (兼容旧的，组装为 CommonSelect 接受的结构)
const fetchAiModels = async () => {
  const models = await appStore.getAiModels(formData.value.ai)
  if (models) {
    currentAiModels.value = models.map(m => ({ value: m, label: m }))
  } else {
    currentAiModels.value = []
  }
}


// ====== 数据处理 ======
const handleReset = async () => {
  const ok = await confirmStore.confirmAction('确认重置', '这将抹除所有本地缓存数据，确定继续？', { type: 'error' })
  if (ok) appStore.resetDatabase()
}

const save = () => {
  appStore.applySettings(formData.value)
}
</script>

<style scoped>
.cubic-bezier {
  transition-timing-function: cubic-bezier(0.37, 1.95, 0.66, 0.56);
}

.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 10px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: var(--color-accent-primary);
}

/* 页面切换动画 */
.panel-fade-enter-active, .panel-fade-leave-active { transition: opacity 0.4s ease; }
.panel-fade-enter-from, .panel-fade-leave-to { opacity: 0; }

/* 简单的类名修复，如果 Tailwind 不支持 */
.direction-rtl { direction: rtl; }
</style>