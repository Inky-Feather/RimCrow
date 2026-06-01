<template>
  <CommonModalShell :show="appStore.uiState.showSettingsPanel" persistent
    :show-header="false" :close-on-backdrop="false" size="custom" :z-index="100"
    accent="primary"
    panel-class="w-[75%] h-[80%] border-border-base/18" content-class="h-full flex"
    @backdrop="shakeComponent('#btn-cancel')"
    @close="shakeComponent('#btn-cancel')"
  >
        
        <!-- A. 装饰光效 -->
        <div class="absolute -top-24 -left-24 w-64 h-64 bg-accent-primary/10 blur-3xl rounded-full pointer-events-none"></div>
        <div class="absolute -bottom-24 -right-24 w-64 h-64 bg-accent-special/10 blur-3xl rounded-full pointer-events-none"></div>

        <!-- B. 左侧导航栏 -->
        <aside class="w-45 border-r bg-bg-muted border-border-base/5 flex flex-col p-6 relative z-10">
          <div class="mb-10 px-2">
            <h2 class="text-xl font-black text-text-main tracking-tighter italic">系统 <span class="text-accent-primary">设置</span></h2>
          </div>

          <!-- 动态 Glider 导航 -->
          <nav class="flex flex-col relative space-y-1" :style="{ '--total-tabs': tabs.length }">
            <button v-for="(tab, index) in tabs" :key="tab.id" :data-tour="`settings-tab-${tab.id}`"
              class="relative z-10 flex items-center gap-3 px-4 py-3 text-md font-bold transition-all duration-300 group"
              :class="currentTab === tab.id ? 'text-accent-primary' : 'text-text-dim hover:text-text-dim'"
              @click="changeTab(tab.id)" >
              <component :is="tab.icon" class="size-4" />
              <span>{{ tab.label }}</span>
            </button>

            <!-- 物理 Glider 滑块 -->
            <div class="glider-container absolute left-0 top-0 w-full h-full pointer-events-none">
              <div class="glider absolute -left-6 w-1 h-11 bg-accent-primary brightness-120 shadow-[0_0_15px_rgba(var(--rgb-accent-primary),0.75)] transition-transform duration-500 cubic-bezier"
                :style="{ transform: `translateY(${tabs.findIndex(t => t.id === currentTab) * 2.85}rem)` }">
                <!-- 侧边发光层 -->
                <div class="absolute left-0 top-0 w-40 h-full bg-linear-to-r from-accent-primary/10 to-transparent"></div>
              </div>
            </div>
          </nav>

          <!-- 底部版本号 -->
          <div class="mt-auto px-4 py-2 border-t border-border-base/5 opacity-30">
            <p class="text-xs font-mono text-text-dim">V{{ appStore.appVersion }}</p>
          </div>
        </aside>

        <!-- C. 右侧主内容区 -->
        <main class="flex-1 flex flex-col min-w-0 bg-bg-deep relative z-10">
          <!-- 顶部状态条 -->
          <header class="h-14 flex items-center justify-between px-8 border-b border-border-base/5">
            <span class="text-xs font-mono text-text-disabled uppercase tracking-[0.3em]">
              / root / {{ currentTabLabel }}
            </span>
            <div class="flex gap-1.5 text-text-disabled relative">
              <Settings class="absolute size-23 -top-16 -right-13" />
            </div>
          </header>

          <!-- 内容滚动容器 -->
          <div class="flex-1 overflow-y-auto p-8 custom-scrollbar">
            <div class=" mx-auto space-y-10">

              <!-- 路径设置 (Paths) -->
              <section v-if="currentTab === 'paths'" class="animate-in fade-in slide-in-from-right-4">
                <div class="flex items-center justify-between mb-6">
                  <h3 class="text-lg font-bold text-text-main">环境与路径配置
                    <label v-tooltip="'此处会直接修改当前环境的路径配置'" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
                    <label class="ml-5 text-xs py-0.5 px-2 text-accent-cool bg-accent-cool/20 rounded-md" v-tooltip="`当前环境：${profileStore?.currentProfile?.name}\n说明：${profileStore?.currentProfile?.description}`">
                      {{ profileStore?.currentProfile?.name }}
                    </label>
                  </h3>
                  <button @click="autoDetect" v-tooltip="'尝试通过注册表自动搜索路径'" class="px-3 py-1 bg-accent-success/10 hover:bg-accent-success/20 border border-accent-success/30 rounded text-xs font-bold text-accent-success transition-all">
                    自动搜索路径
                  </button>
                </div>
                <div class="grid gap-6">
                  <CommonPathInput label="游戏安装目录" v-model="formData.game_install_path" @browse="handleGameBrowse('game_install_path')" 
                    :check="formData.check_info?.game_install_path"
                    :description="'游戏安装目录即游戏主程序所在的目录，默认安装目录一般位于：\nC:/Program Files (x86)/Steam/steamapps/common/RimWorld'" 
                    @blur="checkPath('game_install_path', formData.game_install_path)"/>
                  <CommonPathInput label="用户数据目录" v-model="formData.user_data_path" @browse="handleBrowse('user_data_path')" 
                    :check="formData.check_info?.user_data_path"
                    :description="'用户数据目录即游戏数据及存档所在的目录，默认配置目录一般位于：\nC:/Users/{用户名}/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios'" 
                    @blur="checkPath('user_data_path', formData.user_data_path)"/>
                  <!-- <CommonPathInput label="游戏配置目录" v-model="formData.game_config_path" @browse="handleBrowse('game_config_path')" 
                    :check="formData.check_info?.game_config_path"
                    :description="'游戏配置目录即排序文件（ModsConfig.xml）所在的目录，默认配置目录一般位于：\nC:/Users/{用户名}/AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Config'" 
                    @blur="checkPath('game_config_path', formData.game_config_path)"/> -->
                  <CommonPathInput label="创意工坊目录" v-model="formData.workshop_mods_path" @browse="handleBrowse('workshop_mods_path')" 
                    :check="formData.check_info?.workshop_mods_path"
                    :description="'创意工坊目录即创意工坊下载的模组所在的目录，该设置所有环境通用'" 
                    @blur="checkPath('workshop_mods_path', formData.workshop_mods_path)"/>
                  <CommonPathInput label="本地模组目录" v-model="formData.local_mods_path" readOnly @browse="handleBrowse('local_mods_path')" description="根据游戏安装目录自动生成" />
                  <CommonTagInput label="游戏启动参数" v-model="formData.run_commands" :allTags="RUN_COMMAND_TAGS" placeholder="请输入一个完整指令后回车确认……" description="注意不要使用 [[-savedatafolder]] 指令，多环境管理已经默认使用此指令，无需手动配置。" />
                  <div class="modal-section grid grid-cols-1 gap-2 p-3">
                    <CommonPathInput label="Steam程序路径" :check="formData.check_info?.steam_path"
                      :description="'Steam程序路径即Steam.exe所在的目录，默认路径一般位于：\nC:/Program Files (x86)/Steam'" 
                      v-model="formData.steam_path" @browse="handleBrowse('steam_path')" @blur="checkPath('steam_path', formData.steam_path)"
                    />
                    <div class="grid grid-cols-2 gap-2">
                      <CommonSwitch label="优先使用 Steam 启动" :disabled="steamLaunchDisabled" v-model="formData.prefer_steam_launch" description="适用于 Steam 版游戏。开启后，管理器会优先通过 Steam 启动当前环境，并直接使用 Steam 中的创意工坊内容。" />
                      <CommonSwitch label="使用创意工坊 Mod" :disabled="workshopModsDisabled" v-model="formData.use_workshop_mods" description="适用于非 Steam 版环境。开启后，管理器会把创意工坊模组接入当前环境的本地模组目录，这样直接启动游戏本体时也能使用这些模组。" />
                    </div>
                  </div>
                  <div class="modal-section grid grid-cols-2 gap-2 p-3">
                    <h3 class="col-span-2 text-sm font-bold ml-1 text-text-main">管理器模组</h3>
                    <CommonPathInput class=" col-span-2" label="管理器下载模组路径" :check="formData.check_info?.self_mods_path"
                      :description="'由管理器下载的模组所在的目录，可自定义位置，如果将其设为游戏本地模组路径，请关闭该使用开关。'" 
                      v-model="formData.self_mods_path" @browse="handleBrowse('self_mods_path')" @blur="checkPath('self_mods_path', formData.self_mods_path)"
                    />
                    <CommonSwitch label="使用管理器模组" v-model="formData.use_self_mods" description="开启后将通过链接方式自动为游戏加载管理器Mod。" />
                    <CommonSwitch label="改变路径时移动模组" v-model="formData.move_old_self_mods" description="开启后，修改路径时会将原有模组移动到新路径；不开启则保留原有的文件结构。" />
                    <CommonSwitch class="col-span-1" label="自动检查管理器模组更新" v-model="formData.enable_auto_steamcmd_mod_update_check" description="按设定间隔检查管理器模组目录中由 SteamCMD 下载的工坊模组更新。" />
                    <div class="col-span-1 grid grid-cols-2 gap-3 items-end">
                      <CommonNumber class="col-span-1" label="检查间隔（天）" v-model="formData.steamcmd_mod_update_check_interval_days" :step="1" :min="1" :max="365" />
                      <button @click="handleCheckSteamcmdMods" class="px-3 py-1.5 mx-2 my-1 h-8 bg-accent-warn/10 hover:bg-accent-warn/25 border border-accent-warn/20 rounded-lg text-xs font-bold transition-all"> 检查更新 </button>
                    </div>
                  </div>
                  <div class="modal-section grid grid-cols-2 gap-2 p-3">
                    <h3 class="col-span-2 text-sm font-bold ml-1 text-text-main">排序导入/导出 起始选择窗口配置</h3>
                    <CommonSelect class="col-span-1" label="导入起始目录" v-model="formData.load_order_import_dir_mode"
                      :description="'控制“导入加载序列”文件选择器的选择窗口初始目录。默认模式始终使用当前环境用户数据目录下的 ModLists；记忆模式使用上次成功导入的目录；自定义模式使用下方固定目录。'"
                      :options="LOAD_ORDER_DIR_MODE_OPTIONS"
                    />
                    <CommonSelect class="col-span-1" label="导出起始目录" v-model="formData.load_order_export_dir_mode"
                      :description="'控制“导出加载序列”文件选择器的选择窗口初始目录。默认模式保持当前环境备份目录的 other 子目录；记忆模式使用上次成功导出的目录；自定义模式使用下方固定目录。'"
                      :options="LOAD_ORDER_DIR_MODE_OPTIONS"
                    />
                    <CommonPathInput v-if="formData.load_order_import_dir_mode === 'custom'" class="col-span-2" label="自定义导入起始目录" v-model="formData.load_order_import_custom_path"
                      :check="formData.check_info?.load_order_import_custom_path" :description="'仅在导入目录模式为“自定义”时生效；若路径无效，运行时会自动回退到默认目录。'"
                      @browse="handleBrowse('load_order_import_custom_path')" @blur="checkPath('load_order_import_custom_path', formData.load_order_import_custom_path)"
                    />
                    <CommonPathInput v-if="formData.load_order_export_dir_mode === 'custom'" class="col-span-2" label="自定义导出起始目录" v-model="formData.load_order_export_custom_path"
                      :check="formData.check_info?.load_order_export_custom_path" :description="'仅在导出目录模式为“自定义”时生效；若路径无效，运行时会自动回退到默认目录。'"
                      @browse="handleBrowse('load_order_export_custom_path')" @blur="checkPath('load_order_export_custom_path', formData.load_order_export_custom_path)"
                    />
                  </div>
                  <!-- <CommonPathInput label="主目录" v-model="formData.home_path" @browse="handleBrowse('home_path')" /> -->
                </div>
              </section>

              <!-- 常规设置 (General) -->
              <section v-if="currentTab === 'general'" class="animate-in fade-in slide-in-from-right-4">
                <h3 class="text-lg font-bold text-text-main mb-6 flex items-center justify-between">界面与布局
                  <button @click="guideStore.resetAllGuides()" v-tooltip="'重置界面引导，将界面引导重置为默认值'" class="px-3 py-1 bg-accent-warn/10 hover:bg-accent-warn/20 border border-accent-warn/30 rounded text-xs font-bold text-accent-warn transition-all">
                    重置界面引导
                  </button>
                </h3>
                <div class="space-y-6">
                  <div class="grid grid-cols-2 gap-4">
                    <CommonSelect class="pointer-events-none opacity-50" label="界面语言" v-model="formData.language" :options="[{label:'简体中文', value:'zh-CN'}, {label:'English', value:'en'}]" />
                    <ThemeSelect v-if="formData.ui" v-model="currentThemeId" :themes="appStore.themes"
                      @create="openThemeCreate" @edit="openThemeEdit" @delete="handleThemeDelete"
                    />
                  </div>
                  <CommonSwitch label="在系统浏览器中打开 URL" v-model="formData.open_url_on_system" description="关闭则使用内置浏览器" />
                  <div class="grid grid-cols-2 gap-4">
                    <CommonNumber label="字体大小" description="控制界面字体大小，影响所有控件的内容显示" v-model="formData.ui.font_size" :step="1" :min="8" :max="40" />
                    <CommonNumber label="提示悬停时间" description="控制悬浮提示信息的等待时间，单位是毫秒" v-model="formData.ui.tooltip_hover_time" :step="100" :min="100" :max="5000" />
                    <CommonNumber label="拖动判定延迟" description="控制列表项拖动操作的判定延迟，单位是毫秒，默认值为 30 毫秒，为 0 时可能使点击操作出现抖动。" v-model="formData.ui.drag_delay" :step="10" :min="0" :max="500" />
                    <div></div>
                    
                    <div class="modal-section col-span-2 grid grid-cols-2 gap-2 p-2">
                      <span class="col-span-2 ml-2 mt-2 text-sm font-bold tracking-wide">列表设定
                        <label v-tooltip="'可调整列表的显示方式与辅助功能'" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
                      </span>
                      <CommonSwitch label="Mod 悬停面板" v-model="formData.ui.show_mod_hover_panel" description="控制 Mod 列表中悬停时的面板显示。" />
                      <CommonSwitch label="双击启用/停用 Mod" v-model="formData.ui.double_click_active_mod" description="控制 Mod 列表中双击启用/停用 Mod 动作。" />
                      <CommonSwitch label="依赖关系图" v-model="formData.ui.show_dependency_graph" description="控制启用列表中依赖关系图的显示。" />
                      <CommonSwitch label="列表索引" v-model="formData.ui.show_list_index" description="控制列表中索引列的显示。" />
                    </div>

                    <div class="modal-section col-span-2 grid grid-cols-2 gap-2 p-2">
                      <CommonSwitch class="col-span-2 px-2 pt-2" label="列表图标" v-model="formData.ui.show_list_icon" description="控制列表中的所有图标显示，包括简单视图和详细视图。" mini />
                      <CommonSwitch :disabled="!formData.ui.show_list_icon" label="列表 Mod 图标" v-model="formData.ui.show_list_mod_icon" description="控制列表中 Mod 图标显示，不影响详细视图。" />
                      <CommonSwitch :disabled="!formData.ui.show_list_icon" label="列表 Mod 类型图标" v-model="formData.ui.show_list_modtype_icon" description="控制列表中 Mod 类型图标显示，不影响详细视图。" />
                    </div>
                    <div class="modal-section col-span-2 grid grid-cols-2 gap-2 p-2">
                      <CommonSwitch class="col-span-2 px-2 pt-2" mini label="列表分类折叠" v-model="formData.ui.enable_active_section_collapse" description="仅在启用列表生效。名称或别名满足 `=标题=` 或 `/*标题*/` 的纯标题模组会被识别为可折叠分类标题；折叠后拖动标题即整组拖动。^^可工坊订阅 [[分类排列标签合集]] 配合使用。^^" />
                      <CommonSwitch :disabled="!formData.ui.enable_active_section_collapse" label="默认折叠" v-model="formData.ui.default_collapse_active_sections" description="开启后，启用列表中的标题分组会在初始显示时默认折叠。" />
                      <div class="flex items-center gap-1" :class="{'pointer-events-none opacity-50': !formData.ui.enable_active_section_collapse}">
                        <button @click="appStore.openSteamWorkshopById('2138932352')"
                          class="px-2 py-1.5 bg-bg-overlay/5 hover:bg-bg-overlay/10 border border-border-base/10 rounded-lg text-xs font-bold cursor-pointer transition-all">
                          <span class="flex items-center gap-2">
                            访问<p class="text-accent-cool">分类排列标签合集</p>工坊页面
                          </span>
                        </button>
                        <button @click="appStore.openSteamWorkshopById('3542535605')"
                          class="px-2 py-1.5 bg-bg-overlay/5 hover:bg-bg-overlay/10 border border-border-base/10 rounded-lg text-xs font-bold cursor-pointer transition-all">
                          <span class="flex items-center gap-2">
                            访问<p class="text-accent-cool">分类排序合集</p>工坊页面
                          </span>
                        </button>
                      </div>
                    </div>
                    
                    <div class="modal-section col-span-2 grid grid-cols-2 gap-2 p-2">
                      <span class="col-span-2 ml-2 mt-2 text-sm font-bold tracking-wide">分组设定
                        <label v-tooltip="'可调整分组列表的显示方式'" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
                      </span>
                      <CommonSwitch label="分组索引" v-model="formData.ui.show_group_index" description="控制分组列表中Mod索引的显示。" />
                      <CommonSwitch label="分组图标" v-model="formData.ui.show_group_icon" description="控制分组列表中Mod图标的显示。" />
                    </div>
                    <div class="modal-section col-span-2 grid grid-cols-2 gap-2 p-2">
                      <span class="col-span-2 ml-2 mt-2 text-sm font-bold tracking-wide">主页布局
                        <label v-tooltip="'可拖动切换布局顺序'" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
                      </span>
                      <div class="col-span-2 flex gap-1">
                        <div v-for="item, index in formData.ui.main_layout" :key="item.id"
                          class="flex items-center transition-transform duration-150"
                          :class="getLayoutDragClass('main_layout', index)"
                          draggable="true"
                          @dragstart="handleLayoutDragStart('main_layout', index, $event)"
                          @dragover.prevent="handleLayoutDragOver('main_layout', index)"
                          @drop.prevent="handleLayoutDrop('main_layout', index)"
                          @dragend="handleLayoutDragEnd">
                          <CommonSwitch class="flex-1 cursor-move" :key="item.id" :label="appStore.MAIN_LAYOUT_MAPS[item.id].label" v-model="item.visible" :description="appStore.MAIN_LAYOUT_MAPS[item.id].desc" />
                        </div>
                      </div>
                      
                    </div>

                    <div class="modal-section col-span-2 grid grid-cols-2 gap-2 p-2">
                      <CommonSwitch class="col-span-2 px-2 pt-2" mini label="Mod 详情面板" v-model="getDataById('details', formData.ui.main_layout).visible" description="可关闭Mod详情栏。" />
                      <CommonSwitch :disabled="!getDataById('details', formData.ui.main_layout).visible" label="动态图标云" v-model="formData.ui.show_icons_cloud" description="控制详情页闲置时的动态图标云显示。" />
                      <CommonNumber label="详情页加载延迟" description="控制 Mod 详情页加载的延迟时间，单位是毫秒，默认值为 200 毫秒。" v-model="formData.ui.detail_delay" :step="10" :min="0" :max="5000" />
                      <span class="col-span-2 text-xs ml-2 mt-2">Mod 详情布局
                        <label v-tooltip="'可拖动切换布局顺序'" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
                      </span>
                      <div class="col-span-2 flex flex-col gap-1 p-2 rounded-xl bg-bg-deep/10 border border-border-base/10"
                        :class="{ 'pointer-events-none opacity-50': !getDataById('details', formData.ui.main_layout).visible }">
                        <div v-for="item, index in formData.ui.mod_details_layout" :key="item.id"
                          class="flex items-center transition-transform duration-150"
                          :class="getLayoutDragClass('mod_details_layout', index)"
                          :draggable="getDataById('details', formData.ui.main_layout).visible"
                          @dragstart="handleLayoutDragStart('mod_details_layout', index, $event)"
                          @dragover.prevent="handleLayoutDragOver('mod_details_layout', index)"
                          @drop.prevent="handleLayoutDrop('mod_details_layout', index)"
                          @dragend="handleLayoutDragEnd">
                          <span class="p-1 mr-1 rounded-md bg-accent-primary/30">{{ index }}</span>
                          <CommonSwitch class="flex-1 cursor-move" :disabled="!getDataById('details', formData.ui.main_layout).visible" :key="item.id" :label="appStore.DETAILS_LAYOUT_MAPS[item.id].label" v-model="item.visible" :description="appStore.DETAILS_LAYOUT_MAPS[item.id].desc" />
                        </div>
                      </div>
                      
                    </div>
                    
                  </div>
                </div>
              </section>

              <!-- 功能设置 -->
              <section v-if="currentTab === 'features'" class="animate-in fade-in slide-in-from-right-4">
                <h3 class="text-lg font-bold text-text-main mb-6">功能设置</h3>
                <div class="space-y-6">
                  <div class="grid grid-cols-2 gap-4">
                    <CommonSwitch class="col-span-1" label="启动时自动扫描 Mod 目录" v-model="formData.enable_auto_scan" description="关闭后，需要手动点击扫描按钮才能更新 Mod 列表。" />
                    <CommonSwitch class="col-span-1" label="环境直启前检查同步" v-model="formData.enable_launch_profile_quick_scan" description="从环境列表直接启动非当前环境时，会先检查并同步运行前所需的链接。开启后会先做一次轻量扫描再同步；关闭后只按当前数据库缓存和环境配置强制同步。" />
                    <CommonSwitch class="col-span-1" label="扫描时检查文件大小" v-model="formData.enable_file_size_scan" description="开启后，扫描时会自动检查 Mod 的文件大小，以此识别新增或更新的内容。该功能会增加扫描耗时，但能显著提高文件变动的识别精度。" />
                    <CommonSwitch class="col-span-1" label="自动清理缺失的 Mod 数据" v-model="formData.delete_missing_mods_data" description="关闭后，缺失的 Mod 数据将保留在数据库中，列表内可以重新订阅。" />
                    <CommonSwitch class="col-span-1" label="关键动作前必要检查" v-model="formData.enable_action_prechecks" description="开启后，保存、运行、自动排序前会检查未安装项和未启用项；关闭后将直接执行，不再弹出检查窗口。" />
                    <CommonSwitch class="col-span-1" label="检查语言支持" v-model="formData.check_language_support" description="开启后，将会在 Mod 问题提示增加“语言支持”警告，提示 Mod 是否支持当前语言。" />
                    <CommonSwitch class="col-span-1" label="显示共存冲突提示" v-model="formData.show_coexistence_message" description="关闭后，将不会显示共存Mod的冲突提示信息。" />
                    <CommonSwitch class="col-span-1" label="语言包贴紧前置" v-model="formData.language_packs_follow_targets" description="开启后，自动排序会尽量让语言包紧跟在它已启用的最后一个前置/依赖模组后方；如果找不到目标，就保持原来的默认底层位置。" />
                    <CommonSwitch class="col-span-1" label="使用辅助工具模组" v-model="formData.enable_tool_mods" description="开启后，将在保存或自动排序时自动启用辅助工具模组，如提供日志获取等功能。" />
                    <CommonSelect class="col-span-1" label="自动排序策略" v-model="formData.auto_sort_strategy" showBottom
                      description="旧版更保守、更接近传统手工整理结果，但对带有置顶/置底倾向的模组及其关联链的处理效果较差；新版会更积极地把带有置顶/置底倾向的模组及其关联链推向列表两端。"
                      :options="[{label:'经典自动排序（旧版）', value:'classic_sort_logic'},{label:'两端强化排序（新版）', value:'edge_enhanced_sort_logic'}]" />
                    <CommonSelect class="col-span-1" label="排序顺序" v-model="formData.sort_mods_by" showBottom
                      description="影响自动排序时同档次的Mod顺序，处理优先级是 别名>原名>包名，所以即使Mod没有别名，也能按原名参与排序。" 
                      :options="[{label:'按别名', value:'alias_name'},{label:'按原名', value:'name'},{label:'按包名', value:'id'}]" />
                    <CommonSelect class="col-span-1" label="共存Mod文件夹生成方式" v-model="formData.coexist_mod_folder_name_type" showBottom
                      description="影响创建共存Mod时的文件夹名称，处理优先级是 别名>原名>包名>工坊ID，所以即使Mod没有别名，也能按原名创建文件夹。" 
                      :options="[{label:'按工坊ID', value:'workshop_id'},{label:'按包名', value:'package_id'},{label:'按原名', value:'name'},{label:'按别名', value:'alias_name'}]" />
                    <CommonSelect class="col-span-1" label="链接部署模式" v-model="formData.link_deployment_mode_full" showBottom
                      description="影响启用管理器Mod或多环境下使用创意工坊Mod时的链接部署行为模式，增量部署会尽量保留已正确的链接，只处理变化项；完全重建会先移除全部旧链接，再按当前扫描结果重新部署。"
                      :options="[{label:'增量部署（默认）', value:'incremental'},{label:'完全重建', value:'full'}]" />
                    <CommonNumber class="col-span-1" label="自动备份保留天数" description="管理自动备份的最长保留时间，手动备份不受影响。" v-model="formData.backup_retention_days" :step="1" :min="0" :max="365" />
                  </div>
                </div>
              </section>

              <!-- 外部依赖 -->
              <section v-if="currentTab === 'community'" class="animate-in fade-in slide-in-from-right-4">
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

              <!-- 网络设置 (Network) -->
              <section v-if="currentTab === 'network'" class="animate-in fade-in slide-in-from-right-4">
                <h3 class="text-lg font-bold text-text-main mb-6">网络协议与代理</h3>
                <div class="space-y-8">
                  <div class="modal-section space-y-6 p-4">
                    <CommonSwitch label="启用代理服务" v-model="formData.network.proxy.enabled" :description="'启用代理服务，所有网络请求将通过代理服务器处理，部分外置数据下载、更新检查、简介图片加载、内部浏览器访问等功能可能需要该配置才能正常使用。\n\n也可以在软件外部自行配置全局网络环境。'" mini />
                    <div v-if="formData.network.proxy.enabled" class="grid grid-cols-6 gap-3 animate-in zoom-in-95">
                      <CommonSelect class="col-span-2" label="协议" v-model="formData.network.proxy.type" :options="[{label:'HTTP', value:'http'},{label:'SOCKS5', value:'socks5'}]" />
                      <CommonInput class="col-span-3" label="主机地址" v-model="formData.network.proxy.host" placeholder="127.0.0.1" />
                      <CommonNumber class="col-span-1" label="端口" v-model="formData.network.proxy.port" :step="1" :min="1" :max="65535" />
                      <CommonInput class="col-span-3" label="用户名" v-model="formData.network.proxy.username" />
                      <CommonInput class="col-span-3" label="密码" v-model="formData.network.proxy.password" is-password />
                      <div class="col-span-6">
                        <CommonTagInput label="不走代理的域名" v-model="formData.network.proxy.bypass_list" />
                      </div>

                      <div class="col-span-6 grid grid-cols-2 gap-3">
                        <CommonSwitch label="是否为 SteamCMD 使用代理" v-model="formData.network.use_proxy_on_steamcmd" :description="'SteamCMD 是否使用代理服务器。\n\n如果启用，SteamCMD 下载、更新、安装等操作将通过代理服务器进行。'" />
                        <CommonSwitch label="是否为 AI请求 使用代理" v-model="formData.network.use_proxy_on_ai" :description="'如果启用，AI 将通过代理服务器进行。已经是国内代理后的端口不用开此选项。'" />
                      </div>
                    </div>
                  </div>
                  <CommonKVEditor label="自定义 Hosts 映射" v-model="formData.network.hosts" />
                  <CommonSwitch label="将自定义 Hosts 写入系统 hosts 文件" v-model="formData.network.write_to_system_hosts" description="注意：这将直接修改系统 hosts 文件，可能需要管理员权限。" />
                
                  <div class="modal-section space-y-4 p-4">
                    <div class="text-xs ">
                      <h4 class="text-sm font-bold text-text-main">Steamworks Web API</h4>
                      <p class="mt-1 leading-relaxed text-text-dim">
                        仅用于在线搜索创意工坊模组，该 Key 仅保存在本地配置，不会上传到任何服务器，如有顾虑可以不用填写。
                      </p>
                      <span class="text-accent-warn">注意！“API 密钥（API Key）相当于你的 Steam 账号后门钥匙”。可以读取账号公开数据/库存信息 以及 管理与监听交易报价。</span>
                      <p>任何人一旦获取了此 Key，就可以在不触发 Steam 令牌的情况下，暗中取消玩家的真实交易，并替换为发给骗子的假交易。绝对不要将 API 密钥分享给任何人或任何未经验证的第三方网站。</p>
                    </div>
                    <div class="flex items-end gap-2">
                      <CommonInput class="flex-1" label="Steam Web API Key" v-model="formData.steam_web_api_key" is-password placeholder="填写后可启用在线搜索" description="在线搜索需要填写该 Key，否则将无法使用该功能。" />
                    
                      <button @click="openUrlOnSteam('https://steamcommunity.com/dev/apikey')"
                        class="px-2 py-2 m-0.5 bg-bg-overlay/5 hover:bg-bg-overlay/10 border border-border-base/10 rounded-lg text-xs font-bold cursor-pointer transition-all">
                        <span class="flex items-center gap-2">
                          访问<p class="text-accent-cool">API Key</p>获取页面
                        </span>
                      </button>
                    </div>
                  </div>

                </div>
              </section>

              <!-- AI 设置 (AI) -->
              <section v-if="currentTab === 'ai'" data-tour="settings-ai-section" class="animate-in fade-in slide-in-from-right-4">
                <div class="mb-6 flex items-center justify-between">
                  <h3 class="text-lg font-bold text-text-main flex items-center gap-2">
                    人工智能
                    <span class="px-2 py-0.5 rounded bg-accent-special/20 text-accent-special text-xs font-black uppercase">实验性</span>
                  </h3>

                  <button v-if="formData.ai.enabled" @click="appStore.uiState.showAIDefinitionManager = true"
                    class="px-4 py-1.5 rounded-lg bg-accent-special/10 hover:bg-accent-special/20 text-accent-special border border-accent-special/30 text-xs font-bold transition-colors flex items-center gap-2">
                    <Drama class="size-4" /> AI 定义管理
                  </button>
                </div>
                <div class="space-y-6">
                  <div data-tour="settings-ai-enable">
                    <CommonSwitch label="启用 AI 功能" v-model="formData.ai.enabled" description="用于日志分析、模组说明和 AI 助手对话等功能。" />
                  </div>
                  <div v-if="formData.ai.enabled" class="space-y-6 animate-in slide-in-from-top-2">
                      
                    <!-- 2. 动态表单区 -->
                    <div data-tour="settings-ai-connection" class="p-4 rounded-xl bg-bg-overlay/5 border border-border-base/10 space-y-5">
                      <div class="grid grid-cols-2 gap-3">
                        <!-- 厂商/协议选择 -->
                        <CommonSelect label="接口协议" description="大多数中转服务、本地运行时、国产模型平台都优先兼容 OpenAI-compatible 接口。只有目标服务没有稳定的 OpenAI-compatible API 时，才建议切换到原生协议。"
                          v-model="formData.ai.provider" :options="currentAiProviders" @change="handleProviderChange"/>
                        <!-- 模型选择 (带刷新动作) -->
                        <div class="relative flex items-end gap-2">
                          <div class="flex-1">
                            <!-- 加上 editable 允许用户手输未被探测到的模型名 -->
                            <CommonSelect label="模型" editable v-model="formData.ai.model" :options="currentAiModels" 
                              placeholder="下拉选择或手动输入模型名称" @visible-change="(val) => val && fetchAiModels({ silent: true })"/>
                          </div>
                          <!-- 对于自定义模式，提供显式的刷新按钮让用户主动拉取 -->
                          <button @click="fetchAiModels({ forceRefresh: true, warnOnEmpty: true, silent: false })" v-tooltip="'重新获取模型列表'"
                            class="h-9 px-3 bg-bg-inset/70 hover:bg-accent-special/20 text-accent-special border border-accent-special/30 rounded-lg flex items-center justify-center transition-colors">
                            <svg class="size-4" :class="{'animate-spin': aiStore.isLoading}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 21v-5h5"/></svg>
                          </button>
                        </div>

                        <!-- Base URL (自定义必填，官方高级选填) -->
                        <CommonInput label="Base URL" v-model="formData.ai.base_url" class="col-span-2"
                          placeholder="留空使用协议默认地址；也可填写 http://127.0.0.1:11434 或 https://api.deepseek.com/v1"
                          description="留空时使用当前协议的默认地址。Ollama 默认连接本机 127.0.0.1:11434；中转服务或非默认本地地址需要手动填写。"
                        />
                        <!-- API Key -->
                        <CommonInput label="API Key" v-model="formData.ai.api_key" is-password class="col-span-2" 
                          placeholder="接口需要时填写 API Key；本地部署通常可以留空。" 
                        />
                      </div>

                    </div>

                    <!-- 3. 测试与高级参数区 -->
                    <div data-tour="settings-ai-advanced" class="">
                      <div class="grid grid-cols-3 gap-2">
                        <CommonNumber label="最大并发数" v-model="formData.ai.max_concurrency" :step="1" :min="1" :max="100" description="同时发出的请求数量。大多数情况下设为 3 到 5 就够了。" />
                        <CommonNumber label="输出随机性" v-model="formData.ai.temperature" :step="0.1" :min="0" :max="2.0" description="值越低越稳定，值越高越发散。一般用 0.7 左右即可。" />
                        <CommonNumber label="上下文窗口" v-model="formData.ai.context_window_tokens" :step="1024" :min="0"
                          description="模型总上下文窗口。0 表示按模型名自动预设；本地模型如果服务端限制了上下文，建议填实际值。" />
                        <CommonNumber label="最大输入预算" v-model="formData.ai.max_input_tokens" :step="1024" :min="0"
                          description="日志、附件、批量任务最多喂给模型的输入预算。0 表示自动按上下文窗口扣除输出预算。" />
                        <CommonNumber label="最大输出预算" v-model="formData.ai.max_output_tokens" :step="512" :min="0"
                          description="单次回复的输出保护阀。0 表示按模型预设自动控制；只有排查成本、延迟或长回复截断时才需要手动设置。" />
                        <CommonSelect v-if="formData.ai.provider === 'openai_compatible'"
                          label="接口模式" v-model="formData.ai.endpoint_mode"
                          description="用于指定 OpenAI-compatible 接口应走哪一类 endpoint。`Auto` 会根据模型能力和请求结构自动选择更稳妥的路径；只有在排查特定中转服务或本地运行时兼容问题时，才建议手动切换。"
                          :options="[
                            { label: 'Auto', value: 'auto' },
                            { label: 'Chat Completions API', value: 'chat_completions' },
                            { label: 'Responses API', value: 'responses' }
                          ]" />
                      </div>

                      <!-- 测试区 -->
                      <div data-tour="settings-ai-test" class="pt-4 flex gap-3">
                        <CommonInput label="测试内容" class="flex-1" v-model="testPrompt" placeholder="输入一句简单的话测试连接，例如：你好" @keydown.enter="testModel"></CommonInput>
                        <button class="mt-[1.3rem] flex items-center justify-center bg-accent-special/70 hover:bg-accent-special hover:text-text-main text-text-dim px-6 py-2 rounded-lg font-bold transition-all" 
                          :class="[aiStore.isLoading?'cursor-not-allowed pointer-events-none opacity-50':'cursor-pointer']"
                          @click="testModel">
                          <svg v-if="aiStore.isLoading" class="animate-spin size-4 mr-2" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                          发起测试
                        </button>
                      </div>

                      <div v-if="testResponse" class="p-4 rounded-xl text-text-soft bg-accent-special/10 border border-border-base/10 relative">
                        <button @click="clearTestResult" class="absolute top-2 right-2 text-text-dim hover:text-text-main">×</button>
                        <div class="text-xs text-text-dim mb-1 font-bold">AI 响应结果：</div>
                        <div class="text-sm whitespace-pre-wrap leading-relaxed">{{ testResponse }}</div>
                        <details v-if="testRawResponse" class="modal-section-subtle mt-3 p-3 text-xs text-text-dim">
                          <summary class="cursor-pointer font-bold text-text-main">查看原始返回内容</summary>
                          <pre class="mt-2 whitespace-pre-wrap break-all rounded-lg border border-border-base/10 bg-bg-inset/70 p-3 text-xs text-text-main">{{ prettyTestRawResponse }}</pre>
                        </details>
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

            </div>
          </div>

          <!-- D. 底部操作栏 -->
          <footer class="modal-footer flex items-center justify-end gap-4 px-10 py-3">
            <button id="btn-cancel" @click="appStore.closeSettingsPanel()" class="text-sm font-bold text-text-dim hover:text-text-main transition-colors">放弃修改</button>
            <button data-tour="settings-save-button" @click="save" class="relative overflow-hidden px-8 py-2.5 bg-accent-primary rounded-xl text-on-accent-primary font-black text-sm shadow-[0_0_20px_rgba(var(--rgb-accent-primary),0.3)] hover:scale-105 active:scale-95 transition-all group">
              <div class="absolute inset-0 bg-bg-overlay/10 -translate-x-full group-hover:translate-x-full transition-transform duration-500 skew-x-12"></div>
              应用并保存配置
            </button>
          </footer>
        </main>

  </CommonModalShell>

  <CommonModalShell
    :show="showDataBundleModal && appStore.uiState.showSettingsPanel"
    title="导出软件数据"
    description="勾选要打包的数据；如果选择环境数据，会打包对应环境的完整目录。"
    size="custom"
    :z-index="120"
    accent="primary"
    panel-class="w-[min(920px,92vw)] max-h-[84vh] border-accent-primary/20"
    content-class="min-h-0 flex flex-col"
    @close="closeDataBundleModal"
  >
          <div class="absolute -top-20 -left-16 w-56 h-56 rounded-full bg-accent-primary/10 blur-3xl pointer-events-none"></div>
          <div class="absolute -bottom-20 -right-16 w-56 h-56 rounded-full bg-accent-special/10 blur-3xl pointer-events-none"></div>

          <div class="relative z-10 flex-1 overflow-y-auto px-5 py-4 custom-scrollbar">
            <div class="grid grid-cols-3 gap-3">
              <label v-for="module in bundleModuleDefs" :key="module.key" class="rounded-xl border px-3 py-2.5 transition-all"
                :class="dataBundleModuleSelection[module.key] ? 'border-accent-primary/40 bg-accent-primary/10' : 'modal-section-subtle hover:border-border-base/18'"
              >
                <div class="flex items-center gap-2">
                  <input :checked="!!dataBundleModuleSelection[module.key]" type="checkbox" class="accent-accent-primary"
                    @change="toggleDataBundleModule(module.key, $event.target.checked)"
                  >
                  <span class="text-sm font-bold text-text-main">{{ module.label }}</span>
                  <button v-if="buildBundleModuleTooltip(module)" type="button" v-tooltip="buildBundleModuleTooltip(module)" @click.prevent
                    class="ml-auto size-5 rounded-full border border-border-base/10 text-xs font-bold text-text-dim hover:text-text-main hover:border-border-base/18 transition-all"
                  >?
                  </button>
                </div>
              </label>
            </div>

            <div v-if="isBundleProfileModuleSelected" class="modal-section mt-4">
              <button @click="showBundleProfilePicker = !showBundleProfilePicker" class="w-full flex items-center justify-between gap-3 px-4 py-3 text-left" >
                <div>
                  <div class="text-sm font-bold text-text-main">环境数据</div>
                  <div class="text-xs text-text-dim mt-1">选择要打包的环境。</div>
                </div>
                <span class="text-xs font-bold text-accent-primary">
                  {{ showBundleProfilePicker ? '收起' : '展开' }}
                </span>
              </button>

              <div v-if="showBundleProfilePicker" class="px-4 pb-4">
                <div class="grid grid-cols-2 gap-3">
                  <label v-for="profile in bundleProfileDefs" :key="profile.id" class="rounded-xl border p-3 transition-all"
                    :class="profile.has_user_data ? 'border-border-base/10 bg-bg-inset/55 hover:border-border-base/18' : 'border-accent-danger/20 bg-accent-danger/8 opacity-60'"
                  >
                    <div class="flex items-start gap-3">
                      <input v-model="dataBundleProfileSelection" :disabled="!profile.has_user_data" :value="profile.id" type="checkbox" class="mt-0.5 accent-accent-primary"  >
                      <div class="min-w-0">
                        <div class="flex items-center gap-2 flex-wrap">
                          <span class="text-sm font-bold text-text-main">{{ profile.name }}</span>
                          <span v-if="profile.is_default" class="text-[0.7rem] px-1.5 py-0.5 rounded bg-accent-highlight/20 text-accent-highlight">默认</span>
                          <span v-if="profile.game_version" class="text-[0.7rem] px-1.5 py-0.5 rounded bg-accent-secondary/20 text-accent-secondary">{{ profile.game_version }}</span>
                        </div>
                        <p class="text-xs text-text-dim mt-1">
                          {{ profile.has_user_data ? (profile.description || '将打包整个环境目录') : '未检测到可打包的用户数据目录' }}
                        </p>
                      </div>
                    </div>
                  </label>
                </div>
              </div>
            </div>
          </div>

          <footer class="modal-footer relative z-10 flex items-center justify-between gap-4 px-5 py-4">
            <p class="text-xs leading-relaxed text-text-dim">
              <span class="text-accent-primary font-bold">环境数据</span> 会打包整个环境目录；
              <span class="text-accent-tip font-bold">路径绑定、敏感信息、当前激活环境 ID</span> 不会导出。
              <span class="text-accent-warn font-bold">环境导入冲突</span> 会在导入面板统一处理新建/覆盖。
            </p>
            <button @click="handleExportDataBundle"
              class="shrink-0 px-5 py-2 rounded-xl bg-accent-primary hover:bg-accent-primary/85 text-on-accent-primary text-sm font-black shadow-[0_0_18px_rgba(var(--rgb-accent-primary),0.24)] transition-all"
            >
              导出当前选择
            </button>
          </footer>
  </CommonModalShell>
</template>

<script setup>
import { ref, watch, onMounted, nextTick, h, computed } from 'vue'
import { FolderTree, AppWindow, Globe, Cpu, Terminal, Search, Component, Settings, Drama, Download, LoaderCircle } from 'lucide-vue-next'
import { deepClone, toast } from '../utils/common'
import { flashComponent, shakeComponent } from '../utils/domEffects'

// 导入 Common UI
import CommonPathInput from './common/input/CommonPathInput.vue'
import CommonSwitch from './common/input/CommonSwitch.vue'
import CommonInput from './common/input/CommonInput.vue'
import CommonNumber from './common/input/CommonNumber.vue'
import CommonSelect from './common/input/CommonSelect.vue'
import CommonTagInput from './common/input/CommonTagInput.vue'
import CommonKVEditor from './common/input/CommonKVEditor.vue'
import ThemeSelect from './settings/ThemeSelect.vue'
import CommonModalShell from './common/CommonModalShell.vue'
import { RUN_COMMAND_TAGS } from '../utils/constants'
import { formatFileSize } from '../utils/format'
import { DEFAULT_THEME_ID, applyTheme, createEditableThemeFrom, findThemeById, normalizeTheme } from '../modules/theme/themeManager'
import { useRuleStore } from '../stores/ruleStore'
import { useAppStore } from '../stores/appStore'
import { useAiStore } from '../stores/aiStore'
import { useConfirmStore } from '../stores/confirmStore'
import { useProfileStore } from '../stores/profileStore'
import { useModStore } from '../stores/modStore'
import { useGuideStore } from '../stores/guideStore'

const appStore = useAppStore()
const aiStore = useAiStore()
const ruleStore = useRuleStore()
const confirmStore = useConfirmStore()
const profileStore = useProfileStore()
const modStore = useModStore()
const guideStore = useGuideStore()

const currentTab = ref('paths')
const formData = ref({})
const layoutDragState = ref({ key: '', fromIndex: -1, overIndex: -1 })

const selectedFormTheme = computed(() => {
  return findThemeById(appStore.themes, currentThemeId.value)
})
const currentThemeId = computed({
  get: () => appStore.settings.ui?.theme_id || DEFAULT_THEME_ID,
  set: async (themeId) => {
    if (!appStore.settings.ui) appStore.settings.ui = {}
    appStore.settings.ui.theme_id = themeId || DEFAULT_THEME_ID
    applyTheme(findThemeById(appStore.themes, appStore.settings.ui.theme_id))
    await appStore.saveSetting('ui', appStore.settings.ui)
  },
})

const openThemeCreate = () => {
  appStore.themeEditor.theme = createEditableThemeFrom(selectedFormTheme.value)
  appStore.themeEditor.isOpen = true
}
const openThemeEdit = (theme) => {
  if (!theme || theme.builtin) return
  appStore.themeEditor.theme = normalizeTheme(theme)
  appStore.themeEditor.isOpen = true
}
const handleThemeDelete = async (theme) => {
  if (!theme || theme.builtin) return
  const ok = await confirmStore.confirmAction('删除主题', `确定要删除自定义主题「${theme.name}」吗？此操作不可撤销。`, { type: 'error' })
  if (!ok) return
  const deleted = await appStore.deleteUserTheme(theme.id)
  if (deleted && currentThemeId.value === theme.id) {
    currentThemeId.value = DEFAULT_THEME_ID
  }
}

const getLayoutList = (layoutKey) => {
  const list = formData.value?.ui?.[layoutKey]
  return Array.isArray(list) ? list : []
}
const handleLayoutDragStart = (layoutKey, index, event) => {
  // 设置页只有少量布局项，不需要再依赖 SortableJS。
  // 这里用原生拖拽维护“从哪个布局、哪个下标开始拖”，drop 时直接重排数组即可。
  const list = getLayoutList(layoutKey)
  if (!list[index]) return
  layoutDragState.value = { key: layoutKey, fromIndex: index, overIndex: index }
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', `${layoutKey}:${index}`)
}
const handleLayoutDragOver = (layoutKey, index) => {
  if (layoutDragState.value.key !== layoutKey) return
  layoutDragState.value = { ...layoutDragState.value, overIndex: index }
}
const handleLayoutDrop = (layoutKey, toIndex) => {
  const { key, fromIndex } = layoutDragState.value
  const list = getLayoutList(layoutKey)
  if (key !== layoutKey || fromIndex < 0 || toIndex < 0 || fromIndex === toIndex || !list[fromIndex]) {
    handleLayoutDragEnd()
    return
  }
  const nextList = [...list]
  const [moving] = nextList.splice(fromIndex, 1)
  nextList.splice(toIndex, 0, moving)
  formData.value.ui[layoutKey] = nextList
  handleLayoutDragEnd()
}
const handleLayoutDragEnd = () => {
  layoutDragState.value = { key: '', fromIndex: -1, overIndex: -1 }
}
const getLayoutDragClass = (layoutKey, index) => {
  if (layoutDragState.value.key !== layoutKey) return ''
  if (layoutDragState.value.fromIndex === index) return 'opacity-50 scale-[0.98]'
  if (layoutDragState.value.overIndex === index) return 'translate-y-0 ring-1 ring-accent-primary/60 rounded-xl'
  return ''
}
const detectedIsSteam = computed(() => {
  const checkedInstall = formData.value?.check_info?.game_install_path
  if (checkedInstall && Object.prototype.hasOwnProperty.call(checkedInstall, 'pass')) {
    if (checkedInstall.data && Object.prototype.hasOwnProperty.call(checkedInstall.data, 'is_steam')) {
      return !!checkedInstall.data.is_steam
    }
    return false
  }
  return !!formData.value?.is_steam
})
const steamLaunchDisabled = computed(() => !detectedIsSteam.value)
const hasWorkshopPath = computed(() => !!String(formData.value?.workshop_mods_path || '').trim())
const workshopModsDisabled = computed(() => steamLaunchDisabled.value || !!formData.value?.prefer_steam_launch || !hasWorkshopPath.value)

const Steam = h('svg', { viewBox: "0 0 448 512", fill: "currentColor" }, 
  [ h('path', { d: "M273.5 177.5a61 61 0 1 1 122 0 61 61 0 1 1 -122 0zm174.5 .2c0 63-51 113.8-113.7 113.8L225 371.3c-4 43-40.5 76.8-84.5 76.8-40.5 0-74.7-28.8-83-67L0 358 0 250.7 97.2 290c15.1-9.2 32.2-13.3 52-11.5l71-101.7C220.7 114.5 271.7 64 334.2 64 397 64 448 115 448 177.7zM203 363c0-34.7-27.8-62.5-62.5-62.5-4.5 0-9 .5-13.5 1.5l26 10.5c25.5 10.2 38 39 27.7 64.5-10.2 25.5-39.2 38-64.7 27.5-10.2-4-20.5-8.3-30.7-12.2 10.5 19.7 31.2 33.2 55.2 33.2 34.7 0 62.5-27.8 62.5-62.5zM410.5 177.7a76.4 76.4 0 1 0 -152.8 0 76.4 76.4 0 1 0 152.8 0z" })]
)

const tabs = [
  { id: 'paths', label: '路径配置', icon: FolderTree },
  { id: 'general', label: '界面设置', icon: AppWindow },
  { id: 'features', label: '功能设置', icon: Component },
  { id: 'community', label: '外部依赖', icon: Steam },
  { id: 'network', label: '网络连接', icon: Globe },
  { id: 'ai', label: 'AI 集成', icon: Cpu },
  { id: 'dev', label: '开发调试', icon: Terminal },
]

const currentTabLabel = computed(() => (
  tabs.find(item => item.id === currentTab.value)?.label || currentTab.value
))

const LOAD_ORDER_DIR_MODE_OPTIONS = [
  { label: '默认', value: 'default' },
  { label: '记忆', value: 'remember' },
  { label: '自定义', value: 'custom' },
]


const downloadState = ref({
  workshop_db: false,
  instead_db: false,
})
const currentAiProviders = computed(() => aiStore.listAiProviders())
const currentAiModels = computed(() => aiStore.getCachedAiModelOptions(formData.value?.ai || {}))
const dataBundleSchema = ref({
  modules: [],
  profiles: [],
  presets: {},
  file_extension: '.rmmdata.zip',
})
const showDataBundleModal = ref(false)
const showBundleProfilePicker = ref(false)
const dataBundleModuleSelection = ref({})
const dataBundleProfileSelection = ref([])

const bundleModuleDefs = computed(() => dataBundleSchema.value?.modules || [])
const bundleProfileDefs = computed(() => dataBundleSchema.value?.profiles || [])
const selectedBundleModuleKeys = computed(() => (
  bundleModuleDefs.value
    .filter(module => !!dataBundleModuleSelection.value?.[module.key])
    .map(module => module.key)
))
const isBundleProfileModuleSelected = computed(() => !!dataBundleModuleSelection.value?.profiles)

const resetDataBundleSelections = () => {
  dataBundleModuleSelection.value = Object.fromEntries(
    bundleModuleDefs.value.map(module => [module.key, false])
  )
  dataBundleProfileSelection.value = []
}

const ensureModuleEnabled = (moduleKey, selection) => {
  const target = bundleModuleDefs.value.find(module => module.key === moduleKey)
  if (!target) return
  selection[moduleKey] = true
  for (const dependencyKey of target.dependencies || []) {
    ensureModuleEnabled(dependencyKey, selection)
  }
}

const disableModuleAndDependents = (moduleKey, selection) => {
  selection[moduleKey] = false
  const dependentKeys = bundleModuleDefs.value
    .filter(module => (module.dependencies || []).includes(moduleKey))
    .map(module => module.key)
  for (const dependentKey of dependentKeys) {
    disableModuleAndDependents(dependentKey, selection)
  }
}

const toggleDataBundleModule = (moduleKey, enabled) => {
  const nextSelection = { ...(dataBundleModuleSelection.value || {}) }
  if (enabled) {
    ensureModuleEnabled(moduleKey, nextSelection)
  } else {
    disableModuleAndDependents(moduleKey, nextSelection)
  }
  dataBundleModuleSelection.value = nextSelection
  if (!nextSelection.profiles) {
    dataBundleProfileSelection.value = []
    showBundleProfilePicker.value = false
  } else if (moduleKey === 'profiles' && enabled) {
    showBundleProfilePicker.value = true
  }
}

const loadDataBundleSchema = async () => {
  const schema = await appStore.getDataBundleSchema()
  if (!schema) return
  dataBundleSchema.value = schema
  resetDataBundleSelections()
}

const openDataBundleModal = async () => {
  if (!bundleModuleDefs.value.length) {
    await loadDataBundleSchema()
  }
  showDataBundleModal.value = true
}

const closeDataBundleModal = () => {
  showDataBundleModal.value = false
}

const buildBundleModuleTooltip = (module) => {
  const lines = []
  if (module?.description) {
    lines.push(module.description)
  }
  const dependencyLabels = (module?.dependencies || [])
    .map(key => bundleModuleDefs.value.find(item => item.key === key)?.label || key)
  if (dependencyLabels.length) {
    lines.push(`依赖：${dependencyLabels.join('、')}`)
  }
  return lines.join('\n')
}

// 数据同步：打开时深度拷贝
watch(() => appStore.uiState.showSettingsPanel, (val) => {
  if (val) {
    // 利用 requestAnimationFrame 或 setTimeout
    // 让浏览器先渲染出弹窗的“背景”和“动画第一帧”，然后再去塞数据
    requestAnimationFrame(async () => {
      // 使用 structuredClone (Node 17+ / 现代浏览器均支持，速度更快)，将全局 Settings 和 当前 Context 捏合成一个对象给表单用
      // 如果环境不支持，保留原来的 JSON 方式，但放在 requestAnimationFrame 里依然能解决卡顿
      try {
      formData.value = {
          ...structuredClone(appStore.settings),
          ...structuredClone(profileStore.activeContext) // 覆盖/合并上下文路径
        }
      } catch (e) {
        formData.value = { 
          ...JSON.parse(JSON.stringify(appStore.settings)),
          ...JSON.parse(JSON.stringify(profileStore.activeContext))
        }
      }
      // 如果当前上下文不健康，自动检测路径
      if (!profileStore.activeContext || profileStore.activeContext.is_healthy === false) {
        await autoDetect()
      }
      // 检测所有路径是否有效
      await checkPaths()
      await loadDataBundleSchema()
      await appStore.refreshRemoteImageCacheStats()
      // AI 厂商定义已在 aiStore 初始化时一并获取。
      // 模型列表仍按需请求，但优先复用 aiStore 缓存，避免设置面板维护重复状态。
      if (formData.value.ai) {
        hydrateAiProviderDrafts()
        if (formData.value.ai.provider) {
          await fetchAiModels({ silent: true })
        }
      }
    })
  } else {
    showDataBundleModal.value = false
    showBundleProfilePicker.value = false
    if (!appStore.themeEditor.isOpen) applyTheme(appStore.currentTheme)
  }
})
watch(() => !!formData.value?.prefer_steam_launch, (enabled) => {
  if (enabled && formData.value) {
    formData.value.use_workshop_mods = false
  }
})
watch(detectedIsSteam, (isSteam) => {
  if (!isSteam && formData.value?.prefer_steam_launch) {
    formData.value.prefer_steam_launch = false
  }
})
watch(hasWorkshopPath, (available) => {
  if (!available && formData.value?.use_workshop_mods) {
    formData.value.use_workshop_mods = false
  }
})

// 监听当前页面切换
const changeTab = (tab) => {
  currentTab.value = tab
  // 检测所有路径是否有效
  // if (['paths','community'].includes(tab)) {
  //   checkPaths()
  // }
}

// 通过ID获取数据项
const getDataById = (id, datas) => {
  return datas.find(item => item.id === id)
}

// 自动检测路径
const autoDetect = async () => {
  const paths = await appStore.autoDetectPaths(false)
  if (paths) Object.assign(formData.value, paths)
}
// 重置外部依赖路径为默认值
const resetToDefaultExternalPaths = async () => {
  const paths = await appStore.getDefaultExternalPaths()
  if (!paths) return
  const { texture_opt, ...rest } = paths
  Object.assign(formData.value, rest)
  if (texture_opt && typeof texture_opt === 'object') {
    formData.value.texture_opt = {
      ...(formData.value.texture_opt || {}),
      ...texture_opt,
    }
  }
}

// 检查游戏路径是否有效
const checkPath = async (type, path) => {
  console.log('checkPath:', type, path)
  const res = await appStore.checkPath(type, path)
  if (!formData.value['check_info']) {
    formData.value['check_info'] = {};
  }
  formData.value['check_info'][type] = res
}
// 检查全部路径
const checkPaths = async () => {
  const paths_data = {}
  for (const key in formData.value) {
    if (key.endsWith('_path')) {
      paths_data[key] = formData.value[key]
    }
  }
  const textureToolsPath = formData.value?.texture_opt?.texture_tools_path
  if (textureToolsPath !== undefined) {
    paths_data.texture_tools_path = textureToolsPath
  }
  // console.log('检查路径', paths_data)
  const res = await appStore.checkPaths(paths_data)
  if (res) {
    formData.value['check_info'] = res
  }
}

// 手动选择游戏路径
const handleGameBrowse = async () => {
  let current = formData.value
  const res = await appStore.getFolderPath(current['game_install_path'])
  if (res) {
    current['game_install_path'] = res
    // 自动获取游戏信息
    checkPath('game_install_path', current['game_install_path'])
  }
}

const getNestedField = (target, pathKey) => {
  return String(pathKey || '').split('.').filter(Boolean)
    .reduce((current, key) => current?.[key], target)
}

const setNestedField = (target, pathKey, value) => {
  const segments = String(pathKey || '').split('.').filter(Boolean)
  if (!segments.length) return
  let current = target
  for (let index = 0; index < segments.length - 1; index += 1) {
    const key = segments[index]
    if (!current[key] || typeof current[key] !== 'object') {
      current[key] = {}
    }
    current = current[key]
  }
  current[segments[segments.length - 1]] = value
}

// 手动选择其他路径
const handleBrowse = async (pathKey, fileTypes, checkTarget = undefined) => {
  console.log('路径选择',pathKey, fileTypes)
  const currentValue = getNestedField(formData.value, pathKey) || ''
  let res
  if (fileTypes) {
    res = await appStore.getFilePath(currentValue, fileTypes)
  } else {
    res = await appStore.getFolderPath(currentValue)
  }
  if (res) {
    setNestedField(formData.value, pathKey, res)
    // 自动检查路径是否有效
    const finalCheckTarget = checkTarget === undefined ? pathKey : checkTarget
    if (typeof finalCheckTarget === 'string' && finalCheckTarget) {
      await checkPath(finalCheckTarget, res)
    }
  }
}

// ======= AI 集成 ======
// 测试提示词
const testPrompt = ref("介绍一下自己")
const testResponse = ref("")
const testRawResponse = ref(null)
const prettyTestRawResponse = computed(() => {
  if (testRawResponse.value == null) return ''
  try {
    return JSON.stringify(testRawResponse.value, null, 2)
  } catch {
    return String(testRawResponse.value)
  }
})
const clearTestResult = () => {
  testResponse.value = ""
  testRawResponse.value = null
}
const aiProviderDrafts = ref({})

const DEFAULT_AI_BASE_URLS = {
  openai_compatible: 'https://api.openai.com/v1',
  anthropic: 'https://api.anthropic.com',
  gemini: 'https://generativelanguage.googleapis.com',
  ollama: 'http://127.0.0.1:11434',
}

const normalizeAiProvider = (provider = '') => {
  const normalized = String(provider || '').trim().toLowerCase()
  if (['openai', 'custom_openai'].includes(normalized)) return 'openai_compatible'
  return normalized || 'openai_compatible'
}

const createAiProviderDraft = (ai = {}) => ({
  provider: normalizeAiProvider(ai.provider),
  base_url: String(ai.base_url || '').trim(),
  api_key: String(ai.api_key || '').trim(),
  model: String(ai.model || '').trim(),
  endpoint_mode: String(ai.endpoint_mode || 'auto').trim().toLowerCase() || 'auto',
})

const syncCurrentAiProviderDraft = () => {
  const ai = formData.value?.ai
  if (!ai) return
  const provider = normalizeAiProvider(ai.provider)
  aiProviderDrafts.value[provider] = createAiProviderDraft(ai)
}

const hydrateAiProviderDrafts = () => {
  const ai = formData.value?.ai
  if (!ai) return
  aiProviderDrafts.value = {
    [normalizeAiProvider(ai.provider)]: createAiProviderDraft(ai),
  }
}

const applyAiDraftForProvider = (provider) => {
  const ai = formData.value?.ai
  if (!ai) return
  const normalizedProvider = normalizeAiProvider(provider)
  const hasDraft = Object.prototype.hasOwnProperty.call(aiProviderDrafts.value, normalizedProvider)
  const draft = hasDraft ? aiProviderDrafts.value[normalizedProvider] : null
  ai.provider = normalizedProvider
  ai.base_url = draft ? String(draft.base_url || '') : (DEFAULT_AI_BASE_URLS[normalizedProvider] || '')
  ai.api_key = draft ? String(draft.api_key || '') : ''
  ai.model = draft ? String(draft.model || '') : ''
  ai.endpoint_mode = draft ? (String(draft.endpoint_mode || 'auto').trim().toLowerCase() || 'auto') : 'auto'
}

// 测试模型
const testModel = async () => {
  clearTestResult()
  const res = await aiStore.chatWithAI(testPrompt.value, formData.value.ai)
  testRawResponse.value = res?.raw ?? null
  if (res?.ok) {
    testResponse.value = res.text
    toast.success("模型测试成功")
    return
  }
  if (res?.isEmpty) {
    testResponse.value = '模型已返回，但内容为空。可尝试切换模型、检查代理兼容策略或改用正式助手会话测试。'
    toast.warning('模型返回了空内容')
    return
  }
  testResponse.value = res?.error || '模型测试失败'
  toast.error(res?.error || '模型测试失败')
}

// 切换协议只重置连接表单，不主动探测模型列表；模型列表由下拉展开或手动刷新触发。
const handleProviderChange = (selectedProvider) => {
  syncCurrentAiProviderDraft()
  const nextProvider = normalizeAiProvider(selectedProvider?.value ?? selectedProvider ?? formData.value?.ai?.provider)
  applyAiDraftForProvider(nextProvider)
}
// 拉取模型列表 (兼容旧的，组装为 CommonSelect 接受的结构)
const fetchAiModels = async ({ forceRefresh = false, warnOnEmpty = false, silent = true } = {}) => {
  if (!formData.value.ai.provider || !formData.value.ai.enabled) {
    return
  }
  await aiStore.getAiModels(formData.value.ai, { forceRefresh, warnOnEmpty, silent })
}

const openUrlOnSteam = (url) => {
  window.open('steam://openurl/'+url, '_blank')
}

// 更新外部数据库
const updateExternalDB = async (dbType) => {
  downloadState.value[dbType] = true
  await appStore.updateExternalDB(dbType)
  downloadState.value[dbType] = false
}

const handleCheckTools = async () => {
  await appStore.checkToolMaintenance({ manual: true, prompt: true })
}

const handleCheckExternalData = async () => {
  await appStore.checkExternalDataUpdates({ manual: true, prompt: true })
}

const handleCheckSteamcmdMods = async () => {
  await appStore.checkSteamcmdModUpdates({ manual: true, prompt: true })
}

const handleClearRemoteImageCache = async () => {
  const ok = await confirmStore.confirmAction(
    '确认清理网络图片缓存',
    '这会删除当前已缓存的远程图片文件。后续再次显示这些图片时，会按需重新下载。',
    { type: 'warning', confirmText: '立即清理', cancelText: '取消' }
  )
  if (!ok) return
  const cleared = await appStore.clearRemoteImageCache()
  if (!cleared) return
  const clearedCount = Number(cleared?.cleared?.file_count || 0)
  const clearedBytes = formatFileSize(cleared?.cleared?.total_bytes || 0)
  toast.success(`已清理 ${clearedCount} 张缓存图片，释放 ${clearedBytes}`)
}

const handleExportDataBundle = async () => {
  const moduleKeys = selectedBundleModuleKeys.value
  if (moduleKeys.length === 0) {
    toast.warning('请至少勾选一个要导出的数据模块')
    return
  }
  if (moduleKeys.includes('profiles') && dataBundleProfileSelection.value.length === 0) {
    toast.warning('已勾选环境数据，请至少选择一个环境')
    return
  }

  const exported = await appStore.exportDataBundle({
    preset: 'custom',
    module_keys: moduleKeys,
    profile_ids: dataBundleProfileSelection.value,
  })
  if (exported) {
    closeDataBundleModal()
  }
}

const openDataBundleImportDialog = async () => {
  const schema = await appStore.getDataBundleSchema()
  if (!schema) return

  const extensions = [
    schema.file_extension || '.rmmdata.zip',
    ...(Array.isArray(schema.legacy_file_extensions) ? schema.legacy_file_extensions : ['.rmmdata']),
  ]
    .map(item => String(item || '').trim())
    .filter(Boolean)
  const bundlePath = await appStore.getFilePath('', [
    `RMM Data Package (${extensions.map(item => `*${item}`).join(';')})`,
    'All Files (*.*)',
  ])
  if (!bundlePath) return

  const inspectData = await appStore.inspectDataBundle(bundlePath)
  if (!inspectData) return

  appStore.openPackageTransferDialog('data-import', {
    title: '导入软件数据包',
    bundlePath,
    inspectData,
    dataBundleSchema: schema,
  })
}

const openModPackageImportDialog = async () => {
  const schema = await appStore.getModPackageSchema()
  if (!schema) return

  const bundlePath = await appStore.getFilePath('', [
    `RMM Mod Package (*${schema.file_extension || '.rmmmods.zip'})`,
    'All Files (*.*)',
  ])
  if (!bundlePath) return

  const availableInstalls = Array.isArray(schema.available_installs) ? schema.available_installs : []
  const targetKind = availableInstalls.length > 0 ? 'game_install' : 'self_mods'
  const gameInstallPath = String(availableInstalls[0]?.install_path || '')
  const inspectData = await appStore.prepareModPackageImport(bundlePath, {
    target_kind: targetKind,
    game_install_path: gameInstallPath,
  })
  if (!inspectData) return

  appStore.openPackageTransferDialog('mod-import', {
    title: '导入模组包',
    bundlePath,
    inspectData,
    modPackageSchema: schema,
    targetKind,
    gameInstallPath,
  })
}

const openCurrentProfileExportDialog = () => {
  const currentProfile = profileStore.currentProfile || {}
  appStore.openPackageTransferDialog('mod-export', {
    title: '导出当前环境模组',
    description: '可在导出前选择当前环境有效模组或当前启用模组，并按需附带环境数据。',
    sourceProfile: true,
    profileId: currentProfile.id || appStore.settings.current_profile_id || 'default',
    profileName: currentProfile.name || '当前环境',
    scopeOptions: [
      { value: 'profile-effective', label: `当前环境有效模组（${modStore.exportableVisibleCount}）`, description: '导出当前环境里能正常使用的模组。' },
      { value: 'profile-active', label: `当前环境启用模组（${modStore.exportableActiveCount}）`, description: '只导出当前环境里已经启用的模组。' },
    ],
    export_scope: 'profile-effective',
    folder_name_type: formData.value?.bundle_mod_folder_name_type || appStore.settings.bundle_mod_folder_name_type || 'default',
  })
}

// ====== 数据处理 ======
const handleReset = async () => {
  const ok = await confirmStore.confirmAction('确认重置', '重置后，分组、备注等本地数据将被清空，且无法撤销。确定继续吗？', { type: 'error' })
  if (ok) appStore.resetDatabase()
}

const handleRepair = async () => {
  const ok = await confirmStore.confirmAction(
    '确认修复',
    '这会尝试修复当前数据库。修复成功后需要重启软件才能生效。\n确定继续吗？',
    { type: 'warning', confirmText: '开始修复' }
  )
  if (!ok) return

  const res = await appStore.repairDatabase()
  if (!res || res.status !== 'success') {
    // 主动修复失败时不自动切换任何数据库，直接提示用户转向更保守的重置方案。
    const shouldReset = await confirmStore.confirmAction(
      '修复失败',
      '数据库修复失败，当前数据可能无法正常使用。建议立即重置数据库。',
      { type: 'error', confirmText: '立即重置', cancelText: '稍后处理' }
    )
    if (shouldReset) {
      await appStore.resetDatabase()
    }
    return
  }

  if (res.data?.initialized) {
    appStore.closeSettingsPanel()
    toast.success('未找到本地数据库，已重新创建。')
    return
  }

  const restartNow = await confirmStore.confirmAction(
    '修复完成',
    '数据库修复已完成。现在重启软件即可生效；如果暂不重启，当前仍会继续使用旧状态。',
    { type: 'success', confirmText: '立即重启', cancelText: '稍后重启' }
  )

  if (!restartNow) {
    toast.info('修复已完成，重启软件后生效。', { timeout: 4000 })
    return
  }

  appStore.closeSettingsPanel()
  await appStore.restartApplication()
}

const save = async () => {
  // 校验拦截
  // const hasError = Object.values(formData.value.check_info || {}).some(info => info && !info.pass)
  // if (hasError) {
  //   toast.error("存在无效路径，请修正后再保存！")
  //   return
  // }
  if (formData.value?.ui) {
    formData.value.ui.theme_id = appStore.settings.ui?.theme_id || DEFAULT_THEME_ID
  }
  await appStore.applySettings(formData.value)
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
  background: var(--color-border-subtle);
  border-radius: 10px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: var(--color-accent-primary);
}

/* 简单的类名修复，如果 Tailwind 不支持 */
.direction-rtl { direction: rtl; }
</style>
