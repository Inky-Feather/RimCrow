<template>
  <div v-if="selectedMod" class="flex flex-col h-full p-1 bg-bg-surface/50 select-text">
    
    <!-- 1. 顶部大图与标题区 (保持原有设计风格但优化) -->
    <div class="w-full aspect-video bg-black/40 rounded-xl overflow-hidden relative border border-white/10 shadow-lg group">
      
      <!-- 图片 (优先显示大图，没有大图时回退显示 store 中的缩略图，防止留白) -->
      <Transition name="fade">
        <!-- 这里的 key 绑定 Base64 字符串或 Mod ID，变动时触发动画 -->
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

      <!-- 版本标签 -->
      <div v-show="displayVersions.length" class="absolute top-1 right-2 z-10 pointer-events-none">
        
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
          :style="{ fontSize: computedFontSize }">{{ selectedMod.name }}</h2>
      </div>
    </div>

    <!-- 2. 内容滚动区 -->
    <div class="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar pt-3 space-y-4">
      
      <!-- 包ID -->
      <div class="px-2 text-[11px] flex items-center gap-1 text-text-dim tracking-wider border-b border-white/5 pb-1" :title="selectedMod.package_id">
        <svg width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M44 14L24 4L4 14V34L24 44L44 34V14Z" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/><path d="M4 14L24 24" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M24 44V24" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M44 14L24 24" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M34 9L14 19" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <span class="truncate flex-1 min-w-0">{{ selectedMod.package_id }}</span>
      </div>
      <!-- A. 用户自定义属性 (标签 & 颜色 & 备注) -->
      <div class="bg-black/20 rounded-xl p-3 border border-white/5 space-y-3">
        
        <!-- 标签管理 (带自动补全) -->
        <div>
          <label class="text-[10px] uppercase text-text-dim font-bold tracking-wider mb-1 block">Custom Tags</label>
          <div class="flex flex-wrap gap-2 mb-2">
            <span v-for="tag in userTags" :key="tag" 
              class="px-2 py-0.5 rounded bg-accent-primary/20 text-accent-primary text-xs border border-accent-primary/20 flex items-center gap-1 group">
              {{ tag }}
              <button @click="removeTag(tag)" class="hover:text-white font-bold opacity-50 group-hover:opacity-100">×</button>
            </span>
            <!-- 添加标签输入框 -->
            <div class="relative">
              <input type="text" v-model="newTagInput" @keydown.enter="addTag" list="known-tags"
                placeholder="+ Add Tag" 
                class="px-2 py-0.5 rounded bg-black/40 border border-white/10 text-xs text-white focus:border-accent-primary focus:outline-none w-24 focus:w-40 transition-all"/>
              <datalist id="known-tags">
                <option v-for="t in store.knownTags" :key="t" :value="t"></option>
              </datalist>
            </div>
          </div>
        </div>

        <!-- 颜色选择 (简单版) -->
        <div class="flex items-center justify-between">
          <label class="text-[10px] uppercase text-text-dim font-bold tracking-wider">Highlight Color</label>
          <div class="flex gap-1.5">
            <button v-for="c in presetColors" :key="c" @click="updateColor(c)"
              :class="['w-4 h-4 rounded-full border border-white/10 transition-transform hover:scale-125', 
                      selectedMod.sign_color === c ? 'ring-2 ring-white scale-110' : '']"
              :style="{backgroundColor: c}">
            </button>
            <button @click="updateColor(null)" class="w-4 h-4 rounded-full border border-white/10 bg-transparent text-[8px] flex items-center justify-center text-gray-500 hover:text-white" title="Clear">×</button>
          </div>
        </div>

        <!-- 别名 -->
        <div>
          <input v-model="selectedMod.alias_name" placeholder="Add alias here..."
              class="w-full bg-black/20 border border-white/10 rounded p-2 text-xs text-white focus:border-accent-primary focus:outline-none"/>
        </div>

        <!-- 备注 -->
        <div>
            <textarea v-model="userNotes" @blur="saveUserData" placeholder="Add private notes here..."
              class="w-full bg-black/20 border border-white/10 rounded p-2 text-xs text-gray-300 focus:border-accent-primary focus:outline-none h-20 resize-none custom-scrollbar"></textarea>
        </div>
        
      </div>
      <!-- B. 统计信息与路径 -->
      <div class="grid grid-flow-row-dense p-1 grid-cols-2 gap-1.5">
        <!-- 作者 -->
        <div class="col-span-2 flex items-center gap-1 bg-white/5 rounded-lg p-1.5 border border-white/5 space-y-1">
          <svg class="text-text-dim" width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M24 20C27.866 20 31 16.866 31 13C31 9.13401 27.866 6 24 6C20.134 6 17 9.13401 17 13C17 16.866 20.134 20 24 20Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 40.8V42H42V40.8C42 36.3196 42 34.0794 41.1281 32.3681C40.3611 30.8628 39.1372 29.6389 37.6319 28.8719C35.9206 28 33.6804 28 29.2 28H18.8C14.3196 28 12.0794 28 10.3681 28.8719C8.86278 29.6389 7.63893 30.8628 6.87195 32.3681C6 34.0794 6 36.3196 6 40.8Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <div class="flex-1 min-w-0 m-0 space-y-1">
            <div class="text-[10px] text-text-dim uppercase">Author</div>
            <div class="flex flex-wrap gap-1" :title="selectedMod.author.join(', ')">
              <span v-if="selectedMod.author?.length" v-for="author in selectedMod.author" :key="author" 
                class="px-1 rounded bg-accent-highlight/20 text-text-main/90 text-xs border border-accent-highlight/20 flex items-center gap-1 group">
                {{ author }}
              </span>
              <span v-else class="px-1 rounded bg-text-dim/20 text-text-dim text-xs border border-text-dim/20 flex items-center gap-1 group" title="Unknown">
                Unknown
              </span>
            </div>
          </div>
        </div>
        <!-- 支持语言 -->
        <div class="col-span-2 flex items-center gap-1 bg-white/5 rounded-lg p-1.5 border border-white/5">
          <svg class="text-text-dim" width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M28.2857 37H39.7143M42 42L39.7143 37L42 42ZM26 42L28.2857 37L26 42ZM28.2857 37L34 24L39.7143 37H28.2857Z" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 6L17 9" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 11H28" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 16C10 16 11.7895 22.2609 16.2632 25.7391C20.7368 29.2174 28 32 28 32" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M24 11C24 11 22.2105 19.2174 17.7368 23.7826C13.2632 28.3478 6 32 6 32" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <div class="flex-1 min-w-0 m-0 space-y-1">
            <div class="text-[10px] text-text-dim uppercase">Supported Languages</div>
            <div class="flex flex-wrap gap-1" :title="selectedMod.supported_languages.join(', ')">
              <span v-if="selectedMod.supported_languages?.length" v-for="lang in selectedMod.supported_languages" :key="lang" 
                class="px-1 rounded bg-accent-secondary/20 text-accent-secondary text-xs border border-accent-secondary/20 flex items-center gap-1 group">
                {{ lang }}
              </span>
              <span v-else class="px-1 rounded bg-text-dim/20 text-text-dim text-xs border border-text-dim/20 flex items-center gap-1 group" title="Unknown">
                Unknown
              </span>
            </div>
          </div>
        </div>
        <!-- Url显示 -->
        <div :title="selectedMod.url" class="flex gap-1 justify-between items-center bg-white/5 rounded-lg p-1.5 border border-white/5 cursor-pointer hover:bg-white/10" @click="openUrl(selectedMod.url)">
          <svg width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="34.6074" y="3.4939" width="14" height="18" rx="2" transform="rotate(45 34.6074 3.4939)" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/><rect x="16.2227" y="21.8787" width="14" height="18" rx="2" transform="rotate(45 16.2227 21.8787)" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/><path d="M31.0723 16.929L16.9301 31.0711" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <div class="flex-1 min-w-0 m-0">
            <div class="text-[10px] text-text-dim uppercase flex justify-between items-center">
              <span class="min-w-0 truncate">Url</span>
              <svg width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M16 32L33 15" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M15 15H33V33" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
            <div class="text-xs text-accent-cool truncate direction-rtl">{{ selectedMod.source }}</div>
          </div>
          
        </div>
        <!-- 路径显示 -->
        <div :title="selectedMod.path" class="flex gap-1 justify-between items-center bg-white/5 rounded-lg p-1.5 border border-white/5 cursor-pointer hover:bg-white/10" @click="openPath">
          <svg width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5 8C5 6.89543 5.89543 6 7 6H19L24 12H41C42.1046 12 43 12.8954 43 14V40C43 41.1046 42.1046 42 41 42H7C5.89543 42 5 41.1046 5 40V8Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/><path d="M21 23L16 28L21 33" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 28H32V22" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <div class="flex-1 min-w-0 m-0">
            <div class="text-[10px] text-text-dim uppercase flex justify-between items-center">
              <span class="min-w-0 truncate">Location</span>
              <svg class="shrink-0" width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M16 32L33 15" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M15 15H33V33" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </div>
            <div class="text-xs text-accent-cool truncate direction-rtl m-0">{{ selectedMod.path }}</div>
          </div>
          
        </div>

      </div>
      
      <!-- C. 文件统计 (Analyzer Data) -->
      <div v-if="selectedMod.file_stats" class="p-1 space-y-2">
        <h3 class="text-xs font-bold text-text-dim uppercase tracking-wider border-b border-white/5 pb-1">File Content</h3>
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
          <div class="p-1 col-span-2 bg-white/5 rounded-lg border text-text-dim border-white/5 flex items-center justify-center">
            <svg v-show="selectedMod.mod_type=='LanguagePack'" width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M28.2857 37H39.7143M42 42L39.7143 37L42 42ZM26 42L28.2857 37L26 42ZM28.2857 37L34 24L39.7143 37H28.2857Z" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 6L17 9" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 11H28" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 16C10 16 11.7895 22.2609 16.2632 25.7391C20.7368 29.2174 28 32 28 32" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M24 11C24 11 22.2105 19.2174 17.7368 23.7826C13.2632 28.3478 6 32 6 32" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="selectedMod.mod_type=='XML'" width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M16 13L4 25.4322L16 37" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M32 13L44 25.4322L32 37" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M28 4L21 44" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg>
            <svg v-show="selectedMod.mod_type=='Assembly'" width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="6" y="6" width="36" height="36" rx="3" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M19 16V32" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M29 16V32" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 19H32" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 29H32" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="selectedMod.mod_type=='Texture'" width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M39 6H9C7.34315 6 6 7.34315 6 9V39C6 40.6569 7.34315 42 9 42H39C40.6569 42 42 40.6569 42 39V9C42 7.34315 40.6569 6 39 6Z" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M18 23C20.7614 23 23 20.7614 23 18C23 15.2386 20.7614 13 18 13C15.2386 13 13 15.2386 13 18C13 20.7614 15.2386 23 18 23Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M27.7901 26.2194C28.6064 25.1269 30.2528 25.1538 31.0329 26.2725L39.8077 38.8561C40.7322 40.182 39.7835 42.0001 38.1671 42.0001H16L27.7901 26.2194Z" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="selectedMod.mod_type=='Audio'" width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M30 34.5C30 32.567 31.567 31 33.5 31H41V34.4C41 36.3882 39.3882 38 37.4 38H33.5C31.567 38 30 36.433 30 34.5Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/><path d="M6 38.5C6 36.567 7.567 35 9.5 35H16V38.4C16 40.3882 14.3882 42 12.4 42H9.5C7.567 42 6 40.433 6 38.5Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/><path d="M16 18.044V18.044L41 12.125" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 38V10L41 4V33.6924" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="selectedMod.mod_type=='Mixed'" width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="16" y="16" width="27" height="27" rx="2" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><rect x="5" y="5" width="27" height="27" rx="2" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M27 16L16 27" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M32 21L21 32" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="selectedMod.mod_type=='Unknown'" width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M39 6H9C7.34315 6 6 7.34315 6 9V39C6 40.6569 7.34315 42 9 42H39C40.6569 42 42 40.6569 42 39V9C42 7.34315 40.6569 6 39 6Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/><path d="M24 28.625V24.625C27.3137 24.625 30 21.9387 30 18.625C30 15.3113 27.3137 12.625 24 12.625C20.6863 12.625 18 15.3113 18 18.625" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path fill-rule="evenodd" clip-rule="evenodd" d="M24 37.625C25.3807 37.625 26.5 36.5057 26.5 35.125C26.5 33.7443 25.3807 32.625 24 32.625C22.6193 32.625 21.5 33.7443 21.5 35.125C21.5 36.5057 22.6193 37.625 24 37.625Z" fill="currentColor"/></svg>
            <span class="flex-1 truncate">{{ selectedMod.mod_type }}</span>
          </div>
        </div>
      </div>

      <!-- D. 依赖与冲突 -->
      <div v-if="hasDependencies" class="p-1 space-y-3">
         <h3 class="text-xs font-bold text-text-dim uppercase tracking-wider border-b border-white/5 pb-1">Relations</h3>
         
         <!-- Dependencies -->
         <div v-if="selectedMod.dependencies_mods?.length" class="space-y-1">
            <div class="text-[10px] text-accent-cool mb-0.5">Requires</div>
            <div v-for="dep in selectedMod.dependencies_mods" :key="dep.packageId" 
                 class="flex items-center gap-2 p-1.5 rounded bg-black/20 border-l-2 border-accent-cool text-xs">
                 <span class="text-gray-300">{{ displayNameByMod(dep) }}</span>
            </div>
         </div>
         
         <!-- Incompatible -->
         <div v-if="selectedMod.incompatible_mods?.length" class="space-y-1">
            <div class="text-[10px] text-accent-danger mb-0.5">Incompatible With</div>
            <div v-for="inc in selectedMod.incompatible_mods" :key="inc" 
                 class="flex items-center gap-2 p-1.5 rounded bg-black/20 border-l-2 border-accent-danger text-xs">
                 <span class="text-gray-300">{{ displayNameById(inc) }}</span>
            </div>
         </div>
      </div>

      <!-- E. 描述 (HTML) -->
      <div class="p-1 space-y-2">
        <h3 class="text-xs font-bold text-text-dim uppercase tracking-wider border-b border-white/5 pb-1">Description</h3>
        <div class="prose prose-invert prose-xs max-w-none text-gray-300 leading-relaxed break-words" v-html="formattedDescription"></div>
      </div>

      <!-- 底部占位提示 -->
      <div class="text-[10px] text-text-dim opacity-50">
        * Some mod information may not be available.
      </div>

    </div>
  </div>

  <!-- 无选中Mod时 -->
  <div v-else class="flex flex-col items-center justify-center h-full text-text-dim">
    <div class="text-4xl opacity-20 mb-2">❖</div>
    <div class="text-xs uppercase tracking-widest opacity-50">Select a Mod</div>
  </div>

</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useModStore } from '../stores/modStore'

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
const userNotes = ref('')
const newTagInput = ref('')
const presetColors = ['#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#ec4899']


// 监听选中变化，同步本地编辑状态
watch(selectedMod, (newVal) => {
  if (newVal) {
    userTags.value = [...(newVal.tags || [])]
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
  const mod_id = dependencies_mod.packageId
  return store.getModById(mod_id)?.alias_name || store.getModById(mod_id)?.name || dependencies_mod.displayName || dependencies_mod.packageId
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
