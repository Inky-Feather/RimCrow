<!-- src/components/workspace/views/GithubCommand.vue -->
<template>
  <div class="h-full flex gap-4 p-4 overflow-hidden">
    
    <!-- 左侧：已订阅仓库阵列 (40%) -->
    <div class="w-[40%] flex flex-col bg-black/40 border border-text-main/10 rounded-2xl overflow-hidden shadow-2xl" data-tour="workspace-github-list">
      <div class="px-4 py-3 bg-text-main/10 border-b border-text-main/10 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <Github class="size-4 text-text-main" />
          <h3 class="text-sm font-bold text-text-main">GitHub订阅列表</h3>
        </div>
        <button @click="workspaceStore.fetchGithubRepos" class="p-1 text-text-dim hover:text-text-main transition-colors">
          <RefreshCw class="size-4" :class="{'animate-spin': workspaceStore.github.isLoading}" />
        </button>
      </div>

      <div class="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-1">
        <div v-for="repo in workspaceStore.github.subscribedRepos" :key="repo.repo_url"
          @click="selectRepo(repo)"
          class="flex flex-col gap-1 p-3 rounded-xl border transition-all cursor-pointer group relative overflow-hidden"
          :class="workspaceStore.github.activeRepo?.repo_url === repo.repo_url ? 'bg-text-main/10 border-text-main/30 shadow-inner' : 'border-text-main/5 bg-black/20 hover:bg-text-main/5'">
          
          <div class="flex justify-between items-center z-10">
            <div class="font-bold text-sm text-text-main truncate">{{ repo.repo_name }}</div>
            <span class="px-1.5 py-0.5 rounded bg-black/50 text-[0.6rem] font-mono text-text-dim border border-text-main/10">
              {{ repo.owner }}
            </span>
          </div>
          
          <div class="flex justify-between items-center mt-1 z-10">
            <div class="flex items-center gap-1 text-[0.65rem] font-mono">
              <span v-if="repo.install_type === 'release'" class="px-2 py-1 text-accent-primary bg-accent-primary/10 rounded">Release</span>
              <span v-else class="px-2 py-1 text-accent-success bg-accent-success/10 rounded">Source</span>
              <span class="px-2 py-1 text-text-dim opacity-70 ml-1">{{ repo.installed_version || '未部署' }}</span>
              <span v-if="need_update(repo)" class="px-2 py-1 rounded bg-black/50 text-[0.65rem] font-mono text-accent-warn">
                有新版本可用 ({{ repo.online_info.latest_release_tag }})
              </span>
            </div>
          </div>
          
          <!-- 删除按钮 -->
          <button @click.stop="removeRepo(repo.repo_url)" class="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-lg bg-accent-danger/20 text-accent-danger opacity-0 group-hover:opacity-100 transition-all z-20 hover:bg-accent-danger hover:text-black">
            <Trash2 class="size-4" />
          </button>
        </div>
      </div>
    </div>

    <!-- 右侧：链接解析操作面板 (60%) -->
    <div class="w-[60%] flex flex-col gap-4" data-tour="workspace-github-workspace">
      
      <!-- 顶部：新增仓库解析器 -->
      <div class="bg-black/40 p-3 rounded-2xl border border-text-main/10 flex items-center gap-3 shadow-lg" data-tour="workspace-github-input">
        <div class="flex-1 relative">
          <Link class="absolute left-4 top-1/2 -translate-y-1/2 size-4 text-text-dim" />
          <input v-model="newRepoUrl" @keydown.enter="parseNewRepo"
            placeholder="粘贴 GitHub 仓库地址 (如: https://github.com/user/repo)" 
            class="w-full bg-black/60 border border-text-main/10 rounded-xl pl-10 pr-4 py-2.5 text-sm text-text-main outline-none focus:border-text-main/50 transition-all" />
        </div>
        <button @click="parseNewRepo" :disabled="isParsing"
          class="px-6 py-2.5 bg-text-main/10 text-text-main hover:bg-text-main hover:text-black border border-text-main/30 rounded-xl text-sm font-black transition-all disabled:opacity-50 flex items-center gap-2">
          <span v-if="isParsing" class="animate-spin">⟳</span> 解析地址
        </button>
      </div>

      <!-- 解析结果区 (如果正在解析新仓库) -->
      <div v-if="workspaceStore.github.previewInfo" data-tour="workspace-github-preview" class="p-6 bg-accent-primary/10 border border-accent-primary/30 rounded-2xl animate-in zoom-in-95">
        <h3 class="text-lg font-black text-text-main mb-2">{{ workspaceStore.github.previewInfo.repo }}</h3>
        <p class="text-sm text-text-dim mb-4">作者: {{ workspaceStore.github.previewInfo.owner }} | 默认分支: {{ workspaceStore.github.previewInfo.default_branch }}</p>
        
        <div class="flex gap-4">
          <!-- Source 模式 -->
          <button @click="confirmSubscribe('source')" class="flex-1 p-4 rounded-xl border border-accent-secondary/30 bg-accent-secondary/10 hover:bg-accent-secondary/20 transition-all text-left">
            <div class="font-bold text-accent-secondary mb-1">同步源码分支 (Source)</div>
            <div class="text-xs text-text-dim/80">获取分支最新代码。适合频繁更新或未发布 Release 的测试版模组。</div>
          </button>

          <!-- Release 模式 -->
          <button @click="confirmSubscribe('release')" :disabled="!workspaceStore.github.previewInfo.has_release"
            class="flex-1 p-4 rounded-xl border border-accent-success/30 bg-accent-success/10 hover:bg-accent-success/20 transition-all text-left disabled:opacity-30 disabled:cursor-not-allowed">
            <div class="font-bold text-accent-success mb-1">获取发行版 (Release)</div>
            <div class="text-xs text-text-dim/80 mb-2">获取作者打包的稳定版。</div>
            <div v-if="workspaceStore.github.previewInfo.has_release" class="inline-block px-2 py-0.5 bg-black/40 rounded text-[0.65rem] font-mono text-text-main">
              Latest: {{ workspaceStore.github.previewInfo.latest_release_tag }}
            </div>
            <div v-else class="text-xs text-accent-warn">该仓库尚未发布任何 Release</div>
          </button>
        </div>
      </div>

      <!-- 选中仓库的操作面板与日志轴 -->
      <div v-else-if="workspaceStore.github.activeRepo" data-tour="workspace-github-panel" class="flex-1 flex flex-col bg-black/30 border border-text-main/10 rounded-2xl overflow-hidden shadow-xl">
        
        <!-- 操作头部 -->
        <div class="p-6 bg-text-main/5 border-b border-text-main/10 flex justify-between items-start">
          <div>
            <h2 class="text-2xl font-black text-text-main">{{ workspaceStore.github.activeRepo.repo_name }}</h2>
            <div class="flex gap-2 mt-2">
              <span class="px-2 py-1 rounded bg-black/50 text-[0.65rem] font-mono text-text-dim">
                当前模式: {{ workspaceStore.github.activeRepo.install_type.toUpperCase() }}
              </span>
              <span class="px-2 py-1 rounded bg-black/50 text-[0.65rem] font-mono text-text-dim border border-text-main/10">
                已部署版本: {{ workspaceStore.github.activeRepo.installed_version || 'NONE' }}
              </span>
              <span v-if="need_update(workspaceStore.github.activeRepo)" class="px-2 py-1 rounded bg-black/50 text-[0.65rem] font-mono text-accent-warn">
                有新版本可用 ({{ workspaceStore.github.activeRepo.online_info.latest_release_tag }})
              </span>
            </div>
          </div>
          
          <!-- 一键更新/部署按钮 -->
          <button @click="checkAndUpdate" :disabled="isChecking"
            class="px-6 py-3 rounded-xl bg-accent-success text-black font-black text-sm shadow-[0_0_15px_rgba(16,185,129,0.3)] hover:scale-105 active:scale-95 transition-all flex items-center gap-2 disabled:opacity-50">
            <CloudDownload class="size-4" :class="{'animate-bounce': isChecking}" />
            {{ workspaceStore.github.activeRepo.installed_version ? '获取并部署最新' : '立即部署' }}
          </button>
        </div>

        <!-- 本地日志时间线 (Timeline) -->
        <div class="flex-1 overflow-y-auto custom-scrollbar p-6 relative">
          <h4 class="text-xs font-bold text-text-dim uppercase tracking-widest mb-6 flex items-center gap-2">
            <Activity class="size-4" /> 本地执行追踪 (Local Audit Log)
          </h4>

          <div class="relative pl-4">
            <!-- 轨道线 -->
            <div class="absolute left-0.5 top-2 bottom-0 w-px bg-linear-to-b from-text-main/30 to-transparent"></div>
            
            <div v-for="(log, i) in workspaceStore.github.repoTimelines" :key="i" class="mb-6 relative group">
              <!-- 节点圆点 -->
              <div class="absolute -left-[1.2rem] top-1.5 size-3 rounded-full border-2 bg-bg-deep z-10 transition-transform group-hover:scale-150" 
                :class="getLogColor(log.type)"></div>
              
              <div class="flex items-center gap-2">
                <span class="text-xs font-mono text-text-dim/80">{{ formatDate(log.time) }}</span>
                <span class="px-1.5 py-0.5 rounded text-[10px] font-black uppercase" :class="getLogBgColor(log.type)">
                  {{ log.title }}
                </span>
              </div>
              <div class="text-sm text-text-main/90 mt-1 leading-relaxed">{{ log.desc }}</div>
            </div>
            
            <div v-if="workspaceStore.github.repoTimelines.length === 0" class="text-sm text-text-dim/50 italic">
              暂无追踪记录
            </div>
          </div>
        </div>

      </div>

      <!-- 闲置空状态 -->
      <div v-else class="flex-1 flex flex-col items-center justify-center opacity-20 border-2 border-dashed border-text-main/20 rounded-2xl">
        <Github class="size-24 mb-4" />
        <span class="text-sm font-black uppercase tracking-widest">Select or Add a Repository</span>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Github, RefreshCw, Trash2, Link, CloudDownload, Activity } from 'lucide-vue-next'
import { useToast } from 'vue-toastification'
import { useWorkspaceStore } from '../../../stores/workspaceStore'
import { checkResult } from '../../../utils/tools'

const toast = useToast()
const workspaceStore = useWorkspaceStore()

const newRepoUrl = ref('')
const isParsing = ref(false)
const isChecking = ref(false)

onMounted(() => {
  workspaceStore.fetchGithubRepos()
})

// 判断是否需要更新
const need_update = (repo) => {
  if(!repo.online_info || !repo.installed_version) return false
  return repo.installed_version !== repo.online_info.latest_release_tag
}

// 解析新仓库链接
const parseNewRepo = async () => {
  if (!newRepoUrl.value) return
  isParsing.value = true
  try {
    const res = await window.pywebview.api.github_fetch_info(newRepoUrl.value)
    if (checkResult(res, "解析 GitHub 链接")) {
      workspaceStore.github.previewInfo = res.data
    }
  } finally {
    isParsing.value = false
  }
}

// 确认订阅仓库
const confirmSubscribe = async (type) => {
  const info = workspaceStore.github.previewInfo
  console.log('githubinfo',info)
  const payload = {
    url: newRepoUrl.value,
    owner: info.owner,
    repo: info.repo,
    default_branch: info.default_branch,
    install_type: type,
    installed_version: info.latest_release_tag,
    info: info,
  }
  const res = await window.pywebview.api.github_subscribe(payload)
  if (checkResult(res, "建立订阅")) {
    workspaceStore.github.previewInfo = null
    newRepoUrl.value = ''
    toast.success("仓库已成功订阅")
    workspaceStore.fetchGithubRepos()
  }
}

// 选择仓库
const selectRepo = (repo) => {
  workspaceStore.github.previewInfo = null // 清除预览
  workspaceStore.github.activeRepo = repo
  workspaceStore.fetchGithubTimeline(repo.repo_url)
}


// 移除仓库订阅
const removeRepo = async (url) => {
  const res = await window.pywebview.api.github_remove_subscription(url)
  if (checkResult(res, "移除订阅")) {
    if (workspaceStore.github.activeRepo?.repo_url === url) {
      workspaceStore.github.activeRepo = null
    }
    workspaceStore.fetchGithubRepos()
  }
}

// 检查并更新仓库
const checkAndUpdate = async () => {
  const repo = workspaceStore.github.activeRepo
  isChecking.value = true
  try {
    // 1. 获取最新信息 (看是否有新版本)
    const infoRes = await window.pywebview.api.github_fetch_info(repo.repo_url)
    if (infoRes.status !== 'success') {
      toast.error("GitHub 服务器连接失败")
      return
    }
    let targetVersion = repo.target_branch
    if (repo.install_type === 'release') {
      targetVersion = infoRes.data.latest_release_tag
    }
    // 2. 触发下载引擎 (带着钩子)
    const dlRes = await window.pywebview.api.github_trigger_download(repo.repo_url, repo.install_type, targetVersion)
    if (checkResult(dlRes, "请求数据传输")) {
      toast.info("已开始获取数据流，请在底部状态栏查看进度", {timeout: 4000})
      // 每隔几秒刷新一次日志轴，直到下载完成
      let retryCount = 0
      const timer = setInterval(() => {
        workspaceStore.fetchGithubTimeline(repo.repo_url)
        retryCount++
        if (retryCount > 15) clearInterval(timer) // 最多监控一分钟
      }, 4000)
    }
  } finally {
    isChecking.value = false
  }
}

const formatDate = (ts) => ts ? new Date(ts).toLocaleString() : 'N/A'

// 日志色彩解析
const getLogColor = (action) => {
  if (action === 'error') return 'border-accent-danger'
  if (action === 'success') return 'border-accent-success shadow-[0_0_10px_var(--color-accent-success)]'
  if (action === 'download' || action === 'extract') return 'border-accent-primary animate-pulse'
  return 'border-text-dim'
}

const getLogBgColor = (action) => {
  if (action === 'error') return 'bg-accent-danger/20 text-accent-danger'
  if (action === 'success') return 'bg-accent-success/20 text-accent-success'
  if (action === 'download' || action === 'extract') return 'bg-accent-primary/20 text-accent-primary'
  return 'bg-text-main/10 text-text-main'
}
</script>
<!-- END OF FILE -->
