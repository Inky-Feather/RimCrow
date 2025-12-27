<template>
  <div v-if="selectedMod" class="flex flex-col h-full p-1 bg-bg-surface/50 select-text"
    :style="{ '--rgb-components': hexToRgb(selectedMod.sign_color) }">
    <!-- 使用方法 bg-[rgba(var(--rgb-components),0.2)] -->
    <!-- 1. 顶部大图与标题区 (保持原有设计风格但优化) -->
    <div class="w-full aspect-video opacity-90 backdrop-blur-sm bg-black/40 rounded-xl overflow-hidden relative border border-white/10 shadow-lg group">
      
      <!-- 图片 (优先显示大图，没有大图时回退显示 store 中的缩略图，防止留白) -->
      <Transition name="fade">
        <!-- 这里的 key Mod ID，变动时触发动画 -->
        <img v-if="selectedMod.preview_url" :key="selectedMod.package_id" :src="selectedMod.preview_url" 
          class="absolute inset-0 w-full h-full object-cover"/>
        <!-- 文字提示兜底 -->
        <div v-else-if="!selectedMod.preview_url" class="absolute inset-0 flex items-center justify-center text-gray-600 bg-bg-surface">
           <div class="text-center">
             <div class="text-4xl mb-2 opacity-20">IMG</div>
             <div class="text-xs">图片不存在</div>
           </div>
        </div>
      </Transition>
      <!-- Mod版本 -->
      <div v-tooltip="'Mod版本'" class="absolute top-1.5 left-2 px-1 py-0.5 rounded text-[10px] text-text-main font-bold text-shadow-lg bg-bg-surface/20 border border-white/5">
        V {{ selectedMod.version ? selectedMod.version : '未知版本' }}
      </div>
      <!-- 支持版本标签 -->
      <div v-tooltip="'支持的游戏版本'" v-show="displayVersions.length" class="absolute top-1 right-2 z-10 pointer-events-none">
        <span v-for="versions in displayVersions" :key="versions" :class="{'bg-accent-success/70': versionIsCompatible(versions)}"
          class="px-1 py-0.4 m-0.5 rounded-md bg-accent-cool/60 text-amber-50 border border-text-main/30 text-[10px] font-bold text-shadow-2xs shadow-md">
          {{ versions }}
        </span>
      </div>
      <!-- 标题 -->
      <div class="absolute bottom-0 inset-x-0 bg-linear-to-t from-bg-deep/90 to-transparent p-2 pt-12">
        <!-- 大小：{{ computedFontSize }}  
        字数：{{ selectedMod.name.length }} -->
        <h2 class="font-bold leading-tight line-clamp-2 text-shadow wrap-break-word adaptive-text" 
          :style="{ fontSize: computedFontSize }" v-tooltip="selectedMod.name">{{ selectedMod.name }}</h2>
      </div>
    </div>

    <!-- 2. 内容滚动区 -->
    <div class="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar pt-3 space-y-4">
      
      <!-- 包ID -->
      <div class="px-2 text-[11px] flex items-center gap-1 text-text-dim tracking-wider border-b border-white/5 pb-1" v-tooltip="selectedMod.package_id">
        <svg width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M44 14L24 4L4 14V34L24 44L44 34V14Z" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/><path d="M4 14L24 24" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M24 44V24" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M44 14L24 24" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M34 9L14 19" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <span class="truncate flex-1 min-w-0">{{ selectedMod.package_id }}</span>
      </div>
      <!-- B. 统计信息与路径 -->
      <div class="grid grid-flow-row-dense p-1 grid-cols-2 gap-1.5">
        <!-- 作者 -->
        <div class="col-span-2 flex items-center gap-1 bg-white/5 rounded-lg p-1.5 border border-white/5 space-y-1">
          <svg class="text-text-dim" width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M24 20C27.866 20 31 16.866 31 13C31 9.13401 27.866 6 24 6C20.134 6 17 9.13401 17 13C17 16.866 20.134 20 24 20Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 40.8V42H42V40.8C42 36.3196 42 34.0794 41.1281 32.3681C40.3611 30.8628 39.1372 29.6389 37.6319 28.8719C35.9206 28 33.6804 28 29.2 28H18.8C14.3196 28 12.0794 28 10.3681 28.8719C8.86278 29.6389 7.63893 30.8628 6.87195 32.3681C6 34.0794 6 36.3196 6 40.8Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <div class="flex-1 min-w-0 m-0 space-y-1">
            <div class="text-[10px] text-text-dim uppercase">作者</div>
            <div class="flex flex-wrap gap-1" v-tooltip="selectedMod.author.join(', ')">
              <span v-if="selectedMod.author?.length" v-for="author in selectedMod.author" :key="author" 
                class="px-1 rounded bg-accent-highlight/20 text-text-main/90 text-xs border border-accent-highlight/20 flex items-center gap-1 group">
                {{ author }}
              </span>
              <span v-else v-tooltip="'未知'" class="px-1 rounded bg-text-dim/20 text-text-dim text-xs border border-text-dim/20 flex items-center gap-1 group">
                未知
              </span>
            </div>
          </div>
        </div>
        <!-- 支持语言 -->
        <div class="col-span-2 flex items-center gap-1 bg-white/5 rounded-lg p-1.5 border border-white/5">
          <svg class="text-text-dim" width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M28.2857 37H39.7143M42 42L39.7143 37L42 42ZM26 42L28.2857 37L26 42ZM28.2857 37L34 24L39.7143 37H28.2857Z" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 6L17 9" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 11H28" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 16C10 16 11.7895 22.2609 16.2632 25.7391C20.7368 29.2174 28 32 28 32" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M24 11C24 11 22.2105 19.2174 17.7368 23.7826C13.2632 28.3478 6 32 6 32" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <div class="flex-1 min-w-0 m-0 space-y-1">
            <div class="text-[10px] text-text-dim uppercase">支持语言</div>
            <div class="flex flex-wrap gap-1" v-tooltip="selectedMod.supported_languages.join(', ')">
              <span v-if="selectedMod.supported_languages?.length" v-for="lang in selectedMod.supported_languages" :key="lang" 
                class="px-1 rounded bg-accent-secondary/20 text-accent-secondary text-xs border border-accent-secondary/20 flex items-center gap-1 group">
                {{ lang }}
              </span>
              <span v-else v-tooltip="'未知'" class="px-1 rounded bg-text-dim/20 text-text-dim text-xs border border-text-dim/20 flex items-center gap-1 group">
                未知
              </span>
            </div>
          </div>
        </div>
        <!-- Url显示 -->
        <div v-tooltip="selectedMod.url" class="flex gap-1 justify-between items-center bg-white/5 rounded-lg p-1.5 border border-white/5 cursor-pointer hover:bg-white/10" @click="openUrl(selectedMod.url)">
          <svg width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="34.6074" y="3.4939" width="14" height="18" rx="2" transform="rotate(45 34.6074 3.4939)" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/><rect x="16.2227" y="21.8787" width="14" height="18" rx="2" transform="rotate(45 16.2227 21.8787)" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/><path d="M31.0723 16.929L16.9301 31.0711" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <div class="flex-1 min-w-0 m-0">
            <div class="text-[10px] text-text-dim uppercase flex justify-between items-center">
              <span class="min-w-0 truncate">网络地址</span>
              <svg width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M16 32L33 15" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M15 15H33V33" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
            <div class="text-xs text-accent-cool truncate direction-rtl">{{ selectedMod.source }}</div>
          </div>
          
        </div>
        <!-- 路径显示 -->
        <div v-tooltip="selectedMod.path" class="flex gap-1 justify-between items-center bg-white/5 rounded-lg p-1.5 border border-white/5 cursor-pointer hover:bg-white/10" @click="openPath">
          <svg width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5 8C5 6.89543 5.89543 6 7 6H19L24 12H41C42.1046 12 43 12.8954 43 14V40C43 41.1046 42.1046 42 41 42H7C5.89543 42 5 41.1046 5 40V8Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/><path d="M21 23L16 28L21 33" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 28H32V22" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <div class="flex-1 min-w-0 m-0">
            <div class="text-[10px] text-text-dim uppercase flex justify-between items-center">
              <span class="min-w-0 truncate">本地路径</span>
              <svg class="shrink-0" width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M16 32L33 15" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M15 15H33V33" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
            <div class="text-xs text-accent-cool truncate direction-rtl m-0">{{ selectedMod.path }}</div>
          </div>
          
        </div>

      </div>
      
      <!-- C. 文件统计 (Analyzer Data) -->
      <div v-if="selectedMod.file_stats" class="p-1 space-y-2">
        <h3 class="text-xs font-bold text-text-dim uppercase tracking-wider border-b border-white/5 pb-1">
          文件统计
          <span v-tooltip="'注意：本统计仅涵盖通用文件，及 Mod 所支持的游戏最高版本对应的文件（不涉及其他游戏版本的文件）。'" class="text-text-dim/50 hover:text-text-main">⚠︎</span>
        </h3>
        <div class="grid grid-cols-4 gap-1.5 text-center text-text-dim">
          <StatItem label="Defs" :value="selectedMod.file_stats.game_xml || 0" >
            <svg width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10 44H38C39.1046 44 40 43.1046 40 42V14H30V4H10C8.89543 4 8 4.89543 8 6V42C8 43.1046 8.89543 44 10 44Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M30 4L40 14" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M27 24L32 29L27 34" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M21 24L16 29L21 34" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </StatItem>
          <StatItem label="Patches" :value="selectedMod.file_stats.patch_xml || 0" >
            <svg width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10 44H38C39.1046 44 40 43.1046 40 42V14H30V4H10C8.89543 4 8 4.89543 8 6V42C8 43.1046 8.89543 44 10 44Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M30 4L40 14" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="24" cy="27" r="5" fill="none" stroke="currentColor" stroke-width="3"/><path d="M24 19V22" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M24 32V35" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M29.8281 21L27.7068 23.1213" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M19.8281 31L17.7068 33.1213" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M18 21L20.1213 23.1213" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M28 31L30.1213 33.1213" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 27H17.5H19" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M29 27H30.5H32" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </StatItem>
          <StatItem label="Textures" :value="selectedMod.file_stats.image || 0" >
            <svg width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10 44H38C39.1046 44 40 43.1046 40 42V14H30V4H10C8.89543 4 8 4.89543 8 6V42C8 43.1046 8.89543 44 10 44Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M30 4L40 14" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="18" cy="17" r="4" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M15 28V37H33V21L23.4894 31.5L15 28Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </StatItem>
          <StatItem label="Audio" :value="selectedMod.file_stats.audio || 0" >
            <svg width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10 44H38C39.1046 44 40 43.1046 40 42V14H30V4H10C8.89543 4 8 4.89543 8 6V42C8 43.1046 8.89543 44 10 44Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M30 4L40 14" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M31 20L25 22.9688V33.5" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="21" cy="33" r="4" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </StatItem>
          <StatItem label="DLLs" :value="selectedMod.file_stats.code_dll || 0" highlight >
            <svg width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10 44H38C39.1046 44 40 43.1046 40 42V14H30V4H10C8.89543 4 8 4.89543 8 6V42C8 43.1046 8.89543 44 10 44Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M30 4L40 14" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M17 25H24L31 25" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M17 31H24L31 31" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M21 21V35" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M27 21V35" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </StatItem>
          <StatItem label="Langs" :value="selectedMod.file_stats.lang_xml || 0" >
            <svg width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10 44H38C39.1046 44 40 43.1046 40 42V14H30V4H10C8.89543 4 8 4.89543 8 6V42C8 43.1046 8.89543 44 10 44Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M30 4L40 14" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M24 22V36" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M18 22H24L30 22" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </StatItem>
          <div v-tooltip="selectedMod.mod_type" class="p-1 col-span-2 bg-white/5 rounded-lg border text-text-dim border-white/5 flex items-center justify-center">
            <svg v-show="selectedMod.mod_type=='LanguagePack'" width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M28.2857 37H39.7143M42 42L39.7143 37L42 42ZM26 42L28.2857 37L26 42ZM28.2857 37L34 24L39.7143 37H28.2857Z" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 6L17 9" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 11H28" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 16C10 16 11.7895 22.2609 16.2632 25.7391C20.7368 29.2174 28 32 28 32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M24 11C24 11 22.2105 19.2174 17.7368 23.7826C13.2632 28.3478 6 32 6 32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="selectedMod.mod_type=='XML'" width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M16 13L4 25.4322L16 37" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M32 13L44 25.4322L32 37" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M28 4L21 44" stroke="currentColor" stroke-width="4" stroke-linecap="round"/></svg>
            <svg v-show="selectedMod.mod_type=='Assembly'" width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="6" y="6" width="36" height="36" rx="3" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M19 16V32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M29 16V32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 19H32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 29H32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="selectedMod.mod_type=='Texture'" width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M39 6H9C7.34315 6 6 7.34315 6 9V39C6 40.6569 7.34315 42 9 42H39C40.6569 42 42 40.6569 42 39V9C42 7.34315 40.6569 6 39 6Z" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M18 23C20.7614 23 23 20.7614 23 18C23 15.2386 20.7614 13 18 13C15.2386 13 13 15.2386 13 18C13 20.7614 15.2386 23 18 23Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M27.7901 26.2194C28.6064 25.1269 30.2528 25.1538 31.0329 26.2725L39.8077 38.8561C40.7322 40.182 39.7835 42.0001 38.1671 42.0001H16L27.7901 26.2194Z" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="selectedMod.mod_type=='Audio'" width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M30 34.5C30 32.567 31.567 31 33.5 31H41V34.4C41 36.3882 39.3882 38 37.4 38H33.5C31.567 38 30 36.433 30 34.5Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/><path d="M6 38.5C6 36.567 7.567 35 9.5 35H16V38.4C16 40.3882 14.3882 42 12.4 42H9.5C7.567 42 6 40.433 6 38.5Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/><path d="M16 18.044V18.044L41 12.125" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 38V10L41 4V33.6924" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="selectedMod.mod_type=='Mixed'" width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="16" y="16" width="27" height="27" rx="2" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><rect x="5" y="5" width="27" height="27" rx="2" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M27 16L16 27" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M32 21L21 32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="selectedMod.mod_type=='Unknown'" width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M39 6H9C7.34315 6 6 7.34315 6 9V39C6 40.6569 7.34315 42 9 42H39C40.6569 42 42 40.6569 42 39V9C42 7.34315 40.6569 6 39 6Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/><path d="M24 28.625V24.625C27.3137 24.625 30 21.9387 30 18.625C30 15.3113 27.3137 12.625 24 12.625C20.6863 12.625 18 15.3113 18 18.625" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path fill-rule="evenodd" clip-rule="evenodd" d="M24 37.625C25.3807 37.625 26.5 36.5057 26.5 35.125C26.5 33.7443 25.3807 32.625 24 32.625C22.6193 32.625 21.5 33.7443 21.5 35.125C21.5 36.5057 22.6193 37.625 24 37.625Z" fill="currentColor"/></svg>
            <span class="flex-1 truncate">{{ selectedMod.mod_type }}</span>
          </div>
        </div>
      </div>

      <!-- 时间戳列表 及 其他信息 -->
      <div class="p-1 space-y-2">
        <h3 class="text-xs font-bold text-text-dim uppercase tracking-wider border-b border-white/5 pb-1">其他信息</h3>
        <div class="grid grid-flow-col grid-cols-4 grid-rows-2 gap-1.5">
          <div v-tooltip="selectedMod.icon_url ? '图标': '未能找到该Mod图标'" class="col-span-1 row-span-1 flex items-center justify-center bg-white/5 rounded-lg border border-white/5">
            <img v-if="selectedMod.icon_url" :src="selectedMod.icon_url" class="w-8 h-8 inline-block">
            <svg v-else class="text-text-dim" xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>
          </div>
          <!-- 是否破坏存档 -->
          <div v-tooltip="['危险：注意！中途启用或停用该Mod会破坏存档！','未知：暂时无法知道该Mod是否会破坏存档。','安全：该Mod不会破坏存档，可放心加入或移除。'][parseInt(selectedMod.save_breaking)+1]" class="col-span-1 row-span-1 p-1.5 flex items-center justify-around text-[10px] text-text-dim bg-white/5 rounded-lg border border-white/5">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-save-off-icon lucide-save-off"><path d="M13 13H8a1 1 0 0 0-1 1v7"/><path d="M14 8h1"/><path d="M17 21v-4"/><path d="m2 2 20 20"/><path d="M20.41 20.41A2 2 0 0 1 19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 .59-1.41"/><path d="M29.5 11.5s5 5 4 5"/><path d="M9 3h6.2a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V15"/></svg>
            <svg v-show="parseInt(selectedMod.save_breaking)===-1" class=" text-accent-danger" width="18" height="18" xmlns="http://www.w3.org/2000/svg"viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m14.5 9.5-5 5"/><path d="m9.5 9.5 5 5"/></svg>
            <svg v-show="parseInt(selectedMod.save_breaking)===0" class=" text-text-main" width="18" height="18" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M9.1 9a3 3 0 0 1 5.82 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>
            <svg v-show="parseInt(selectedMod.save_breaking)===1" class=" text-accent-success" width="18" height="18" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></svg>
          </div>
          <div class="row-span-2 col-span-3 p-2 pr-3 space-y-1 flex flex-col justify-center text-[10px] text-text-dim bg-white/5 rounded-lg border border-white/5">
            <div class="flex justify-between items-center">
              <span class="font-bold">文件创建时间：</span>
              {{ selectedMod.file_create_time ? new Date(selectedMod.file_create_time).toLocaleString() : '无' }}
            </div>
            <div class="flex justify-between items-center">
              <span class="font-bold">文件修改时间：</span>
              {{ selectedMod.file_modify_time ? new Date(selectedMod.file_modify_time).toLocaleString() : '无' }}
            </div>
            <div class="flex justify-between items-center">
              <span class="font-bold">最后启用时间：</span>
              {{ selectedMod.last_active_time ? new Date(selectedMod.last_active_time).toLocaleString() : '无' }}
            </div>
            <div class="flex justify-between items-center">
              <span class="font-bold">工坊更新时间：</span>
              {{ selectedMod.mod_update_time ? new Date(selectedMod.mod_update_time).toLocaleString() : '无' }}
            </div>
          </div>
        </div>

      </div>

      <!-- D. 依赖与冲突 -->
      <div v-if="hasDependencies" class="p-1 space-y-3">
        <h3 class="text-xs font-bold text-text-dim uppercase tracking-wider border-b border-white/5 pb-1">模组关系</h3>
        
        <!-- 依赖 -->
        <div v-if="selectedMod.dependencies_mods?.length" class="space-y-1">
          <div class="mb-1 text-[10px] font-bold uppercase tracking-wider text-accent-highlight">依赖于</div>
          <!-- 依赖项列表 -->
          <!-- 显示前5个或全部（展开状态） -->
          <div v-for="(dep, index) in showAllDependencies ? selectedMod.dependencies_mods : selectedMod.dependencies_mods.slice(0, 5)" 
            :key="dep.package_id" 
            class="flex items-center justify-between gap-2 p-1.5 rounded-sm bg-black/20 border-l-2 transition-colors text-xs border-accent-highlight hover:bg-accent-highlight/10">
            <span v-preview="store.getModById(dep.package_id)" class="text-gray-300">{{ displayNameByMod(dep) }}</span>
            <!-- 操作按钮 -->
            <div class="flex items-center gap-2">
              <span v-if="!store.getModById(dep.package_id).is_missing" @click="targetItem(dep.package_id)" v-tooltip="'定位Mod位置'" class="hover:text-accent-highlight">
                <svg width="15" height="15" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-crosshair-icon lucide-crosshair"><circle cx="12" cy="12" r="10"/><line x1="22" x2="18" y1="12" y2="12"/><line x1="6" x2="2" y1="12" y2="12"/><line x1="12" x2="12" y1="6" y2="2"/><line x1="12" x2="12" y1="22" y2="18"/></svg>
              </span>
              <span v-if="dep.workshop_url" @click="openUrl(dep.workshop_url)" @click.middle.stop="openSteamUrl(dep.workshop_url)" v-tooltip="'打开工坊页面'" class="hover:text-accent-highlight">
                <svg width="15" height="15" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-square-arrow-out-up-right-icon lucide-square-arrow-out-up-right"><path d="M21 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h6"/><path d="m21 3-9 9"/><path d="M15 3h6v6"/></svg>
              </span>
            </div>

          </div>
          
          <!-- 展开/收起按钮（只有当数量超过5个时显示） -->
          <button v-if="selectedMod.dependencies_mods.length > 5"
            @click="showAllDependencies = !showAllDependencies"
            class="w-full py-1.5 mt-1 flex items-center justify-center gap-1 rounded bg-white/5 hover:bg-white/10 text-[11px] text-gray-400 hover:text-accent-highlight transition-all group"
          >
            {{ showAllDependencies ? '收起' : `查看全部(${selectedMod.dependencies_mods.length})` }}
            <svg :class="{'rotate-180': showAllDependencies}" class="w-3 h-3 transition-transform duration-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>
        
        <!-- 不兼容 -->
        <div v-if="selectedMod.incompatible_mods?.length" class="space-y-1">
          <div class="mb-1 text-[10px] font-bold uppercase tracking-wider text-accent-danger">冲突于</div>
          <!-- 不兼容项列表 -->
          <div v-for="inc in showAllIncompatible ? selectedMod.incompatible_mods : selectedMod.incompatible_mods.slice(0, 5)" :key="inc" 
              class="flex items-center justify-between gap-2 p-1.5 rounded-sm bg-black/20 border-l-2 transition-colors text-xs border-accent-danger hover:bg-accent-danger/10">
            <span class="text-gray-300">{{ displayNameById(inc) }}</span>
            <!-- 操作按钮 -->
            <div class="flex items-center gap-2">
              <span v-if="!store.getModById(inc).is_missing" @click="targetItem(inc)" v-tooltip="'定位Mod位置'" class="hover:text-accent-danger">
                <svg width="15" height="15" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-crosshair-icon lucide-crosshair"><circle cx="12" cy="12" r="10"/><line x1="22" x2="18" y1="12" y2="12"/><line x1="6" x2="2" y1="12" y2="12"/><line x1="12" x2="12" y1="6" y2="2"/><line x1="12" x2="12" y1="22" y2="18"/></svg>
              </span>
            </div>
          </div>
          <!-- 展开/收起按钮（只有当数量超过5个时显示） -->
          <button v-if="selectedMod.incompatible_mods.length > 5"
            @click="showAllIncompatible = !showAllIncompatible"
            class="w-full py-1.5 mt-1 flex items-center justify-center gap-1 rounded bg-white/5 hover:bg-white/10 text-[11px] text-gray-400 hover:text-accent-danger transition-all group"
          >
            {{ showAllIncompatible ? '收起' : `展开全部 (${selectedMod.incompatible_mods.length})` }}
            <svg :class="{'rotate-180': showAllIncompatible}" class="w-3 h-3 transition-transform duration-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>

        <!-- 前置加载 -->
        <div v-if="selectedMod.load_after_mods?.length" class="space-y-1">
          <div class="mb-1 text-[10px] font-bold uppercase tracking-wider text-accent-warm">前置加载</div>
          <!-- 前置加载项列表 -->
          <div v-for="aft in showAllLoadAfter ? selectedMod.load_after_mods : selectedMod.load_after_mods.slice(0, 5)" :key="aft" 
            class="flex items-center justify-between gap-2 p-1.5 rounded-sm bg-black/20 border-l-2 transition-colors text-xs border-accent-warm hover:bg-accent-warm/10">
            <span class="text-gray-300">{{ displayNameById(aft) }}</span>
            <!-- 操作按钮 -->
            <div class="flex items-center gap-2">
              <span v-if="!store.getModById(aft).is_missing" @click="targetItem(aft)" v-tooltip="'定位Mod位置'" class="hover:text-accent-warm">
                <svg width="15" height="15" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-crosshair-icon lucide-crosshair"><circle cx="12" cy="12" r="10"/><line x1="22" x2="18" y1="12" y2="12"/><line x1="6" x2="2" y1="12" y2="12"/><line x1="12" x2="12" y1="6" y2="2"/><line x1="12" x2="12" y1="22" y2="18"/></svg>
              </span>
            </div>
          </div>
          <!-- 展开/收起按钮（只有当数量超过5个时显示） -->
          <button v-if="selectedMod.load_after_mods.length > 5"
            @click="showAllLoadAfter = !showAllLoadAfter"
            class="w-full py-1.5 mt-1 flex items-center justify-center gap-1 rounded bg-white/5 hover:bg-white/10 text-[11px] text-gray-400 hover:text-accent-warm transition-all group"
          >
            {{ showAllLoadAfter ? '收起' : `展开全部 (${selectedMod.load_after_mods.length})` }}
            <svg :class="{'rotate-180': showAllLoadAfter}" class="w-3 h-3 transition-transform duration-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>

        <!-- 后置加载 -->
        <div v-if="selectedMod.load_before_mods?.length" class="space-y-1">
          <div class="mb-1 text-[10px] font-bold uppercase tracking-wider text-accent-primary">后置加载</div>
          <!-- 后置加载项列表 -->
          <div v-for="bef in showAllLoadBefore ? selectedMod.load_before_mods : selectedMod.load_before_mods.slice(0, 5)" :key="bef" 
            class="flex items-center justify-between gap-2 p-1.5 rounded-sm bg-black/20 border-l-2 transition-colors text-xs border-accent-primary hover:bg-accent-primary/10">
            <span class="text-gray-300">{{ displayNameById(bef) }}</span>
            <!-- 操作按钮 -->
            <div class="flex items-center gap-2">
              <span v-if="!store.getModById(bef).is_missing" @click="targetItem(bef)" v-tooltip="'定位Mod位置'" class="hover:text-accent-primary">
                <svg width="15" height="15" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-crosshair-icon lucide-crosshair"><circle cx="12" cy="12" r="10"/><line x1="22" x2="18" y1="12" y2="12"/><line x1="6" x2="2" y1="12" y2="12"/><line x1="12" x2="12" y1="6" y2="2"/><line x1="12" x2="12" y1="22" y2="18"/></svg>
              </span>
            </div>
          </div>
          <!-- 展开/收起按钮（只有当数量超过5个时显示） -->
          <button v-if="selectedMod.load_before_mods.length > 5"
            @click="showAllLoadBefore = !showAllLoadBefore"
            class="w-full py-1.5 mt-1 flex items-center justify-center gap-1 rounded bg-white/5 hover:bg-white/10 text-[11px] text-gray-400 hover:text-accent-primary transition-all group"
          >
            {{ showAllLoadBefore ? '收起' : `展开全部 (${selectedMod.load_before_mods.length})` }}
            <svg :class="{'rotate-180': showAllLoadBefore}" class="w-3 h-3 transition-transform duration-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
        </div>

      </div>

      <!-- A. 用户自定义属性 (标签 & 颜色 & 备注) -->
      <div class="rounded-xl p-3 border bg-[rgba(var(--rgb-components),0.1)]  border-white/10 backdrop-blur-sm space-y-3">
        
        <!-- 标签管理 (带自动补全) -->
        <div>
          <label v-tooltip="'可在此添加自定义标签'" class="text-[10px] uppercase text-text-dim font-bold tracking-wider mb-1 block">标签*</label>
          <div class="flex flex-wrap gap-2 mb-2">
            <span v-for="tag in userTags" :key="tag" 
              class="px-2 py-0.5 rounded bg-accent-primary/20 text-accent-primary text-xs border border-accent-primary/20 flex items-center gap-1 group">
              {{ tag }}
              <button @click="removeTag(tag)" class="hover:text-white font-bold opacity-50 group-hover:opacity-100">×</button>
            </span>
            <!-- 添加标签输入框 -->
            <div class="relative">
              <input type="text" v-model="newTagInput" @keydown.enter="addTag" @blur="newTagInput=''" list="known-tags"
                placeholder="+ 添加标签" 
                class="px-1.5 py-0.5 rounded bg-black/40 border border-white/10 text-xs text-white focus:border-accent-primary focus:outline-none w-6 focus:w-20 transition-all"/>
              <datalist id="known-tags">
                <option v-for="t in store.knownTags" :key="t" :value="t"></option>
              </datalist>
            </div>
          </div>
        </div>

        <!-- 颜色选择 (简单版) -->
        <div class="flex items-center">
          <label v-tooltip="'可自定义颜色标识'" class="flex-none text-[10px] uppercase text-text-dim font-bold tracking-wider">颜色标记*</label>
          <div v-tooltip="'点击可选择合适的标记颜色'" class="flex-1 flex ml-2 min-w-20 gap-1.5 items-center justify-end">
            <button v-for="c in presetColors" :key="c" @click="updateColor(c)"
              :class="['w-4 h-4 min-w-1 rounded-full border border-white/10 transition-transform hover:scale-125', 
                      selectedMod.sign_color === c ? 'ring-2 ring-white scale-110' : '']"
              :style="{backgroundColor: c}">
            </button>
            <button @click="updateColor(null)" v-tooltip="'清除颜色标记'" 
              class="w-4 h-4 rounded-full border border-white/10 bg-transparent text-xm flex items-center justify-center text-gray-500 hover:text-white">
              ×
            </button>
          </div>
        </div>

        <!-- 别名 -->
        <div class="mb-2">
          <input v-model="userAliasName" @blur="saveUserData" placeholder="在此添加自定义别名"
              class="w-full bg-black/20 border border-white/10 rounded p-2 text-xs text-white focus:border-accent-primary focus:outline-none"/>
        </div>

        <!-- 备注 -->
        <div>
            <textarea v-model="userNotes" @blur="saveUserData" placeholder="在此添加自定义备注"
              class="w-full bg-black/20 border border-white/10 rounded p-2 text-xs text-gray-300 focus:border-accent-primary focus:outline-none h-20 resize-none custom-scrollbar"></textarea>
        </div>
        
      </div>

      <!-- E. 描述 (HTML) -->
      <div class="p-1 space-y-2">
        <h3 class="text-xs font-bold text-text-dim uppercase tracking-wider border-b border-white/5 pb-1">描述</h3>
        <div class="prose prose-invert prose-xs max-w-none text-gray-300 leading-relaxed wrap-break-word" v-html="formattedDescription"></div>
      </div>

      <!-- 底部占位提示 -->
      <div class="text-[10px] text-text-dim opacity-50">
        * 由于格式和规范性方面的限制，部分模组信息可能无法完全获取。
      </div>

    </div>
  </div>

  <!-- 无选中Mod时 -->
  <div v-else class="flex flex-col items-center justify-center h-full text-text-dim">
    <div class="text-4xl opacity-20 mb-2">❖</div>
    <div class="text-xs uppercase tracking-widest opacity-50">Select a Mod</div>
    <!-- <LampEffect>
      <ImageCloud 
        :images="imageUrls" 
        :size="400" 
        :imageSize="50"
        class="border border-white/20"
      />
      
    </LampEffect> -->
  </div>

</template>

<script setup >
import { computed, ref, watch } from 'vue'
import { useModStore } from '../stores/modStore'
import ImageCloud from './utils/ImageCloud.vue';
import LampEffect from './utils/LampEffect.vue';

// 随机选30个Mod的图标URL
const imageUrls = computed(() => Array.from(store.allModsMap.values())
  .filter(mod => mod.icon_url) // 过滤掉没有图标URL的Mod
  .sort(() => 0.5 - Math.random()) // 随机排序
  .slice(0, 30) // 取前30个
  .map(mod => mod.icon_url))

// 子组件: 简单统计块
const StatItem = {
  props: ['label', 'value', 'highlight'],
  template: `
    <!-- 外层改为 flex-row 横向排列，加 gap 控制图标与内容间距 -->
    <div class="bg-white/5 rounded-lg p-1 flex items-center border border-white/5 gap-0">
      <!-- 图标插槽：flex-shrink-0 防止图标被压缩，可选插槽（无图标时不占空间） -->
      <slot />
      
      <!-- 内容容器：保持垂直布局，居中对齐 -->
      <div class="flex flex-col items-center flex-1 min-w-10">
        <span class="text-lg font-bold leading-none" :class="highlight && value > 0 ? 'text-accent-primary' : 'text-gray-400'">{{ value }}</span>
        <span class="text-[9px] text-text-dim uppercase scale-90">{{ label }}</span>
      </div>
    </div>
  `
}
const store = useModStore()
const selectedMod = computed(() => store.selectedMods.at(-1)) // 取最后一个选中的
const userTags = ref([])
const userAliasName = ref('')
const userNotes = ref('')
const newTagInput = ref('')
const presetColors = ['#ef4444', '#ec4899', '#8b5cf6', '#3b82f6', '#06b6d4', '#10b981', '#84cc16', '#eab308', '#f97316']

const showAllDependencies = ref(false);
const showAllIncompatible = ref(false);
const showAllLoadBefore = ref(false);
const showAllLoadAfter = ref(false);

// 监听选中变化，同步本地编辑状态
watch(selectedMod, (newVal) => {
  if (newVal) {
    userTags.value = [...(newVal.tags || [])]
    userAliasName.value = newVal.alias_name || ''
    userNotes.value = newVal.notes || ''
    newTagInput.value = ''
  }
}, { immediate: true })

// 辅助计算：格式化描述（换行转为 <br>）
const formattedDescription = computed(() => {
  if (!selectedMod.value?.description) return 'No description provided.'
  // 简单把换行转为 <br>，防止 XSS 可用 DOMPurify，这里假设 Mod 描述相对安全或后端处理
  return selectedMod.value.description.replace(/\n/g, '<br/>')
})
// 辅助计算：是否有依赖项或冲突项
const hasDependencies = computed(() => {
  return (selectedMod.value?.dependencies_mods?.length > 0) || (selectedMod.value?.incompatible_mods?.length > 0)
})
// 根据 mod 名字长度动态调整字体大小
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
// 显示版本信息（最多显示5个版本）
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

// 辅助函数：根据 mod 依赖项获取显示名称
const displayNameByMod = (dependencies_mod) => {
  const mod_id = dependencies_mod.package_id
  return store.getModById(mod_id)?.alias_name || store.getModById(mod_id)?.name || dependencies_mod.display_name || dependencies_mod.package_id
}
const displayNameById = (mod_id) => {
  return store.getModById(mod_id)?.alias_name || store.getModById(mod_id)?.name || mod_id
}

// 检查版本是否兼容
const versionIsCompatible = (version) => {
  // 截取版本号（只保留主版本号，如 1.2.3 截取为 1.2）
  const game_version = store.settings.game_version.match(/^\d+\.\d+/)?.[0] || ''
  // 转为浮点数比较版本号，返回 true 表示兼容，false 表示不兼容
  return parseFloat(version) >= parseFloat(game_version)
}
// 添加标签
const addTag = () => {
  const val = newTagInput.value.trim()
  if (val && !userTags.value.includes(val)) {
    userTags.value.push(val)
    saveUserData()
  }
  newTagInput.value = ''
}
// 移除标签
const removeTag = (tag) => {
  userTags.value = userTags.value.filter(t => t !== tag)
  saveUserData()
}
// 更新颜色
const updateColor = (color) => {
  if (selectedMod.value) {
    store.updateModUserData(selectedMod.value.package_id, { sign_color: color })
  }
}
// 保存用户数据（标签和备注）
const saveUserData = () => {
  if (selectedMod.value) {
    store.updateModUserData(selectedMod.value.package_id, {
      tags: userTags.value,
      alias_name: userAliasName.value,
      notes: userNotes.value
    })
  }
}
// 打开Mod路径
const openPath = () => {
  if(selectedMod.value?.path) store.openPath(selectedMod.value.path)
}
// 打开Url
const openUrl = (url) => {
  if(url) window.open(url, '_blank')
}
// 打开SteamUrl
const openSteamUrl = (url) => {
  if(url) {
    url = url.replace('https://steamcommunity.com/sharedfiles/filedetails/?id=', 'steam://url/CommunityFilePage/')
    window.open(url, '_blank')
  }
}



// 定位Mod位置
const targetItem = (mod_id) => {
  store.currentTargetId = mod_id
}

// 颜色格式转换
const hexToRgb = (hex) => {
  if (!hex || typeof hex !== 'string') return `0, 0, 0`; // 返回纯组件字符串
  let cleanHex = hex.replace('#', '');
  if (cleanHex.length === 3) {
    cleanHex = cleanHex.split('').map(char => char + char).join('');
  }
  // 确保是六位
  if (cleanHex.length !== 6) {
    console.error(`Invalid hex color: ${hex}`);
    return `0, 0, 0`;
  }
  // 提取 R, G, B 分量，并从十六进制转换为十进制
  const r = parseInt(cleanHex.substring(0, 2), 16);
  const g = parseInt(cleanHex.substring(2, 4), 16);
  const b = parseInt(cleanHex.substring(4, 6), 16);
  return `${r}, ${g}, ${b}`;
};
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
