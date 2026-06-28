<!-- ModItem.vue -->
<template>
  <div class="py-[2px] flex items-center gap-1 select-none relative" :data-id="item_id"
    @contextmenu="handleContextMenu" @dblclick="handleDoubleClick" @click.left="handleClick">
    <!-- 序号（通过位数计算动态调整字体大小） -->
    <!-- :style="{ fontSize: 18-(index+1).toString().length*3 + 'px' }" -->
    <div v-if="showIndex" class="swipe-trigger w-6 h-6 p-3 flex items-center justify-center rounded"
      :class="[ props.isSelected ? `text-text-main bg-accent-${listColor}/50` : `text-accent-${listColor}/50 bg-accent-${listColor}/10 hover:text-text-main hover:bg-accent-${listColor}/50`, `digits-${(index+1).toString().length}`, isInSearch ? ' ring-2 ring-accent-highlight' : '']"
      :style="{ width: appStore.scalePx(25) + 'px', height: appStore.scalePx(25) + 'px'}">
      {{ index+1 }}
    </div>
    
    <!-- 内容区域 -->
      <!-- :class="[searchMatch ? 'ring-2 ring-accent-highlight scale-[1.02] z-20' : '', getCardClass, simple ? 'h-[30px]' : 'h-[50px]']"  -->
    <div class="select-trigger drag-handle flex-1 flex items-center min-w-0 gap-1.5 p-1 rounded-lg border hover:opacity-90 backdrop-blur-sm group shadow-sm text-text-main/80"
      :class="[searchMatch ? 'ring-2 ring-accent-highlight scale-[1.02] z-20' : '', getCardClass]" 
      :style="getCardStyle(item_id)"
      v-preview="modData">
      <div v-if="showIcon">
        <!-- 图标 -->
        <div v-if="simple" class="flex items-center gap-1">

          <div v-if="showModIcon">
            <img v-if="!!modData.path && modData.thumb_url" :src="modData.thumb_url"
              :class="`size-6 rounded object-cover border border-accent-${listColor}/30 pointer-events-none`">
            <div v-else-if="!modData.path" :class="`size-6 rounded flex items-center justify-center text-red-500 font-bold text-lg bg-red-900/50 border border-red-500/30`">!</div>
            <div v-else :class="`size-6 rounded border-2 border-dashed border-text-main/10 flex items-center justify-center`">
              <svg :class="`size-5 opacity-20`" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
            </div>
          </div>

          <!-- 图标 -->
          <div v-if="showTypeIcon" class="flex items-center justify-center -mr-1">
            <!-- 类型图标 -->
            <span class="flex items-center justify-center hover:scale-120 transition-transform duration-200" tabindex="0" v-tooltip="`类型：${MOD_TYPE_MAP[modType] || modType || '未知'}`">
              <component :is="MOD_TYPE_ICON_MAP[modType] || MOD_TYPE_ICON_MAP.Unknown" class="w-4 h-4" />
            </span>
            <!-- 来源图标 -->
            <span  class="flex items-center justify-center hover:scale-120 transition-transform duration-200" tabindex="0" v-tooltip="`来源：${SOURCE_TYPE_MAP[modData.source] || modData.source || '未知'}`">
              <svg v-if="modData.source==='workshop'" class="fill-current -m-0.5 size-4.5" viewBox="0 0 640 640" xmlns="http://www.w3.org/2000/svg"><path d="M261.6 373.1C280.2 380.8 288.9 402 281.2 420.5C273.5 439 252.2 447.7 233.6 439.9L205.1 428.1C210.1 438.7 218.9 447.5 230.5 452.3C255.7 462.8 284.6 450.9 295.1 425.8C300.2 413.7 300.2 400.3 295.2 388.1C290.1 376 280.7 366.5 268.5 361.4C256.4 356.4 243.5 356.6 232.1 360.9L261.6 373.1zM544 160C544 124.7 515.3 96 480 96L160 96C124.7 96 96 124.7 96 160L96 304.7L212.6 352.8C224.6 344.6 238.8 340.7 253.3 341.5L308.7 261.3L308.7 260.2C308.7 212 348 172.7 396.3 172.7C444.6 172.7 483.9 212 483.9 260.2C483.9 309.4 443 348.9 394.3 347.7L315.3 404C316.9 442.5 286.2 472.8 249.6 472.8C217.8 472.8 191.1 450.1 185.1 420.1L96 383.2L96 480C96 515.3 124.7 544 160 544L480 544C515.3 544 544 515.3 544 480L544 160zM337.9 260.2C337.9 292.5 364 318.6 396.3 318.6C428.6 318.6 454.7 292.5 454.7 260.2C454.7 227.9 428.6 201.8 396.3 201.8C364 201.8 337.9 227.9 337.9 260.2zM440.3 260.1C440.3 284.3 420.6 304 396.4 304C372.2 304 352.5 284.3 352.5 260.1C352.5 235.9 372.2 216.2 396.4 216.2C420.6 216.2 440.3 235.9 440.3 260.1z"/></svg>
              <svg v-else-if="modData.source==='github'"class="fill-current -m-0.5 size-4.5" viewBox="0 0 640 640" xmlns="http://www.w3.org/2000/svg"><path d="M544 160C544 124.7 515.3 96 480 96L160 96C124.7 96 96 124.7 96 160L96 480C96 515.3 124.7 544 160 544L480 544C515.3 544 544 515.3 544 480L544 160zM361.8 471.7C361.8 469.9 361.8 465.7 361.9 460.1C362 448.7 362 431.3 362 416.4C362 400.8 356.8 390.9 350.7 385.7C387.7 381.6 426.7 376.5 426.7 312.6C426.7 294.4 420.2 285.3 409.6 273.6C411.3 269.3 417 251.6 407.9 228.6C394 224.3 362.2 246.5 362.2 246.5C335.6 239 305.6 239 279 246.5C279 246.5 247.2 224.3 233.3 228.6C224.2 251.5 229.8 269.2 231.6 273.6C221 285.3 216 294.4 216 312.6C216 376.2 253.3 381.6 290.3 385.7C285.5 390 281.2 397.4 279.7 408C270.2 412.3 245.9 419.7 231.4 394.1C222.3 378.3 205.9 377 205.9 377C189.7 376.8 204.8 387.2 204.8 387.2C215.6 392.2 223.2 411.4 223.2 411.4C232.9 441.1 279.3 431.1 279.3 431.1C279.3 440.1 279.4 452.8 279.4 461.7C279.4 466.5 279.5 470.3 279.5 471.7C279.5 476 276.5 481.2 268 479.7C202 457.6 155.8 394.8 155.8 321.4C155.8 229.6 226 159.9 317.8 159.9C409.6 159.9 484 229.6 484 321.4C484.1 394.8 439.3 457.7 373.3 479.7C364.9 481.2 361.8 476 361.8 471.7zM271.3 416.9C271.1 415.4 272.4 414.1 274.3 413.7C276.2 413.5 278 414.3 278.2 415.6C278.5 416.9 277.2 418.2 275.2 418.6C273.3 419 271.5 418.2 271.3 416.9zM262.2 420.1C260 420.3 258.5 419.2 258.5 417.7C258.5 416.4 260 415.3 262 415.3C263.9 415.1 265.7 416.2 265.7 417.7C265.7 419 264.2 420.1 262.2 420.1zM247.9 417.9C246 417.5 244.7 416 245.1 414.7C245.5 413.4 247.5 412.8 249.2 413.2C251.2 413.8 252.5 415.3 252 416.6C251.6 417.9 249.6 418.5 247.9 417.9zM235.4 410.6C233.9 409.3 233.5 407.4 234.5 406.5C235.4 405.4 237.3 405.6 238.8 407.1C240.1 408.4 240.6 410.4 239.7 411.2C238.8 412.3 236.9 412.1 235.4 410.6zM226.9 400.6C225.8 399.1 225.8 397.4 226.9 396.7C228 395.8 229.7 396.5 230.6 398C231.7 399.5 231.7 401.3 230.6 402.1C229.7 402.7 228 402.1 226.9 400.6zM220.6 391.8C219.5 390.5 219.3 389 220.2 388.3C221.1 387.4 222.6 387.9 223.7 388.9C224.8 390.2 225 391.7 224.1 392.4C223.2 393.3 221.7 392.8 220.6 391.8zM214.6 385.4C213.3 384.8 212.7 383.7 213.1 382.8C213.5 382.2 214.6 381.9 215.9 382.4C217.2 383.1 217.8 384.2 217.4 385C217 385.9 215.7 386.1 214.6 385.4z"/></svg>
              <svg v-else-if="['core','dlc'].includes(modData.source)" class="fill-current size-3.5" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg"><circle cx="100" cy="100" r="90" fill="currentColor" stroke="currentColor" stroke-width="2"/><circle cx="100" cy="100" r="70" fill="#000" /><polygon points="100,48 118.27,74.85 149.46,83.93 129.57,109.61 130.57,142.07 100,131.09 69.43,142.07 70.43,109.61 50.54,83.93 81.73,74.85" fill="currentColor" stroke="currentColor" stroke-width="5"/><circle cx="100" cy="48" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="149.46" cy="83.93" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="130.57" cy="142.07" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="69.43" cy="142.07" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="50.54" cy="83.93" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/></svg>
              <svg v-else="modData.source==='local'" class="fill-current -m-0.5 size-4.5" viewBox="100 -20 420 640" xmlns="http://www.w3.org/2000/svg"><path d="M512 512L128 512C92.7 512 64 483.3 64 448L64 160C64 124.7 92.7 96 128 96L266.7 96C280.5 96 294 100.5 305.1 108.8L343.5 137.6C349 141.8 355.8 144 362.7 144L512 144C547.3 144 576 172.7 576 208L576 448C576 483.3 547.3 512 512 512zM248 304C234.7 304 224 314.7 224 328C224 341.3 234.7 352 248 352L392 352C405.3 352 416 341.3 416 328C416 314.7 405.3 304 392 304L248 304z"/></svg>
            </span>
              
            </div>
        </div>
        <!-- 缩略图 -->
        <div v-else class="relative">
          <img v-if="!!modData.path && modData.thumb_url" :src="modData.thumb_url"
            :class="`w-10 h-8 rounded object-cover border border-accent-${listColor}/30 pointer-events-none`">
          <div v-else-if="!modData.path" class="w-8 h-8 rounded flex items-center justify-center text-red-500 font-bold text-lg bg-red-900/50 border border-red-500/30">!</div>
          <div v-else class="w-10 h-10 rounded border-2 border-dashed border-text-main/10 flex items-center justify-center">
            <svg class="w-6 h-6 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
          </div>
          
          <div class="absolute -top-2 -left-1 flex items-center justify-center ">
            <!-- 类型图标 -->
            <span class="flex items-center justify-center bg-glass-medium/60 rounded-sm mr-0.5 hover:scale-120 transition-transform duration-200" tabindex="0" v-tooltip="`类型：${modType}`">
              <component :is="MOD_TYPE_ICON_MAP[modType] || MOD_TYPE_ICON_MAP.Unknown" class="w-4 h-4" />
            </span>
            <!-- 来源图标 -->
            <span class="flex items-center justify-center bg-glass-medium/70 rounded-sm hover:scale-120 transition-transform duration-200" tabindex="0" v-tooltip="`来源：${modData.source}`">
              <svg v-if="modData.source==='workshop'" class="fill-current -m-0.5 size-4.5" viewBox="0 0 640 640" xmlns="http://www.w3.org/2000/svg"><path d="M261.6 373.1C280.2 380.8 288.9 402 281.2 420.5C273.5 439 252.2 447.7 233.6 439.9L205.1 428.1C210.1 438.7 218.9 447.5 230.5 452.3C255.7 462.8 284.6 450.9 295.1 425.8C300.2 413.7 300.2 400.3 295.2 388.1C290.1 376 280.7 366.5 268.5 361.4C256.4 356.4 243.5 356.6 232.1 360.9L261.6 373.1zM544 160C544 124.7 515.3 96 480 96L160 96C124.7 96 96 124.7 96 160L96 304.7L212.6 352.8C224.6 344.6 238.8 340.7 253.3 341.5L308.7 261.3L308.7 260.2C308.7 212 348 172.7 396.3 172.7C444.6 172.7 483.9 212 483.9 260.2C483.9 309.4 443 348.9 394.3 347.7L315.3 404C316.9 442.5 286.2 472.8 249.6 472.8C217.8 472.8 191.1 450.1 185.1 420.1L96 383.2L96 480C96 515.3 124.7 544 160 544L480 544C515.3 544 544 515.3 544 480L544 160zM337.9 260.2C337.9 292.5 364 318.6 396.3 318.6C428.6 318.6 454.7 292.5 454.7 260.2C454.7 227.9 428.6 201.8 396.3 201.8C364 201.8 337.9 227.9 337.9 260.2zM440.3 260.1C440.3 284.3 420.6 304 396.4 304C372.2 304 352.5 284.3 352.5 260.1C352.5 235.9 372.2 216.2 396.4 216.2C420.6 216.2 440.3 235.9 440.3 260.1z"/></svg>
              <svg v-else-if="modData.source==='github'" class="fill-current -m-0.5 size-4.5" viewBox="0 0 640 640" xmlns="http://www.w3.org/2000/svg"><path d="M544 160C544 124.7 515.3 96 480 96L160 96C124.7 96 96 124.7 96 160L96 480C96 515.3 124.7 544 160 544L480 544C515.3 544 544 515.3 544 480L544 160zM361.8 471.7C361.8 469.9 361.8 465.7 361.9 460.1C362 448.7 362 431.3 362 416.4C362 400.8 356.8 390.9 350.7 385.7C387.7 381.6 426.7 376.5 426.7 312.6C426.7 294.4 420.2 285.3 409.6 273.6C411.3 269.3 417 251.6 407.9 228.6C394 224.3 362.2 246.5 362.2 246.5C335.6 239 305.6 239 279 246.5C279 246.5 247.2 224.3 233.3 228.6C224.2 251.5 229.8 269.2 231.6 273.6C221 285.3 216 294.4 216 312.6C216 376.2 253.3 381.6 290.3 385.7C285.5 390 281.2 397.4 279.7 408C270.2 412.3 245.9 419.7 231.4 394.1C222.3 378.3 205.9 377 205.9 377C189.7 376.8 204.8 387.2 204.8 387.2C215.6 392.2 223.2 411.4 223.2 411.4C232.9 441.1 279.3 431.1 279.3 431.1C279.3 440.1 279.4 452.8 279.4 461.7C279.4 466.5 279.5 470.3 279.5 471.7C279.5 476 276.5 481.2 268 479.7C202 457.6 155.8 394.8 155.8 321.4C155.8 229.6 226 159.9 317.8 159.9C409.6 159.9 484 229.6 484 321.4C484.1 394.8 439.3 457.7 373.3 479.7C364.9 481.2 361.8 476 361.8 471.7zM271.3 416.9C271.1 415.4 272.4 414.1 274.3 413.7C276.2 413.5 278 414.3 278.2 415.6C278.5 416.9 277.2 418.2 275.2 418.6C273.3 419 271.5 418.2 271.3 416.9zM262.2 420.1C260 420.3 258.5 419.2 258.5 417.7C258.5 416.4 260 415.3 262 415.3C263.9 415.1 265.7 416.2 265.7 417.7C265.7 419 264.2 420.1 262.2 420.1zM247.9 417.9C246 417.5 244.7 416 245.1 414.7C245.5 413.4 247.5 412.8 249.2 413.2C251.2 413.8 252.5 415.3 252 416.6C251.6 417.9 249.6 418.5 247.9 417.9zM235.4 410.6C233.9 409.3 233.5 407.4 234.5 406.5C235.4 405.4 237.3 405.6 238.8 407.1C240.1 408.4 240.6 410.4 239.7 411.2C238.8 412.3 236.9 412.1 235.4 410.6zM226.9 400.6C225.8 399.1 225.8 397.4 226.9 396.7C228 395.8 229.7 396.5 230.6 398C231.7 399.5 231.7 401.3 230.6 402.1C229.7 402.7 228 402.1 226.9 400.6zM220.6 391.8C219.5 390.5 219.3 389 220.2 388.3C221.1 387.4 222.6 387.9 223.7 388.9C224.8 390.2 225 391.7 224.1 392.4C223.2 393.3 221.7 392.8 220.6 391.8zM214.6 385.4C213.3 384.8 212.7 383.7 213.1 382.8C213.5 382.2 214.6 381.9 215.9 382.4C217.2 383.1 217.8 384.2 217.4 385C217 385.9 215.7 386.1 214.6 385.4z"/></svg>
              <svg v-else-if="['core','dlc'].includes(modData.source)" class="fill-current size-4" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg"><circle cx="100" cy="100" r="90" fill="currentColor" stroke="currentColor" stroke-width="2"/><circle cx="100" cy="100" r="70" fill="#000" /><polygon points="100,48 118.27,74.85 149.46,83.93 129.57,109.61 130.57,142.07 100,131.09 69.43,142.07 70.43,109.61 50.54,83.93 81.73,74.85" fill="currentColor" stroke="currentColor" stroke-width="5"/><circle cx="100" cy="48" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="149.46" cy="83.93" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="130.57" cy="142.07" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="69.43" cy="142.07" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="50.54" cy="83.93" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/></svg>
              <svg v-else="modData.source==='local'" class="fill-current -m-0.5 size-4.5" viewBox="100 -20 420 640" xmlns="http://www.w3.org/2000/svg"><path d="M512 512L128 512C92.7 512 64 483.3 64 448L64 160C64 124.7 92.7 96 128 96L266.7 96C280.5 96 294 100.5 305.1 108.8L343.5 137.6C349 141.8 355.8 144 362.7 144L512 144C547.3 144 576 172.7 576 208L576 448C576 483.3 547.3 512 512 512zM248 304C234.7 304 224 314.7 224 328C224 341.3 234.7 352 248 352L392 352C405.3 352 416 341.3 416 328C416 314.7 405.3 304 392 304L248 304z"/></svg>
            </span>
            <Copy v-if="modData.is_coexistence" class="size-3.5 ml-1 text-accent-primary  hover:scale-120 transition-transform duration-200" v-tooltip="'该Mod为共存状态，在创意工坊目录同样存在'" />
          </div>

          <div class="absolute -bottom-2 -left-0.5 flex items-center justify-center ">
            <span class="text-xs text-text-dim truncate font-mono bg-glass-medium/70 rounded-sm">
              {{ modData.supported_versions.at(-1) }}
            </span>
          </div>
        </div>
      </div>

      <!-- 文字信息 -->
      <div class="flex-1 min-w-0">
        <!-- 别名 -->
        <div v-if="modData.alias_name && !simple" class="text-[0.7rem] text-text-dim truncate font-mono ">
          {{ modData.name }}
        </div>
        <!-- 主名称 -->
        <div class="text-sm font-medium truncate">
          {{ modData.alias_name ? modData.alias_name : (modData.name ? modData.name : item_id) }}
        </div>
        <!-- 标签 -->
        <div class="overflow-hidden" style="box-shadow: inset 8px 0 10px -8px rgba(0, 0, 0, 0.3), inset -8px 0 10px -8px rgba(0, 0, 0, 0.3);">
          <div v-if="modData?.tags && modData.tags.length && !simple" class="flex gap-0.5 w-full overflow-y-hidden overflow-x-scroll custom-scrollbar mt-0.5 outline-none ">
              <span v-for="tag in modData.tags" :key="tag" class="min-w-fit font-mono px-0.5 py-0 my-0 rounded-md bg-accent-primary/10 text-accent-primary text-[0.7rem] font-bold border border-accent-primary/10 drop-shadow-xl/25">
                {{ tag }}
              </span>
          </div>
        </div>
        
      </div>
      
      <!-- 缺失警告 -->
      <div v-if="issueState" :class="[`rounded-4xl cursor-help text-sm font-bold
        hover:scale-110  text-shadow-2xs text-shadow-black hover:shadow-bg-deep/50 transition-all`,
        issueState === 'error' ? 'text-accent-danger' : issueState === 'warn'? 'text-accent-warn':'text-accent-primary']"
        v-tooltip="issueTooltip">
        <svg class="size-4.5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>
        </svg>
      </div>

      <!-- 分组颜色条 -->
      <div class="w-1.5 -m-1 h-[-webkit-fill-available] relative">
        <div v-if="modGroups.length" class="w-full absolute right-0 inset-y-0 flex flex-col scale-95 opacity-60">
          <div v-for="(g, index) in modGroups" :key="g.id" @click.prevent.stop=""
            :class="[`w-full flex-1 hover:scale-120 transition-all hover:border hover:border-text-main`,index===modGroups.length-1?'rounded-br-lg':'',index===0?'rounded-tr-lg':'']" 
            :style="{'backgroundColor': g.color}" v-tooltip="`分组：${g.name}`"
            v-preview="{component: GroupItem, props: {id: g.group_id, index: 0, groupData: g, expanded: true}}">
          </div><!-- 悬浮显示分组信息 -->
        </div>
      </div>

    </div>

    <!-- 联锁标识 -->
     <div v-if="modData.lock_previous_mod" class="absolute -top-3 right-8 opacity-70" :class="{'text-accent-warn': linkWarn[0]}">
      <svg v-show="!linkWarn[0]" class="rotate-90 size-6" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 17H7A5 5 0 0 1 7 7h2"/><path d="M15 7h2a5 5 0 1 1 0 10h-2"/><line x1="8" x2="16" y1="12" y2="12"/></svg>
      <svg v-show="linkWarn[0]" class="rotate-90 size-6" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 7h0a5 5 0 0 1 0 10h-0m-8 0H7A5 5 0 0 1 7 7h0"/><line x1="14" y1="19" x2="16" y2="21" stroke="currentColor" stroke-width="2"/><line x1="10" y1="19" x2="8" y2="21" stroke="currentColor" stroke-width="2"/><line x1="14" y1="5" x2="16" y2="3" stroke="currentColor" stroke-width="2"/><line x1="10" y1="5" x2="8" y2="3" stroke="currentColor" stroke-width="2"/></svg>
    </div>
    <div v-if="modData.lock_next_mod" class="absolute -bottom-3 right-11 opacity-70" :class="{'text-accent-warn': linkWarn[1]}">
      <svg v-show="!linkWarn[1]" class="rotate-90 size-6" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 17H7A5 5 0 0 1 7 7h2"/><path d="M15 7h2a5 5 0 1 1 0 10h-2"/><line x1="8" x2="16" y1="12" y2="12"/></svg>
      <svg v-show="linkWarn[1]" class="rotate-90 size-6" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 7h0a5 5 0 0 1 0 10h-0m-8 0H7A5 5 0 0 1 7 7h0"/><line x1="14" y1="19" x2="16" y2="21" stroke="currentColor" stroke-width="2"/><line x1="10" y1="19" x2="8" y2="21" stroke="currentColor" stroke-width="2"/><line x1="14" y1="5" x2="16" y2="3" stroke="currentColor" stroke-width="2"/><line x1="10" y1="5" x2="8" y2="3" stroke="currentColor" stroke-width="2"/></svg>
    </div>
  </div>
</template>

<script setup>
import { computed, h, nextTick  } from 'vue'
import { MOD_COLOR_LIST, ISSUE_TYPE, MOD_TYPE_MAP, ISSUE_TITLE_MAP, MOD_TYPE_ICON_MAP, SOURCE_TYPE_MAP } from '../../utils/constants'
import { useAppStore } from '../../stores/appStore'
import { useModStore } from '../../stores/modStore'
import { useGroupStore } from '../../stores/groupStore'
import { useRuleStore } from '../../stores/ruleStore'
import { useContextMenuStore } from '../../stores/contextMenuStore'
import { useConfirmStore } from '../../stores/confirmStore'
import { hexToRgba, hexToRgb } from '../../utils/colorDeal'
import { X, FolderInput, Tag, Group, Palette, ChessPawn, Goal, Trash2, Link2, Link2Off, PencilRuler, MegaphoneOff, Megaphone, ExternalLink, Flag, FlagOff, Copy, CircleSlash2, CircleCheckBig } from 'lucide-vue-next';
import GroupItem from './GroupItem.vue'

const props = defineProps({
  item_id: { type: String, required: true },
  index: { type: Number, required: true },
  showIndex: { type: Boolean, default: true },
  showIcon: { type: Boolean, default: true },
  showModIcon: { type: Boolean, default: true },
  showTypeIcon: { type: Boolean, default: true },
  simple: { type: Boolean, default: false },
  listColor: { type: String, default: 'primary'}, // 用于不同列表的颜色区分
  isSelected: { type: Boolean, default: false },
  isDragging: { type: Boolean, default: false }, // 用于外部控制样式
  isInSearch: { type: Boolean, default: false }, // 是否在搜索结果中
  searchMatch: { type: Boolean, default: false } // 是否是当前搜索焦点
})

defineEmits(['contextmenu'])

const appStore = useAppStore()
const modStore = useModStore()
const groupStore = useGroupStore()
const menuStore = useContextMenuStore()
const ruleStore = useRuleStore()
const confirmStore = useConfirmStore()

// 使用 computed 缓存，只有当 id 变化时才重新获取对象
// 极大地减少了父组件重绘时的计算量
const modData = computed(() => modStore.takeModById(props.item_id))
const modGroups = computed(() => groupStore.takeGroupsByModId(props.item_id))
// const modIcon = computed(() => modStore.getIconUrl(props.id))

// 是否启用
const isActive = computed(() => modStore.activeIds.includes(props.item_id))

const modType = computed(() => modStore.displayModType(modData.value))

const linkWarn = computed(() => {
  if (!issues.value) return (false, false)
  let lockPrev = false
  let lockNext = false
  for (const issue of issues.value) {
    if (issue.type === ISSUE_TYPE.WARN_LINK_WRONG_ORDER || issue.type === ISSUE_TYPE.WARN_LINK_MOD_MISSING) {
      if (issue.targetId === modData.value.lock_previous_mod) {
        lockPrev = true
      } else if (issue.targetId === modData.value.lock_next_mod) {
        lockNext = true
      }
    }
  }
  return [lockPrev, lockNext]
})

// 构造提示文本
const issueTooltip = computed(() => {
    if (!issues.value) return null
    // console.log('问题:', issues.value)
    // 换行显示所有错误
    return issues.value.map(i => i.message).join('\n')
})

// 错误提示
const issueState = computed(() => modStore.getModIssueState(props.item_id))
const issues = computed(() => modStore.modIssues.get(props.item_id.toLowerCase()))
const getCardClass = computed(() => {
    const select = props.isSelected ? 'ring-2 ring-accent-special ' : ''
    if (issueState.value === 'error') return `${select} border-accent-danger/40 border bg-accent-danger/10 hover:bg-accent-danger/20`
    if (issueState.value === 'warn') return `${select} border-accent-warn/40 border bg-accent-warn/10 hover:bg-accent-warn/20`
    return `${select} bg-bg-surface/20 border-text-main/10 hover:border-text-main/20 hover:bg-text-dim/20` // 原有的选中样式
})

const getCardStyle = (id) => {
  const base = { height: (props.simple ? appStore.scalePx(30) : appStore.scalePx(50))+'px' }
  const color = modStore.takeModById(id).sign_color
  // console.log(color)
  if (!color) return base
  if(!issueState.value) { // 防止覆盖错误样式
    base['backgroundColor'] = hexToRgba(color, 0.1)
  }
  base['borderColor'] = hexToRgba(color, 0.3)
  base['color'] = color
  return base
}

// 双击启用/停用 Mod
const handleDoubleClick = () => {
  if (appStore.settings.ui.double_click_active_mod) {
    modStore.changeModsActive([props.item_id], !isActive.value)
  }
}
const handleClick = (e) => {
  if (e.altKey) { //  alt 键点击触发
    ruleStore.currentId = props.item_id
    return
  }
  if (e.ctrlKey) { //  ctrl 键点击触发
    return
  }
  if (e.shiftKey) { //  shift 键点击触发
    return
  }
  if (e.button === 0) { // 左键点击
    return
  }
}
// 删除选中项文件
const deleteMod = async () => {
  appStore.deletePath(modData.value.path)
}
// 删除选中项文件
const deleteModFiles = async () => {
  const paths = modStore.selectedMods.map(m => m.path)
  appStore.deletePaths(paths)
}

// 取消订阅模组
const unsubscribeMod = async (delete_file = false) => {
  const res = await confirmStore.confirmAction('警告',`确定要取消订阅选中项${delete_file?'并删除文件':''}吗？${delete_file?'软件将主动删除Mod文件':'Steam 会自动删除已取消订阅的文件！'}`,{type:'error'})
  if(res) {
    appStore.unsubscribeMod(props.item_id, delete_file)
  }
}

// 1. 定义图标组件变量
const IconSteam = h('svg', { viewBox: "0 0 448 512", fill: "currentColor" }, 
  [ h('path', { d: "M273.5 177.5a61 61 0 1 1 122 0 61 61 0 1 1 -122 0zm174.5 .2c0 63-51 113.8-113.7 113.8L225 371.3c-4 43-40.5 76.8-84.5 76.8-40.5 0-74.7-28.8-83-67L0 358 0 250.7 97.2 290c15.1-9.2 32.2-13.3 52-11.5l71-101.7C220.7 114.5 271.7 64 334.2 64 397 64 448 115 448 177.7zM203 363c0-34.7-27.8-62.5-62.5-62.5-4.5 0-9 .5-13.5 1.5l26 10.5c25.5 10.2 38 39 27.7 64.5-10.2 25.5-39.2 38-64.7 27.5-10.2-4-20.5-8.3-30.7-12.2 10.5 19.7 31.2 33.2 55.2 33.2 34.7 0 62.5-27.8 62.5-62.5zM410.5 177.7a76.4 76.4 0 1 0 -152.8 0 76.4 76.4 0 1 0 152.8 0z" })]
)
// 右键菜单
const handleContextMenu = async (event) => {
  // console.log(issueState,issueState.value)
  // 检查是否选中，若未选中则添加到选中列表
  if (!modStore.selectedIds.includes(props.item_id)) {
    modStore.selectMods(props.item_id)
    await nextTick()
  }
  const selectedIds = modStore.selectedIds;
  // 获取统计信息
  const stats = modStore.selectedStats
  // 通用菜单
  const commnMenuItems = [
    { label: '标签管理', icon: Tag, disabled: !modStore.allModTags?.length, children: [{type: 'grid', columns: 5, label: '批量分配表情',
      children: modStore.allModTags.map(tag => ({ state: stats.tags[tag] || null, 
        label: '#'+tag, action: () => modStore.selectModsTag(tag)
      }))}]
    },
    { label: '分组管理', icon: Group, disabled: !groupStore.groupList?.length, children: [{type: 'grid', columns: 4, label: '批量加入分组',
      children: groupStore.groupList.map(group => ({ state: stats.groups[group.group_id] || null,
        label: group.name, color: group.color, bgColor: hexToRgba(group.color, 0.1), action: () => modStore.selectModsGroup(group.group_id)
      }))}]
    },
    { label: '标记颜色', icon: Palette, children: [{ type: 'grid', columns: 5, label: '批量设置颜色',
        children:[...MOD_COLOR_LIST.map(c => ({ tooltip: c, color: c, 
          active: modData.value.sign_color === c, action: () => modStore.setModsColor(selectedIds, c)
        })), 
        { icon: X, color: 'transparent', tooltip: '清除', action: () => modStore.setModsColor(selectedIds, null) }]
      }]
    },
    { label: '修改类型', icon: ChessPawn,
      children: [...Object.entries(MOD_TYPE_MAP).map(([key, value]) => ({ 
        icon: MOD_TYPE_ICON_MAP[key],
        label: value, action: () => modStore.setModsType(selectedIds, key)
      })),{ label: '恢复默认', level: 'warn', action: () => modStore.setModsType(selectedIds, null) }]
    },
    { label: isActive.value?'停用':'启用', icon: isActive.value? CircleSlash2:CircleCheckBig, 
      action: () => modStore.changeModsActive(selectedIds, !isActive.value) 
    },
  ]
  // 文件处理菜单
  const fileMenuItems = [
    { divider: true },
    { label: '创建本地共存', icon: Copy,
      disabled: !modStore.selectedMods.some(m => m.source === 'workshop'),
      action: () => modStore.localizeSelectedMods(),
    },
    { label: '删除', disabled: !modData.value.path, icon: Trash2, level: 'danger', action: () => deleteModFiles() },
  ]
  // 单选菜单
  const singleMenuItems = [
    { divider: true },
    { label: '编辑排序规则', icon: PencilRuler, action: () => ruleStore.currentId = props.item_id },
    { label: '访问网页', disabled: !modData.value.url, icon: ExternalLink, action: () => appStore.openUrl(modData.value.url) },
    { label: '打开文件夹', disabled: !modData.value.path, icon: FolderInput, action: () => appStore.openPath(modData.value.path) },
    { label: 'Steam操作', icon: IconSteam, disabled: modData.value.source!=='workshop', children: [
      { label: '访问创意工坊', disabled: modData.value.source!=='workshop', icon: IconSteam, action: () => appStore.openSteamWorkshopUrl(modData.value.url) },
      { label: '订阅模组', disabled: (!!modData.value.workshop_id && !!modData.value.path), icon: Flag, action: () => appStore.subscribeMod(props.item_id) },
      { label: '取消订阅', disabled: modData.value.source!=='workshop', icon: FlagOff, level: 'danger', action: () => unsubscribeMod() },
      { label: '取消订阅并删除文件', disabled: modData.value.source!=='workshop', icon: Trash2, level: 'danger', action: () => unsubscribeMod(true) },
    ]},
  ]
  // 多选菜单
  const selectedMenuItems = [
    { divider: true },
    { label: '联锁选中项', icon: Link2, action: () => modStore.linkMods(selectedIds) },
  ]
  if (modData.value.lock_previous_mod || modData.value.lock_next_mod) {
    selectedMenuItems.push({ label: '解除联锁', icon: Link2Off, action: () => modStore.unlinkMods(selectedIds) })
  }
  // 1. 获取所有选中 Mod 的当前问题并集
  const allSelectedIssues = selectedIds.flatMap(id => modStore.modIssues.get(id.toLowerCase()) || []);
  // 2. 提取唯一的错误类型 (Type Unique Set)
  const uniqueIssueTypes = [...new Set(allSelectedIssues.map(i => i.type))];

  // 3. 检查选中项中是否有人已经设置了忽略 (用于显示“恢复警告”)
  const anyModHasIgnored = selectedIds.some(id => {
    const m = modStore.takeModById(id);
    return m && m.ignored_issues && m.ignored_issues.length > 0;
  });
  // 统一的忽略/恢复菜单组
  const issueManagementItems = [];
  // A. 如果并集不为空，显示“忽略...”子菜单
  if (uniqueIssueTypes.length > 0) {
    issueManagementItems.push({ divider: true });
    issueManagementItems.push({
      label: selectedIds.length > 1 ? `批量忽略问题 (${uniqueIssueTypes.length})...` : '忽略问题...',
      icon: MegaphoneOff,
      children: uniqueIssueTypes.map(type => ({
        label: `忽略：${ISSUE_TITLE_MAP[type] || type}`,
        // 这里的 level 可以取该类型在所有 Mod 中的最高级别
        level: allSelectedIssues.find(i => i.type === type)?.level || 'warn',
        action: () => modStore.batchIgnoreIssues(selectedIds, type)
      }))
    });
  }
  // B. 如果有人被忽略了，显示“恢复警告”
  if (anyModHasIgnored) {
    // 如果之前没加 divider，补一个
    if (issueManagementItems.length === 0) issueManagementItems.push({ divider: true });
    issueManagementItems.push({
      label: selectedIds.length > 1 ? '恢复所有选中项警告' : '恢复警告',
      icon: Megaphone,
      level: 'warn',
      action: () => modStore.batchIgnoreIssues(selectedIds, null)
    });
  }

  // 合并菜单
  const menuItems = [
  ...commnMenuItems,
  ...(selectedIds.length > 1 ? selectedMenuItems : singleMenuItems),
  ...issueManagementItems, // 插入新的批量忽略逻辑
  ...fileMenuItems, // 插入文件处理菜单
];

  menuStore.open(event, menuItems)
}

</script>

<style scoped>
.digits-1 { font-size: 18px; }
.digits-2 { font-size: 15px; }
.digits-3 { font-size: 12px; }
.digits-4 { font-size: 9px; }
.custom-scrollbar::-webkit-scrollbar {
  width: 0;
  height: 0;
  scroll-behavior: smooth;
}
</style>