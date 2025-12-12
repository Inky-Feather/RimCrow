
<template>
  <!-- 1. 详情卡片-->
  <div v-if="selectedMod" class="flex flex-col h-full p-1 overflow-y-auto custom-scrollbar">
    <!-- 封面图区域 -->
    <div class="w-full aspect-video bg-black/40 rounded-xl overflow-hidden relative border border-white/10 shadow-lg group">
      
      <!-- 加载中动画 -->
      <div v-if="isLoadingImage && !currentPreviewImage" class="absolute inset-0 flex items-center justify-center bg-bg-surface z-20">
        <div class="flex flex-col items-center gap-2">
           <div class="w-8 h-8 border-2 border-accent-primary border-t-transparent rounded-full animate-spin"></div>
           <span class="text-xs text-gray-500">正在加载...</span>
        </div>
      </div>

      <!-- 图片 (优先显示大图，没有大图时回退显示 store 中的缩略图，防止留白) -->
      <Transition name="fade">
        <!-- 这里的 key 绑定 Base64 字符串或 Mod ID，变动时触发动画 -->
        <img v-if="currentPreviewImage" :key="selectedMod.package_id" :src="currentPreviewImage" 
          class="absolute inset-0 w-full h-full object-cover"/>
        <!-- 文字提示兜底 -->
        <div v-else-if="!isLoadingImage" class="absolute inset-0 flex items-center justify-center text-gray-600 bg-bg-surface">
           <div class="text-center">
             <div class="text-4xl mb-2 opacity-20">IMG</div>
             <div class="text-xs">图片不存在</div>
           </div>
        </div>
      </Transition>
      <!-- 缩略图模糊背景 (可选优化：在 Base64 加载前，底层显示模糊的缩略图，防止背景过黑) -->
      <!-- 这层永远在最底下 (z-0)，当上面的 img fade-enter 时，用户会隐约看到这层 -->
      <img 
        :src="store.getAssetUrl(selectedMod.package_id)" 
        class="absolute inset-0 w-full h-full object-cover opacity-30 blur-md z-0 transition-opacity duration-500"
      />

      <!-- 版本标签 -->
      <div v-show="displayVersions.length" class="absolute top-1 right-2 z-10 pointer-events-none">
        <span v-for="versions in displayVersions" :key="versions" versions
          class="px-1 py-0.4 m-0.5 rounded-md bg-accent-cool/60 text-amber-50 border border-text-main/30 text-[10px] font-bold text-shadow-2xs shadow-md">
          {{ versions }}
        </span>
      </div>
      <!-- 标题 -->
      <div class="absolute bottom-0 inset-x-0 bg-linear-to-t from-bg-deep/90 to-transparent p-2 pt-12">
        <!-- 大小：{{ computedFontSize }}  
        字数：{{ selectedMod.name.length }} -->
        <h2 class="font-bold leading-tight line-clamp-2 text-shadow wrap-break-word adaptive-text" 
          :style="{ fontSize: computedFontSize }">{{ selectedMod.name }}</h2>
      </div>
    </div>

    <!-- 详情内容滚动区 -->
    <div class="flex-1 overflow-y-auto overflow-x-hidden custom-scroll select-text p-1 pt-2 space-y-2 after:pointer-events-none 
        after:content-[''] after:absolute after:bottom-0 after:w-full after:h-5 
        after:bg-linear-to-t after:from-bg-deep/80 after:to-transparent">
      <!-- ID & Version -->
      <div class="flex justify-between items-center text-xs text-text-dim font-mono">
        <span class="truncate max-w-[150px]" :title="selectedMod?.package_id">{{ selectedMod?.package_id || '---' }}</span>
        <span class="bg-white/5 px-2 py-0.5 rounded text-accent-secondary">{{ selectedMod?.version || 'Unknown Ver' }}</span>
      </div>

      <!-- Tags -->
      <div class="flex flex-wrap gap-1" v-if="selectedMod?.tags">
        <span v-for="tag in selectedMod.tags" :key="tag" class="px-1 py-0.5 rounded-md bg-accent-primary/10 text-accent-primary text-[10px] font-bold border border-accent-primary/10 drop-shadow-xl/25">
          {{ tag }}
        </span>
        <span class="px-1 py-0.5 rounded-md bg-bg-deep/10 text-[10px] font-bold text-text-dim/70 border border-dashed border-text-dim/70 drop-shadow-xl/25
          hover:text-text-main hover:border-text-main hover:bg-text-main/15 transition-colors cursor-pointer">+</span>
      </div>

      <!-- Author & Links -->
      <div class="p-3 rounded-lg bg-white/5 text-xs space-y-2 border border-white/5">
        <div class="flex justify-between">
          <span class="text-text-dim">Author</span>
          <span class="text-white">{{ selectedMod?.author || 'Unknown' }}</span>
        </div>
        <div class="flex justify-between">
          <span class="text-text-dim">Steam ID</span>
          <span class="text-white hover:text-accent-primary cursor-pointer transition">Open Workshop ↗</span>
        </div>
      </div>

      <div>路径：{{ selectedMod?.path }}</div>

      <!-- 备注编辑 -->
      <div>
          <label for="notes" class="block text-sm text-gray-500 dark:text-gray-300">备注</label>
          <textarea placeholder="可在此输入备注或说明翻译。" 
            class="block px-2 h-32 py-2 mt-2 w-full text-[15px] placeholder-gray-400/70 dark:placeholder-gray-500 rounded-lg 
            border border-gray-200 bg-white text-gray-700 focus:border-accent-primary 
            focus:outline-none focus:ring focus:ring-accent-primary focus:ring-opacity-40 dark:border-gray-600 
            dark:bg-gray-900 dark:text-gray-300 dark:focus:border-accent-primary "></textarea>
      </div>

      <!-- Description -->
      <div>
        <h3 class="text-xs font-bold text-text-dim uppercase tracking-wider mb-2">About</h3>
        <div class="prose prose-invert prose-sm max-w-none">
          <!-- 使用 v-html 渲染 -->
          <div>{{ selectedMod?.description }}</div>
          <!-- <div v-html="renderedDescription"></div> -->
           <!-- <RichTextRenderer :content="selectedMod?.description" /> -->

        </div>
      </div>
      
      <!-- Dependencies (示例) -->
      <div v-if="selectedMod?.dependencies?.length">
        <h3 class="text-xs font-bold text-text-dim uppercase tracking-wider mb-2">Requires</h3>
        <div class="space-y-1">
          <div v-for="dep in selectedMod.dependencies" :key="dep.packageId" class="flex items-center gap-2 p-2 rounded bg-black/20 border-l-2 border-accent-danger">
            <span class="text-xs">{{ dep.displayName || dep.packageId }}</span>
          </div>
        </div>
      </div>

    </div>
    
  </div>

  <!-- 空状态 -->
  <div v-else class="flex flex-col items-center justify-center h-full text-gray-600 gap-3">
    <div class="w-16 h-16 rounded-2xl border-2 border-dashed border-white/10 flex items-center justify-center">
      <svg class="w-8 h-8 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
    </div>
    <span class="text-xs uppercase tracking-widest opacity-50">选择一个Mod查看信息</span>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useModStore } from '../stores/modStore'
import MarkdownIt from 'markdown-it'
import RichTextRenderer from './utils/RichTextRenderer.vue'

const store = useModStore()
const currentPreviewImage = ref('') // 用于存储当前图片的 Base64 数据
const isLoadingImage = ref(false)  // 是否正在读取硬盘数据

// 配置 markdown 解析器，开启 html 支持 (因为模组简介常包含 HTML 标签)
const md = new MarkdownIt({
  html: true,
  linkify: true,
  break: true, // 转换 \n 为 <br>
  typographer: true
})

// 1. 获取最后选中的模组 (使用 .at(-1))
const selectedMod = computed(() => {
  if (store.selectedMods.length === 0) return null
  return store.selectedMods.at(-1)
})

// 计算属性：根据 mod 名字长度动态调整字体大小
const computedFontSize = computed(() => {
  if (store.selectedMods.length === 0) return '1.25vw';
  const text = store.selectedMods.at(-1).name;
  if (!text) return '1.25vw';
  const length = text.length;

  // 根据文字长度动态计算字体大小
  if (length > 100) return '0.5vw';
  if (length > 90) return '0.65vw';
  if (length > 80) return '0.7vw';
  if (length > 70) return '0.8vw';
  if (length > 60) return '0.9vw';
  if (length > 50) return '1.0vw';
  if (length > 40) return '1.15vw';
  if (length > 20) return '1.25vw';
  if (length <= 20) return '1.3vw';
  return '1.2vw';
})

const displayVersions = computed(() => {
  // 获取版本数组，如果不存在则返回空数组
  const versions = store.selectedMods.at(-1)?.supported_versions || [];
  // 如果版本数量小于等于5，直接返回所有版本
  if (versions.length < 6) {
    return versions;
  }
  // 如果版本数量大于5，进行合并处理
  // 1. 取第一个版本
  // 2. 取倒数第三个版本，与第一个版本合并
  // 3. 保留最后两个版本
  const firstVersion = versions[0];
  const thirdLastVersion = versions[versions.length - 3];
  const lastTwoVersions = versions.slice(-2);

  return [`${firstVersion} - ${thirdLastVersion}`, ...lastTwoVersions];
})

// 2. 监听 package_id 变化而不是整个对象，性能更好
watch(
  () => selectedMod.value?.package_id, 
  async (newId, oldId, onCleanup) => {
    // 如果没有选中，或者选中的mod没有预览图路径，直接结束
    if (!newId || !selectedMod.value?.preview_path) {
      currentPreviewImage.value = '' // 每次变化先清空，防止显示上一张图
      return
    }

    // 标记加载状态
    isLoadingImage.value = true
    let isCancelled = false

    // onCleanup 是 Vue watch 的回调，当 id 再次变化时触发
    // 用于标记当前这次请求已经“过时”了
    onCleanup(() => {
      isCancelled = true
    })

    try {
      const previewPath = selectedMod.value?.preview_path
      if (previewPath && window.pywebview) {
        // 调用 Python
        const base64Data = await window.pywebview.api.read_image(previewPath)
        
        // 只有在没有被取消（用户没有切换到下一个mod）时才赋值
        if (!isCancelled && base64Data) {
          // 新图到了，替换旧图，触发 Vue Transition
          currentPreviewImage.value = base64Data
        }
      } else {
        // 没有预览图路径的情况，清空
        if (!isCancelled) currentPreviewImage.value = ''
      }
    } catch (e) {
      console.error("加载图片失败", e)
    } finally {
      if (!isCancelled) isLoadingImage.value = false
    }
  }, 
  { immediate: true } // 组件挂载时立即执行一次
)


</script>


<style scoped>

/* 
  核心动画逻辑：
  Vue Transition 默认是 "先移除旧的，再添加新的"。
  要实现 "交叉淡入淡出 (Cross-fade)"，两张图片必须有一瞬间是重叠的。
  所以图片必须是 absolute positioning (绝对定位)，
  这样新图片进入时会覆盖在旧图片上方，旧图片透明度变 0，新图片透明度变 1。
*/

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.4s ease-in-out;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* 
  为了确保图片在动画过程中能够重叠，
  img 标签在 template 里已经加了 absolute inset-0 
*/

</style>
