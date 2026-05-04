<template>
  <div v-if="selectedMod" class="flex flex-col h-full p-1 bg-bg-surface/50 select-text">
    <!-- 1. 顶部大图与标题区 (保持原有设计风格但优化) -->
    <div class="w-full aspect-video opacity-90 backdrop-blur-sm bg-black/40 rounded-xl overflow-hidden relative border border-text-main/10 shadow-lg group">
      
      <!-- 图片 (优先显示大图，没有大图时回退显示 store 中的缩略图，防止留白) -->
      <Transition :name="appStore.settings.ui.detail_delay ?'fade': ''">
        <!-- 这里的 key Mod ID，变动时触发动画 -->
        <img v-if="selectedMod.preview_path" :key="selectedMod.package_id" :src="appStore.getLocalUrl(selectedMod.preview_path)" 
          class="absolute inset-0 w-full h-full object-cover" loading="lazy"/>
        <!-- 文字提示兜底 -->
        <div v-else class="absolute inset-0 flex items-center justify-center text-gray-600 bg-bg-surface">
          <div class="text-center">
            <div class="text-4xl mb-2 opacity-20">IMG</div>
            <div class="text-xs">图片不存在</div>
          </div>
        </div>
      </Transition>
      <!-- Mod版本 -->
      <div v-tooltip="'Mod版本'" class="absolute top-1.5 left-2 px-1 py-0.5 rounded text-xs text-text-main font-bold text-shadow-lg bg-bg-surface/20 border border-text-main/5">
        v {{ selectedMod.version ? selectedMod.version : '未知版本' }}
      </div>
      <!-- 支持版本标签 -->
      <div v-tooltip="'支持的游戏版本'" v-if="displayVersions.length" class="absolute p-0 top-1.5 right-2 z-10 pointer-events-none hover:opacity-20">
        <span v-for="versions in displayVersions" :key="versions" :class="{'bg-accent-success/70': versionIsCompatible(versions)}"
          class="px-1 py-0.4 m-0.5 rounded-md bg-accent-cool/60 text-amber-50 border border-text-main/30 text-xs font-bold text-shadow-2xs shadow-md">
          {{ versions }}
        </span>
      </div>
      <!-- 标题 -->
      <div class="@container absolute bottom-0 inset-x-0 bg-linear-to-t from-bg-deep/90 to-transparent p-2 pt-12">
        <!-- 大小：{{ computedFontSize }}  
        字数：{{ selectedMod.name.length }} -->
        <h2 class="font-bold leading-tight line-clamp-2 text-shadow wrap-break-word adaptive-text" 
          :style="{ fontSize: computedFontSize }" v-tooltip="selectedMod.name">{{ selectedMod.name }}</h2>
      </div>
    </div>

    <!-- 2. 内容滚动区 -->
    <div class="flex-1 overflow-y-auto overflow-x-hidden custom-scrollbar pt-3 space-y-4">
      <!-- 包ID -->
      <div class="px-2 text-xs flex items-center gap-1 text-text-dim tracking-wider border-b border-text-main/5 pb-1" v-tooltip="selectedMod.package_id">
        <svg class="size-4" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M44 14L24 4L4 14V34L24 44L44 34V14Z" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/><path d="M4 14L24 24" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M24 44V24" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M44 14L24 24" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M34 9L14 19" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <span class="truncate flex-1 min-w-0">{{ selectedMod.package_id_raw }}</span>
      </div>
      <!-- 遍历布局配置 -->
      <template v-for="block in layoutConfig" :key="block.id">
        <!-- 只有当 visible 为 true 时才渲染 -->
        <template v-if="block.visible">

          <!-- 作者信息与路径 -->
          <div v-if="block.id === 'basic_info'" class="p-1 space-y-2">
            <h3 class="text-xs font-bold text-text-dim uppercase tracking-wider border-b border-text-main/5 pb-1">
              {{ appStore.DETAILS_LAYOUT_MAPS[block.id].label }}
            </h3>
            <div class="grid grid-flow-row-dense grid-cols-2 gap-1.5">
              <!-- 作者 -->
              <div class="col-span-2 flex items-center gap-1 bg-text-main/5 rounded-lg p-1.5 border border-text-main/5 space-y-1">
                <svg class="text-text-dim size-6" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M24 20C27.866 20 31 16.866 31 13C31 9.13401 27.866 6 24 6C20.134 6 17 9.13401 17 13C17 16.866 20.134 20 24 20Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 40.8V42H42V40.8C42 36.3196 42 34.0794 41.1281 32.3681C40.3611 30.8628 39.1372 29.6389 37.6319 28.8719C35.9206 28 33.6804 28 29.2 28H18.8C14.3196 28 12.0794 28 10.3681 28.8719C8.86278 29.6389 7.63893 30.8628 6.87195 32.3681C6 34.0794 6 36.3196 6 40.8Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
                <div class="flex-1 min-w-0 m-0 space-y-1">
                  <div class="text-xs text-text-dim uppercase">作者</div>
                  <div class="flex flex-wrap gap-1" v-tooltip="selectedMod.author?.join(', ')">
                    <span v-if="selectedMod.author?.length" v-for="author in selectedMod.author" :key="author" 
                      class="px-1 rounded bg-accent-highlight/20 text-text-main/90 text-sm border border-accent-highlight/20 flex items-center gap-1 group">
                      {{ author }}
                    </span>
                    <span v-else v-tooltip="'未知'" class="px-1 rounded bg-text-dim/20 text-text-dim text-sm border border-text-dim/20 flex items-center gap-1 group">
                      未知
                    </span>
                  </div>
                </div>
              </div>
              <!-- 支持语言 -->
              <div class="col-span-2 flex items-center gap-1 bg-text-main/5 rounded-lg p-1.5 border border-text-main/5">
                <svg class="text-text-dim size-6" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M28.2857 37H39.7143M42 42L39.7143 37L42 42ZM26 42L28.2857 37L26 42ZM28.2857 37L34 24L39.7143 37H28.2857Z" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 6L17 9" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 11H28" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 16C10 16 11.7895 22.2609 16.2632 25.7391C20.7368 29.2174 28 32 28 32" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M24 11C24 11 22.2105 19.2174 17.7368 23.7826C13.2632 28.3478 6 32 6 32" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
                <div class="flex-1 min-w-0 m-0 space-y-1">
                  <div class="text-xs text-text-dim uppercase">支持语言</div>
                  <div class="flex flex-wrap gap-1" v-tooltip="selectedMod.supported_languages?.join(', ')">
                    <span v-if="selectedMod.supported_languages?.length" v-for="lang in selectedMod.supported_languages" :key="lang" 
                      class="px-1 rounded bg-accent-secondary/20 text-accent-secondary text-sm border border-accent-secondary/20 flex items-center gap-1 group">
                      {{ lang }}
                    </span>
                    <span v-else v-tooltip="'未知'" class="px-1 rounded bg-text-dim/20 text-text-dim text-sm border border-text-dim/20 flex items-center gap-1 group">
                      未知
                    </span>
                  </div>
                </div>
              </div>
              <!-- Url显示 -->
              <div v-tooltip="selectedMod.url" class="flex gap-1 justify-between items-center bg-text-main/5 rounded-lg p-1.5 border border-text-main/5 " 
                :class="[selectedMod.source === 'local' || !selectedMod.url ? 'text-text-dim pointer-events-none' : 'cursor-pointer hover:bg-text-main/10']" 
                @click="openUrl(selectedMod.url)">
                <svg v-if="selectedMod.source==='workshop'" class="fill-current -m-0.5 size-7" viewBox="0 0 640 640" xmlns="http://www.w3.org/2000/svg"><path d="M568 320C568 457 456.8 568 319.6 568C205.8 568 110 491.7 80.6 387.6L175.8 426.9C182.2 459 210.7 483.3 244.7 483.3C283.9 483.3 316.6 450.9 314.9 409.8L399.4 349.6C451.5 350.9 495.2 308.7 495.2 256.1C495.2 204.5 453.2 162.6 401.5 162.6C349.8 162.6 307.8 204.6 307.8 256.1L307.8 257.3L248.6 343C233.1 342.1 217.9 346.4 205.1 355.1L72 300.1C82.2 172.4 189.1 72 319.6 72C456.8 72 568 183 568 320zM227.7 448.3L197.2 435.7C202.8 447.3 212.5 456.5 224.4 461.5C251.3 472.7 282.2 459.9 293.4 433.1C298.8 420.1 298.9 405.8 293.5 392.8C288.1 379.8 278 369.6 265 364.2C252.1 358.8 238.3 359 226.1 363.6L257.6 376.6C277.4 384.8 286.8 407.5 278.5 427.3C270.2 447.2 247.5 456.5 227.7 448.3zM401.5 193.8C435.9 193.8 463.8 221.7 463.8 256.1C463.8 290.5 435.9 318.4 401.5 318.4C367.1 318.4 339.2 290.5 339.2 256.1C339.2 221.7 367.1 193.8 401.5 193.8zM401.6 302.8C427.4 302.8 448.4 281.8 448.4 256C448.4 230.2 427.4 209.2 401.6 209.2C375.8 209.2 354.8 230.2 354.8 256C354.8 281.8 375.8 302.8 401.6 302.8z"/></svg>
                <svg v-else-if="selectedMod.source==='github'" class="fill-current -m-0.5 size-7" viewBox="0 0 640 640" xmlns="http://www.w3.org/2000/svg"><path d="M237.9 461.4C237.9 463.4 235.6 465 232.7 465C229.4 465.3 227.1 463.7 227.1 461.4C227.1 459.4 229.4 457.8 232.3 457.8C235.3 457.5 237.9 459.1 237.9 461.4zM206.8 456.9C206.1 458.9 208.1 461.2 211.1 461.8C213.7 462.8 216.7 461.8 217.3 459.8C217.9 457.8 216 455.5 213 454.6C210.4 453.9 207.5 454.9 206.8 456.9zM251 455.2C248.1 455.9 246.1 457.8 246.4 460.1C246.7 462.1 249.3 463.4 252.3 462.7C255.2 462 257.2 460.1 256.9 458.1C256.6 456.2 253.9 454.9 251 455.2zM316.8 72C178.1 72 72 177.3 72 316C72 426.9 141.8 521.8 241.5 555.2C254.3 557.5 258.8 549.6 258.8 543.1C258.8 536.9 258.5 502.7 258.5 481.7C258.5 481.7 188.5 496.7 173.8 451.9C173.8 451.9 162.4 422.8 146 415.3C146 415.3 123.1 399.6 147.6 399.9C147.6 399.9 172.5 401.9 186.2 425.7C208.1 464.3 244.8 453.2 259.1 446.6C261.4 430.6 267.9 419.5 275.1 412.9C219.2 406.7 162.8 398.6 162.8 302.4C162.8 274.9 170.4 261.1 186.4 243.5C183.8 237 175.3 210.2 189 175.6C209.9 169.1 258 202.6 258 202.6C278 197 299.5 194.1 320.8 194.1C342.1 194.1 363.6 197 383.6 202.6C383.6 202.6 431.7 169 452.6 175.6C466.3 210.3 457.8 237 455.2 243.5C471.2 261.2 481 275 481 302.4C481 398.9 422.1 406.6 366.2 412.9C375.4 420.8 383.2 435.8 383.2 459.3C383.2 493 382.9 534.7 382.9 542.9C382.9 549.4 387.5 557.3 400.2 555C500.2 521.8 568 426.9 568 316C568 177.3 455.5 72 316.8 72zM169.2 416.9C167.9 417.9 168.2 420.2 169.9 422.1C171.5 423.7 173.8 424.4 175.1 423.1C176.4 422.1 176.1 419.8 174.4 417.9C172.8 416.3 170.5 415.6 169.2 416.9zM158.4 408.8C157.7 410.1 158.7 411.7 160.7 412.7C162.3 413.7 164.3 413.4 165 412C165.7 410.7 164.7 409.1 162.7 408.1C160.7 407.5 159.1 407.8 158.4 408.8zM190.8 444.4C189.2 445.7 189.8 448.7 192.1 450.6C194.4 452.9 197.3 453.2 198.6 451.6C199.9 450.3 199.3 447.3 197.3 445.4C195.1 443.1 192.1 442.8 190.8 444.4zM179.4 429.7C177.8 430.7 177.8 433.3 179.4 435.6C181 437.9 183.7 438.9 185 437.9C186.6 436.6 186.6 434 185 431.7C183.6 429.4 181 428.4 179.4 429.7z"/></svg>
                <svg v-else-if="selectedMod.source==='local'" class="fill-current size-6" viewBox="0 0 640 640" xmlns="http://www.w3.org/2000/svg"><path d="M73 39.1C63.6 29.7 48.4 29.7 39.1 39.1C29.8 48.5 29.7 63.7 39 73.1L567 601.1C576.4 610.5 591.6 610.5 600.9 601.1C610.2 591.7 610.3 576.5 600.9 567.2L478.9 445.2C483.1 441.8 487.2 438.1 491 434.3L562.1 363.2C591.4 333.9 607.9 294.1 607.9 252.6C607.9 166.2 537.9 96.1 451.4 96.1C414.1 96.1 378.3 109.4 350.1 133.3C370.4 143.4 388.8 156.8 404.6 172.8C418.7 164.5 434.8 160.1 451.4 160.1C502.5 160.1 543.9 201.5 543.9 252.6C543.9 277.1 534.2 300.6 516.8 318L445.7 389.1C441.8 393 437.6 396.5 433.1 399.6L385.6 352.1C402.1 351.2 415.3 337.7 415.8 321C415.8 319.7 415.8 318.4 415.8 317.1C415.8 230.8 345.9 160.2 259.3 160.2C240.1 160.2 221.4 163.7 203.8 170.4L73 39.1zM257.9 224C258.5 224 259 224 259.6 224C274.7 224 289.1 227.7 301.7 234.2C303.5 235.4 305.3 236.5 307.2 237.3C334 253.6 352 283.2 352 316.9C352 317.3 352 317.7 352 318.1L257.9 224zM378.2 480L224 325.8C225.2 410.4 293.6 478.7 378.1 479.9zM171.7 273.5L126.4 228.2L77.8 276.8C48.5 306.1 32 345.9 32 387.4C32 473.8 102 543.9 188.5 543.9C225.7 543.9 261.6 530.6 289.8 506.7C269.5 496.6 251 483.2 235.2 467.2C221.2 475.4 205.1 479.8 188.5 479.8C137.4 479.8 96 438.4 96 387.3C96 362.8 105.7 339.3 123.1 321.9L171.7 273.3z"/></svg>
                <svg v-else="selectedMod.source==='other'" class="fill-current size-6" viewBox="0 0 640 640" xmlns="http://www.w3.org/2000/svg"><path d="M451.5 160C434.9 160 418.8 164.5 404.7 172.7C388.9 156.7 370.5 143.3 350.2 133.2C378.4 109.2 414.3 96 451.5 96C537.9 96 608 166 608 252.5C608 294 591.5 333.8 562.2 363.1L491.1 434.2C461.8 463.5 422 480 380.5 480C294.1 480 224 410 224 323.5C224 322 224 320.5 224.1 319C224.6 301.3 239.3 287.4 257 287.9C274.7 288.4 288.6 303.1 288.1 320.8C288.1 321.7 288.1 322.6 288.1 323.4C288.1 374.5 329.5 415.9 380.6 415.9C405.1 415.9 428.6 406.2 446 388.8L517.1 317.7C534.4 300.4 544.2 276.8 544.2 252.3C544.2 201.2 502.8 159.8 451.7 159.8zM307.2 237.3C305.3 236.5 303.4 235.4 301.7 234.2C289.1 227.7 274.7 224 259.6 224C235.1 224 211.6 233.7 194.2 251.1L123.1 322.2C105.8 339.5 96 363.1 96 387.6C96 438.7 137.4 480.1 188.5 480.1C205 480.1 221.1 475.7 235.2 467.5C251 483.5 269.4 496.9 289.8 507C261.6 530.9 225.8 544.2 188.5 544.2C102.1 544.2 32 474.2 32 387.7C32 346.2 48.5 306.4 77.8 277.1L148.9 206C178.2 176.7 218 160.2 259.5 160.2C346.1 160.2 416 230.8 416 317.1C416 318.4 416 319.7 416 321C415.6 338.7 400.9 352.6 383.2 352.2C365.5 351.8 351.6 337.1 352 319.4C352 318.6 352 317.9 352 317.1C352 283.4 334 253.8 307.2 237.5z"/></svg>
                <div class="flex-1 min-w-0 m-0">
                  <div class="text-xs text-text-dim uppercase flex justify-between items-center">
                    <span class="min-w-0 truncate">来源地址</span>
                    <svg class="shrink-0 size-4" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M16 32L33 15" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M15 15H33V33" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
                  </div>
                  <div class="text-sm text-accent-cool truncate direction-rtl ">{{ displaySourceType }}</div>
                </div>
                
              </div>
              <!-- 路径显示 -->
              <div v-tooltip="selectedMod.path" class="flex gap-1 justify-between items-center bg-text-main/5 rounded-lg p-1.5 border border-text-main/5 " 
                :class="[!selectedMod.path ? 'text-text-dim pointer-events-none' : 'cursor-pointer hover:bg-text-main/10']" 
                @click="openPath(selectedMod.path)">
                <svg class="size-6" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5 8C5 6.89543 5.89543 6 7 6H19L24 12H41C42.1046 12 43 12.8954 43 14V40C43 41.1046 42.1046 42 41 42H7C5.89543 42 5 41.1046 5 40V8Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/><path d="M21 23L16 28L21 33" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 28H32V22" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
                <div class="flex-1 min-w-0 m-0">
                  <div class="text-xs text-text-dim uppercase flex justify-between items-center">
                    <span class="min-w-0 truncate flex gap-2 items-center">本地路径<Copy v-if="selectedMod.is_coexistence" class="size-3 cursor-help text-accent-primary hover:text-text-main" v-tooltip="'该Mod为共存状态，在创意工坊目录同样存在'" /></span>
                    <svg class="shrink-0 size-4" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M16 32L33 15" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M15 15H33V33" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
                  </div>
                  <div class="text-sm text-accent-cool truncate direction-rtl m-0">{{ selectedMod.path }}</div>
                </div>
                
              </div>
              <!-- 已禁用路径 shadow_paths -->
              <div v-if="selectedMod.shadow_paths?.length" class="col-span-2 flex items-center gap-1 bg-text-main/5 rounded-lg p-1.5 border border-text-main/5">
                <svg class=" text-text-dim size-6" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16h.01"/><path d="M12 8v4"/><path d="M15.312 2a2 2 0 0 1 1.414.586l4.688 4.688A2 2 0 0 1 22 8.688v6.624a2 2 0 0 1-.586 1.414l-4.688 4.688a2 2 0 0 1-1.414.586H8.688a2 2 0 0 1-1.414-.586l-4.688-4.688A2 2 0 0 1 2 15.312V8.688a2 2 0 0 1 .586-1.414l4.688-4.688A2 2 0 0 1 8.688 2z"/></svg>
                <div class="flex-1 min-w-0 m-0 space-y-1">
                  <div class="text-xs text-text-dim uppercase">已禁用的包名重复Mod</div>
                  <div class="flex flex-col gap-1 text-accent-danger text-sm">
                    <span v-for="path in selectedMod.shadow_paths" :key="path" v-tooltip="path" @click="openPath(path)"
                      class="px-1 truncate rounded bg-accent-danger/20 border border-accent-danger/20 cursor-pointer">
                      {{ path }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          
          <!-- 文件统计 -->
          <div v-if="selectedMod.file_stats && block.id === 'files_info'" class="p-1 space-y-2">
            <h3 class="flex items-center gap-1 text-xs font-bold text-text-dim uppercase tracking-wider border-b border-text-main/5 pb-1">
              {{ appStore.DETAILS_LAYOUT_MAPS[block.id].label }}
              <span v-tooltip="'注意：本统计仅涵盖通用文件，及 Mod 所支持的游戏最高版本对应的文件（不涉及其他游戏版本的文件）。'" class="text-text-dim/50 hover:text-text-main">⚠︎</span>
              <!-- 文件大小 -->
              <span class="text-[0.65rem] text-text-dim font-normal flex-1 flex items-center justify-end px-1">
                大小: {{ formatFileSize(selectedMod.file_size) }}
              </span>
            </h3>
            <div class="grid grid-cols-4 gap-1.5 text-center text-text-dim">
              <StatItem v-tooltip="'定义XML文件数量'" label="Defs" :value="selectedMod.file_stats.game_xml || 0" >
                <svg width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10 44H38C39.1046 44 40 43.1046 40 42V14H30V4H10C8.89543 4 8 4.89543 8 6V42C8 43.1046 8.89543 44 10 44Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M30 4L40 14" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M27 24L32 29L27 34" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M21 24L16 29L21 34" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </StatItem>
              <StatItem v-tooltip="'补丁XML文件数量'" label="Patches" :value="selectedMod.file_stats.patch_xml || 0" >
                <svg width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10 44H38C39.1046 44 40 43.1046 40 42V14H30V4H10C8.89543 4 8 4.89543 8 6V42C8 43.1046 8.89543 44 10 44Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M30 4L40 14" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="24" cy="27" r="5" fill="none" stroke="currentColor" stroke-width="3"/><path d="M24 19V22" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M24 32V35" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M29.8281 21L27.7068 23.1213" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M19.8281 31L17.7068 33.1213" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M18 21L20.1213 23.1213" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M28 31L30.1213 33.1213" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 27H17.5H19" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M29 27H30.5H32" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </StatItem>
              <StatItem v-tooltip="'图像纹理文件数量'" label="Textures" :value="selectedMod.file_stats.image || 0" >
                <svg width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10 44H38C39.1046 44 40 43.1046 40 42V14H30V4H10C8.89543 4 8 4.89543 8 6V42C8 43.1046 8.89543 44 10 44Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M30 4L40 14" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="18" cy="17" r="4" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M15 28V37H33V21L23.4894 31.5L15 28Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </StatItem>
              <StatItem v-tooltip="'音频文件数量'" label="Audio" :value="selectedMod.file_stats.audio || 0" >
                <svg width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10 44H38C39.1046 44 40 43.1046 40 42V14H30V4H10C8.89543 4 8 4.89543 8 6V42C8 43.1046 8.89543 44 10 44Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M30 4L40 14" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M31 20L25 22.9688V33.5" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="21" cy="33" r="4" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </StatItem>
              <StatItem v-tooltip="'程序集DLL文件数量'" label="DLLs" :value="selectedMod.file_stats.code_dll || 0" highlight >
                <svg width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10 44H38C39.1046 44 40 43.1046 40 42V14H30V4H10C8.89543 4 8 4.89543 8 6V42C8 43.1046 8.89543 44 10 44Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M30 4L40 14" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M17 25H24L31 25" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M17 31H24L31 31" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M21 21V35" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M27 21V35" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </StatItem>
              <StatItem v-tooltip="'语言XML文件数量'" label="Langs" :value="selectedMod.file_stats.lang_xml || 0" >
                <svg width="24" height="24" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10 44H38C39.1046 44 40 43.1046 40 42V14H30V4H10C8.89543 4 8 4.89543 8 6V42C8 43.1046 8.89543 44 10 44Z" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M30 4L40 14" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M24 22V36" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M18 22H24L30 22" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </StatItem>
              <div v-tooltip="tooltipModType" class="p-1 col-span-2 bg-text-main/5 rounded-lg border text-text-dim border-text-main/5 flex items-center justify-center">
                <!-- 模组类型 -->
                <component :is="MOD_TYPE_ICON_MAP[modType] || MOD_TYPE_ICON_MAP.Unknown" class="size-6 opacity-75" />
                <span v-if="modType" class="flex-1 truncate">{{ MOD_TYPE_MAP[modType] }}</span>
              </div>
            </div>
          </div>

          <!-- 时间戳列表 及 其他信息 -->
          <div v-if="!!selectedMod.path && block.id === 'time_info'" class="p-1 space-y-2">
            <h3 class="text-xs font-bold text-text-dim uppercase tracking-wider border-b border-text-main/5 pb-1">
              {{ appStore.DETAILS_LAYOUT_MAPS[block.id].label }}
            </h3>
            <div class="grid grid-flow-col grid-cols-4 grid-rows-2 gap-1.5">
              <div v-tooltip="selectedMod.icon_url ? '图标': '未能找到该Mod图标'" class="col-span-1 row-span-1 flex items-center justify-center bg-text-main/5 rounded-lg border border-text-main/5">
                <img v-if="selectedMod.icon_url" :src="selectedMod.icon_url" class="size-8 inline-block">
                <svg v-else class="text-text-dim size-8" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>
              </div>
              <!-- 是否破坏存档 -->
              <div v-tooltip="tooltipSaveBreaking" class="col-span-1 row-span-1 p-1.5 flex items-center justify-around text-sm text-text-dim bg-text-main/5 rounded-lg border border-text-main/5">
                <svg class="size-6" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="M13 13H8a1 1 0 0 0-1 1v7"/><path d="M14 8h1"/><path d="M17 21v-4"/><path d="m2 2 20 20"/><path d="M20.41 20.41A2 2 0 0 1 19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 .59-1.41"/><path d="M29.5 11.5s5 5 4 5"/><path d="M9 3h6.2a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V15"/></svg>
                <svg v-show="selectedMod.save_breaking===true" class=" text-accent-danger size-5" xmlns="http://www.w3.org/2000/svg"viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m14.5 9.5-5 5"/><path d="m9.5 9.5 5 5"/></svg>
                <svg v-show="selectedMod.save_breaking===null" class=" text-text-main size-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M9.1 9a3 3 0 0 1 5.82 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>
                <svg v-show="selectedMod.save_breaking===false" class=" text-accent-success size-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></svg>
              </div>
              <div class="row-span-2 col-span-3 p-2 pr-3 space-y-1 flex flex-col justify-center text-xs text-text-dim bg-text-main/5 rounded-lg border border-text-main/5">
                <div class="flex justify-between items-center">
                  <span class="flex-1 font-bold truncate min-w-0">文件创建时间：</span>
                  {{ selectedMod.file_create_time ? new Date(selectedMod.file_create_time).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '无' }}
                </div>
                <div class="flex justify-between items-center">
                  <span class="flex-1 font-bold truncate min-w-0">文件修改时间：</span>
                  {{ selectedMod.file_modify_time ? new Date(selectedMod.file_modify_time).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '无' }}
                </div>
                <div class="flex justify-between items-center">
                  <span class="flex-1 font-bold truncate min-w-0">最后启用时间：</span>
                  {{ selectedMod.last_active_time ? new Date(selectedMod.last_active_time).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '无' }}
                </div>
                <!-- <div class="flex justify-between items-center">
                  <span class="flex-1 font-bold truncate min-w-0">最后移动时间：</span>
                  {{ selectedMod.last_moved_time ? new Date(selectedMod.last_moved_time).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '无' }}
                </div> -->
                <div class="flex justify-between items-center">
                  <span class="flex-1 font-bold truncate min-w-0">工坊更新时间：</span>
                  {{ selectedMod.mod_update_time ? new Date(selectedMod.mod_update_time).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '无' }}
                </div>
              </div>
            </div>

          </div>

          <!-- 依赖与冲突 -->
          <div v-if="hasDependencies && block.id === 'relations_info'" class="p-1 space-y-3">
            <h3 class="text-xs font-bold text-text-dim uppercase tracking-wider border-b border-text-main/5 pb-1">
              {{ appStore.DETAILS_LAYOUT_MAPS[block.id].label }}
            </h3>
            
            <!-- 依赖 -->
            <div v-if="selectedMod.dependencies_mods?.length" class="space-y-1">
              <div class="mb-1 text-[0.7rem] font-bold uppercase tracking-wider text-accent-highlight">依赖于</div>
              <!-- 依赖项列表 -->
              <!-- 显示前5个或全部（展开状态） -->
              <div v-for="(dep, index) in showAllDependencies ? selectedMod.dependencies_mods : selectedMod.dependencies_mods.slice(0, 5)" 
                :key="dep.package_id" 
                class="flex items-center justify-between gap-2 p-1.5 rounded-sm bg-black/20 border-l-2 transition-colors text-xs border-accent-highlight hover:bg-accent-highlight/10">
                <div class="flex min-w-0 flex-1 items-center gap-1.5">
                  <span v-preview="modStore.takeModById(dep.package_id)" class="min-w-0 flex-1 text-gray-300 truncate">{{ displayNameByMod(dep) }}</span>
                  <span
                    v-if="relationVersionInactive(dep)"
                    v-tooltip="relationVersionTooltip(dep)"
                    class="shrink-0 px-1 py-0.5 rounded bg-text-dim/18 text-text-dim text-[0.65rem] border border-text-dim/18"
                  >
                    未生效
                  </span>
                </div>
                <!-- 操作按钮 -->
                <div class="flex items-center gap-2">
                  <span v-if="!!modStore.takeModById(dep.package_id)?.path" @click="targetItem(dep.package_id)" v-tooltip="'定位Mod位置'" class="hover:text-accent-highlight">
                    <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><circle cx="12" cy="12" r="10"/><line x1="22" x2="18" y1="12" y2="12"/><line x1="6" x2="2" y1="12" y2="12"/><line x1="12" x2="12" y1="6" y2="2"/><line x1="12" x2="12" y1="22" y2="18"/></svg>
                  </span>
                  <span v-if="dep.workshop_url" @click="openUrl(dep.workshop_url)" @click.middle.stop="openSteamUrl(dep.workshop_url)" v-tooltip="'打开工坊页面'" class="hover:text-accent-highlight">
                    <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><path d="M21 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h6"/><path d="m21 3-9 9"/><path d="M15 3h6v6"/></svg>
                  </span>
                </div>

              </div>
              <!-- 展开/收起按钮（只有当数量超过5个时显示） -->
              <button v-if="selectedMod.dependencies_mods.length > 5"
                @click="showAllDependencies = !showAllDependencies"
                class="w-full py-1.5 mt-1 flex items-center justify-center gap-1 rounded bg-text-main/5 hover:bg-text-main/10 text-xs text-gray-400 hover:text-accent-highlight transition-all group"
              >
                {{ showAllDependencies ? '收起' : `查看全部(${selectedMod.dependencies_mods.length})` }}
                <svg :class="{'rotate-180': showAllDependencies}" class="w-3 h-3 transition-transform duration-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
            </div>
            
            <!-- 不兼容 -->
            <div v-if="selectedMod.incompatible_mods?.length" class="space-y-1">
              <div class="mb-1 text-[0.7rem] font-bold uppercase tracking-wider text-accent-danger">冲突于</div>
              <!-- 不兼容项列表 -->
              <div v-for="inc in showAllIncompatible ? selectedMod.incompatible_mods : selectedMod.incompatible_mods.slice(0, 5)" :key="inc.package_id" 
                  class="flex items-center justify-between gap-2 p-1.5 rounded-sm bg-black/20 border-l-2 transition-colors text-xs border-accent-danger hover:bg-accent-danger/10">
                <div class="flex min-w-0 flex-1 items-center gap-1.5">
                  <span v-preview="modStore.takeModById(inc.package_id)" class="min-w-0 flex-1 text-gray-300 truncate">{{ displayNameById(inc.package_id) }}</span>
                  <span
                    v-if="relationVersionInactive(inc)"
                    v-tooltip="relationVersionTooltip(inc)"
                    class="shrink-0 px-1 py-0.5 rounded bg-text-dim/18 text-text-dim text-[0.65rem] border border-text-dim/18"
                  >
                    未生效
                  </span>
                </div>
                <!-- 操作按钮 -->
                <div class="flex items-center gap-2">
                  <span v-if="!!modStore.takeModById(inc.package_id)?.path" @click="targetItem(inc.package_id)" v-tooltip="'定位Mod位置'" class="hover:text-accent-danger">
                    <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><circle cx="12" cy="12" r="10"/><line x1="22" x2="18" y1="12" y2="12"/><line x1="6" x2="2" y1="12" y2="12"/><line x1="12" x2="12" y1="6" y2="2"/><line x1="12" x2="12" y1="22" y2="18"/></svg>
                  </span>
                </div>
              </div>
              <!-- 展开/收起按钮（只有当数量超过5个时显示） -->
              <button v-if="selectedMod.incompatible_mods.length > 5"
                @click="showAllIncompatible = !showAllIncompatible"
                class="w-full py-1.5 mt-1 flex items-center justify-center gap-1 rounded bg-text-main/5 hover:bg-text-main/10 text-xs text-gray-400 hover:text-accent-danger transition-all group"
              >
                {{ showAllIncompatible ? '收起' : `展开全部 (${selectedMod.incompatible_mods.length})` }}
                <svg :class="{'rotate-180': showAllIncompatible}" class="w-3 h-3 transition-transform duration-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
            </div>

            <!-- 前置加载 -->
            <div v-if="selectedMod.load_after_mods?.length" class="space-y-1">
              <div class="mb-1 text-[0.7rem] font-bold uppercase tracking-wider text-accent-warn">前置加载</div>
              <!-- 前置加载项列表 -->
              <div v-for="aft in showAllLoadAfter ? selectedMod.load_after_mods : selectedMod.load_after_mods.slice(0, 5)" :key="aft" 
                class="flex items-center justify-between gap-2 p-1.5 rounded-sm bg-black/20 border-l-2 transition-colors text-xs border-accent-warn hover:bg-accent-warn/10">
                <div class="flex min-w-0 flex-1 items-center gap-1.5">
                  <span v-preview="modStore.takeModById(aft.package_id)" class="min-w-0 flex-1 text-gray-300 truncate">{{ displayNameById(aft.package_id) }}</span>
                  <span
                    v-if="relationVersionInactive(aft)"
                    v-tooltip="relationVersionTooltip(aft)"
                    class="shrink-0 px-1 py-0.5 rounded bg-text-dim/18 text-text-dim text-[0.65rem] border border-text-dim/18"
                  >
                    未生效
                  </span>
                </div>
                <!-- 操作按钮 -->
                <div class="flex items-center gap-2">
                  <span v-if="!!modStore.takeModById(aft.package_id)?.path" @click="targetItem(aft.package_id)" v-tooltip="'定位Mod位置'" class="hover:text-accent-warn">
                    <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><circle cx="12" cy="12" r="10"/><line x1="22" x2="18" y1="12" y2="12"/><line x1="6" x2="2" y1="12" y2="12"/><line x1="12" x2="12" y1="6" y2="2"/><line x1="12" x2="12" y1="22" y2="18"/></svg>
                  </span>
                </div>
              </div>
              <!-- 展开/收起按钮（只有当数量超过5个时显示） -->
              <button v-if="selectedMod.load_after_mods.length > 5"
                @click="showAllLoadAfter = !showAllLoadAfter"
                class="w-full py-1.5 mt-1 flex items-center justify-center gap-1 rounded bg-text-main/5 hover:bg-text-main/10 text-xs text-gray-400 hover:text-accent-warn transition-all group"
              >
                {{ showAllLoadAfter ? '收起' : `展开全部 (${selectedMod.load_after_mods.length})` }}
                <svg :class="{'rotate-180': showAllLoadAfter}" class="w-3 h-3 transition-transform duration-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
            </div>

            <!-- 后置加载 -->
            <div v-if="selectedMod.load_before_mods?.length" class="space-y-1">
              <div class="mb-1 text-[0.7rem] font-bold uppercase tracking-wider text-accent-primary">后置加载</div>
              <!-- 后置加载项列表 -->
              <div v-for="bef in showAllLoadBefore ? selectedMod.load_before_mods : selectedMod.load_before_mods.slice(0, 5)" :key="bef" 
                class="flex items-center justify-between gap-2 p-1.5 rounded-sm bg-black/20 border-l-2 transition-colors text-xs border-accent-primary hover:bg-accent-primary/10">
                <div class="flex min-w-0 flex-1 items-center gap-1.5">
                  <span v-preview="modStore.takeModById(bef.package_id)" class="min-w-0 flex-1 text-gray-300 truncate">{{ displayNameById(bef.package_id) }}</span>
                  <span
                    v-if="relationVersionInactive(bef)"
                    v-tooltip="relationVersionTooltip(bef)"
                    class="shrink-0 px-1 py-0.5 rounded bg-text-dim/18 text-text-dim text-[0.65rem] border border-text-dim/18"
                  >
                    未生效
                  </span>
                </div>
                <!-- 操作按钮 -->
                <div class="flex items-center gap-2">
                  <span v-if="!!modStore.takeModById(bef.package_id)?.path" @click="targetItem(bef.package_id)" v-tooltip="'定位Mod位置'" class="hover:text-accent-primary">
                    <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ><circle cx="12" cy="12" r="10"/><line x1="22" x2="18" y1="12" y2="12"/><line x1="6" x2="2" y1="12" y2="12"/><line x1="12" x2="12" y1="6" y2="2"/><line x1="12" x2="12" y1="22" y2="18"/></svg>
                  </span>
                </div>
              </div>
              <!-- 展开/收起按钮（只有当数量超过5个时显示） -->
              <button v-if="selectedMod.load_before_mods.length > 5"
                @click="showAllLoadBefore = !showAllLoadBefore"
                class="w-full py-1.5 mt-1 flex items-center justify-center gap-1 rounded bg-text-main/5 hover:bg-text-main/10 text-xs text-gray-400 hover:text-accent-primary transition-all group"
              >
                {{ showAllLoadBefore ? '收起' : `展开全部 (${selectedMod.load_before_mods.length})` }}
                <svg :class="{'rotate-180': showAllLoadBefore}" class="w-3 h-3 transition-transform duration-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
            </div>

          </div>

          <!-- 用户自定义属性 (标签 & 颜色 & 备注) -->
          <div v-if="!!selectedMod.path && block.id === 'user_info'" class="rounded-xl p-3 border border-text-main/10 backdrop-blur-sm space-y-3" :style="{'backgroundColor': hexToRgba(selectedMod.sign_color, 0.1)}">
            <h3 class="text-sm font-bold text-text-dim uppercase tracking-wider border-b border-text-main/5 pb-1">
              {{ appStore.DETAILS_LAYOUT_MAPS[block.id].label }}
            </h3>
            <!-- 标签管理 -->
            <div>
              <label v-tooltip="'在此管理Mod标记的自定义标签'" class="text-xs uppercase text-text-dim font-bold tracking-wider mb-1 block">标签*</label>
              <div class="flex flex-wrap gap-1 mb-2">
                <!-- 现有标签列表 -->
                <TransitionGroup name="list">
                  <span v-for="tag in userTags" :key="tag" 
                    class="px-1 py-0.5 rounded truncate text-shadow-lg/20 bg-accent-primary/20 text-accent-primary text-xs border border-accent-primary/20 flex items-center gap-1 group animate-in">
                    {{ tag }}
                    <button @click="removeTag(tag)" v-tooltip="'移除标签'" class="w-3 h-3 flex items-center justify-center rounded-full hover:bg-accent-danger hover:text-text-main transition-colors opacity-50 group-hover:opacity-100">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" class="w-2 h-2"><path d="M18 6L6 18M6 6l12 12"/></svg>
                    </button>
                  </span>
                </TransitionGroup>

                <!-- 添加标签输入框 (带自定义下拉建议) -->
                <div class="relative flex-1 flex" :ref="el => tagInputRef = el">
                  <input type="text" v-model="tagInput" @focus="showTagSuggest = true" placeholder="+" 
                    @keydown.enter.prevent="confirmAddTag" @keydown.up.prevent="navTag(-1)" @keydown.down.prevent="navTag(1)"
                    @keydown.esc="showTagSuggest = false" v-tooltip="'添加新标签'"
                    class="px-1 py-0.5 w-5 text-center rounded bg-black/20 border border-text-main/10 text-xs text-text-main placeholder-text-dim/50 focus:flex-1 focus:bg-black/40 focus:border-accent-primary focus:outline-none focus:w-24 transition-all"
                  />
                  <FixedPopover :is-open="showTagSuggest && filteredKnownTags.length > 0" :trigger-ref="tagInputRef">
                      <!-- 标签建议下拉框 -->
                      <div class="max-h-40 overflow-y-auto bg-bg-surface border border-text-main/10 rounded-lg shadow-xl z-50 flex flex-col gap-0.5 p-1 items-center">
                        <button v-for="(t, idx) in filteredKnownTags" :key="t"  @click="addTag(t)"
                          class="text-left px-2 min-w-20 text-xs items-center rounded hover:bg-accent-primary/20 hover:text-accent-primary transition-colors truncate"
                          :class="{'bg-accent-primary/10 text-accent-primary': idx === tagNavIndex}">
                          {{ t }}
                        </button>
                      </div>
                  </FixedPopover>
                </div>

              </div>
            </div>

            <!-- 分组 -->
            <div>
              <label v-tooltip="'在此管理Mod的所属分组'" class="text-xs uppercase text-text-dim font-bold tracking-wider mb-1 block">分组*</label>
              <div class="flex flex-wrap gap-1 mb-2">
                <!-- 现有分组列表 -->
                <TransitionGroup name="list">
                  <span v-for="group in userGroups" :key="group.group_id" 
                    class="px-1 py-0.5 rounded truncate text-xs text-shadow-lg/20 border border-text-main/5 flex items-center gap-1 group hover:border-text-main/20 transition-colors"
                    :style="{'backgroundColor': hexToRgba(group.color, 0.15), 'color': group.color}">
                    {{ group.name }}
                    <button @click="removeModInGroup(group.group_id, selectedMod.package_id)" v-tooltip="'从分组移出'"
                      class="w-3 h-3 flex items-center justify-center rounded-full hover:bg-accent-danger hover:text-text-main transition-colors opacity-50 group-hover:opacity-100">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" class="w-2 h-2"><path d="M18 6L6 18M6 6l12 12"/></svg>
                    </button>
                  </span>
                </TransitionGroup>

                
                <!-- 添加分组按钮 (Dropdown) -->
                <div class="relative" :ref="el => groupDropRef = el" v-tooltip="'添加新分组'">
                  <button @click="toggleGroupDrop" class="px-1 py-1 rounded bg-black/20 border border-text-main/10 text-xs text-text-dim hover:text-text-main hover:border-text-main/30 hover:bg-black/40 transition-all flex items-center gap-1">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="w-3 h-3"><path d="M12 5v14M5 12h14"/></svg>
                  </button>
                  <FixedPopover :is-open="showGroupDrop" :trigger-ref="groupDropRef">
                      <!-- 分组选择下拉框 -->
                      <div class="w-40 max-h-48 overflow-y-auto bg-bg-surface border border-text-main/10 rounded-lg shadow-xl z-50 flex flex-col p-1">
                        <!-- 搜索过滤 -->
                        <input v-model="groupSearch" :ref="el => groupSearchRef = el" placeholder="搜索分组..." 
                          class="mb-1 px-2 py-1 text-xs bg-black/20 rounded border border-text-main/5 focus:outline-none focus:border-accent-primary" />
                        <div v-if="availableGroups.length === 0" class="px-2 py-1 text-xs text-text-dim/50 text-center">无可用分组</div>
                        <button v-for="g in availableGroups" :key="g.group_id" @click="addGroup(g.group_id)"
                          class="text-left px-2 py-1 text-xs rounded hover:bg-text-main/10 transition-colors truncate flex items-center gap-2">
                          <span class="w-2 h-2 rounded-full shrink-0" :style="{backgroundColor: g.color}"></span>
                          {{ g.name }}
                        </button>
                      </div>
                  </FixedPopover>
                </div>
              </div>
            </div>

            <!-- 颜色选择 (简单版) -->
            <div class="flex items-center">
              <label v-tooltip="'可自定义颜色标识'" class="flex-none text-xs uppercase text-text-dim font-bold tracking-wider">颜色标记*</label>
              <div class="flex-1 flex ml-2 min-w-20 gap-1.5 items-center justify-end">
                <button v-for="(name, c) in presetColors" :key="c" @click="updateColor(c)"
                  :class="['w-4 h-4 min-w-1 rounded-full border border-text-main/10 transition-transform hover:scale-125', 
                          selectedMod.sign_color === c ? 'ring-2 ring-text-main scale-110' : '']"
                  :style="{backgroundColor: c}" v-tooltip="'点击将'+MOD_SIGN_COLOR_MAP[c]+'颜色设为标记颜色'">
                </button>
                <div class="flex items-center" v-tooltip="'自定义其它颜色'">
                  <ColorPicker v-model:pureColor="customSignColor" @pureColorChange="handleCustomColorChange" shape="circle" format="hex" picker-type="fk" disable-alpha round-history />
                </div>
                <button @click="updateColor(null)" v-tooltip="'清除颜色标记'" 
                  class="text-gray-500 hover:text-text-main">
                  <CircleX class="size-4.5" />
                </button>
              </div>
            </div>

            <!-- 别名 -->
            <div class="mb-2 flex flex-row items-center justify-around">
              <input v-model="userAliasName" @blur="saveUserData" placeholder="在此添加自定义别名"
                  class="flex-1 w-full bg-black/20 border border-text-main/10 rounded p-2 text-sm text-text-main focus:border-accent-primary focus:outline-none"/>
              <!-- 翻译按钮 -->
              <button @click="translateModInfo" v-tooltip="'通过AI生成Mod别名及备注，需要配置AI'" :disabled="isUsingAI"
                class="min-w-8 h-6 px-1.5 ml-1 flex items-center justify-center text-sm rounded-sm bg-text-dim/50 hover:bg-accent-primary hover:text-text-main transition-colors active:bg-accent-cool">
                <span v-if="!isUsingAI">AI生成</span>
                <svg v-else class="animate-spin size-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
              </button>
            </div>

            <!-- 备注 -->
            <div>
                <textarea v-model="userNotes" @blur="saveUserData" placeholder="在此添加自定义备注" :class="[expandTextarea?'min-h-100':'']"
                  class="w-full bg-black/20 border border-text-main/10 rounded p-2 text-sm text-gray-300 
                  focus:border-accent-primary focus:outline-none min-h-20 resize-none custom-scrollbar">
                </textarea>
                <button @click="expandTextarea=!expandTextarea" v-tooltip="'展开/收起'" class="w-full -mb-2 flex justify-center items-center cursor-pointer rounded-md hover:bg-text-main/10 transition-colors">
                  <ChevronUp v-if="expandTextarea" class="size-5"/>
                  <ChevronDown v-else class="size-5"/>
                </button>
            </div>
            
          </div>

          <!-- 描述 (HTML) -->
          <div v-if="block.id === 'description'" class="p-1 space-y-2">
            <h3 class="text-xs font-bold text-text-dim uppercase tracking-wider border-b border-text-main/5 pb-1">描述</h3>
            <div class="prose prose-invert prose-sm max-w-none text-gray-300 leading-relaxed wrap-break-word" v-html="formattedDescription"></div>
          </div>

        </template>
      </template>

      <!-- 底部占位提示 -->
      <div class="text-xs text-text-dim opacity-50">
        * 由于格式和规范性方面的限制，部分模组信息可能无法完全获取。
      </div>

    </div>
  </div>

  <!-- 无选中Mod时 -->
  <div v-else class="flex flex-col h-full text-text-dim">
    
    
    <LampEffect>
      <template #top>
        <div class="flex flex-col items-center justify-end p-3 h-30">
          <div class="text-4xl opacity-80 mb-2">❖</div>
          <div class="text-xs uppercase tracking-widest">Select a Mod</div>
        </div>
      </template>
      <template #bottom>
        <div class="relative">
          
          <div v-if="appStore.settings.ui.show_icons_cloud" class="z-999">
            <ImageCloud :images="imageUrls" :size="300" :imageSize="50"/>
          </div>
          <LuxBreatheIcon>
            <svg class="size-60" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" fill="currentColor" stroke="currentColor"><path d="M158.25 87.297 61 143.499V368.5l97.5 56.291 97.5 56.29 97.5-56.29L451 368.5V143.499l-97.441-56.25c-53.592-30.937-97.579-56.228-97.75-56.202-.17.026-44.071 25.338-97.559 56.25m6 10.969L74 150.432v211.136l90.451 52.216C214.199 442.503 255.403 466 256.015 466c.613 0 41.81-23.499 91.549-52.219L438 361.562v-211.13l-90.451-52.216c-49.748-28.719-91.036-52.194-91.75-52.166-.714.027-41.911 23.524-91.549 52.216m4.509 7.073L82.017 155.5V256l.001 100.5 86.991 50.198L256 456.897l86.991-50.199 86.991-50.198.001-100.5.001-100.5-86.61-50c-47.636-27.5-86.895-50.072-87.243-50.161-.347-.088-39.665 22.412-87.372 50m2.241 4.029-83.5 48.309v195.647l83 48.015c45.65 26.408 83.9 48.014 85 48.014 1.1 0 39.35-21.609 85-48.02l83-48.021V157.688l-83-47.967c-45.65-26.382-83.675-48.124-84.5-48.314-.825-.191-39.075 21.392-85 47.961m93-2.278c0 10.951.337 19.908.75 19.906 3.934-.019 7.25-4.177 7.25-9.088 0-4.464.225-5.037 1.75-4.458 2.589.981 38.535 21.656 40.046 23.033 1.024.933-2.488 3.354-16.75 11.546L279 158.394v37.681c0 28.941.29 37.913 1.25 38.685 1.063.855 32.313 18.972 93.25 54.061l14 8.062v35.319l-13.5 7.81c-7.425 4.296-31.371 18.141-53.213 30.768l-39.713 22.957-.287-8.568-.287-8.569-8.25-4.751-8.25-4.751v28.451c0 15.648.285 28.451.633 28.451.349 0 32.299-18.287 71-40.637L406 342.726v-56.311l-10.25-5.348c-5.637-2.942-18.8-10.306-29.25-16.365-36.006-20.877-43.042-24.941-56.265-32.493l-13.265-7.575.265-28.46.265-28.46 17.741-10.272 17.74-10.272 14.26 8.294c7.842 4.561 20.109 11.681 27.259 15.821l13 7.527.264 32.594c.145 17.927-.08 32.583-.5 32.571-.42-.013-2.874-1.251-5.454-2.75-2.579-1.5-9.329-5.419-15-8.709-5.67-3.29-16.385-9.651-23.81-14.135l-13.5-8.153-.294-5.974c-.258-5.233-.599-6.114-2.75-7.094L324 196.043v23.508l10.25 6.091c9.626 5.72 58.182 33.868 67.5 39.129l4.25 2.4v-97.776l-71-41.107-71-41.108v19.91m-84.724 19.189c-36.424 21.022-66.224 38.446-66.222 38.721.001.275 3.855 2.691 8.564 5.37 7.167 4.076 8.913 4.698 10.722 3.817 1.188-.579 20.385-11.605 42.66-24.501l40.5-23.447.26 48.585c.203 38.046-.014 48.841-1 49.766-.693.649-21.285 12.712-45.76 26.805l-44.5 25.626-.5-42.691-.5-42.691-4.5-2.611-9.25-5.361-4.75-2.751v142.866l9.491-5.641 9.49-5.641.01-7.654.009-7.654 27.75-15.985a29704.77 29704.77 0 0 0 46.03-26.571l18.279-10.586-.279 12.584-.28 12.584-54.75 31.609L106 332.436v4.768c0 4.459.26 4.94 4.025 7.431 4.948 3.274-1.888 6.569 56.975-27.459l48.5-28.038.268 23.931c.147 13.162.147 34.678 0 47.812l-.268 23.882-36-20.836c-19.8-11.46-36.592-20.857-37.315-20.882-1.39-.048-18.427 10.046-17.88 10.593.176.176 27.854 16.265 61.507 35.753L247 424.825V403.08l-6.481-3.79-6.481-3.79-.018-81-.017-81 6.497-3.5 6.497-3.5.002-10.239.001-10.239-6.5 3.978-6.5 3.978.019-49.239.019-49.239 6.481-3.79 6.481-3.79v-9.96c0-5.478-.338-9.947-.75-9.931-.412.016-30.551 17.228-66.974 38.25m28.962 57.574c-.741.458-1.27 4.661-1.452 11.527l-.286 10.807-2.658-2.094c-4.096-3.226-5.534-2.627-8.778 3.657l-2.968 5.75-.048-9.823c-.043-8.803-.23-9.789-1.798-9.488-1.561.3-1.78 1.99-2.027 15.666-.326 18.073.069 18.437 6.862 6.35l4.585-8.158 4.23 3.111c2.364 1.739 4.587 2.721 5.038 2.227 1.071-1.176 2.24-29.157 1.243-29.773-.427-.264-1.301-.156-1.943.241M360 187.251c0 7.982 2.087 11.764 8.191 14.845 3.306 1.669 6.156 2.891 6.332 2.714.291-.291-11.409-15.996-13.602-18.26-.573-.591-.921-.326-.921.701m-184.449 15.721c-8.69 4.847-8.518 4.48-8.536 18.123-.02 15.703.912 16.722 10.428 11.4 8.309-4.647 8.594-5.239 8.497-17.698-.132-16.896-.515-17.333-10.389-11.825m.199 5.248-3.75 2.173v19.735l4.125-2.314c4.928-2.764 4.689-2.15 5.07-13.064.336-9.641.201-9.803-5.445-6.53m-21.577 6.954L147 219.153v14.923c0 8.208.36 14.924.8 14.924 1.904 0 3.2-2.706 3.2-6.681 0-5.459 3.118-6.77 7.826-3.29 1.641 1.214 3.477 1.902 4.079 1.53 1.631-1.009 1.323-4.672-.506-6.009-1.449-1.06-1.403-1.495.497-4.61 3.015-4.947 2.803-17.074-.321-18.273-.676-.259-4.456 1.319-8.402 3.507m15.327 26.813c-23.65 13.705-43.417 25.078-43.927 25.274-.51.196-.61.87-.222 1.498.708 1.146 6.489-1.587 9.47-4.478.727-.705 1.763-1.281 2.303-1.281 1.006 0 21.974-11.828 22.876-12.903.275-.329 3.537-2.172 7.249-4.097 3.711-1.925 6.749-3.838 6.75-4.25 0-.412.607-.75 1.348-.75.741 0 2.385-.9 3.653-2 1.268-1.1 2.88-2 3.582-2 .701 0 1.87-.582 2.597-1.292.726-.711 2.784-1.891 4.571-2.622 1.787-.731 3.25-1.724 3.25-2.207 0-.484.675-.879 1.5-.879s1.5-.477 1.5-1.059.414-.803.919-.491c.506.313 1.599-.111 2.429-.941.83-.83 1.991-1.509 2.581-1.509.589 0 1.071-.477 1.071-1.059s.399-.812.887-.511c.487.301 1.442-.122 2.122-.941.68-.819 1.787-1.489 2.46-1.489 1.319 0 5.531-3.326 5.531-4.367 0-1.343-2.744.158-44.5 24.354m-14.75-21.767c-3.592 2.082-3.75 2.397-3.75 7.502v5.329l2.75-1.449c4.929-2.598 5.999-4.031 6.61-8.852.697-5.505.037-5.803-5.61-2.53M135 226.035c-8.374 4.981-8.899 6.309-8.955 22.666L126 261.902l8.25-4.749c5.873-3.381 8.342-5.383 8.57-6.951.428-2.955-1.066-2.78-7.448.871L130 254.147v-19.829l5-2.721 5-2.722v3.063c0 3.468 1.423 4.009 2.965 1.128 1.501-2.805 1.339-11.086-.215-10.982-.687.046-4.175 1.824-7.75 3.951m259.577 5.61c1.287 7.016 2.377 8.254 2.142 2.434-.139-3.432-.702-5.581-1.534-5.855-1.012-.334-1.152.455-.608 3.421M264 270.095v18.096l5.75-3.244c3.163-1.784 6.443-3.677 7.29-4.205 1.397-.871 59.954 31.623 59.933 33.258-.004.275-4.612 3.118-10.24 6.318-5.628 3.2-16.533 9.501-24.233 14.003l-14 8.186-.286 10.35-.286 10.351 3.286-2.022c1.807-1.113 8.911-5.268 15.786-9.234a32131.36 32131.36 0 0 0 29-16.762c9.075-5.252 19.681-11.299 23.569-13.438 3.888-2.139 8.285-4.87 9.772-6.07l2.702-2.182-17.772-10.095c-9.774-5.553-24.296-13.912-32.271-18.577C291.961 267.259 265.313 252 264.668 252c-.367 0-.668 8.143-.668 18.095" fill-rule="evenodd"/></svg>
          </LuxBreatheIcon>
          
        </div>
      </template>
    </LampEffect>
    
  </div>

</template>

<script setup >
import { computed, ref, watch, nextTick } from 'vue'
import { refDebounced, onClickOutside, useDebounceFn } from '@vueuse/core' // 引入防抖函数
import { MOD_SIGN_COLOR_MAP, MOD_TYPE_MAP, SOURCE_TYPE_MAP, MOD_TYPE_ICON_MAP } from '../utils/constants'
import { useModStore } from '../stores/modStore'
import { useAppStore } from '../stores/appStore'
import { useGroupStore } from '../stores/groupStore'
import { parseUnityRichText } from '../utils/text'
import { DEFAULT_ACCENT_HEX, hexToRgba, hexToRgb, normalizeHexColor } from '../utils/color'
import { formatFileSize } from '../utils/format'
import ImageCloud from './utils/ImageCloud.vue';
import LampEffect from './utils/LampEffect.vue';
import LuxBreatheIcon from './utils/LuxBreatheIcon.vue'
import { ChevronDown, ChevronUp, CircleX, Copy } from 'lucide-vue-next'
import FixedPopover from './common/FixedPopover.vue'
import { useProfileStore } from '../stores/profileStore'
import { ColorPicker } from 'vue3-colorpicker'

// 随机选30个Mod的图标URL
const imageUrls = computed(() => Array.from(modStore.allModsMap.values())
  .filter(mod => mod.icon_url) // 过滤掉没有图标URL的Mod
  .sort(() => 0.5 - Math.random()) // 随机排序
  .slice(0, 30) // 取前30个
  .map(mod => mod.icon_url))

// 子组件: 简单统计块
const StatItem = {
  props: ['label', 'value', 'highlight'],
  template: `
    <!-- 外层改为 flex-row 横向排列，加 gap 控制图标与内容间距 -->
    <div class="bg-text-main/5 rounded-lg p-1 flex items-center border border-text-main/5 gap-0">
      <!-- 图标插槽：flex-shrink-0 防止图标被压缩，可选插槽（无图标时不占空间） -->
      <slot />
      
      <!-- 内容容器：保持垂直布局，居中对齐 -->
      <div class="flex flex-col items-center flex-1 min-w-10">
        <span class="text-lg font-bold leading-none" :class="highlight && value > 0 ? 'text-accent-primary' : 'text-gray-400'">{{ value }}</span>
        <span class="text-[0.7rem] text-text-dim uppercase scale-90">{{ label }}</span>
      </div>
    </div>
  `
}
const appStore = useAppStore()
const modStore = useModStore()
const groupStore = useGroupStore()
const profileStore = useProfileStore()
const userTags = ref([])
const userAliasName = ref('')
const userNotes = ref('')
const newTagInput = ref('')
const customSignColor = ref(DEFAULT_ACCENT_HEX)
const presetColors = MOD_SIGN_COLOR_MAP
const isUsingAI = ref(false)

// === 标签管理逻辑 ===
const tagInput = ref('')
const showTagSuggest = ref(false)
const tagInputRef = ref(null)
const tagNavIndex = ref(0) // 键盘导航索引
// === 分组管理逻辑 ===
const showGroupDrop = ref(false)
const groupDropRef = ref(null)
const groupSearch = ref('')
const groupSearchRef = ref(null)

const showAllDependencies = ref(false);
const showAllIncompatible = ref(false);
const showAllLoadBefore = ref(false);
const showAllLoadAfter = ref(false);
const expandTextarea = ref(false)

// 1. 获取原始数据
const rawSelectedMod = computed(() => modStore.lastSelectedMod)

// 2. 创建一个防抖的引用
// 含义：当 rawSelectedMod 变化时，debouncedMod 会等待 200ms 且无新变化后才更新
const selectedMod = refDebounced(rawSelectedMod, appStore.settings.ui.detail_delay) 
const modType = computed(() => modStore.displayModType(selectedMod.value))


// 获取布局配置 (如果没有配置则使用默认兜底)
const layoutConfig = computed(() => {
  return appStore.settings.ui.mod_details_layout || appStore.DEFAULT_DETAILS_LAYOUT
})

// 监听选中变化，同步本地编辑状态
watch(selectedMod, (newVal) => {
  if (newVal) {
    userTags.value = [...(newVal.tags || [])]
    userAliasName.value = newVal.alias_name || ''
    userNotes.value = newVal.notes || ''
    // 颜色选择器必须始终持有合法十六进制颜色，空标记时退回到中性色。
    customSignColor.value = normalizeHexColor(newVal.sign_color, DEFAULT_ACCENT_HEX)
    newTagInput.value = ''
  }
}, { immediate: true })

// 计算可用分组 (排除已加入的)
const availableGroups = computed(() => {
  const search = groupSearch.value.toLowerCase().trim()
  const currentGroupIds = new Set(userGroups.value.map(g => g.group_id))
  
  return groupStore.groupList
    .filter(g => !currentGroupIds.has(g.group_id)) // 排除已加入
    .filter(g => g.name.toLowerCase().includes(search)) // 搜索过滤
})
// 计算过滤后的建议标签 (排除已存在的)
const filteredKnownTags = computed(() => {
  const input = tagInput.value.toLowerCase().trim()
  return modStore.allModTags
    .filter(t => !userTags.value.includes(t)) // 排除已添加
    .filter(t => t.toLowerCase().includes(input)) // 模糊匹配
    .slice(0, 8) // 最多显示8个
})
// 辅助计算：格式化描述（换行转为 <br>）
const formattedDescription = computed(() => {
  if (!selectedMod.value?.description) return '该Mod未提供描述。'
  // console.log(parseUnityRichText(selectedMod.value.description, false))
  // 第二个参数 false 表示不移除图片，如果想移除则传 true
  return parseUnityRichText(selectedMod.value.description, false)
})
// 辅助计算：是否有依赖项或冲突项
const hasDependencies = computed(() => {
  return (selectedMod.value?.dependencies_mods?.length > 0) || (selectedMod.value?.incompatible_mods?.length > 0) || (selectedMod.value?.load_before_mods?.length > 0) || (selectedMod.value?.load_after_mods?.length > 0)
})
// 根据 mod 名字长度动态调整字体大小
const computedFontSize = computed(() => {
  if (!selectedMod.value) return '1.25vw';
  const text = selectedMod.value.name;
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
const computedFontSize0 = computed(() => {
  const text = displayMod.value?.name;
  
  // 默认大小 (比如容器宽度的 10%)
  if (!text) return 'clamp(2px, 5cqi, 16px)'; 
  
  const len = text.length;
  let cqiRate = 5; // 默认基准：短名字占宽度的 10%
  if (len > 80) cqiRate = 2;       // 超长：只占 4%
  else if (len > 60) cqiRate = 3;
  else if (len > 40) cqiRate = 4;
  else if (len > 20) cqiRate = 5;  // 中等：占 8%
  else cqiRate = 6;               // 短：占 10%
  return `clamp(2px, ${cqiRate}cqi, 16px)`;
})

const displaySourceType = computed(() => { 
  return SOURCE_TYPE_MAP[selectedMod.value.source] || selectedMod.value.source
})


// 显示版本信息（最多显示5个版本）
const displayVersions = computed(() => {
  // 获取版本数组，如果不存在则返回空数组
  const versions = selectedMod.value?.supported_versions || [];
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
const tooltipSaveBreaking = computed((index) => {
  if (selectedMod.value.save_breaking === true) return '危险：注意！中途启用或停用该Mod会破坏存档！'
  if (selectedMod.value.save_breaking === false) return '安全：该Mod不会破坏存档，可放心加入或移除。'
  return '未知：暂时无法知道该Mod是否会破坏存档。'
})
const tooltipModType = computed(() => {
  return '模组类型：'+MOD_TYPE_MAP[selectedMod.value.mod_type]+'\n__(粗略判断)__'
})

const displayNameByMod = (mod) => {
  return modStore.displayModName(mod);
}
const displayNameById = (id) => {
  return modStore.displayModName(id);
}

const getCurrentGameShortVersion = () => (
  String(profileStore.activeContext?.game_version || '').match(/^\d+\.\d+/)?.[0] || ''
)

const normalizeRelationVersions = (relation) => (
  Array.isArray(relation?.version_requirement)
    ? relation.version_requirement.map(version => String(version || '').trim()).filter(Boolean)
    : []
)

const relationVersionInactive = (relation) => {
  const versions = normalizeRelationVersions(relation)
  if (versions.length === 0 || versions.includes('all')) return false
  const currentVersion = getCurrentGameShortVersion()
  if (!currentVersion) return false
  return !versions.includes(currentVersion)
}

const relationVersionTooltip = (relation) => {
  const versions = normalizeRelationVersions(relation)
  if (versions.length === 0 || versions.includes('all')) return '该关系当前生效'
  const currentVersion = getCurrentGameShortVersion()
  const versionText = versions.join(', ')
  if (!currentVersion) return `仅在 ${versionText} 生效`
  return `当前版本 ${currentVersion} 不生效\n仅在 ${versionText} 生效`
}

// 检查版本是否兼容
const versionIsCompatible = (version) => {
  // 截取版本号（只保留主版本号，如 1.2.3 截取为 1.2）
  const game_version = profileStore.activeContext.game_version.match(/^\d+\.\d+/)?.[0] || ''
  // 转为浮点数比较版本号，返回 true 表示兼容，false 表示不兼容
  return parseFloat(version) >= parseFloat(game_version)
}
const userGroups = computed(() => {return groupStore.takeGroupsByModId(selectedMod.value?.package_id);})
const toggleGroupDrop = async () => {
  showGroupDrop.value = !showGroupDrop.value
  if (showGroupDrop.value) {
    groupSearch.value = ''
    await nextTick()
    groupSearchRef.value?.focus() // 自动聚焦搜索框
  }
}

const addGroup = (groupId) => {
  if (selectedMod.value) {
    groupStore.groupAddMods(groupId, [selectedMod.value.package_id])
  }
  showGroupDrop.value = false
}

// 点击外部关闭分组下拉
onClickOutside(groupDropRef, () => {
  showGroupDrop.value = false
})
// 从分组中移除模组
const removeModInGroup =(groupId, modId) => {
  groupStore.groupRemoveMods(groupId, [modId]);
}
// 添加标签
const addTag = (tag) => {
  if (tag && !userTags.value.includes(tag)) {
    userTags.value.push(tag)
    saveUserData()
  }
  tagInput.value = ''
  showTagSuggest.value = false
  tagNavIndex.value = 0
}
// 移除标签
const removeTag = (tag) => {
  userTags.value = userTags.value.filter(t => t !== tag)
  saveUserData()
}
// 确认添加 (回车键)
const confirmAddTag = () => {
  // 如果有建议项被选中，优先使用建议项
  if (showTagSuggest.value && filteredKnownTags.value.length > 0) {
    addTag(filteredKnownTags.value[tagNavIndex.value])
  } else if (tagInput.value.trim()) {
    // 否则创建新标签
    addTag(tagInput.value.trim())
  }
}
// 键盘导航
const navTag = (step) => {
  if (!showTagSuggest.value) return
  const len = filteredKnownTags.value.length
  if (len === 0) return
  tagNavIndex.value = (tagNavIndex.value + step + len) % len
}
// 点击外部关闭标签建议
onClickOutside(tagInputRef, () => {
  showTagSuggest.value = false
})


const persistSignColor = useDebounceFn((packageId, color) => {
  // 自定义取色拖动时会连续触发事件，这里做轻量防抖，避免频繁写后端。
  modStore.updateModUserData(packageId, { sign_color: color })
}, 120)

// 更新颜色
const updateColor = (color) => {
  if (!selectedMod.value) return
  if (typeof color === 'string' && color) {
    const normalizedColor = normalizeHexColor(color, DEFAULT_ACCENT_HEX)
    customSignColor.value = normalizedColor
    modStore.updateModUserData(selectedMod.value.package_id, { sign_color: normalizedColor })
    return
  }
  modStore.updateModUserData(selectedMod.value.package_id, { sign_color: null })
}

const handleCustomColorChange = (color) => {
  if (!selectedMod.value) return
  const normalizedColor = normalizeHexColor(color, DEFAULT_ACCENT_HEX)
  customSignColor.value = normalizedColor
  persistSignColor(selectedMod.value.package_id, normalizedColor)
}
// 保存用户数据（标签和备注）
const saveUserData = () => {
  if (selectedMod.value) {
    modStore.updateModUserData(selectedMod.value.package_id, {
      tags: userTags.value,
      alias_name: userAliasName.value,
      notes: userNotes.value
    })
  }
}
// 打开Mod路径
const openPath = (path) => {
  // console.log('openPath',path)
  if(typeof path === 'string' && path) appStore.openPath(path)
  else appStore.openPath(selectedMod.value.path)
}
// 打开Url
const openUrl = (url) => {
  appStore.openUrl(url)
}
// 打开SteamUrl
const openSteamUrl = (url) => {
  appStore.openSteamWorkshopUrl(url)
}

// 定位Mod位置
const targetItem = (mod_id) => {
  modStore.currentTargetId = mod_id
}

// 翻译Mod信息
const translateModInfo = async () => {
  if (!selectedMod.value) return
  isUsingAI.value = true
  const res = await appStore.useAI('alias_generation',{
    name: selectedMod.value.name,
    description: selectedMod.value.description,
  })
  if (res) {
    userAliasName.value = res.alias_name
    userNotes.value = res.notes
    saveUserData()
  }
  isUsingAI.value = false
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
.loader {
  --size: 250px;
  --duration: 5s;
  --logo-color: grey;
  --background: linear-gradient(
    0deg,
    rgba(21, 30, 49, 0.2) 0%,
    rgba(35, 51, 85, 0.2) 100%
  );
  height: var(--size);
  aspect-ratio: 1;
  position: relative;
}

.loader .box {
  position: absolute;
  background: rgba(67, 101, 152, 0.15);
  background: var(--background);
  border-radius: 50%;
  border-top: 1px solid rgba(100, 100, 100, 1);
  box-shadow: rgba(0, 0, 0, 0.3) 0px 10px 10px -0px;
  backdrop-filter: blur(5px);
  animation: ripple var(--duration) infinite ease-in-out;
}

.loader .box:nth-child(1) {
  inset: 40%;
  z-index: 99;
}

.loader .box:nth-child(2) {
  inset: 30%;
  z-index: 98;
  border-color: rgba(100, 100, 100, 0.8);
  animation-delay: 0.5s;
}

.loader .box:nth-child(3) {
  inset: 20%;
  z-index: 97;
  border-color: rgba(100, 100, 100, 0.6);
  animation-delay: 1s;
}

.loader .box:nth-child(4) {
  inset: 10%;
  z-index: 96;
  border-color: rgba(100, 100, 100, 0.4);
  animation-delay: 1.5s;
}

.loader .box:nth-child(5) {
  inset: 0%;
  z-index: 95;
  border-color: rgba(100, 100, 100, 0.2);
  animation-delay: 2s;
}

.loader .logo {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  padding: 30%;
}

.loader .logo svg {
  fill: var(--logo-color);
  width: 100%;
  animation: color-change var(--duration) infinite ease-in-out;
}

@keyframes ripple {
  0% {
    transform: scale(1);
    box-shadow: rgba(0, 0, 0, 0.3) 0px 10px 10px -0px;
  }
  50% {
    transform: scale(1.3);
    box-shadow: rgba(0, 0, 0, 0.3) 0px 20px 20px -0px;
  }
  100% {
    transform: scale(1);
    box-shadow: rgba(0, 0, 0, 0.3) 0px 10px 10px -0px;
  }
}

@keyframes color-change {
  0% {
    fill: var(--logo-color);
  }
  50% {
    fill: white;
  }
  100% {
    fill: var(--logo-color);
  }
}

/* 列表项动画 */
.list-enter-active,
.list-leave-active {
  transition: all 0.3s ease;
}
.list-enter-from,
.list-leave-to {
  opacity: 0;
  transform: scale(0.9);
  width: 0;
  margin: 0;
  padding: 0;
}


/* 取色器样式优化 */
:deep(.vc-color-wrap.round) {
  width: 1rem !important;
  height: 1rem !important;
  border: 2px solid #ffffff !important;
  margin: 0 !important;
  padding: 0 !important;
  transition: all 0.15s ease;
}

:deep(.vc-color-wrap.round:hover) {
  transform: scale(1.3);
  z-index: 10;
}

:deep(.vc-color-wrap.transparent) {
  background-image: none !important;
}
</style>
