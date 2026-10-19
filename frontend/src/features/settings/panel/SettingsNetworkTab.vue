<template>
  <section class="animate-in fade-in slide-in-from-right-4">
    <div class="flex items-center justify-between mb-6">
      <h3 class="text-lg font-bold text-text-main">{{ t('ui.settings.network.title', '网络协议与代理') }}
        <label v-tooltip="t('ui.settings.network.github_access_choice', '网络问题如果有稳定代理优先推荐代理，Github下载慢时可先试镜像源，无法连接可试下方的动态 Hosts。一种方式解决问题后，不必同时开启；两者都不能代替代理。')" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
      </h3>
      <button type="button" class="inline-flex items-center gap-1 px-3 py-1 bg-accent-success/10 hover:bg-accent-success/20 border border-accent-success/30 rounded text-xs font-bold text-accent-success transition-all" :disabled="networkCheckState.status === 'loading'" v-tooltip="t('tooltip.settings.network.network_check', '使用当前表单中的代理、Hosts 和 GitHub 镜像配置检测常用站点')" @click="handleNetworkCheck">
        <LoaderCircle v-if="networkCheckState.status === 'loading'" class="size-3 animate-spin" aria-hidden="true" />
        {{ networkCheckState.status === 'loading' ? t('ui.settings.network.network_checking', '检测中…') : t('ui.settings.network.network_check', '检测访问') }}
      </button>
    </div>
    <div v-if="networkCheckState.status !== 'idle'" class="mb-6 rounded-lg border border-border-base/10 bg-bg-inset/30 p-3 space-y-1.5" aria-live="polite">
      <p class="mb-2 text-xs text-text-dim">{{ t('ui.settings.network.network_check_desc', '检测当前表单中的代理、Hosts 和 GitHub 镜像配置对常用站点的访问情况与响应延迟。') }}</p>
      <p v-if="networkCheckState.status === 'error'" class="text-xs text-accent-danger">{{ t('ui.settings.network.network_check_failed', '检测请求未完成，请稍后重试。') }}</p>
      <div v-if="networkCheckState.targets?.length>0" class="overflow-x-auto">
        <table class="network-check-table w-full table-auto text-xs border-separate border-spacing-x-3 border-spacing-y-1.5">
          <colgroup><col class="network-check-fit-col" /><col class="network-check-domain-col" /><col class="network-check-fit-col" /><col class="network-check-fit-col" /></colgroup>
          <thead class="text-text-dim">
            <tr class="text-accent-primary">
              <th scope="col" class="text-left whitespace-nowrap font-normal">{{ t('ui.settings.network.network_check_name', '名称') }}</th>
              <th scope="col" class="text-left font-normal">{{ t('ui.settings.network.network_check_domain', '域名') }}</th>
              <th scope="col" class="text-right whitespace-nowrap font-normal">{{ t('ui.settings.network.network_check_latency', '延时') }}</th>
              <th scope="col" class="text-right whitespace-nowrap font-normal">{{ t('ui.settings.network.network_check_result', '状态码结果') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in (networkCheckState.targets || [])" :key="item.id">
              <td class="text-left text-text-main"><span class="block truncate" :title="item.label">{{ item.label }}</span></td>
              <td class="text-left font-mono text-text-dim"><span class="block truncate" :title="item.final_url || item.url">{{ item.domain }}</span></td>
              <td class="text-right whitespace-nowrap text-text-dim tabular-nums">{{ item.latency_ms != null ? `${item.latency_ms} ms` : '—' }}</td>
              <td class="text-right whitespace-nowrap" :class="networkCheckStatusClass(item)" v-tooltip="networkCheckTooltip(item)">{{ networkCheckStatusText(item) }}<template v-if="item.http_status"> · HTTP {{ item.http_status }}</template></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <div class="space-y-6">
      <div class="modal-section space-y-6 p-4">
        <CommonSwitch :label="t('ui.settings.network.enable_proxy', '启用代理服务')" v-model="formData.network.proxy.enabled" :description="t('ui.settings.network.enable_proxy_desc', '启用代理服务，所有网络请求将通过代理服务器处理，部分外置数据下载、更新检查、简介图片加载、内部浏览器访问等功能可能需要该配置才能正常使用。\n\n也可以在软件外部自行配置全局网络环境。')" mini />
        <div v-if="formData.network.proxy.enabled" class="grid grid-cols-6 gap-3 animate-in zoom-in-95">
          <CommonSelect class="col-span-2" :label="t('ui.settings.network.protocol', '协议')" v-model="formData.network.proxy.type" :options="proxyTypeOptions" />
          <CommonInput class="col-span-3" :label="t('ui.settings.network.host', '主机地址')" v-model="formData.network.proxy.host" placeholder="127.0.0.1" />
          <CommonNumber class="col-span-1" :label="t('ui.settings.network.port', '端口')" v-model="formData.network.proxy.port" :step="1" :min="1" :max="65535" />
          <CommonSecretInput class="col-span-3" :label="t('ui.settings.network.username', '用户名')" v-model="formData.network.proxy.username"
            secret-key="network.proxy.username" :secret-status="secretStatus('network.proxy.username')" :preserved="isSecretPreserved('network.proxy.username')" :reveal-secret="revealSecret"
            :placeholder="t('ui.settings.network.proxy_username_placeholder', '代理用户名（可选）')" @preserve="$emit('preserve-secret', $event)" @clear="$emit('clear-secret', $event)" />
          <CommonSecretInput class="col-span-3" :label="t('ui.settings.network.password', '密码')" v-model="formData.network.proxy.password"
            secret-key="network.proxy.password" :secret-status="secretStatus('network.proxy.password')" :preserved="isSecretPreserved('network.proxy.password')" :reveal-secret="revealSecret"
            :placeholder="t('ui.settings.network.proxy_password_placeholder', '代理密码（可选）')" @preserve="$emit('preserve-secret', $event)" @clear="$emit('clear-secret', $event)" />
          <div class="col-span-6">
            <CommonTagInput :label="t('ui.settings.network.proxy_bypass_domains', '不走代理的域名')" v-model="formData.network.proxy.bypass_list" />
          </div>

          <div class="col-span-6 grid grid-cols-2 gap-3">
            <CommonSwitch :label="t('ui.settings.network.use_proxy_on_steamcmd', '为 SteamCMD 使用代理')" v-model="formData.network.use_proxy_on_steamcmd" :description="t('ui.settings.network.use_proxy_on_steamcmd_desc', 'SteamCMD 是否使用代理服务器。\n\n如果启用，SteamCMD 下载、更新、安装等操作将通过代理服务器进行。')" />
            <CommonSwitch :label="t('ui.settings.network.use_proxy_on_ai', '为 AI 请求使用代理')" v-model="formData.network.use_proxy_on_ai" :description="t('ui.settings.network.use_proxy_on_ai_desc', '如果启用，AI 将通过代理服务器进行。已经是国内代理后的端口不用开此选项。')" />
          </div>
        </div>
      </div>
      <div class="modal-section space-y-2 p-4">
        <h4 class="text-sm font-bold text-text-main flex items-center gap-1">
          {{ t('ui.settings.network.github_access_title', 'GitHub 镜像源') }}
          <label v-tooltip="t('ui.settings.network.github_access_desc', 'GitHub 镜像源可以代替 GitHub 提供项目页面、文件、源码包和发行版下载，帮助解决访问慢或失败。镜像不可用时会回退直连。')" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
        </h4>
        <div class="flex gap-2">
          <CommonSelect class="flex-1" v-model="formData.github_mirror_id" :options="githubMirrorOptions" 
            :label="t('ui.settings.network.github_mirror_selector_label', '镜像节点')" :description="t('ui.settings.network.github_mirror_selector_help', '选择要使用的 GitHub 镜像节点。自动选择会从当前可用节点中选择延迟较低的节点。')" />
          <div class="flex gap-2 justify-end items-end">
            <button type="button" class="input-addon-button size-9 rounded-lg flex items-center justify-center" :aria-label="t('ui.settings.network.mirror_add', '新增镜像')" v-tooltip="mirrorActionTooltip('add')" @click="handleEditMirror()"><Plus class="size-4" aria-hidden="true" /></button>
            <button type="button" class="input-addon-button size-9 rounded-lg flex items-center justify-center disabled:opacity-40" :disabled="!selectedMirror" :aria-label="t('ui.settings.network.mirror_edit', '编辑所选镜像')" v-tooltip="mirrorActionTooltip('edit')" @click="handleEditMirror(selectedMirror)"><Pencil class="size-4" aria-hidden="true" /></button>
            <button type="button" class="input-addon-button size-9 rounded-lg flex items-center justify-center disabled:opacity-40" :disabled="!selectedMirror" :aria-label="t('ui.settings.network.mirror_remove', '删除所选镜像')" v-tooltip="mirrorActionTooltip('remove')" @click="handleRemoveMirror"><Trash2 class="size-4" aria-hidden="true" /></button>
            <button type="button" class="input-addon-button size-9 rounded-lg flex items-center justify-center disabled:opacity-40" :disabled="!formData._github_mirrors_path" :aria-label="t('ui.settings.network.mirror_open_file', '打开镜像配置文件')" v-tooltip="mirrorActionTooltip('open')" @click="handleOpenMirrorsFile"><ExternalLink class="size-4" aria-hidden="true" /></button>
          </div>
        </div>
        <div class="text-xs text-text-dim pl-1">
          <p>{{ t('ui.settings.network.mirror_file_help', '新增、编辑、删除后，点击设置页的“保存”才会生效。也可以直接编辑配置文件，修改后需要重启软件。') }}</p>
        </div>
        <CommonSwitch :label="t('ui.settings.network.dynamic_mirrors_enabled', '启用动态镜像节点')" v-model="formData.github_dynamic_mirrors_enabled" :description="t('ui.settings.network.dynamic_mirrors_enabled_desc', '开启后立即获取并检测动态镜像节点，并将通过检测的节点加入上方镜像节点选择器。关闭后不会使用动态节点。')" />
      </div>
      <div class="modal-section space-y-2 p-4">
        <h4 class="text-sm font-bold text-text-main flex items-center gap-1">
          {{ t('ui.settings.network.hosts_title', 'Hosts 地址映射') }}
          <label v-tooltip="t('ui.settings.network.hosts_help', 'Hosts 就像网站地址簿，告诉软件某个域名应该连接哪个 IP。域名解析出错时，它可能帮助恢复访问，但不能保证目标服务器一定可用。默认只在软件内部生效。动态 Hosts 从来源自动获取，自定义 Hosts 由你手动填写。')" class="text-text-dim ml-1 cursor-help italic underline hover:text-text-main">?</label>
        </h4>
        <CommonKVEditor :label="t('ui.settings.network.custom_hosts', '自定义 Hosts 映射')" :description="t('ui.settings.network.custom_hosts_desc', '手动指定域名对应的 IP 地址。一般不需要修改，只有在你明确知道目标地址时才使用。')" v-model="formData.network.hosts" />
        
        <CommonSwitch :label="t('ui.settings.network.github_hosts_enabled', '动态 Hosts')" v-model="formData.network.github_hosts_enabled" :description="t('ui.settings.network.github_hosts_enabled_desc', '从可信来源获取网站的 IP 地址，帮助解决域名解析导致的连接失败，适用于来源中包含的任何网站。打开开关立即后台获取，保存后生效；失败时保留已有映射。')" />
        <div v-if="formData.network.github_hosts_enabled" class="grid grid-cols-2 gap-3 animate-in zoom-in-95">
          <div class="col-span-2 space-y-1 py-2">
            <div class="flex items-center justify-between gap-2 px-1 mb-2">
              <span class="text-xs font-bold text-text-dim">{{ t('ui.settings.network.github_hosts_url', 'Hosts 来源') }}<label v-tooltip="t('ui.settings.network.github_hosts_url_desc', '支持 Hosts 文本或 JSON 的 HTTPS 地址，可逐条编辑、启停和删除。同一域名优先使用排在前面的有效来源；某个来源失败时仍会使用其他成功来源。')" class="ml-1 cursor-help italic underline">?</label></span>
              <button type="button" class="text-xs text-accent-primary hover:underline" @click="hostsSources.push({ url: '', enabled: true })">{{ t('ui.settings.network.hosts_source_add', '+ 新增来源') }}</button>
            </div>
            <div v-for="(source, index) in hostsSources" :key="index" class="flex items-center gap-1 group pl-2 animate-in slide-in-from-left-2 duration-200">
              <input type="checkbox" v-model="source.enabled" class="size-4 shrink-0 accent-accent-primary" :aria-label="t('ui.settings.network.hosts_source_enabled', '启用此 Hosts 来源')" v-tooltip="t('ui.settings.network.hosts_source_enabled', '启用此 Hosts 来源')" />
              <input class="min-w-0 flex-1 bg-bg-inset/70 border border-border-base/5 rounded-md px-2 py-1 text-sm text-text-main font-mono focus:outline-none focus:border-accent-primary/40" :class="{ 'opacity-60': !source.enabled }" :value="source.url" placeholder="https://example.com/hosts" :aria-label="t('ui.settings.network.github_hosts_url', 'Hosts 来源')" @change="source.url = $event.target.value.trim()" @keydown.enter.prevent="$event.target.blur()" />
              <button type="button" class="px-2 text-text-dim hover:text-accent-danger transition-colors opacity-0 group-hover:opacity-100" :aria-label="t('ui.settings.network.hosts_source_remove', '删除此 Hosts 来源')" v-tooltip="t('ui.settings.network.hosts_source_remove', '删除此 Hosts 来源')" @click="hostsSources.splice(index, 1)"><Trash2 class="size-3.5" aria-hidden="true" /></button>
            </div>
            <p v-if="!activeHostsSources" class="text-xs text-text-dim">{{ t('ui.settings.network.hosts_sources_empty', '当前没有启用的 Hosts 来源，请添加地址并勾选启用。') }}</p>
          </div>
          <CommonSwitch :label="t('ui.settings.network.github_hosts_auto_update', '自动更新动态 Hosts')" v-model="formData.network.github_hosts_auto_update" :description="t('ui.settings.network.github_hosts_auto_update_desc', '软件启动时，超过更新间隔后自动更新动态 Hosts。')" />
          <CommonNumber :label="t('ui.settings.network.github_hosts_refresh_interval', '更新间隔（小时）')" v-model="formData.network.github_hosts_refresh_interval_hours" :step="1" :min="1" :max="720" />
        </div>
        <div v-if="formData.network.github_hosts_enabled" class="text-xs px-2 mt-4" aria-live="polite">
          <p v-if="hostsState.status === 'loading'" class="flex items-center gap-2 text-text-dim" role="status">
            <LoaderCircle class="size-4 animate-spin shrink-0" aria-hidden="true" />
            {{ t('ui.settings.network.github_hosts_loading', '正在后台获取 Hosts，请稍候。网络较慢时可能需要一分钟以上，不影响保存设置。') }}
          </p>
          <div v-else-if="hostsState.status === 'error'" class="flex flex-wrap items-center gap-2 text-accent-danger" role="alert">
            <span>{{ hostsState.error === 'timeout' ? t('ui.settings.network.github_hosts_timeout', '获取 Hosts 超时，请检查网络或稍后重试。已有映射会继续保留。') : t('ui.settings.network.github_hosts_failed', '获取 Hosts 失败，请检查网络和来源地址后重试。已有映射会继续保留。') }}</span>
            <button type="button" class="px-2 py-2 underline" @click="hostsRetry += 1">{{ t('ui.settings.network.github_hosts_retry', '重新获取') }}</button>
          </div>
          <p v-else-if="hostsState.status === 'ready'" class="text-accent-success">
            {{ hostsState.is_applied ? t('ui.settings.network.github_hosts_ready', 'Hosts 已获取并应用。') : t('ui.settings.network.hosts_pending_save', 'Hosts 已获取，保存设置后生效。') }}
          </p>
          <p v-if="hostsState.status === 'ready' && hostsState.source_errors?.length" class="mt-1 text-accent-warn" :title="hostsState.source_errors.map(item => item.url).join('\n')">{{ t('ui.settings.network.hosts_partial_failure', '部分来源获取失败，已使用成功来源的映射。可检查来源后重新获取。') }} <button type="button" class="underline" @click="hostsRetry += 1">{{ t('ui.settings.network.github_hosts_retry', '重新获取') }}</button></p>
        </div>
        <details v-if="formData.network.github_hosts_enabled" class="rounded-lg border border-border-base/10 bg-bg-inset/30 px-3 py-2 mb-4">
          <summary class="cursor-pointer text-xs font-bold text-text-dim hover:text-text-main">{{ t('ui.settings.network.effective_hosts_title', '查看当前生效的动态 Hosts') }}</summary>
          <div v-if="Object.keys(hostsState.dynamic_hosts || {}).length" class="mt-3 space-y-1.5">
            <div v-for="(ip, host) in (hostsState.dynamic_hosts || {})" :key="host" class="flex flex-wrap items-center gap-2 rounded-md bg-bg-inset/60 px-2.5 py-1.5 text-xs font-mono">
              <span class="min-w-0 flex-1 break-all text-text-main">{{ host }}</span>
              <span class="break-all text-accent-primary">{{ ip }}</span>
            </div>
          </div>
          <p v-else class="mt-3 text-xs text-text-dim">{{ t('ui.settings.network.effective_hosts_empty', '当前没有生效的动态 Hosts 映射。') }}</p>
          <p class="mt-2 text-[0.7rem] text-text-dim break-all">{{ t('ui.settings.network.effective_hosts_desc', '只读显示动态 Hosts；缓存文件：') }} {{ hostsState.cache_path || 'data/cache/github_hosts.json' }}</p>
        </details>
        <CommonSwitch :label="t('ui.settings.network.write_to_system_hosts', '将 Hosts 映射应用到系统')" v-model="formData.network.write_to_system_hosts" :description="t('ui.settings.network.write_to_system_hosts_desc', '将动态和自定义映射写入系统 Hosts，让其他软件也能使用，通常无需开启。保存相关设置或点击重试时，Windows 可能请求管理员授权；启动更新和退出清理不会弹出授权窗口。退出时会尝试移除映射，无权清理时可能保留，请在退出前关闭此项并保存。')" />
        <p v-if="hostsState.system_hosts?.status === 'authorizing'" class="text-xs text-text-dim px-4" role="status">{{ t('ui.settings.network.system_hosts_authorizing', '正在等待管理员授权，请留意系统授权窗口。不影响设置保存。') }}</p>
        <p v-else-if="hostsState.system_hosts?.status === 'applying'" class="text-xs text-text-dim px-4" role="status">{{ t('ui.settings.network.system_hosts_applying', '正在更新系统 Hosts') }}</p>
        <div v-else-if="hostsState.system_hosts?.status === 'error'" class="text-xs text-accent-warn px-4 space-y-1" role="alert">
          <p>{{ t(hostsState.system_hosts.message_key, hostsState.system_hosts.message) }}</p>
          <button type="button" class="underline py-1" @click="systemHostsRetry += 1">{{ t('ui.settings.network.system_hosts_retry', '重试已保存的系统 Hosts 设置') }}</button>
        </div>
        <p class="text-xs text-text-dim px-2">{{ t('ui.settings.network.hosts_priority', '同一域名同时出现在动态和自定义映射中时，优先使用自定义映射。') }}</p>
      </div>
      
    
      <div class="modal-section space-y-4 p-4">
        <CommonSwitch :label="t('ui.settings.network.enable_steam_enhanced_api', '启用工坊增强信息')" v-model="formData.enable_steam_enhanced_api" mini :description="t('ui.settings.network.enable_steam_enhanced_api_desc', '开启并填写 Key 后，工坊页会优先使用在线增强信息；没有 Key 或关闭此项时会自动使用本地缓存搜索。')" />
        <div class="flex items-end gap-2" :class="{'opacity-60': !formData.enable_steam_enhanced_api}">
          <CommonSecretInput class="flex-1" :label="t('ui.settings.network.steam_web_api_key', 'Steam Web API Key')" v-model="formData.steam_web_api_key"
            secret-key="steam.web_api_key" :secret-status="secretStatus('steam.web_api_key')" :preserved="isSecretPreserved('steam.web_api_key')" :reveal-secret="revealSecret"
            :placeholder="t('ui.settings.network.steam_web_api_key_placeholder', '填写后启用增强搜索')" :description="t('ui.settings.network.steam_web_api_key_desc', 'Key 会安全保存在本机凭据库。没有 Key 时会自动回到缓存搜索。')"
            @preserve="$emit('preserve-secret', $event)" @clear="$emit('clear-secret', $event)" />
          <button @click="openUrlOnSteam('https://steamcommunity.com/dev/apikey')"
            class="px-2 py-2 m-0.5 bg-bg-overlay/5 hover:bg-bg-overlay/10 border border-border-base/10 rounded-lg text-xs font-bold cursor-pointer transition-all">
            <span class="flex items-center gap-2">
              {{ t('ui.settings.network.visit', '访问') }}<p class="text-accent-cool">API Key</p>{{ t('ui.settings.network.get_page', '获取页面') }}
            </span>
          </button>
        </div>
        <div class="text-xs ">
          <p class="mt-1 leading-relaxed text-text-dim">
            {{ t('ui.settings.network.steam_web_api_key_help', '开启并填写 Key 后，会使用 Steam Web API 获取更完整的工坊搜索、合集搜索、作者作品和依赖关联信息。关闭时仍可使用本地缓存工坊数据库。') }}
          </p>
          <span class="text-accent-warn">{{ t('ui.settings.network.steam_web_api_key_warning', '注意！“API 密钥（API Key）相当于你的 Steam 账号后门钥匙”。可以读取账号公开数据/库存信息 以及 管理与监听交易报价。') }}</span>
          <p>{{ t('ui.settings.network.steam_web_api_key_risk', '任何人一旦获取了此 Key，就可以在不触发 Steam 令牌的情况下，暗中取消玩家的真实交易，并替换为发给骗子的假交易。绝对不要将 API 密钥分享给任何人或任何未经验证的第三方网站。') }}</p>
        </div>
      </div>
      <section aria-labelledby="network-community-tools-title" class="modal-section space-y-3 p-4">
        <h4 id="network-community-tools-title" class="text-sm font-bold text-text-main">{{ t('ui.settings.network.community_tools_title', '社区网络工具推荐') }}</h4>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <a href="https://steampp.net/" target="_blank" rel="noopener noreferrer" @click.prevent="appStore.openUrl('https://steampp.net/')"
            class="group flex min-w-0 flex-col gap-2 rounded-xl border border-border-base/10 bg-bg-inset/30 p-4 transition-colors hover:border-accent-primary/30 hover:bg-accent-primary/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-primary">
            <span class="flex items-center justify-between gap-2 text-sm font-bold text-text-main">
              Watt Toolkit (Steam++)
              <ExternalLink class="size-4 shrink-0 text-text-dim group-hover:text-accent-primary" aria-hidden="true" />
            </span>
            <p class="text-xs leading-relaxed text-text-dim">{{ t('ui.settings.network.steampp_description', '为 Steam 社区、创意工坊等网站提供访问加速，并集成账号切换等 Steam 实用工具。') }}</p>
            <span class="mt-auto flex flex-wrap items-center justify-between gap-2 pt-2 text-xs">
              <span class="text-text-dim">steampp.net</span>
              <span class="font-bold text-accent-primary">{{ t('ui.settings.network.visit_tool_website', '访问工具网页') }}</span>
            </span>
          </a>
          <a href="https://www.dogfight360.com/blog/18682/" target="_blank" rel="noopener noreferrer" @click.prevent="appStore.openUrl('https://www.dogfight360.com/blog/18682/')"
            class="group flex min-w-0 flex-col gap-2 rounded-xl border border-border-base/10 bg-bg-inset/30 p-4 transition-colors hover:border-accent-primary/30 hover:bg-accent-primary/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-primary">
            <span class="flex items-center justify-between gap-2 text-sm font-bold text-text-main">
              Steamcommunity 302
              <ExternalLink class="size-4 shrink-0 text-text-dim group-hover:text-accent-primary" aria-hidden="true" />
            </span>
            <p class="text-xs leading-relaxed text-text-dim">{{ t('ui.settings.network.steamcommunity302_description', '改善 Steam 社区、创意工坊等页面的连接问题，遇到网页打不开或图片加载异常时可以尝试。') }}</p>
            <span class="mt-auto flex flex-wrap items-center justify-between gap-2 pt-2 text-xs">
              <span class="text-text-dim">dogfight360.com</span>
              <span class="font-bold text-accent-primary">{{ t('ui.settings.network.visit_tool_website', '访问工具网页') }}</span>
            </span>
          </a>
        </div>
        <p class="text-xs leading-relaxed text-text-dim">{{ t('ui.settings.network.community_tools_help', '以上工具由社区独立维护，需自行下载并按工具说明启用。建议先使用一种，避免多个加速工具同时开启造成冲突。') }}</p>
      </section>
    </div>
  </section>
  <CommonModalShell :show="!!mirrorDraft" :title="t('ui.settings.network.mirror_editor', '编辑 GitHub 镜像源')" size="compact" :z-index="UI_Z_INDEX.SECONDARY_MODAL" content-class="overflow-y-auto" @close="mirrorDraft = null">
    <form v-if="mirrorDraft" class="p-5 space-y-4" @submit.prevent="handleApplyMirror">
      <CommonInput :label="t('ui.settings.network.mirror_name', '镜像名称')" v-model="mirrorDraft.label" />
      <CommonInput :label="t('ui.settings.network.mirror_id', '镜像 ID（字母、数字、下划线或短横线）')" v-model="mirrorDraft.id" />
      <CommonInput :label="t('ui.settings.network.mirror_url', '镜像转换地址')" v-model="mirrorDraft.url_template" placeholder="https://example.com/{url}" />
      <p class="px-2 text-xs text-text-dim">{{ t('ui.settings.network.mirror_url_help', '填写镜像服务提供的 HTTPS 转换地址，用 {url} 代表原始 GitHub 地址。保存前会自动检查项目页面、Raw 文件和源码压缩包是否支持。') }}</p>
      <div v-if="mirrorProbeRunning" class="flex items-center gap-2 text-xs text-text-dim" role="status">
        <LoaderCircle class="size-4 animate-spin" aria-hidden="true" />
        {{ t('ui.settings.network.mirror_probe_loading', '正在检测镜像支持的功能，请稍候…') }}
      </div>
      <div v-else-if="mirrorProbe" class="space-y-1 rounded-lg border border-border-base/10 bg-bg-inset/30 px-3 py-2 text-xs">
        <p class="font-bold text-text-dim">{{ t('ui.settings.network.mirror_probe_result', '自动检测结果') }}</p>
        <p v-for="(item, key) in mirrorProbe" :key="key" :class="item.status === 'supported' ? 'text-accent-success' : item.status === 'unsupported' ? 'text-accent-danger' : 'text-accent-warn'">
          {{ mirrorCapabilityLabel(key) }}：{{ mirrorProbeStatusLabel(item.status) }}
        </p>
      </div>
      <p v-if="mirrorError" class="text-xs text-accent-danger" role="alert">{{ mirrorError }}</p>
      <div class="flex justify-end gap-2">
        <button type="button" class="input-addon-button min-h-10 rounded-lg px-4 text-sm" @click="mirrorDraft = null">{{ t('common.action.cancel', '取消') }}</button>
        <button type="submit" class="min-h-10 rounded-lg px-4 text-sm bg-accent-primary text-on-accent-primary disabled:opacity-50" :disabled="mirrorProbeRunning">{{ t('ui.settings.network.mirror_apply', '检测并加入设置') }}</button>
      </div>
    </form>
  </CommonModalShell>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ExternalLink, FolderOpen, Link, LoaderCircle, Pencil, Plus, Trash2 } from 'lucide-vue-next'
import { useAppStore } from '../../../app/stores/appStore'
import CommonSwitch from '../../../shared/components/input/CommonSwitch.vue'
import CommonInput from '../../../shared/components/input/CommonInput.vue'
import CommonSecretInput from '../../../shared/components/input/CommonSecretInput.vue'
import CommonNumber from '../../../shared/components/input/CommonNumber.vue'
import CommonSelect from '../../../shared/components/input/CommonSelect.vue'
import CommonTagInput from '../../../shared/components/input/CommonTagInput.vue'
import CommonKVEditor from '../../../shared/components/input/CommonKVEditor.vue'
import CommonModalShell from '../../../shared/components/modal/CommonModalShell.vue'
import { UI_Z_INDEX } from '../../../shared/lib/constants'
import { toast } from '../../../shared/lib/common'
import { buildSteamOpenUrl, dispatchSteamUri } from '../../../shared/lib/steamUri'
import { t } from '../../../shared/i18n.js'

const props = defineProps({
  formData: { type: Object, required: true },
  revealSecret: { type: Function, default: null },
  isSecretPreserved: { type: Function, default: () => false },
})

defineEmits(['preserve-secret', 'clear-secret'])

const appStore = useAppStore()
const proxyTypeOptions = computed(() => [
  { label: 'HTTP', value: 'http' },
  { label: 'SOCKS5', value: 'socks5' },
])

const githubMirrorCatalog = ref({ status: 'idle', mirrors: [], updated_at: 0, source_errors: [] })
const mirrorSupportLabel = (item) => {
  const labels = { web: '内容', raw: '文件', archive: '源码包', release_asset: '发行版', api: 'API', gist: 'Gist', git_clone: 'Clone', lfs_media: 'LFS' }
  const statuses = item?.support || {}
  return Object.entries(labels).filter(([key]) => statuses[key]?.status === 'supported').map(([, label]) => label).join('/')
}
const mirrorOption = (item) => ({
  label: `${item.label || item.id}${mirrorSupportLabel(item) ? ` · ${mirrorSupportLabel(item)}` : ''}`,
  value: item.selection_id || `${item.origin || 'custom'}:${item.id}`,
})
const githubMirrorOptions = computed(() => {
  const pools = githubMirrorCatalog.value.pools || {}
  const builtin = Array.isArray(pools.builtin) && pools.builtin.length ? pools.builtin : [{ id: 'gh_proxy', selection_id: 'builtin:gh_proxy', label: 'GH-Proxy', support: { web: { status: 'supported' }, raw: { status: 'supported' }, archive: { status: 'supported' }, release_asset: { status: 'supported' } } }]
  const custom = (Array.isArray(props.formData.github_mirrors) ? props.formData.github_mirrors : []).map(item => ({ ...item, origin: 'custom', selection_id: item.selection_id || `custom:${item.id}` }))
  const dynamic = formDataDynamicEnabled.value ? (Array.isArray(pools.dynamic) ? pools.dynamic : githubMirrorCatalog.value.mirrors || []) : []
  const options = [
    { label: t('ui.settings.network.github_mirror_direct', 'GitHub 直连'), value: 'direct' },
    ...(formDataDynamicEnabled.value ? [{ label: t('ui.settings.network.github_mirror_auto', '自动选择镜像'), value: 'auto' }] : []),
    ...builtin.map(mirrorOption),
    ...custom.map(mirrorOption),
    ...dynamic.map(mirrorOption),
  ]
  return options.filter((item, index, all) => all.findIndex(candidate => candidate.value === item.value) === index)
})
const formDataDynamicEnabled = computed(() => !!props.formData.github_dynamic_mirrors_enabled)
const selectedMirror = computed(() => {
  const selected = String(props.formData.github_mirror_id || '')
  return selected.startsWith('custom:')
    ? (props.formData.github_mirrors || []).find(item => `custom:${item.id}` === selected || item.id === selected) || null
    : null
})
const handleRefreshMirrorCatalog = async () => {
  githubMirrorCatalog.value = { ...githubMirrorCatalog.value, status: 'loading' }
  try {
    const result = await window.pywebview?.api?.github_refresh_mirror_catalog?.({ probe_limit: 8 })
    if (result?.status !== 'success') throw new Error('catalog refresh failed')
    githubMirrorCatalog.value = result.data || { status: 'error', mirrors: [] }
    if (githubMirrorCatalog.value.status === 'loading') {
      const poll = async () => {
        const next = await window.pywebview?.api?.github_mirror_catalog?.()
        if (next?.status !== 'success') throw new Error('catalog status failed')
        githubMirrorCatalog.value = next.data || { status: 'error', mirrors: [] }
        if (githubMirrorCatalog.value.status === 'loading') window.setTimeout(() => void poll(), 800)
      }
      window.setTimeout(() => void poll(), 500)
    }
  } catch {
    githubMirrorCatalog.value = { ...githubMirrorCatalog.value, status: 'error' }
  }
}
const loadMirrorCatalogCache = async () => {
  try {
    const result = await window.pywebview?.api?.github_mirror_catalog?.()
    if (result?.status === 'success') githubMirrorCatalog.value = result.data || githubMirrorCatalog.value
  } catch { /* 缓存读取失败不影响其它网络设置。 */ }
}
watch(formDataDynamicEnabled, (enabled, previous) => {
  if (enabled && !previous) void handleRefreshMirrorCatalog()
  if (!enabled && (props.formData.github_mirror_id === 'auto' || String(props.formData.github_mirror_id || '').startsWith('dynamic:'))) {
    props.formData.github_mirror_id = 'direct'
  }
})
onMounted(() => { void loadMirrorCatalogCache() })
const networkCheckState = ref({ status: 'idle', targets: [] })
const networkCheckRunId = ref(0)

const buildNetworkCheckPayload = () => ({
  network: {
    ...(props.formData.network || {}),
    proxy: { ...(props.formData.network?.proxy || {}) },
    effective_hosts: {
      ...(props.formData.network?.effective_hosts || {}),
      ...(hostsState.value?.dynamic_hosts || {}),
    },
  },
  github_mirror_id: props.formData.github_mirror_id,
  github_dynamic_mirrors_enabled: props.formData.github_dynamic_mirrors_enabled,
  github_mirrors: Array.isArray(props.formData.github_mirrors) ? props.formData.github_mirrors.map(item => ({ ...item })) : [],
  _preserve_secret_keys: Array.isArray(props.formData._preserve_secret_keys) ? [...props.formData._preserve_secret_keys] : [],
})

const handleNetworkCheck = async () => {
  const runId = ++networkCheckRunId.value
  networkCheckState.value = { status: 'loading', targets: [] }
  try {
    const payload = buildNetworkCheckPayload()
    const plan = await window.pywebview?.api?.network_check_access({ ...payload, _network_check_plan_only: true })
    if (runId !== networkCheckRunId.value || plan?.status !== 'success') throw new Error('Network check plan failed')
    const plannedTargets = (plan.data?.targets || []).map(item => ({
      ...item,
      status: 'loading',
      http_status: null,
      latency_ms: null,
      error: '',
      error_code: '',
    }))
    networkCheckState.value = { status: 'loading', targets: plannedTargets }

    await Promise.all(plannedTargets.map(async target => {
      let resultItem
      try {
        const result = await window.pywebview?.api?.network_check_access({
          ...payload,
          _network_check_target_ids: [target.id],
        })
        if (result?.status === 'success') resultItem = result.data?.targets?.[0]
      } catch { /* 单个目标失败时仍显示其它目标的结果。 */ }
      if (!resultItem) resultItem = { ...target, status: 'failed', error: t('ui.settings.network.network_check_failed_item', '无法访问') }
      if (runId !== networkCheckRunId.value) return
      networkCheckState.value = {
        ...networkCheckState.value,
        targets: networkCheckState.value.targets.map(item => item.id === target.id ? resultItem : item),
      }
    }))
    if (runId === networkCheckRunId.value) networkCheckState.value = { ...networkCheckState.value, status: 'ready' }
  } catch {
    if (runId === networkCheckRunId.value) networkCheckState.value = { status: 'error', targets: [] }
  }
}

const networkCheckStatusClass = (item) => {
  if (item?.status === 'loading') return 'text-text-dim'
  if (item?.http_status >= 400 || ['failed', 'timeout'].includes(item?.status)) return 'text-accent-danger'
  if (item?.http_status >= 300 || item?.status === 'http_error') return 'text-accent-warn'
  if (item?.status === 'ok') return 'text-accent-success'
  return 'text-accent-danger'
}

const networkCheckStatusText = (item) => {
  if (item?.status === 'loading') return t('ui.settings.network.network_check_loading_item', '正在加载')
  if (item?.status === 'ok' && item?.http_status < 300) return t('ui.settings.network.network_check_ok', '可访问')
  if (item?.http_status >= 300 && item?.http_status < 400) return t('ui.settings.network.network_check_redirect', '需要跳转')
  if (item?.status === 'http_error' || item?.http_status >= 300) return t('ui.settings.network.network_check_http_error', '服务返回错误')
  if (item?.status === 'timeout') return t('ui.settings.network.network_check_timeout', '连接超时')
  return t('ui.settings.network.network_check_failed_item', '无法访问')
}

const networkCheckTooltip = (item) => [
  item?.url ? `${t('ui.settings.network.network_check_url', '地址')}: ${item.url}${item.final_url && item.final_url !== item.url ? ` → ${item.final_url}` : ''}` : '',
  item?.http_status ? `${t('ui.settings.network.network_check_status_code', '状态码')}: HTTP ${item.http_status}` : '',
  item?.error_code ? `${t('ui.settings.network.network_check_error_code', '错误代码')}: ${item.error_code}` : '',
  item?.route ? `${t('ui.settings.network.network_check_route', '连接方式')}: ${item.route === 'proxy' ? t('ui.settings.network.network_check_proxy', '代理') : t('ui.settings.network.network_check_direct', '直连')}${item.proxy_bypassed ? `（${t('ui.settings.network.network_check_bypass', '已按绕过列表直连')}）` : ''}` : '',
  item?.mirror_label ? `${t('ui.settings.network.network_check_mirror', '已使用镜像源')}: ${item.mirror_label}` : '',
  item?.hosts_hit ? t('ui.settings.network.network_check_hosts_hit', '已使用 Hosts 映射') : '',
  item?.error ? `${t('ui.settings.network.network_check_reason', '说明')}: ${item.error}` : '',
].filter(Boolean).join('\n')

const mirrorActionTooltip = (action) => {
  if (action === 'edit') return `${t('ui.settings.network.mirror_edit', '编辑所选镜像')}：${t('ui.settings.network.mirror_edit_help', '修改当前选中的镜像配置')}`
  if (action === 'remove') return `${t('ui.settings.network.mirror_remove', '删除所选镜像')}：${t('ui.settings.network.mirror_remove_help', '删除当前选中的镜像配置')}`
  if (action === 'open') return `${t('ui.settings.network.mirror_open_file', '打开镜像配置文件')}：${t('ui.settings.network.mirror_open_file_help', '打开镜像列表文件进行查看或编辑')}`
  return `${t('ui.settings.network.mirror_add', '新增镜像')}：${t('ui.settings.network.mirror_add_help', '添加一个自定义 GitHub 镜像源')}`
}

const mirrorDraft = ref(null)
const mirrorEditingId = ref(null)
const mirrorError = ref('')
const mirrorProbe = ref(null)
const mirrorProbeRunning = ref(false)
const mirrorCapabilityLabel = (key) => ({
  web: t('ui.settings.network.mirror_type_web', '项目页面'),
  raw: t('ui.settings.network.mirror_type_raw', 'Raw 文件'),
  archive: t('ui.settings.network.mirror_type_archive', '源码压缩包'),
  release_asset: t('ui.settings.network.mirror_type_release', '发行版附件'),
  api: t('ui.settings.network.mirror_type_api', 'GitHub API'),
  git_clone: t('ui.settings.network.mirror_type_clone', 'Git Clone'),
  gist: t('ui.settings.network.mirror_type_gist', 'Gist 内容'),
  lfs_media: t('ui.settings.network.mirror_type_lfs', 'LFS 媒体文件'),
}[key] || key)
const mirrorProbeStatusLabel = (status) => ({
  supported: t('ui.settings.network.mirror_status_supported', '支持'),
  unsupported: t('ui.settings.network.mirror_status_unsupported', '不支持'),
  unknown: t('ui.settings.network.mirror_status_unknown', '未知'),
}[status] || t('ui.settings.network.mirror_status_unknown', '未知'))

const handleEditMirror = (mirror = null) => {
  mirrorEditingId.value = mirror?.id ?? null
  mirrorError.value = ''
  mirrorProbe.value = mirror?.support || null
  mirrorDraft.value = mirror ? { ...mirror, support: mirror.support ? { ...mirror.support } : undefined, health: mirror.health ? { ...mirror.health } : undefined }
    : { id: '', label: '', url_template: '' }
}

const handleApplyMirror = async () => {
  const draft = mirrorDraft.value
  const id = draft.id.trim().toLowerCase()
  const template = draft.url_template.trim()
  const mirrors = props.formData.github_mirrors || []
  let isValidUrl = false
  try {
    const url = new URL(template.replace('{url}', 'https://github.com/example/repo'))
    isValidUrl = url.protocol === 'https:' && !!url.hostname && !url.username && !url.password && !url.hash
      && !new URL(template).host.includes('{')
  } catch { /* 无效地址由下方统一提示。 */ }
  if (!/^[a-z0-9_-]+$/.test(id) || id === 'direct' || mirrors.some(item => item.id === id && item.id !== mirrorEditingId.value)
    || !draft.label.trim() || !isValidUrl || template.split('{url}').length !== 2
    || /[{}\r\n]/.test(template.replace('{url}', ''))) {
    mirrorError.value = t('ui.settings.network.mirror_invalid', '请填写名称、唯一的有效 ID 和包含一个 {url} 的 HTTPS 地址。ID 不能使用 direct。')
    return
  }
  mirrorProbeRunning.value = true
  mirrorError.value = ''
  try {
    const probeApi = window.pywebview?.api?.github_probe_mirror
    if (typeof probeApi !== 'function') throw new Error('probe API unavailable')
    const result = await probeApi({ id, label: draft.label.trim(), url_template: template })
    if (result?.status !== 'success' || !result.data?.support) throw new Error('probe failed')
    const probe = result.data
    mirrorProbe.value = probe.support
    const mirror = { id, label: draft.label.trim(), url_template: template, url_mode: draft.url_mode || 'full_url', origin: 'custom', enabled: true, support: probe.support || {}, health: probe.health || {} }
    props.formData.github_mirrors = mirrorEditingId.value === null ? [...mirrors, mirror]
      : mirrors.map(item => item.id === mirrorEditingId.value ? mirror : item)
    if (mirrorEditingId.value === null || props.formData.github_mirror_id === `custom:${mirrorEditingId.value}`) props.formData.github_mirror_id = `custom:${id}`
    mirrorDraft.value = null
  } catch {
    mirrorError.value = t('ui.settings.network.mirror_probe_failed', '镜像探测失败，未保存此配置。请检查地址和网络连接后重试。')
  } finally {
    mirrorProbeRunning.value = false
  }
}

const handleRemoveMirror = () => {
  const mirror = selectedMirror.value
  if (!mirror) return
  props.formData.github_mirrors = props.formData.github_mirrors.filter(item => item.id !== mirror.id)
  props.formData.github_mirror_id = 'direct'
}

const handleOpenMirrorsFile = async () => {
  try {
    const result = await window.pywebview.api.path_open_file(props.formData._github_mirrors_path)
    if (result?.status !== 'success') throw new Error('Open failed')
  } catch {
    toast.error(t('ui.settings.network.mirror_open_failed', '无法打开镜像配置文件，请根据显示的路径手动打开。'))
  }
}

const hostsState = ref({ status: 'idle' })
const hostsRetry = ref(0)
const systemHostsRetry = ref(0)
let hostsRequest = Promise.resolve()
const hostsSources = computed(() => props.formData.network.hosts_sources || [])
const activeHostsSources = computed(() => [...new Set(hostsSources.value.filter(row => row.enabled).map(row => row.url.trim()).filter(Boolean))].join('\n'))

const selectHostsState = (state, sourceUrl) => {
  const runtime = state || {}
  const preview = runtime.preview
  const selected = preview?.source_url === sourceUrl
    ? preview
    : runtime.source_url === sourceUrl ? runtime : { ...runtime, status: 'idle', source_url: '' }
  return {
    ...selected,
    // 预览只描述候选结果；生效映射和应用状态始终来自已保存运行态。
    dynamic_hosts: runtime.dynamic_hosts || {},
    effective_hosts: runtime.effective_hosts || {},
    cache_path: runtime.cache_path,
    system_hosts: runtime.system_hosts,
    is_applied: !!runtime.is_applied,
  }
}

// 轮询只更新展示状态，不写入表单，避免后台获取被当作用户修改保存。
watch([
  () => !!props.formData.network.github_hosts_enabled,
  () => activeHostsSources.value,
  hostsRetry,
  () => JSON.stringify({ proxy: props.formData.network.proxy, hosts: props.formData.network.hosts }),
  systemHostsRetry,
], ([enabled, sourceUrl, retry, networkSnapshot], previous, onCleanup) => {
  let isActive = true
  let timer = null
  onCleanup(() => {
    isActive = false
    clearTimeout(timer)
  })
  const shouldRefresh = enabled && previous?.length > 0 && (!previous[0] || sourceUrl !== previous[1] || retry !== previous[2] || networkSnapshot !== previous[3])
  const shouldCancel = !enabled && previous?.[0]
  const shouldRetrySystem = previous?.length > 0 && systemHostsRetry.value !== previous[4]
  hostsState.value = { ...hostsState.value, status: shouldRefresh ? 'loading' : 'idle', is_applied: false }
  const load = async (isInitial) => {
    try {
      const api = window.pywebview?.api
      if (!api) throw new Error('Network API unavailable')
      const payload = isInitial && (shouldRefresh || shouldCancel) ? {
            github_hosts_enabled: enabled,
            hosts_sources: hostsSources.value.map(row => ({ ...row })),
            proxy: { ...(props.formData.network?.proxy || {}) },
            hosts: { ...(props.formData.network?.hosts || {}) },
            _preserve_secret_keys: Array.isArray(props.formData._preserve_secret_keys) ? [...props.formData._preserve_secret_keys] : [],
          } : null
      // 表单切换会作废旧 watcher；串行处理，避免慢响应期间堆积查询线程。
      hostsRequest = hostsRequest.catch(() => {}).then(() => {
        if (!isActive) return null
        if (isInitial && shouldRetrySystem) return api.network_apply_system_hosts()
        return payload ? api.network_refresh_github_hosts(payload) : api.network_github_hosts_status()
      })
      const result = await hostsRequest
      if (!isActive) return
      if (result?.status !== 'success') throw new Error('Hosts request failed')
      const state = result.data
      const displayState = selectHostsState(state, sourceUrl)
      // 只展示当前来源的任务结果，已生效映射由后端单独返回。
      if (!enabled || displayState.source_url !== sourceUrl) {
        hostsState.value = { ...displayState, status: 'idle', can_refresh: false, is_applied: false }
        if (['applying', 'authorizing'].includes(displayState.system_hosts?.status)) timer = setTimeout(() => load(false), 800)
        return
      }
      hostsState.value = displayState
      if ((enabled && displayState.status === 'loading') || ['applying', 'authorizing'].includes(displayState.system_hosts?.status)) timer = setTimeout(() => load(false), 800)
    } catch {
      if (isActive) hostsState.value = { ...hostsState.value, status: 'error', error: 'failed' }
    }
  }
  void load(true)
}, { immediate: true })

const secretStatus = (secretKey) => props.formData?._secret_status?.[secretKey] || {}

watch(
  () => JSON.stringify({
    proxy: props.formData.network?.proxy,
    github_hosts: props.formData.network?.github_hosts_enabled,
    hosts_sources: props.formData.network?.hosts_sources,
    hosts: props.formData.network?.hosts,
    github_mirror_id: props.formData.github_mirror_id,
    github_dynamic_mirrors_enabled: props.formData.github_dynamic_mirrors_enabled,
    github_mirrors: props.formData.github_mirrors,
  }),
  () => {
    if (networkCheckState.value.status !== 'loading') networkCheckState.value = { status: 'idle', targets: [] }
  },
)

const openUrlOnSteam = (url) => {
  void dispatchSteamUri(buildSteamOpenUrl(url))
}
</script>

<style scoped>
/* 适合内容的三列固定宽度，域名列独占剩余空间，避免指标列被长 URL 挤开。 */
.network-check-fit-col { width: max-content; }
.network-check-domain-col { width: auto; }
.network-check-table td:nth-child(1),
.network-check-table td:nth-child(2) { max-width: 16rem; }
</style>
