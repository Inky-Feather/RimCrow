<!-- ModItem.vue -->
<template>
  <div class="py-[2px] flex items-center gap-1 select-none relative" :data-id="item_id"
    @contextmenu="handleContextMenu" @dblclick="handleDoubleClick" @click.left="handleClick">
    <!-- 序号（通过位数计算动态调整字体大小） -->
    <!-- :style="{ fontSize: 18-(index+1).toString().length*3 + 'px' }" -->
    <button v-if="showIndex" type="button"
      class="swipe-trigger w-6 h-6 flex items-center justify-center rounded transition-all"
      :class="[ props.isSelected ? `text-text-main bg-accent-${listColor}/50` : `text-accent-${listColor}/50 bg-accent-${listColor}/10 hover:text-text-main hover:bg-accent-${listColor}/50`, !sectionHeader ? `digits-${(index+1).toString().length}` : '', isInSearch ? ' ring-2 ring-accent-highlight' : '', sectionHeader && !sectionCollapsed ? 'rotate-180' : '']"
      :style="{ width: appStore.scalePx(25) + 'px', height: appStore.scalePx(25) + 'px'}"
      :title="sectionHeader ? (sectionCollapsed ? '展开分割组' : '折叠分割组') : null"
      @click.stop="sectionHeader ? emit('toggle-section', item_id) : null">
      <!-- 分割线项复用普通序号列，只把数字替换为折叠图标，避免额外引入新布局。 -->
      <svg v-if="sectionHeader" class="size-4 transition-transform duration-200" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
      </svg>
      <template v-else>{{ index+1 }}</template>
    </button>

    <!-- 内容区域 -->
    <!-- 行组件会被虚拟列表频繁复用。这里避免在每一行使用 backdrop-filter，
      否则开启多列列表时浏览器会为大量半透明卡片持续保留合成层，空闲 GPU 占用会明显升高。 -->
    <div class="select-trigger drag-handle flex-1 flex items-center min-w-0 gap-1.5 p-1 rounded-lg relative group border hover:brightness-150 group shadow-sm text-text-soft"
      :class="[searchMatch ? 'ring-2 ring-accent-highlight scale-[1.02] z-20' : '', cardClass]"
      :style="getCardStyle(item_id)"
      v-preview="modData">
      <div v-if="showIcon">
        <!-- 图标 -->
        <div v-if="simple" class="flex items-center gap-1">

          <div v-if="showModIcon">
            <img v-if="!!modData.path && modData.preview_path" :src="appStore.getThumbUrl(modData.package_id, modData.preview_path)" loading="lazy"
              :class="`size-6 rounded object-cover border border-accent-${listColor}/30 pointer-events-none`">
            <div v-else-if="!modData.path" :class="`size-6 rounded flex items-center justify-center text-accent-danger font-bold text-lg bg-accent-danger/15 border border-accent-danger/30`">!</div>
            <div v-else :class="`size-6 rounded border-2 border-dashed border-border-base/10 flex items-center justify-center`">
              <svg :class="`size-5 opacity-20`" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
            </div>
          </div>

          <!-- 图标 -->
          <div v-if="showTypeIcon && !sectionHeader" class="flex items-center justify-center -mr-1">
            <!-- 类型图标 -->
            <span class="flex items-center justify-center hover:scale-120 transition-transform duration-200" tabindex="0" v-tooltip="`类型：${MOD_TYPE_MAP[modType] || modType || '未知'}`">
              <component :is="MOD_TYPE_ICON_MAP[modType] || MOD_TYPE_ICON_MAP.Unknown" class="w-4 h-4" />
            </span>
            <!-- 来源图标 -->
            <button type="button" class="relative flex items-center justify-center hover:scale-120 transition-transform duration-200" :class="canToggleCoexistSource ? 'cursor-pointer' : 'cursor-default'" tabindex="0" v-tooltip="sourceToggleTooltip" @click.stop="handleSourceToggle">
              <svg v-if="modData.store==='workshop'" class="fill-current -m-0.5 size-4.5" viewBox="0 0 640 640" xmlns="http://www.w3.org/2000/svg"><path d="M261.6 373.1C280.2 380.8 288.9 402 281.2 420.5C273.5 439 252.2 447.7 233.6 439.9L205.1 428.1C210.1 438.7 218.9 447.5 230.5 452.3C255.7 462.8 284.6 450.9 295.1 425.8C300.2 413.7 300.2 400.3 295.2 388.1C290.1 376 280.7 366.5 268.5 361.4C256.4 356.4 243.5 356.6 232.1 360.9L261.6 373.1zM544 160C544 124.7 515.3 96 480 96L160 96C124.7 96 96 124.7 96 160L96 304.7L212.6 352.8C224.6 344.6 238.8 340.7 253.3 341.5L308.7 261.3L308.7 260.2C308.7 212 348 172.7 396.3 172.7C444.6 172.7 483.9 212 483.9 260.2C483.9 309.4 443 348.9 394.3 347.7L315.3 404C316.9 442.5 286.2 472.8 249.6 472.8C217.8 472.8 191.1 450.1 185.1 420.1L96 383.2L96 480C96 515.3 124.7 544 160 544L480 544C515.3 544 544 515.3 544 480L544 160zM337.9 260.2C337.9 292.5 364 318.6 396.3 318.6C428.6 318.6 454.7 292.5 454.7 260.2C454.7 227.9 428.6 201.8 396.3 201.8C364 201.8 337.9 227.9 337.9 260.2zM440.3 260.1C440.3 284.3 420.6 304 396.4 304C372.2 304 352.5 284.3 352.5 260.1C352.5 235.9 372.2 216.2 396.4 216.2C420.6 216.2 440.3 235.9 440.3 260.1z"/></svg>
              <!-- <svg v-else-if="modData.source==='github'"class="fill-current -m-0.5 size-4.5" viewBox="0 0 640 640" xmlns="http://www.w3.org/2000/svg"><path d="M544 160C544 124.7 515.3 96 480 96L160 96C124.7 96 96 124.7 96 160L96 480C96 515.3 124.7 544 160 544L480 544C515.3 544 544 515.3 544 480L544 160zM361.8 471.7C361.8 469.9 361.8 465.7 361.9 460.1C362 448.7 362 431.3 362 416.4C362 400.8 356.8 390.9 350.7 385.7C387.7 381.6 426.7 376.5 426.7 312.6C426.7 294.4 420.2 285.3 409.6 273.6C411.3 269.3 417 251.6 407.9 228.6C394 224.3 362.2 246.5 362.2 246.5C335.6 239 305.6 239 279 246.5C279 246.5 247.2 224.3 233.3 228.6C224.2 251.5 229.8 269.2 231.6 273.6C221 285.3 216 294.4 216 312.6C216 376.2 253.3 381.6 290.3 385.7C285.5 390 281.2 397.4 279.7 408C270.2 412.3 245.9 419.7 231.4 394.1C222.3 378.3 205.9 377 205.9 377C189.7 376.8 204.8 387.2 204.8 387.2C215.6 392.2 223.2 411.4 223.2 411.4C232.9 441.1 279.3 431.1 279.3 431.1C279.3 440.1 279.4 452.8 279.4 461.7C279.4 466.5 279.5 470.3 279.5 471.7C279.5 476 276.5 481.2 268 479.7C202 457.6 155.8 394.8 155.8 321.4C155.8 229.6 226 159.9 317.8 159.9C409.6 159.9 484 229.6 484 321.4C484.1 394.8 439.3 457.7 373.3 479.7C364.9 481.2 361.8 476 361.8 471.7zM271.3 416.9C271.1 415.4 272.4 414.1 274.3 413.7C276.2 413.5 278 414.3 278.2 415.6C278.5 416.9 277.2 418.2 275.2 418.6C273.3 419 271.5 418.2 271.3 416.9zM262.2 420.1C260 420.3 258.5 419.2 258.5 417.7C258.5 416.4 260 415.3 262 415.3C263.9 415.1 265.7 416.2 265.7 417.7C265.7 419 264.2 420.1 262.2 420.1zM247.9 417.9C246 417.5 244.7 416 245.1 414.7C245.5 413.4 247.5 412.8 249.2 413.2C251.2 413.8 252.5 415.3 252 416.6C251.6 417.9 249.6 418.5 247.9 417.9zM235.4 410.6C233.9 409.3 233.5 407.4 234.5 406.5C235.4 405.4 237.3 405.6 238.8 407.1C240.1 408.4 240.6 410.4 239.7 411.2C238.8 412.3 236.9 412.1 235.4 410.6zM226.9 400.6C225.8 399.1 225.8 397.4 226.9 396.7C228 395.8 229.7 396.5 230.6 398C231.7 399.5 231.7 401.3 230.6 402.1C229.7 402.7 228 402.1 226.9 400.6zM220.6 391.8C219.5 390.5 219.3 389 220.2 388.3C221.1 387.4 222.6 387.9 223.7 388.9C224.8 390.2 225 391.7 224.1 392.4C223.2 393.3 221.7 392.8 220.6 391.8zM214.6 385.4C213.3 384.8 212.7 383.7 213.1 382.8C213.5 382.2 214.6 381.9 215.9 382.4C217.2 383.1 217.8 384.2 217.4 385C217 385.9 215.7 386.1 214.6 385.4z"/></svg> -->
              <svg v-else-if="['core','dlc'].includes(modData.source)" class="fill-current size-3.5" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg"><circle cx="100" cy="100" r="90" fill="currentColor" stroke="currentColor" stroke-width="2"/><circle cx="100" cy="100" r="70" fill="var(--color-text-inverse)" /><polygon points="100,48 118.27,74.85 149.46,83.93 129.57,109.61 130.57,142.07 100,131.09 69.43,142.07 70.43,109.61 50.54,83.93 81.73,74.85" fill="currentColor" stroke="currentColor" stroke-width="5"/><circle cx="100" cy="48" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="149.46" cy="83.93" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="130.57" cy="142.07" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="69.43" cy="142.07" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="50.54" cy="83.93" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/></svg>
              <!-- <svg v-else-if="modData.source==='other'" class="fill-current -m-0.5 size-4.5" viewBox="100 -20 420 640" xmlns="http://www.w3.org/2000/svg"><path d="M512 512L128 512C92.7 512 64 483.3 64 448L64 160C64 124.7 92.7 96 128 96L266.7 96C280.5 96 294 100.5 305.1 108.8L343.5 137.6C349 141.8 355.8 144 362.7 144L512 144C547.3 144 576 172.7 576 208L576 448C576 483.3 547.3 512 512 512zM248 304C234.7 304 224 314.7 224 328C224 341.3 234.7 352 248 352L392 352C405.3 352 416 341.3 416 328C416 314.7 405.3 304 392 304L248 304z"/></svg> -->
              <!-- <svg viewBox="0 0 96 96" ></svg> -->
              <IconSelf v-else-if="modData.store==='self'" class=" size-4 grayscale-20" />
              <svg v-else class="fill-current -m-0.5 size-4.5" viewBox="100 -20 420 640" xmlns="http://www.w3.org/2000/svg"><path d="M512 512L128 512C92.7 512 64 483.3 64 448L64 160C64 124.7 92.7 96 128 96L266.7 96C280.5 96 294 100.5 305.1 108.8L343.5 137.6C349 141.8 355.8 144 362.7 144L512 144C547.3 144 576 172.7 576 208L576 448C576 483.3 547.3 512 512 512zM248 304C234.7 304 224 314.7 224 328C224 341.3 234.7 352 248 352L392 352C405.3 352 416 341.3 416 328C416 314.7 405.3 304 392 304L248 304z"/></svg>
              <span v-if="canToggleCoexistSource" class="absolute -top-0.5 -right-0.5 size-1.5 rounded-full bg-accent-primary shadow-sm shadow-accent-primary/60"></span>
            </button>
            <!-- Multiplayer 联机兼容性 -->
            <div v-if="!sectionHeader && showMultiplayerCompatBadge" :class="[`w-4 h-4 mr-0.5 shrink-0 rounded border cursor-help text-[0.65rem] leading-none font-mono tabular-nums font-black flex items-center justify-center
              hover:scale-110 text-shadow-2xs text-shadow-black hover:shadow-bg-deep/50 transition-all`, multiplayerCompatBadgeClass]"
              v-tooltip="multiplayerCompatTooltip">
              {{ multiplayerCompatBadgeText }}
            </div>
            
          </div>
        </div>
        <!-- 缩略图 -->
        <div v-else class="relative">
          <img v-if="!!modData.path && modData.preview_path" :src="appStore.getThumbUrl(modData.package_id, modData.preview_path)" loading="lazy"
            :class="`w-10 h-8 rounded object-cover border border-accent-${listColor}/30 pointer-events-none`">
          <div v-else-if="!modData.path" class="w-8 h-8 rounded flex items-center justify-center text-accent-danger font-bold text-lg bg-accent-danger/15 border border-accent-danger/30">!</div>
          <div v-else class="w-10 h-10 rounded border-2 border-dashed border-border-base/10 flex items-center justify-center">
            <svg class="w-6 h-6 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
          </div>

          <div class="absolute -top-2 -left-1 flex items-center justify-center ">
            <!-- 类型图标 -->
            <span class="flex items-center justify-center bg-glass-medium/60 rounded-sm mr-0.5 hover:scale-120 transition-transform duration-200" tabindex="0" v-tooltip="`类型：${modType}`">
              <component :is="MOD_TYPE_ICON_MAP[modType] || MOD_TYPE_ICON_MAP.Unknown" class="w-4 h-4" />
            </span>
            <!-- 来源图标 -->
            <button type="button" class="relative flex items-center justify-center bg-glass-medium/70 rounded-sm hover:scale-120 transition-transform duration-200" :class="canToggleCoexistSource ? 'cursor-pointer' : 'cursor-default'" tabindex="0" v-tooltip="sourceToggleTooltip" @click.stop="handleSourceToggle">
              <svg v-if="modData.store==='workshop'" class="fill-current -m-0.5 size-4.5" viewBox="0 0 640 640" xmlns="http://www.w3.org/2000/svg"><path d="M261.6 373.1C280.2 380.8 288.9 402 281.2 420.5C273.5 439 252.2 447.7 233.6 439.9L205.1 428.1C210.1 438.7 218.9 447.5 230.5 452.3C255.7 462.8 284.6 450.9 295.1 425.8C300.2 413.7 300.2 400.3 295.2 388.1C290.1 376 280.7 366.5 268.5 361.4C256.4 356.4 243.5 356.6 232.1 360.9L261.6 373.1zM544 160C544 124.7 515.3 96 480 96L160 96C124.7 96 96 124.7 96 160L96 304.7L212.6 352.8C224.6 344.6 238.8 340.7 253.3 341.5L308.7 261.3L308.7 260.2C308.7 212 348 172.7 396.3 172.7C444.6 172.7 483.9 212 483.9 260.2C483.9 309.4 443 348.9 394.3 347.7L315.3 404C316.9 442.5 286.2 472.8 249.6 472.8C217.8 472.8 191.1 450.1 185.1 420.1L96 383.2L96 480C96 515.3 124.7 544 160 544L480 544C515.3 544 544 515.3 544 480L544 160zM337.9 260.2C337.9 292.5 364 318.6 396.3 318.6C428.6 318.6 454.7 292.5 454.7 260.2C454.7 227.9 428.6 201.8 396.3 201.8C364 201.8 337.9 227.9 337.9 260.2zM440.3 260.1C440.3 284.3 420.6 304 396.4 304C372.2 304 352.5 284.3 352.5 260.1C352.5 235.9 372.2 216.2 396.4 216.2C420.6 216.2 440.3 235.9 440.3 260.1z"/></svg>
              <!-- <svg v-else-if="modData.source==='github'" class="fill-current -m-0.5 size-4.5" viewBox="0 0 640 640" xmlns="http://www.w3.org/2000/svg"><path d="M544 160C544 124.7 515.3 96 480 96L160 96C124.7 96 96 124.7 96 160L96 480C96 515.3 124.7 544 160 544L480 544C515.3 544 544 515.3 544 480L544 160zM361.8 471.7C361.8 469.9 361.8 465.7 361.9 460.1C362 448.7 362 431.3 362 416.4C362 400.8 356.8 390.9 350.7 385.7C387.7 381.6 426.7 376.5 426.7 312.6C426.7 294.4 420.2 285.3 409.6 273.6C411.3 269.3 417 251.6 407.9 228.6C394 224.3 362.2 246.5 362.2 246.5C335.6 239 305.6 239 279 246.5C279 246.5 247.2 224.3 233.3 228.6C224.2 251.5 229.8 269.2 231.6 273.6C221 285.3 216 294.4 216 312.6C216 376.2 253.3 381.6 290.3 385.7C285.5 390 281.2 397.4 279.7 408C270.2 412.3 245.9 419.7 231.4 394.1C222.3 378.3 205.9 377 205.9 377C189.7 376.8 204.8 387.2 204.8 387.2C215.6 392.2 223.2 411.4 223.2 411.4C232.9 441.1 279.3 431.1 279.3 431.1C279.3 440.1 279.4 452.8 279.4 461.7C279.4 466.5 279.5 470.3 279.5 471.7C279.5 476 276.5 481.2 268 479.7C202 457.6 155.8 394.8 155.8 321.4C155.8 229.6 226 159.9 317.8 159.9C409.6 159.9 484 229.6 484 321.4C484.1 394.8 439.3 457.7 373.3 479.7C364.9 481.2 361.8 476 361.8 471.7zM271.3 416.9C271.1 415.4 272.4 414.1 274.3 413.7C276.2 413.5 278 414.3 278.2 415.6C278.5 416.9 277.2 418.2 275.2 418.6C273.3 419 271.5 418.2 271.3 416.9zM262.2 420.1C260 420.3 258.5 419.2 258.5 417.7C258.5 416.4 260 415.3 262 415.3C263.9 415.1 265.7 416.2 265.7 417.7C265.7 419 264.2 420.1 262.2 420.1zM247.9 417.9C246 417.5 244.7 416 245.1 414.7C245.5 413.4 247.5 412.8 249.2 413.2C251.2 413.8 252.5 415.3 252 416.6C251.6 417.9 249.6 418.5 247.9 417.9zM235.4 410.6C233.9 409.3 233.5 407.4 234.5 406.5C235.4 405.4 237.3 405.6 238.8 407.1C240.1 408.4 240.6 410.4 239.7 411.2C238.8 412.3 236.9 412.1 235.4 410.6zM226.9 400.6C225.8 399.1 225.8 397.4 226.9 396.7C228 395.8 229.7 396.5 230.6 398C231.7 399.5 231.7 401.3 230.6 402.1C229.7 402.7 228 402.1 226.9 400.6zM220.6 391.8C219.5 390.5 219.3 389 220.2 388.3C221.1 387.4 222.6 387.9 223.7 388.9C224.8 390.2 225 391.7 224.1 392.4C223.2 393.3 221.7 392.8 220.6 391.8zM214.6 385.4C213.3 384.8 212.7 383.7 213.1 382.8C213.5 382.2 214.6 381.9 215.9 382.4C217.2 383.1 217.8 384.2 217.4 385C217 385.9 215.7 386.1 214.6 385.4z"/></svg> -->
              <svg v-else-if="['core','dlc'].includes(modData.source)" class="fill-current size-4" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg"><circle cx="100" cy="100" r="90" fill="currentColor" stroke="currentColor" stroke-width="2"/><circle cx="100" cy="100" r="70" fill="currentColor" /><polygon points="100,48 118.27,74.85 149.46,83.93 129.57,109.61 130.57,142.07 100,131.09 69.43,142.07 70.43,109.61 50.54,83.93 81.73,74.85" fill="currentColor" stroke="currentColor" stroke-width="5"/><circle cx="100" cy="48" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="149.46" cy="83.93" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="130.57" cy="142.07" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="69.43" cy="142.07" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="50.54" cy="83.93" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/></svg>
              <!-- <svg v-else-if="modData.source==='other'" class="fill-current -m-0.5 size-4.5" viewBox="100 -20 420 640" xmlns="http://www.w3.org/2000/svg"><path d="M512 512L128 512C92.7 512 64 483.3 64 448L64 160C64 124.7 92.7 96 128 96L266.7 96C280.5 96 294 100.5 305.1 108.8L343.5 137.6C349 141.8 355.8 144 362.7 144L512 144C547.3 144 576 172.7 576 208L576 448C576 483.3 547.3 512 512 512zM248 304C234.7 304 224 314.7 224 328C224 341.3 234.7 352 248 352L392 352C405.3 352 416 341.3 416 328C416 314.7 405.3 304 392 304L248 304z"/></svg> -->
              <!-- <svg v-else-if="modData.store==='self'" class=" size-4 grayscale-20" viewBox="0 0 96 96" > <use href="/icon.svg"></use></svg> -->
              <IconSelf v-else-if="modData.store==='self'" class=" size-4 grayscale-20" />
              <svg v-else class="fill-current -m-0.5 size-4.5" viewBox="100 -20 420 640" xmlns="http://www.w3.org/2000/svg"><path d="M512 512L128 512C92.7 512 64 483.3 64 448L64 160C64 124.7 92.7 96 128 96L266.7 96C280.5 96 294 100.5 305.1 108.8L343.5 137.6C349 141.8 355.8 144 362.7 144L512 144C547.3 144 576 172.7 576 208L576 448C576 483.3 547.3 512 512 512zM248 304C234.7 304 224 314.7 224 328C224 341.3 234.7 352 248 352L392 352C405.3 352 416 341.3 416 328C416 314.7 405.3 304 392 304L248 304z"/></svg>
              <span v-if="canToggleCoexistSource" class="absolute -top-0.5 -right-0.5 size-1.5 rounded-full bg-accent-primary shadow-sm shadow-accent-primary/60"></span>
            </button>
            <!-- Multiplayer 联机兼容性 -->
            <div v-if="!sectionHeader && showMultiplayerCompatBadge" :class="[`w-4 h-4 m-0.5 shrink-0 rounded border cursor-help text-[0.65rem] leading-none font-mono tabular-nums font-black flex items-center justify-center
              hover:scale-110 text-shadow-2xs text-shadow-black hover:shadow-bg-deep/50 transition-all`, multiplayerCompatBadgeClass]"
              v-tooltip="multiplayerCompatTooltip">
              {{ multiplayerCompatBadgeText }}
            </div>
            <!-- <Copy v-if="modData.is_coexistence" class="size-3.5 ml-1 text-accent-primary  hover:scale-120 transition-transform duration-200" v-tooltip="'该Mod为共存状态，在创意工坊目录同样存在'" /> -->
          </div>

          <div v-if="latestSupportedVersion" class="absolute -bottom-2 -left-0.5 flex items-center justify-center ">
            <span class="text-xs text-text-dim truncate font-mono bg-glass-medium/70 rounded-sm">
              {{ latestSupportedVersion }}
            </span>
          </div>
        </div>
      </div>

      <!-- 文字信息 -->
      <div class="flex-1 min-w-0">
        <template v-if="sectionHeader">
          <div class="flex items-center gap-1 min-w-0">
            <div :class="`h-1 flex-1 min-w-0 bg-text-main`"></div>
            <div class="min-w-0 px-1 text-center text-sm font-semibold tracking-[0.08em] truncate">
              {{ sectionHeaderDisplayName }}
            </div>
            <div :class="`h-1 flex-1 min-w-0 bg-text-main`"></div>
          </div>
          <div v-if="!simple" class="text-[0.68rem] text-center text-text-dim truncate font-mono mt-0.5">
            {{ sectionCollapsed ? '拖动分割线模组将整组移动，插入时默认落在组尾' : '当前为展开状态，拖动分割线模组仅移动该项' }}
          </div>
        </template>
        <template v-else>
          <!-- 别名 -->
          <div v-if="modData.alias_name && !simple" class="text-[0.7rem] text-text-dim truncate font-mono ">
            {{ modData.name }}
          </div>
          <!-- 主名称 -->
          <div class="text-sm font-medium truncate">
            {{ displayName }}
          </div>
          <!-- 标签 -->
          <div class="overflow-hidden" style="box-shadow: inset 8px 0 10px -8px var(--shadow-color), inset -8px 0 10px -8px var(--shadow-color);">
            <div v-if="modData?.tags && modData.tags.length && !simple" class="flex gap-0.5 w-full overflow-y-hidden overflow-x-scroll custom-scrollbar mt-0.5 outline-none ">
              <span v-for="tag in modData.tags" :key="tag" class="min-w-fit font-mono px-0.5 py-0 my-0 rounded-md bg-accent-primary/10 text-accent-primary text-[0.7rem] font-bold border border-accent-primary/10 drop-shadow-xl/25">
                {{ tag }}
              </span>
            </div>
          </div>
        </template>
      </div>

      <!-- 分割线项把“组内数量”放到最右侧，保持左侧图标区与普通项一致。 -->
      <div v-if="sectionHeader" class="shrink-0 flex items-center gap-2">
        <span :class="`rounded bg-bg-inset/70 px-2 py-0.5 text-xs text-accent-${listColor}`">
          {{ sectionChildCount }}
        </span>
      </div>

      <!-- 可替换版本 / 共存同步提示 -->
      <div v-if="!sectionHeader && modNoticeTooltip" :class="[`rounded-4xl cursor-help text-sm font-bold
        hover:scale-110  text-shadow-2xs text-shadow-black hover:shadow-bg-deep/50 transition-all`, modNoticeClass]"
        v-tooltip="modNoticeTooltip">
        <svg class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>
        </svg>
      </div>

      <!-- 问题警告 -->
      <div v-if="!sectionHeader && issueState" :class="[`rounded-4xl cursor-help text-sm font-bold
        hover:scale-110  text-shadow-2xs text-shadow-black hover:shadow-bg-deep/50 transition-all`,
        issueState === 'error' ? 'text-accent-danger' : issueState === 'warn'? 'text-accent-warn': issueState === 'info'? 'text-text-dim':'text-accent-primary']"
        v-tooltip="issueTooltip">
        <svg v-if="issueState !== 'info'" class="size-4.5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>
        </svg>
        <svg v-else class="size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>
        </svg>
      </div>

      <!-- 分组颜色条 -->
      <div v-if="!sectionHeader" class="w-1.5 -m-1 h-[-webkit-fill-available] relative">
        <div v-if="modGroups.length" class="w-full absolute right-0 inset-y-0 flex flex-col scale-95 opacity-60">
          <!-- 悬浮显示分组信息 -->
          <div v-for="(g, index) in modGroups" :key="g.group_id || g.id" @click.prevent.stop="focusGroupPanel(g)"
            :class="[`w-full flex-1 cursor-pointer hover:scale-120 transition-all hover:border hover:border-border-base/18`,index===modGroups.length-1?'rounded-br-lg':'',index===0?'rounded-tr-lg':'']"
            :style="{'backgroundColor': g.color}" v-tooltip="`分组：${g.name}\n点击打开分组页`">
            <!-- v-preview="{component: GroupItem, props: {id: g.group_id, index: 0, groupData: g, expanded: true}}"> -->
          </div>
        </div>
      </div>
      <div class="absolute top-0 left-0 -z-100 w-full rounded-lg h-full group-hover:bg-bg-overlay/10"></div>

    </div>

    <!-- 联锁标识 -->
    <div v-if="!sectionHeader && hasLockPrevious" class="absolute -top-2 right-8 opacity-50" :class="{'text-accent-warn': linkWarn[0]}">
      <svg v-show="!linkWarn[0]" class="rotate-90 size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 17H7A5 5 0 0 1 7 7h2"/><path d="M15 7h2a5 5 0 1 1 0 10h-2"/><line x1="8" x2="16" y1="12" y2="12"/></svg>
      <svg v-show="linkWarn[0]" class="rotate-90 size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 7h0a5 5 0 0 1 0 10h-0m-8 0H7A5 5 0 0 1 7 7h0"/><line x1="14" y1="19" x2="16" y2="21" stroke="currentColor" stroke-width="2"/><line x1="10" y1="19" x2="8" y2="21" stroke="currentColor" stroke-width="2"/><line x1="14" y1="5" x2="16" y2="3" stroke="currentColor" stroke-width="2"/><line x1="10" y1="5" x2="8" y2="3" stroke="currentColor" stroke-width="2"/></svg>
    </div>
    <div v-if="!sectionHeader && hasLockNext" class="absolute -bottom-2 right-11 opacity-50" :class="{'text-accent-warn': linkWarn[1]}">
      <svg v-show="!linkWarn[1]" class="rotate-90 size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 17H7A5 5 0 0 1 7 7h2"/><path d="M15 7h2a5 5 0 1 1 0 10h-2"/><line x1="8" x2="16" y1="12" y2="12"/></svg>
      <svg v-show="linkWarn[1]" class="rotate-90 size-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 7h0a5 5 0 0 1 0 10h-0m-8 0H7A5 5 0 0 1 7 7h0"/><line x1="14" y1="19" x2="16" y2="21" stroke="currentColor" stroke-width="2"/><line x1="10" y1="19" x2="8" y2="21" stroke="currentColor" stroke-width="2"/><line x1="14" y1="5" x2="16" y2="3" stroke="currentColor" stroke-width="2"/><line x1="10" y1="5" x2="8" y2="3" stroke="currentColor" stroke-width="2"/></svg>
    </div>

  </div>
</template>

<script setup>
import { computed, nextTick } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { MOD_SIGN_COLOR_MAP, ISSUE_TYPE, MOD_TYPE_MAP, ISSUE_TITLE_MAP, MOD_TYPE_ICON_MAP, SOURCE_TYPE_MAP, IconSteam, IconSelf } from '../../shared/lib/constants'
import { useAppStore } from '../../app/stores/appStore'
import { useAiStore } from '../ai/aiStore'
import { useModStore } from './stores/modStore'
import { useGroupStore } from './stores/groupStore'
import { useContextMenuStore } from '../../shared/components/context-menu/contextMenuStore'
import { useCommandStore } from '../../shared/commands/commandStore'
import { DEFAULT_ACCENT_HEX, hexToRgba, hexToRgb, normalizeHexColor } from '../../shared/lib/color'
import { extractSectionHeaderTitle, isSectionHeaderTitle, sortByDisplayName, sortTextByName, toast, toUserMessage } from '../../shared/lib/common'
import { normalizePackageId, normalizePackageToken } from './lib/modIdentity'
import { X, FolderInput, Tag, Group, Palette, BetweenHorizontalStart, Redo2, ChevronDown, ChevronsDown, ChevronUp, ChevronsUp, ChessPawn, MessageSquareHeart, Download, Eraser, FolderMinus, SquareX, Trash2, Cable, Link2, Link2Off, PencilRuler, MegaphoneOff, Megaphone, ExternalLink, Flag, FlagOff, Copy, RefreshCw, CircleSlash2, CircleCheckBig, BotMessageSquare, CircleFadingPlus, CornerUpRight, Lock, SquaresExclude, Package, ChevronsDownUp, ChevronsUpDown } from 'lucide-vue-next';


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
  searchMatch: { type: Boolean, default: false }, // 是否是当前搜索焦点
  moveMenu: { type: Object, default: null },
  currentSplitGroup: { type: Object, default: null },
  // 仅用于在右键菜单中判断“当前选中项里是否包含分割线模组”，不参与普通模组逻辑。
  sectionFeatureEnabled: { type: Boolean, default: false },
  sectionHeader: { type: Boolean, default: false },
  sectionCollapsed: { type: Boolean, default: false },
  sectionChildCount: { type: Number, default: 0 }
})

// 分割线项需要把折叠动作回传给父列表，真正的折叠状态由父组件统一维护。
const emit = defineEmits(['contextmenu', 'toggle-section', 'expand-selected-sections', 'collapse-selected-sections', 'expand-all-sections', 'collapse-all-sections', 'move-selected'])

const appStore = useAppStore()
const aiStore = useAiStore()
const modStore = useModStore()
const groupStore = useGroupStore()
const menuStore = useContextMenuStore()
const commandStore = useCommandStore()
const queueSetModsColor = useDebounceFn((modIds, color) => {
  modStore.setModsColor(modIds, color)
}, 120)

// 使用 computed 缓存，只有当 id 变化时才重新获取对象
// 极大地减少了父组件重绘时的计算量
const modData = computed(() => modStore.takeModById(props.item_id))
const modGroups = computed(() => groupStore.takeGroupsByModId(props.item_id))
// const modIcon = computed(() => modStore.getIconUrl(props.id))
const displayName = computed(() => modData.value?.alias_name ? modData.value.alias_name : (modData.value?.name ? modData.value.name : props.item_id))
const latestSupportedVersion = computed(() => {
  const versions = Array.isArray(modData.value?.supported_versions) ? modData.value.supported_versions : []
  return versions.length > 0 ? String(versions[versions.length - 1] || '').trim() : ''
})
const sectionHeaderDisplayName = computed(() => extractSectionHeaderTitle(displayName.value) || displayName.value)
const normalizePackageKey = (value = '') => String(value || '').trim().toLowerCase().replace(/_(steam|local)$/, '')
const currentCanonicalId = computed(() => normalizePackageKey(modData.value?.canonical_package_id || modData.value?.package_id || props.item_id))
// ModItem 自己也需要识别“哪些选中项属于分割线模组”，这样右键菜单才能按批量分割组操作显示。
const isSectionHeaderName = (value) => isSectionHeaderTitle(value)
const isSectionHeaderId = (id) => {
  if (!props.sectionFeatureEnabled) return false
  const mod = modStore.takeModById(id)
  return isSectionHeaderName(mod?.alias_name) || isSectionHeaderName(mod?.name)
}
const selectedSectionHeaderIds = computed(() => {
  if (!props.sectionFeatureEnabled) return []
  return [...new Set(modStore.selectedIds.filter(id => isSectionHeaderId(id)))]
})
const focusGroupPanel = (group = {}) => {
  const groupId = String(group?.group_id || group?.id || '').trim()
  if (!groupId) return
  appStore.activeSidebarTab = 'group'
  groupStore.focusGroup(groupId)
}

// 是否启用
const isActive = computed(() => modStore.activeIds.some(id => normalizePackageId(id) === currentCanonicalId.value))
const mpCompatActive = computed(() => modStore.activeIds.some(id => normalizePackageId(id) === 'rwmt.multiplayercompatibility'))
const multiplayerCompat = computed(() => modData.value?.multiplayer_compat || null)
const showMultiplayerCompatBadge = computed(() => !!multiplayerCompat.value?.enabled)
const multiplayerCompatEffective = computed(() => (
  !!multiplayerCompat.value?.has_mp_compat_patch && isActive.value && mpCompatActive.value
))
const multiplayerCompatBadgeText = computed(() => {
  const info = multiplayerCompat.value || {}
  const status = Number(info.effective_status || 0)
  return status > 0 ? String(status) : '?'
})
const multiplayerCompatBadgeClass = computed(() => {
  const info = multiplayerCompat.value || {}
  if (multiplayerCompatEffective.value) return 'text-on-accent-success bg-accent-success/50 border-accent-success/10'
  if (info.has_mp_compat_patch) return 'text-on-accent-warn bg-accent-warn/50 border-accent-warn/10'
  const status = Number(info.effective_status || 0)
  if (status === 1) return 'text-accent-danger bg-accent-danger/30 border-accent-danger/10'
  if (status === 2) return 'text-accent-warn bg-accent-warn/30 border-accent-warn/10'
  if (status === 3) return 'text-accent-tip bg-accent-tip/30 border-accent-tip/10'
  if (status === 4) return 'text-accent-success bg-accent-success/30 border-accent-success/10'
  return 'text-text-dim bg-bg-inset/70 border-border-base/15'
})
const multiplayerCompatTooltip = computed(() => {
  const info = multiplayerCompat.value || {}
  if (!info.enabled) return ''
  const parts = [`联机兼容性：${info.effective_label || '未知'}`]
  if (info.status_source === 'official') parts.push(info.status_description || '来自 Multiplayer 官方兼容表。')
  else if (info.status_source === 'xml_only') parts.push('未检测到程序集，按 Multiplayer 的 XML-only 规则视为完全可用。')
  else parts.push('官方兼容表暂无明确结论。')
  if (info.has_mp_compat_patch) {
    parts.push(multiplayerCompatEffective.value
      ? 'Multiplayer Compatibility 中存在对应修正，当前已随该模组启用生效。'
      : 'Multiplayer Compatibility 中存在对应修正，启用该模组后可生效。')
  }
  if (info.notes) parts.push(`备注：${info.notes}`)
  return parts.join('\n')
})

const modType = computed(() => modStore.displayModType(modData.value))

// 可替换版本是否已经安装
const replacementInstalled = computed(() => {
    if (!modData.value?.replacement) return false
    return modStore.hasInstalledWorkshopId(modData.value.replacement.new_workshop_id)
})
// 可替换版本提示
const replacementTooltip = computed(() => {
    if (!modData.value?.replacement) return null
    if (replacementInstalled.value) {
      return `已安装可替换版本：##${modData.value.replacement.new_name}##（${modData.value.replacement.new_workshop_id}）`
    }
    return `存在可替换版本：##${modData.value.replacement.new_name}##（${modData.value.replacement.new_workshop_id}）\n可在右键菜单中订阅`
})
const canToggleCoexistSource = computed(() => !props.sectionHeader && modStore.canSwitchCoexistenceSource(props.item_id))
const isWorkshopCoexistSource = computed(() => modData.value?.source_preference === 'steam' || props.item_id.endsWith('_steam'))
const sourceToggleTooltip = computed(() => {
  const sourceLabel = SOURCE_TYPE_MAP[modData.value?.store] || modData.value?.store || '未知'
  if (!canToggleCoexistSource.value) {
    return `储存位置：${sourceLabel}`
  }
  return isWorkshopCoexistSource.value
    ? `储存位置：${sourceLabel}\n点击切换到本地版`
    : `储存位置：${sourceLabel}\n点击切换到工坊版`
})
const coexistSyncOutdated = computed(() => modData.value?.coexist_sync_state === 'outdated')
const coexistSyncTooltip = computed(() => (
  coexistSyncOutdated.value
    ? '工坊版本已更新，可右键同步本地共存模组'
    : '本地共存副本与工坊版本一致'
))
const modNoticeTooltip = computed(() => {
  const parts = []
  if (replacementTooltip.value) parts.push(replacementTooltip.value)
  if (coexistSyncOutdated.value) parts.push(coexistSyncTooltip.value)
  return parts.join('\n')
})
const modNoticeClass = computed(() => {
  if (coexistSyncOutdated.value) return 'text-accent-warn'
  return replacementInstalled.value ? 'text-text-dim' : 'text-accent-tip'
})
const handleSourceToggle = async () => {
  if (!canToggleCoexistSource.value) return
  await modStore.toggleCoexistenceSource(props.item_id)
}

// 错误提示
const issueState = computed(() => modStore.getModIssueState(props.item_id))
const issues = computed(() => modStore.modIssues.get(normalizePackageToken(props.item_id)))
const getCardClass = computed(() => {
    const select = props.isSelected ? 'ring-2 ring-accent-special ' : ''
    if (issueState.value === 'error') return `${select} border-accent-danger/40 border bg-accent-danger/10 hover:bg-accent-danger/20`
    if (issueState.value === 'warn') return `${select} border-accent-warn/40 border bg-accent-warn/10 hover:bg-accent-warn/20`
    return `${select} bg-bg-surface/20 border-border-base/10 hover:border-border-base/18 hover:bg-bg-overlay/10` // 原有的选中样式
})
const sectionHeaderClass = computed(() => {
  const select = props.isSelected ? 'ring-2 ring-accent-special ' : ''
  return `${select} bg-accent-${props.listColor}/12 border-accent-${props.listColor}/35 hover:bg-accent-${props.listColor}/20`
})
// 分割线项只替换局部内容，整体卡片仍复用普通项卡片样式体系。
const cardClass = computed(() => props.sectionHeader ? sectionHeaderClass.value : getCardClass.value)

// 构造提示文本
const issueTooltip = computed(() => {
    if (!issues.value) return null
    // console.log('问题:', issues.value)
    // 换行显示所有错误
    return issues.value.map(i => i.message).join('\n')
})

const linkIssueDetails = computed(() => modStore.interlockDetailsMap[modData.value?.interlock_id] || [])
// 联锁标识
const hasLockPrevious = computed(() => {
  if (!modData.value?.interlock_id) return false
  const chain = modStore.interlocksMap[modData.value.interlock_id]
  if (!chain) return false
  const myIdx = chain.findIndex(id => normalizePackageKey(id) === currentCanonicalId.value)
  return myIdx > 0 // 只要不是第一个，就应该有向上的链接头
})
const hasLockNext = computed(() => {
  if (!modData.value?.interlock_id) return false
  const chain = modStore.interlocksMap[modData.value.interlock_id]
  if (!chain) return false
  const myIdx = chain.findIndex(id => normalizePackageKey(id) === currentCanonicalId.value)
  return myIdx !== -1 && myIdx < chain.length - 1 // 只要不是最后一个，就应该有向下的链接头
})
const expectedPrevId = computed(() => {
  if (!hasLockPrevious.value) return null
  const chain = modStore.interlocksMap[modData.value.interlock_id]
  const myIdx = chain.findIndex(id => normalizePackageKey(id) === currentCanonicalId.value)
  return normalizePackageKey(chain[myIdx - 1])
})
const expectedNextId = computed(() => {
  if (!hasLockNext.value) return null
  const chain = modStore.interlocksMap[modData.value.interlock_id]
  const myIdx = chain.findIndex(id => normalizePackageKey(id) === currentCanonicalId.value)
  return normalizePackageKey(chain[myIdx + 1])
})
const linkWarn = computed(() => {
  if (!issues.value) return [false, false]
  let lockPrev = false
  let lockNext = false
  for (const issue of issues.value) {
    if (issue.type === ISSUE_TYPE.WARN_LINK_WRONG_ORDER || issue.type === ISSUE_TYPE.WARN_LINK_MOD_MISSING) {
      // 这里的 targetId 是在 modStore 里我们传入的“期待断裂点”的 ID
      if (expectedPrevId.value && normalizePackageKey(issue.targetId) === expectedPrevId.value) {
        lockPrev = true
      } else if (expectedNextId.value && normalizePackageKey(issue.targetId) === expectedNextId.value) {
        lockNext = true
      }
    }
  }
  return [lockPrev, lockNext]
})
const ensureInterlockDetails = async () => {
  // 旧实现会在每个可见 ModItem 挂载时立即 watch(linkWarn)，
  // 展开多个列表时会同时计算联锁链并触发后台详情查询，表现为列表刚显示就有一波额外响应式和 IO 压力。
  // 详情只服务于右键菜单里的修复操作，按需加载能保留功能，同时让普通滚动和空闲状态更轻。
  const [lockPrevWarn, lockNextWarn] = linkWarn.value
  const interlockId = modData.value?.interlock_id
  if ((!lockPrevWarn && !lockNextWarn) || !interlockId || modStore.interlockDetailsMap[interlockId]) return
  await modStore.loadInterlockDetails(interlockId)
}

const getCardStyle = (id) => {
  const base = { height: (props.simple ? appStore.scalePx(30) : appStore.scalePx(50))+'px', backgroundColor: 'rgba(var(--rgb-bg-highlight),0.3)' }
  // 分割线项保持固定高度，不参与普通模组的签名色着色逻辑。
  if (props.sectionHeader) return base
  const color = modStore.takeModById(id)?.sign_color
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
  if (props.sectionHeader) {
    // 分割线项双击改为折叠/展开，避免误触发普通模组的启用/停用语义。
    emit('toggle-section', props.item_id)
    return
  }
  if (appStore.settings.ui.double_click_active_mod) {
    modStore.changeModsActive(modStore.selectedIds, !isActive.value)
  }
}
// 点击处理
const handleClick = (e) => {
  if (e.altKey) { // Alt+左键是固定手势，但实际执行仍走命令系统，避免右键菜单和快捷键各写一套逻辑。
    commandStore.executeCommand('mods.editSelectedRule', { modId: props.item_id })
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
// 批量生成别名备注
const generateAliasNotes = async () => {
  const selectedMods = Array.isArray(modStore.selectedMods) ? modStore.selectedMods : []
  if (selectedMods.length === 0) return

  if (selectedMods.length === 1) {
    const mod = selectedMods[0]
    const packageId = normalizePackageId(mod?.package_id)
    if (!packageId) return
    const result = await aiStore.requestSingleModAliasGenerationResult({
      packageId,
      name: mod?.name || '',
      description: mod?.description || '',
      ownerType: 'mod_list',
    })
    if (!result) return
    await modStore.updateModUserData(result.package_id, {
      alias_name: String(result.alias_name || ''),
      notes: String(result.notes || ''),
    })
    return
  }

  const shouldSkipLanguagePacks = appStore.settings.skip_language_pack_alias_generation !== false
  const targetMods = shouldSkipLanguagePacks
    ? selectedMods.filter(mod => !modStore.isLanguagePackMod(mod))
    : selectedMods
  const skippedCount = selectedMods.length - targetMods.length
  if (targetMods.length === 0) {
    toast.info('已跳过语言包，没有需要批量生成别名备注的模组')
    return
  }
  if (skippedCount > 0) {
    toast.info(`已跳过 ${skippedCount} 个语言包模组`)
  }
  if (targetMods.length === 1) {
    const mod = targetMods[0]
    const packageId = normalizePackageId(mod?.package_id)
    if (!packageId) return
    const result = await aiStore.requestSingleModAliasGenerationResult({
      packageId,
      name: mod?.name || '',
      description: mod?.description || '',
      ownerType: 'mod_list',
    })
    if (!result) return
    await modStore.updateModUserData(result.package_id, {
      alias_name: String(result.alias_name || ''),
      notes: String(result.notes || ''),
    })
    return
  }

  await aiStore.startModAliasGenerationTask({
    mods: targetMods,
    ownerType: 'mod_list',
    needsReview: true,
  })
}
const COPY_INFO_FIELDS = [
  { key: 'name', label: '名称' },
  { key: 'package_id', label: '包名' },
  { key: 'workshop_id', label: '工坊ID' },
  { key: 'url', label: '网址' },
  { key: 'path', label: '路径' },
]
const normalizeCopyInfoValue = (value) => String(value ?? '').trim()
const getModCopyInfoValue = (mod, fieldKey) => {
  if (!mod) return ''
  if (fieldKey === 'name') return normalizeCopyInfoValue(mod.name)
  if (fieldKey === 'package_id') return normalizeCopyInfoValue(mod.package_id_raw || mod.package_id || mod.canonical_package_id)
  if (fieldKey === 'workshop_id') return normalizeCopyInfoValue(mod.workshop_id)
  if (fieldKey === 'path') return normalizeCopyInfoValue(mod.path)
  if (fieldKey === 'url') return normalizeCopyInfoValue(mod.url)
  return ''
}
const copyTextToClipboard = async (text, label) => {
  try {
    if (!navigator?.clipboard?.writeText) throw new Error('当前环境不支持剪贴板')
    await navigator.clipboard.writeText(text)
    toast.success(`已复制${label}`)
  } catch (error) {
    console.warn(`复制${label}失败:`, error)
    toast.error(toUserMessage(error?.message || error, `复制${label}失败。请检查剪贴板权限，或手动选中文本复制。`))
  }
}
const copySelectedModInfo = async (fieldKey, label, selectedIds = []) => {
  // 批量复制必须保留空值行，确保复制结果和当前选中顺序一一对应。
  const lines = (selectedIds || []).map(id => getModCopyInfoValue(modStore.takeModById(id), fieldKey))
  await copyTextToClipboard(lines.join('\n'), label)
}
// 右键菜单
const handleContextMenu = async (event) => {
  // console.log(issueState,issueState.value)
  // 检查是否选中，若未选中则添加到选中列表
  if (!modStore.selectedIds.includes(props.item_id)) {
    modStore.selectMods(props.item_id)
    await nextTick()
  }
  await ensureInterlockDetails()
  const selectedIds = modStore.selectedIds;
  const selectedCountStr = selectedIds.length>1?` (${selectedIds.length}项)`:''
  const singleSelectedMod = selectedIds.length === 1 ? modStore.takeModById(selectedIds[0]) : null
  const copyInfoMenuItems = COPY_INFO_FIELDS.map(field => ({
    label: field.label + selectedCountStr,
    icon: Copy,
    disabled: selectedIds.length === 1 && !getModCopyInfoValue(singleSelectedMod, field.key),
    action: () => copySelectedModInfo(field.key, field.label, [...selectedIds]),
  }))
  const selectedHasPathHash = modStore.selectedMods.some(m => !!m?.path_hash)
  const localizeSummary = modStore.resolveLocalizeCandidates(modStore.selectedMods, 'workshop')
  const selectedLocalizeCandidates = localizeSummary.candidates
  const selectedCoexistWorkshopCount = localizeSummary.existingCount
  const localizeMenuLabel = localizeSummary.actionTitle
  const localizeMenuIcon = selectedCoexistWorkshopCount > 0 ? RefreshCw : Copy
  const localizeCandidateCountStr = selectedLocalizeCandidates.length>1?` (${selectedLocalizeCandidates.length}项)`:''
  const coexistSelectedIds = selectedIds.filter(id => modStore.canSwitchCoexistenceSource(id))
  const coexistSelectedCountStr = coexistSelectedIds.length>1?` (${coexistSelectedIds.length}项)`:''
  modStore.lastSelectedMod=modStore.takeModById(props.item_id)  // 记录最后选中的模组
  // 获取统计信息
  const stats = modStore.selectedStats
  const selectedColor = typeof stats.color === 'string' && stats.color !== 'mixed'
    ? stats.color
    : (modData.value?.sign_color || null)
  const pickerColor = normalizeHexColor(selectedColor, DEFAULT_ACCENT_HEX)
  const sortedTagNames = sortTextByName(modStore.allModTags)
  const sortedGroups = sortByDisplayName(groupStore.groupList, group => group?.name)
  // 移动菜单
  const moveMenu = props.moveMenu
  const splitGroupTargets = moveMenu?.splitGroupTargets || []
  const moveMenuEnabled = !!moveMenu?.enabled
  const moveableWithinSplitGroup = !!moveMenu?.canMoveWithinSplitGroup
  const moveMenuItems = [
    { label: '列表顶部', icon: ChevronsUp, disabled: !moveMenuEnabled, action: () => emit('move-selected', { action: 'list-top' }) },
    { label: '列表底部', icon: ChevronsDown, disabled: !moveMenuEnabled, action: () => emit('move-selected', { action: 'list-bottom' }) },
    { label: '组内顶部', icon: ChevronUp, hidden: !moveableWithinSplitGroup, disabled: !moveMenuEnabled, action: () => emit('move-selected', { action: 'group-top' }) },
    { label: '组内底部', icon: ChevronDown, hidden: !moveableWithinSplitGroup, disabled: !moveMenuEnabled, action: () => emit('move-selected', { action: 'group-bottom' }) },
    ...splitGroupTargets.map(target => ({
      label: target.label || '其它分割组...',
      icon: BetweenHorizontalStart,
      hidden: !target.groups?.length,
      disabled: !moveMenuEnabled,
      children: (target.groups || []).map(group => ({
        label: `${group.label}${Number.isInteger(group.count) ? ` (${group.count}项)` : ''}`,
        action: () => emit('move-selected', { action: 'split-group', targetGroupId: group.groupId, targetListId: target.listId })
      }))
    }))
  ]
  // 通用菜单
  const commnMenuItems = [
    { commandId: 'mods.toggleSelectedActive', args: { modIds: [...selectedIds] }, labelOverride: (isActive.value?'停用':'启用') + selectedCountStr, icon: isActive.value? CircleSlash2:CircleCheckBig },
    { label: '标签管理'+ selectedCountStr , icon: Tag, disabled: !modStore.allModTags?.length, children: [{type: 'grid', columns: 5, label: '批量分配标签',
      children: sortedTagNames.map(tag => ({ state: stats.tags[tag] || null,
        label: '#'+tag, action: () => modStore.selectModsTag(tag)
      }))}]
    },
    { label: '分组管理'+ selectedCountStr, icon: Group, disabled: !groupStore.groupList?.length, children: [{type: 'grid', columns: 4, label: '批量加入分组',
      children: sortedGroups.map(group => ({ state: stats.groups[group.group_id] || null,
        label: group.name, color: group.color, bgColor: hexToRgba(group.color, 0.1), action: () => modStore.selectModsGroup(group.group_id)
      }))}]
    },
    { label: '标记颜色'+ selectedCountStr, icon: Palette, children: [{ type: 'grid', columns: 5, label: '批量设置颜色',
        children:[...Object.entries(MOD_SIGN_COLOR_MAP).map(([c, name]) => ({ tooltip: name, color: c,
            active: stats.color === c, action: () => modStore.setModsColor(selectedIds, c)
          })), { type: 'color-picker', color: pickerColor, tooltip: stats.color === 'mixed' ? '为当前多选项设置统一自定义颜色' : '自定义颜色',
            action: (color) => queueSetModsColor(selectedIds, normalizeHexColor(color, DEFAULT_ACCENT_HEX))
          }, { icon: X, color: 'transparent', tooltip: '清除', action: () => modStore.setModsColor(selectedIds, null) }
        ]
      }]
    },
    { label: '修改类型'+ selectedCountStr, icon: ChessPawn,
      children: [...Object.entries(MOD_TYPE_MAP).map(([key, value]) => ({
        icon: MOD_TYPE_ICON_MAP[key],
        label: value, action: () => modStore.setModsType(selectedIds, key)
      })),{ label: '恢复默认', icon: SquareX, level: 'warn', action: () => modStore.setModsType(selectedIds, null) }]
    },
    { label: '复制信息' + selectedCountStr, icon: Copy, children: copyInfoMenuItems },
    ...(moveMenu ? [{ label: '移动到' + selectedCountStr, icon: Redo2, children: moveMenuItems }] : []),
  ]
  
  // 单选菜单
  const singleMenuItems = [
    { divider: true },
    { commandId: 'mods.editSelectedRule', args: { modId: props.item_id }, labelOverride: '编辑规则', icon: PencilRuler, gesture: 'Alt+左键' },
    { commandId: 'mods.openSelectedUrl', args: { modId: props.item_id }, labelOverride: '访问网页', icon: ExternalLink },
    { label: 'Steam操作', icon: IconSteam, disabled: !modData.value.workshop_id, children: [
      { commandId: 'mods.openSelectedWorkshopPage', args: { modId: props.item_id }, labelOverride: '访问创意工坊', icon: IconSteam },
      { label: '订阅模组', disabled: (!!modData.value.workshop_id && !!modData.value.path), icon: Flag, action: () => appStore.subscribeWorkshopIds([modData.value.workshop_id]) },
      { commandId: 'mods.unsubscribeSelectedWorkshop', args: { modIds: [...selectedIds] }, labelOverride: '取消订阅'+ selectedCountStr, disabled: modData.value.store!=='workshop', icon: FlagOff },
      { commandId: 'mods.unsubscribeAndDeleteSelectedWorkshop', args: { modIds: [...selectedIds] }, labelOverride: '取订并删除'+ selectedCountStr, disabled: modData.value.store!=='workshop', icon: Trash2 },
    ]},
  ]
  if (modStore.selectedMods.some(m => !!m.replacement)) {
    const workshop_ids = modStore.selectedMods.filter(m => !!m.replacement).map(m => m.replacement.new_workshop_id)
    const _selectedCountStr = workshop_ids.length>1?` (${workshop_ids.length}项)`:''
    singleMenuItems.push(
      { label: '替代版本', icon: Cable, children:[
        { label: '访问创意工坊', icon: IconSteam, action: () => appStore.openSteamWorkshopById(modData.value.replacement.new_workshop_id) },
        { label: '跳转到替代模组',disabled: !replacementInstalled.value, icon: CornerUpRight, action: () => modStore.currentTargetId=modData.value.replacement.new_package_id },
        { label: '订阅替代版本'+ _selectedCountStr, icon: Flag, action: () => appStore.subscribeWorkshopIds(workshop_ids) },
        { label: '下载替代版本'+ _selectedCountStr, icon: Download, action: () => appStore.downloadWorkshopItems(workshop_ids) },
      ]}
    )
  }
  if (modStore.selectedMods.some(m => (m.isMissing || !m.path))) {
    const package_ids = modStore.selectedMods.filter(m => (m.isMissing || !m.path)).map(m => m.package_id)
    const workshop_ids = modStore.selectedMods.filter(m => (m.isMissing || !m.path)&&!!m.workshop_id).map(m => m.workshop_id)
    const _selectedCountStr = package_ids.length>1?` (${package_ids.length}项)`:''
    const _selectedCountStr2 = workshop_ids.length>1?` (${workshop_ids.length}项)`:''
    singleMenuItems.push(
      { label: '缺失处理', icon: CircleFadingPlus, children:[
        { label: '移除缺失项'+ _selectedCountStr, icon: Eraser, action: () => modStore.runListHistoryTransaction({ type: 'remove-missing-items', label: `移除 ${package_ids.length} 个缺失项`, trackedModIds: package_ids }, async () => modStore.removeUnavailableIdsCompletely(package_ids)) },
        { label: '订阅缺失项'+ _selectedCountStr2, disabled: workshop_ids.length === 0, icon: Flag, action: () => appStore.subscribeWorkshopIds(workshop_ids) },
        { label: '下载缺失项'+ _selectedCountStr2, disabled: workshop_ids.length === 0, icon: Download, action: () => appStore.downloadWorkshopItems(workshop_ids) },
      ]}
    )
  }
  // 文件处理菜单
  const fileMenuItems = [
    { divider: true },
    { commandId: 'mods.openSelectedFolder', args: { modId: props.item_id }, labelOverride: '打开文件夹', icon: FolderInput },
    { label: localizeMenuLabel + localizeCandidateCountStr, icon: localizeMenuIcon, disabled: !selectedLocalizeCandidates.length,
      action: () => modStore.localizeMods(localizeSummary.pathHashes, 'workshop', { existingCount: selectedCoexistWorkshopCount }) },
    { label: '切换共存版本', icon: SquaresExclude, disabled: !coexistSelectedIds.length,
      children: [
        { label: '切换为工坊版' + coexistSelectedCountStr, icon: IconSteam, action: () => modStore.switchCoexistenceSource(coexistSelectedIds, 'steam') },
        { label: '切换为本地版' + coexistSelectedCountStr, icon: FolderMinus, action: () => modStore.switchCoexistenceSource(coexistSelectedIds, 'local') },
      ]
    },
    { commandId: 'mods.disableSelectedFiles', args: { modIds: [...selectedIds] }, labelOverride: '禁用'+ selectedCountStr, icon: Lock, level: 'warn', disabled: !selectedHasPathHash },
    { commandId: 'mods.deleteSelectedFiles', args: { modIds: [...selectedIds] }, labelOverride: '删除'+ selectedCountStr, disabled: !modData.value.path, icon: Trash2 },
  ]

  // 多选菜单
  const selectedMenuItems = [
    { divider: true },
    { label: '生成别名备注'+ selectedCountStr, icon: BotMessageSquare, action: () => generateAliasNotes() },
    { label: '打包导出模组' + selectedCountStr, icon: Package,
      action: () => appStore.openCustomModExportDialog({
        title: `打包导出已选模组${selectedCountStr}`,
        description: '可按需附带依赖、联锁项和语言包。缺失磁盘文件的项会自动跳过并给出提示。',
        modIds: [...selectedIds],
        summary: `已选 ${selectedIds.length} 个模组，导出时会自动按当前激活版本或最新版本解析共存项。`,
      })
    },
    // 推荐导出只面向当前多选模组的介绍信息，不处理模组文件和依赖打包。
    { label: '导出推荐' + selectedCountStr, icon: MessageSquareHeart, disabled: selectedIds.length === 0,
      action: () => appStore.openRecommendationExportDialog({
        title: `推荐导出已选模组${selectedCountStr}`,
        sourceName: '已选模组',
        modIds: [...selectedIds],
      })
    },
  ]
  // 只要选中项中包含分割线模组，就允许直接批量展开/折叠。
  // 这里不要求“全部都是分组项”，因为用户常见操作是多选混合项后统一处理分组。
  const currentSplitGroup = props.currentSplitGroup || null
  const showCurrentSplitGroupMenu = props.sectionFeatureEnabled && currentSplitGroup?.headerId
  const showSelectedSplitGroupMenu = selectedSectionHeaderIds.value.length > 1
  const sectionGroupCount = Number(moveMenu?.sectionGroupCount || 0)
  const collapsedSectionGroupCount = Number(moveMenu?.collapsedSectionGroupCount || 0)
  const expandedSectionGroupCount = Math.max(0, sectionGroupCount - collapsedSectionGroupCount)
  const splitGroupMenuItems = [
    { divider: true, hidden: !showCurrentSplitGroupMenu && !showSelectedSplitGroupMenu },
    currentSplitGroup?.collapsed
      ? {
          label: `展开本分割组${currentSplitGroup?.label ? `：${currentSplitGroup.label}` : ''}`,
          icon: ChevronsUpDown,
          hidden: !showCurrentSplitGroupMenu,
          action: () => emit('expand-selected-sections', [currentSplitGroup.headerId]),
        }
      : {
          label: `折叠本分割组${currentSplitGroup?.label ? `：${currentSplitGroup.label}` : ''}`,
          icon: ChevronsDownUp,
          hidden: !showCurrentSplitGroupMenu,
          action: () => emit('collapse-selected-sections', [currentSplitGroup?.headerId]),
        },
    { label: '展开选中分割组' + ` (${selectedSectionHeaderIds.value.length}个)`, icon: ChevronsUpDown, hidden: !showSelectedSplitGroupMenu, action: () => emit('expand-selected-sections', selectedSectionHeaderIds.value) },
    { label: '折叠选中分割组' + ` (${selectedSectionHeaderIds.value.length}个)`, icon: ChevronsDownUp, hidden: !showSelectedSplitGroupMenu, action: () => emit('collapse-selected-sections', selectedSectionHeaderIds.value) },
    { label: `展开全部分割组${sectionGroupCount > 0 ? ` (${collapsedSectionGroupCount}个已折叠)` : ''}`, icon: ChevronsUpDown,
      hidden: !props.sectionFeatureEnabled || collapsedSectionGroupCount === 0, action: () => emit('expand-all-sections') },
    { label: `折叠全部分割组${sectionGroupCount > 0 ? ` (${expandedSectionGroupCount}个已展开)` : ''}`, icon: ChevronsDownUp,
      hidden: !props.sectionFeatureEnabled || expandedSectionGroupCount === 0, action: () => emit('collapse-all-sections') },
  ]
  const allInterlocked = modStore.selectedMods.every(m => m && m.interlock_id)
  if (!allInterlocked) {
    selectedMenuItems.push({ label: '创建联锁'+ selectedCountStr, icon: Link2, action: () => modStore.linkMods(selectedIds) })
  }
  const anyInterlocked = modStore.selectedMods.some(m => !!m.interlock_id)
  if (anyInterlocked) {
    selectedMenuItems.push({ label: '解除联锁'+ selectedCountStr, icon: Link2Off, action: () => modStore.unlinkMods(selectedIds) })
    const disabledIds = linkIssueDetails.value.filter(d => d.reason === 'disabled').map(d => d.package_id)
    const missingPackageIds = linkIssueDetails.value.filter(d => d.reason === 'missing' && d.package_id).map(d => d.package_id)
    if (missingPackageIds.length > 0) {
      selectedMenuItems.push({
        label: '缺失联锁项处理', icon: CircleFadingPlus, children:[
          // { label: '解除禁用联锁项', icon: LockOpen, level: 'warn',action: async () => modStore.healInterlock(modData.value.interlock_id) },
          { label: '剔除失效联锁项', icon: Eraser, level: 'warn',action: async () => modStore.healInterlock(modData.value.interlock_id) },
          { label: '订阅失效联锁项', icon: Flag, action: async () => appStore.subscribePackageIds(missingPackageIds) },
          { label: '下载失效联锁项', icon: Download, action: async () => appStore.downloadPackageIds(missingPackageIds) }
        ]
      })
    }
  }
  // 1. 获取所有选中 Mod 的当前问题并集
  const allSelectedIssues = selectedIds.flatMap(id => modStore.modIssues.get(normalizePackageToken(id)) || []);
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
  ...splitGroupMenuItems,
  ...singleMenuItems,
  ...(selectedIds.length > 1 ? selectedMenuItems : []),
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
