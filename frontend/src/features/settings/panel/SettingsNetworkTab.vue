<template>
              <section class="animate-in fade-in slide-in-from-right-4">
                <h3 class="text-lg font-bold text-text-main mb-6">网络协议与代理</h3>
                <div class="space-y-8">
                  <div class="modal-section space-y-6 p-4">
                    <CommonSwitch label="启用代理服务" v-model="formData.network.proxy.enabled" :description="'启用代理服务，所有网络请求将通过代理服务器处理，部分外置数据下载、更新检查、简介图片加载、内部浏览器访问等功能可能需要该配置才能正常使用。\n\n也可以在软件外部自行配置全局网络环境。'" mini />
                    <div v-if="formData.network.proxy.enabled" class="grid grid-cols-6 gap-3 animate-in zoom-in-95">
                      <CommonSelect class="col-span-2" label="协议" v-model="formData.network.proxy.type" :options="[{label:'HTTP', value:'http'},{label:'SOCKS5', value:'socks5'}]" />
                      <CommonInput class="col-span-3" label="主机地址" v-model="formData.network.proxy.host" placeholder="127.0.0.1" />
                      <CommonNumber class="col-span-1" label="端口" v-model="formData.network.proxy.port" :step="1" :min="1" :max="65535" />
                      <CommonSecretInput class="col-span-3" label="用户名" v-model="formData.network.proxy.username"
                        secret-key="network.proxy.username" :secret-status="secretStatus('network.proxy.username')" :preserved="isSecretPreserved('network.proxy.username')" :reveal-secret="revealSecret"
                        placeholder="代理用户名（可选）" @preserve="$emit('preserve-secret', $event)" @clear="$emit('clear-secret', $event)" />
                      <CommonSecretInput class="col-span-3" label="密码" v-model="formData.network.proxy.password"
                        secret-key="network.proxy.password" :secret-status="secretStatus('network.proxy.password')" :preserved="isSecretPreserved('network.proxy.password')" :reveal-secret="revealSecret"
                        placeholder="代理密码（可选）" @preserve="$emit('preserve-secret', $event)" @clear="$emit('clear-secret', $event)" />
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
                    <CommonSwitch label="启用工坊增强信息" v-model="formData.enable_steam_enhanced_api" mini description="开启并填写 Key 后，工坊页会优先使用在线增强信息；没有 Key 或关闭此项时会自动使用本地缓存搜索。" />
                    <div class="flex items-end gap-2" :class="{'opacity-60': !formData.enable_steam_enhanced_api}">
                      <CommonSecretInput class="flex-1" label="Steam Web API Key" v-model="formData.steam_web_api_key"
                        secret-key="steam.web_api_key" :secret-status="secretStatus('steam.web_api_key')" :preserved="isSecretPreserved('steam.web_api_key')" :reveal-secret="revealSecret"
                        placeholder="填写后启用增强搜索" description="Key 会安全保存在本机凭据库。没有 Key 时会自动回到缓存搜索。"
                        @preserve="$emit('preserve-secret', $event)" @clear="$emit('clear-secret', $event)" />
                      <button @click="openUrlOnSteam('https://steamcommunity.com/dev/apikey')"
                        class="px-2 py-2 m-0.5 bg-bg-overlay/5 hover:bg-bg-overlay/10 border border-border-base/10 rounded-lg text-xs font-bold cursor-pointer transition-all">
                        <span class="flex items-center gap-2">
                          访问<p class="text-accent-cool">API Key</p>获取页面
                        </span>
                      </button>
                    </div>
                    <div class="text-xs ">
                      <p class="mt-1 leading-relaxed text-text-dim">
                        开启并填写 Key 后，会使用 Steam Web API 获取更完整的工坊搜索、合集搜索、作者作品和依赖关联信息。关闭时仍可使用本地缓存工坊数据库。
                      </p>
                      <span class="text-accent-warn">注意！“API 密钥（API Key）相当于你的 Steam 账号后门钥匙”。可以读取账号公开数据/库存信息 以及 管理与监听交易报价。</span>
                      <p>任何人一旦获取了此 Key，就可以在不触发 Steam 令牌的情况下，暗中取消玩家的真实交易，并替换为发给骗子的假交易。绝对不要将 API 密钥分享给任何人或任何未经验证的第三方网站。</p>
                    </div>
                  </div>

                </div>
              </section>
</template>

<script setup>
import CommonSwitch from '../../../shared/components/input/CommonSwitch.vue'
import CommonInput from '../../../shared/components/input/CommonInput.vue'
import CommonSecretInput from '../../../shared/components/input/CommonSecretInput.vue'
import CommonNumber from '../../../shared/components/input/CommonNumber.vue'
import CommonSelect from '../../../shared/components/input/CommonSelect.vue'
import CommonTagInput from '../../../shared/components/input/CommonTagInput.vue'
import CommonKVEditor from '../../../shared/components/input/CommonKVEditor.vue'

const props = defineProps({
  formData: { type: Object, required: true },
  revealSecret: { type: Function, default: null },
  isSecretPreserved: { type: Function, default: () => false },
})

defineEmits(['preserve-secret', 'clear-secret'])

const secretStatus = (secretKey) => props.formData?._secret_status?.[secretKey] || {}

const openUrlOnSteam = (url) => {
  window.open('steam://openurl/' + url, '_blank')
}
</script>
