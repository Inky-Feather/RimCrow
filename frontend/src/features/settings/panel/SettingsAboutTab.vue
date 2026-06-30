<template>
  <section class="animate-in fade-in slide-in-from-right-4">
    <h3 class="mb-6 text-lg font-bold text-text-main">关于项目</h3>

    <div class="space-y-4">
      <div class="modal-section p-4">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div class="flex min-w-0 items-center gap-3">
            <IconSelfOriginal class="size-12 -m-1.5" />
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h4 class="text-sm font-bold text-text-main">{{ aboutMeta.project.name }}</h4>
                <span class="font-mono text-xs text-text-dim">v{{ appStore.appVersion || 'Unknown' }}</span>
              </div>
              <p class="mt-1 text-xs leading-relaxed text-text-dim">{{ aboutMeta.project.description }}</p>
            </div>
          </div>

          <div class="shrink-0 rounded-xl lg:w-50">
            <div class="mb-2">
              <CommonSwitch label="自动检查更新" v-model="formData.enable_auto_update_check" description="开启后，软件启动时会自动提醒新版本。" mini />
            </div>
            <div class="flex flex-wrap gap-2">
              <button type="button" @click="handleShowChangelog()" :disabled="isPending('changelog')" :class="isPending('changelog') ? 'app-action-disabled' : ''"
                class="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-accent-tip/10 bg-accent-tip/15 px-3 py-1.5 text-xs font-bold transition-all hover:bg-accent-tip/30">
                <LoaderCircle v-if="isPending('changelog')" class="size-3 animate-spin" />
                {{ isPending('changelog') ? '读取中' : '更新日志' }}
              </button>
              <button type="button" @click="handleCheckUpdate()" :disabled="appStore.updateState.isChecking"
                class="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-border-base/10 bg-bg-overlay/5 px-3 py-1.5 text-xs font-bold transition-all hover:bg-bg-overlay/10">
                <LoaderCircle v-if="appStore.updateState.isChecking" class="size-3 animate-spin" />
                {{ appStore.updateState.isChecking ? '检查中' : '检查更新' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div class="modal-section p-4">
          <div>
            <h4 class="text-sm font-bold text-text-main">下载地址</h4>
            <p class="mt-1 text-xs leading-relaxed text-text-dim">查看源码、发布包和备用下载地址。</p>
          </div>

          <div class="mt-3 space-y-2">
            <div v-for="item in downloadLinks" :key="item.label" class="border-t border-border-base/10 pt-2 first:border-t-0 first:pt-0">
              <div class="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div class="min-w-0">
                  <div class="text-xs font-bold text-text-main">{{ item.label }}</div>
                  <div class="flex gap-2 items-center mt-0.5 break-all select-text font-mono text-[0.72rem]" :class="item.primary ? 'text-accent-primary' : 'text-text-dim'">
                    {{ item.url }}
                    <div v-if="item.password" class="text-xs text-text-main select-none">
                      密码：<span class="select-text font-mono text-text-dim">{{ item.password }}</span>
                    </div>
                  </div>
                  <div v-if="item.note" class="mt-0.5 text-xs leading-relaxed text-text-dim">{{ item.note }}</div>
                </div>
                <div class="flex shrink-0 gap-2">
                  <button type="button" @click="openExternalUrl(item.url)" class="about-icon-button" title="打开链接">
                    <ExternalLink class="size-3.5" />
                  </button>
                  <button type="button" @click="copyText(item.url)" class="about-icon-button" title="复制地址">
                    <Copy class="size-3.5" />
                  </button>
                  <button v-if="item.password" type="button" @click="copyText(item.password)" class="about-icon-button" title="复制密码">
                    <KeyRound class="size-3.5" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="modal-section p-4">
          <div>
            <h4 class="text-sm font-bold text-text-main">反馈与交流</h4>
            <p class="mt-1 text-xs leading-relaxed text-text-dim">遇到问题时，建议带上截图、日志和复现步骤。</p>
          </div>

          <div class="mt-3 space-y-2">
            <div v-for="item in feedbackItems" :key="item.label" class="border-t border-border-base/10 pt-2 first:border-t-0 first:pt-0">
              <div class="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div class="min-w-0">
                  <div class="text-xs font-bold text-text-main">{{ item.label }}</div>
                  <div class="mt-0.5 break-all select-text font-mono text-[0.72rem]" :class="item.primary ? 'text-accent-primary' : 'text-text-dim'">{{ item.value }}</div>
                  <div class="mt-0.5 text-xs leading-relaxed text-text-dim">{{ item.note }}</div>
                </div>
                <div class="flex shrink-0 gap-2">
                  <button v-if="item.url" type="button" @click="openExternalUrl(item.url)" class="about-icon-button" title="打开链接">
                    <ExternalLink class="size-3.5" />
                  </button>
                  <button type="button" @click="copyText(item.copyValue)" class="about-icon-button" :title="item.copyTitle">
                    <Copy class="size-3.5" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="aboutMeta.references.length" class="modal-section p-4 xl:col-span-2">
          <div>
            <h4 class="text-sm font-bold text-text-main">参考项目</h4>
            <p class="mt-1 text-xs leading-relaxed text-text-dim">这些项目为排序、日志分析和管理功能提供了参考。</p>
          </div>

          <div class="mt-3 grid grid-cols-1 gap-x-6 gap-y-4 xl:grid-cols-2">
            <div v-for="group in aboutMeta.references" :key="group.title" class="min-w-0">
              <div class="mb-1 text-xs font-bold text-text-main">{{ group.title }}</div>
              <div class="space-y-2">
                <div v-for="item in group.items" :key="`${group.title}-${item.url}`" class="border-t border-border-base/10 pt-2 first:border-t-0 first:pt-0">
                  <div class="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                    <div class="min-w-0">
                      <div class="text-xs font-bold text-text-main/70">{{ item.name }}</div>
                      <div class="mt-0.5 break-all select-text font-mono text-[0.72rem] text-text-dim">{{ item.url }}</div>
                    </div>
                    <div class="flex shrink-0 gap-2">
                      <button type="button" @click="openExternalUrl(item.url)" class="about-icon-button" title="打开链接">
                        <ExternalLink class="size-3.5" />
                      </button>
                      <button type="button" @click="copyText(item.url)" class="about-icon-button" title="复制地址">
                        <Copy class="size-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="donate.enabled" class="flex gap-4 items-center modal-section p-4 xl:col-span-2">
          <BrandSignature logo-class="size-16 -m-3" tone-class="text-text-main" />
          <div class="flex-1 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div class="min-w-0">
              <h4 class="text-sm font-bold text-text-main">{{ donate.title }}</h4>
              <p class="mt-1 text-xs leading-relaxed text-text-dim whitespace-pre-line">{{ donate.description }}</p>
            </div>
            <button type="button" @click="showDonateModal = true"
              class="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-border-base/10 bg-bg-overlay/5 px-3 py-1.5 text-xs font-bold transition-all hover:bg-bg-overlay/10">
              <HeartHandshake class="size-3.5" />
              查看收款码
            </button>
          </div>
        </div>

        <div v-if="aboutMeta.credits.length" class="modal-section p-4">
          <h4 class="text-sm font-bold text-text-main">致谢</h4>
          <div class="mt-3 space-y-2">
            <div v-for="item in aboutMeta.credits" :key="item.name" class="border-t border-border-base/10 pt-2 first:border-t-0 first:pt-0">
              <div class="text-xs font-bold text-text-main">{{ item.name }}</div>
              <div v-if="item.note" class="mt-0.5 text-xs leading-relaxed text-text-dim">{{ item.note }}</div>
              <div v-if="item.url" class="mt-0.5 break-all select-text font-mono text-[0.72rem] text-text-dim">{{ item.url }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <Transition name="donate-modal-fade">
        <div v-if="isDonateModalVisible" class="fixed inset-0 z-130 flex items-center justify-center px-3 py-4 text-text-main selection:bg-bg-overlay/10">
          <button type="button" class="absolute inset-0 bg-overlay-scrim backdrop-blur-md" aria-label="关闭打赏弹窗" @click="closeDonateModal"></button>
          <div class="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(var(--rgb-accent-primary),0.10),transparent_32%),radial-gradient(circle_at_bottom_left,rgba(var(--rgb-accent-special),0.08),transparent_34%)]"></div>

          <section class="modal-surface relative z-10 flex w-[min(28rem,calc(100vw-1.5rem))] max-h-[calc(100vh-2rem)] flex-col overflow-hidden rounded-2xl border-border-base/18"
            role="dialog" aria-modal="true" aria-label="打赏支持">
            <div class="pointer-events-none absolute inset-x-0 top-0 h-px bg-linear-to-r from-transparent via-border-base/18 to-transparent"></div>
            <div class="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-accent-tip/10 blur-3xl"></div>

            <header class="modal-header relative z-10 flex shrink-0 items-start justify-between gap-4 px-5 py-4">
              <div class="min-w-0">
                <h2 class="truncate text-lg font-black tracking-wide text-text-main">打赏支持</h2>
                <p class="mt-1 text-xs leading-relaxed text-text-dim">感谢支持！微信和支付宝都可以扫 ~</p>
              </div>
              <button type="button" class="modal-close-button" aria-label="关闭" @click="closeDonateModal">
                <X class="size-4" />
              </button>
            </header>

            <div class="relative z-10 min-h-0 overflow-y-auto p-4 custom-scrollbar">
              <div class="w-full max-w-full flex flex-col gap-3">
                <div v-if="donate.qrImageUrl" class="rounded-xl border border-border-base/10 bg-bg-overlay/5 p-2">
                  <img :src="donate.qrImageUrl" alt="打赏收款码" class="block h-auto w-full max-h-[calc(100vh-12rem)] rounded-lg object-contain" />
                </div>
                <p class="min-w-0 w-full wrap-break-word text-xs leading-relaxed text-text-dim whitespace-pre-line">{{ donate.description }}</p>
              </div>
            </div>
          </section>
        </div>
      </Transition>
    </Teleport>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Copy, ExternalLink, HeartHandshake, KeyRound, LoaderCircle, X } from 'lucide-vue-next'
import { useToast } from 'vue-toastification'
import { useAppStore } from '../../../app/stores/appStore'
import CommonSwitch from '../../../shared/components/input/CommonSwitch.vue'
import BrandSignature from '../../../shared/branding/BrandSignature.vue'
import brandProfile from '../../../shared/branding/brandProfile'
import { IconSelfOriginal } from '../../../shared/lib/constants.js'

defineProps({
  formData: { type: Object, required: true },
})

const appStore = useAppStore()
const toast = useToast()
const pendingAction = ref('')
const showDonateModal = ref(false)
const isDonateModalVisible = computed(() => showDonateModal.value && appStore.uiState.showSettingsPanel)

const DEFAULT_ABOUT_META = Object.freeze({
  project: {
    name: brandProfile.project.name,
    description: brandProfile.project.description,
    githubRepo: 'Inky-Feather/RimCrow',
  },
  update: {
    sources: [],
  },
  feedback: {
    qqGroup: '',
    qqDescription: '',
    tiebaUrl: '',
    tiebaDescription: '',
  },
  references: [],
  credits: [],
  donate: {
    enabled: false,
    title: '打赏支持',
    description: '',
    qrImageUrl: '',
  },
})

const aboutMeta = ref(structuredClone(DEFAULT_ABOUT_META))

const normalizeGithubRepo = (value) => String(value || '').trim().replace(/^\/+|\/+$/g, '')
const createGithubUrl = (repo, suffix = '') => {
  const normalizedRepo = normalizeGithubRepo(repo)
  if (!normalizedRepo) return ''
  const normalizedSuffix = String(suffix || '').replace(/^\/+/, '')
  return normalizedSuffix ? `https://github.com/${normalizedRepo}/${normalizedSuffix}` : `https://github.com/${normalizedRepo}`
}
const resolvePublicAssetUrl = (value) => {
  const path = String(value || '').trim()
  if (!path || /^(https?:|data:|blob:|file:)/i.test(path)) return path
  return `${import.meta.env.BASE_URL || './'}${path.replace(/^\/+/, '')}`
}
const normalizeLinkItem = (item) => ({
  name: String(item?.name || '').trim(),
  url: String(item?.url || '').trim(),
})
const normalizeAboutMeta = (rawMeta) => {
  const githubRepo = normalizeGithubRepo(rawMeta?.project?.github_repo)
  return {
    project: {
      name: String(rawMeta?.project?.name || DEFAULT_ABOUT_META.project.name).trim(),
      description: String(rawMeta?.project?.description || DEFAULT_ABOUT_META.project.description).trim(),
      githubRepo,
    },
    update: {
      sources: Array.isArray(rawMeta?.update?.sources) ? rawMeta.update.sources : [],
    },
    feedback: {
      qqGroup: String(rawMeta?.feedback?.qq_group || '').trim(),
      qqDescription: String(rawMeta?.feedback?.qq_description || '').trim(),
      tiebaUrl: String(rawMeta?.feedback?.tieba_url || '').trim(),
      tiebaDescription: String(rawMeta?.feedback?.tieba_description || '').trim(),
    },
    references: (Array.isArray(rawMeta?.references) ? rawMeta.references : [])
      .map(group => ({
        title: String(group?.title || '').trim(),
        items: (Array.isArray(group?.items) ? group.items : []).map(normalizeLinkItem).filter(item => item.name && item.url),
      }))
      .filter(group => group.title && group.items.length),
    credits: (Array.isArray(rawMeta?.credits) ? rawMeta.credits : [])
      .map(item => ({
        name: String(item?.name || '').trim(),
        note: String(item?.note || '').trim(),
        url: String(item?.url || '').trim(),
      }))
      .filter(item => item.name),
    donate: {
      enabled: !!rawMeta?.donate?.enabled,
      title: String(rawMeta?.donate?.title || '打赏支持').trim(),
      description: String(rawMeta?.donate?.description || '').trim(),
      qrImageUrl: resolvePublicAssetUrl(rawMeta?.donate?.qr_image_url),
    },
  }
}
const loadAboutMeta = async () => {
  try {
    const response = await fetch(resolvePublicAssetUrl('project-meta.json'), { cache: 'no-store' })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    aboutMeta.value = normalizeAboutMeta(await response.json())
  } catch (error) {
    console.warn('加载项目元数据失败，已使用默认信息。', error)
    aboutMeta.value = structuredClone(DEFAULT_ABOUT_META)
  }
}

const repositoryUrl = computed(() => createGithubUrl(aboutMeta.value.project.githubRepo))
const issuesUrl = computed(() => createGithubUrl(aboutMeta.value.project.githubRepo, 'issues'))
const releasesUrl = computed(() => createGithubUrl(aboutMeta.value.project.githubRepo, 'releases'))
const lanzouSource = computed(() => {
  const source = (aboutMeta.value.update.sources || []).find(item => String(item?.type || '').trim().toLowerCase() === 'lanzou')
  if (!source) return null
  const url = String(source.url || '').trim()
  if (!url) return null
  return {
    url,
    password: String(source.password || '').trim(),
  }
})
const downloadLinks = computed(() => {
  const links = [
    { label: 'GitHub 仓库', url: repositoryUrl.value, note: '查看发布包、问题反馈和源码。', primary: true },
    { label: 'GitHub 发布页', url: releasesUrl.value, note: '下载 GitHub 发布包，或查看每个版本的发布内容。' },
  ].filter(item => item.url)
  if (lanzouSource.value) {
    links.push({
      label: '蓝奏云分流',
      url: lanzouSource.value.url,
      password: lanzouSource.value.password,
      note: '网络不稳定时，可以尝试从这里下载备用包。',
    })
  }
  return links
})
const feedbackItems = computed(() => [
  {
    label: '问题反馈',
    value: issuesUrl.value,
    url: issuesUrl.value,
    copyValue: issuesUrl.value,
    copyTitle: '复制地址',
    note: '适合记录需要跟进的问题和建议。',
    primary: true,
  },
  {
    label: 'QQ群',
    value: aboutMeta.value.feedback.qqGroup,
    copyValue: aboutMeta.value.feedback.qqGroup,
    copyTitle: '复制群号',
    note: aboutMeta.value.feedback.qqDescription || '适合快速反馈和补充截图。',
  },
  {
    label: '贴吧主贴',
    value: aboutMeta.value.feedback.tiebaUrl,
    url: aboutMeta.value.feedback.tiebaUrl,
    copyValue: aboutMeta.value.feedback.tiebaUrl,
    copyTitle: '复制地址',
    note: aboutMeta.value.feedback.tiebaDescription || '查看集中说明和公开讨论。',
  },
].filter(item => item.value))
const donate = computed(() => aboutMeta.value.donate)

const isPending = (action) => pendingAction.value === action
const closeDonateModal = () => {
  showDonateModal.value = false
}
const handleDonateModalKeydown = (event) => {
  if (event.key !== 'Escape' || !isDonateModalVisible.value) return
  event.preventDefault()
  closeDonateModal()
}
const runPendingAction = async (action, runner) => {
  if (pendingAction.value) return
  pendingAction.value = action
  try {
    await runner?.()
  } finally {
    pendingAction.value = ''
  }
}
const handleShowChangelog = async () => {
  await runPendingAction('changelog', () => appStore.showChangelog())
}
const handleCheckUpdate = () => {
  appStore.checkUpdate(true)
}
const openExternalUrl = async (url) => {
  const normalizedUrl = String(url || '').trim()
  if (!normalizedUrl) return
  try {
    if (window.pywebview?.api?.open_external_url) {
      await window.pywebview.api.open_external_url(normalizedUrl)
      return
    }
  } catch {
    toast.error('打开失败，请手动复制链接。')
    return
  }
  window.open(normalizedUrl, '_blank', 'noopener,noreferrer')
}
const copyText = async (text) => {
  const normalizedText = String(text || '').trim()
  if (!normalizedText) return
  try {
    await navigator.clipboard.writeText(normalizedText)
    toast.success(`已复制：${normalizedText}`, { timeout: 600 })
  } catch {
    toast.error('复制失败，请手动复制。')
  }
}

watch(isDonateModalVisible, (visible) => {
  if (visible) {
    window.addEventListener('keydown', handleDonateModalKeydown)
    return
  }
  window.removeEventListener('keydown', handleDonateModalKeydown)
}, { immediate: true })

onMounted(() => {
  void loadAboutMeta()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleDonateModalKeydown)
})
</script>

<style scoped>
.about-icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: 0.5rem;
  border: 1px solid rgba(var(--rgb-border-base), 0.1);
  background: rgba(var(--rgb-bg-overlay), 0.05);
  color: rgb(var(--rgb-text-dim));
  transition: background-color 0.15s ease, color 0.15s ease;
}

.about-icon-button:hover {
  background: rgba(var(--rgb-bg-overlay), 0.1);
  color: rgb(var(--rgb-text-main));
}

.donate-modal-fade-enter-active,
.donate-modal-fade-leave-active {
  transition: opacity 0.22s ease;
}

.donate-modal-fade-enter-from,
.donate-modal-fade-leave-to {
  opacity: 0;
}

.donate-modal-fade-enter-active section,
.donate-modal-fade-leave-active section {
  transition: transform 0.22s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.22s ease;
}

.donate-modal-fade-enter-from section,
.donate-modal-fade-leave-to section {
  opacity: 0;
  transform: translateY(10px) scale(0.985);
}
</style>
