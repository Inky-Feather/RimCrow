<!-- ModItem.vue -->
<template>
  <div class="py-0.5 flex items-center gap-1 select-none" :data-id="item_id"
    @contextmenu="handleContextMenu">
    <!-- 序号（通过位数计算动态调整字体大小） -->
    <!-- :style="{ fontSize: 18-(index+1).toString().length*3 + 'px' }" -->
    <div v-if="showIndex" class="swipe-trigger w-6 h-6 min-w-6 min-h-6 flex items-center justify-center rounded"
      :class="[props.isSelected ? `text-text-main bg-accent-${listColor}/50` : `text-accent-${listColor}/50 bg-accent-${listColor}/10 hover:text-text-main hover:bg-accent-${listColor}/50`,
        `digits-${(index+1).toString().length}`, isInSearch ? ' ring-2 ring-accent-highlight' : '']">
      {{ index+1 }}
    </div>
    
    <!-- 内容区域 -->
    <div class="select-trigger drag-handle flex-1 flex items-center min-w-0 gap-1.5 p-1 rounded-lg border hover:opacity-90 backdrop-blur-sm group shadow-sm text-text-main/80"
      :class="[searchMatch ? 'ring-2 ring-accent-highlight scale-[1.02] z-20' : '', getCardClass, simple ? 'h-[30px]' : 'h-[50px]']" 
      :style="getCardStyle(item_id)"
      v-preview="modData">
      <!-- 图标 -->
      <div v-if="simple" class="flex items-center gap-1">
        <img v-if="!modData.is_missing && modData.thumb_url" :src="modData.thumb_url"
          :class="`w-5 h-5 rounded object-cover border border-accent-${listColor}/30 pointer-events-none`">
        <div v-else-if="modData.is_missing" class="w-5 h-5 rounded flex items-center justify-center text-red-500 font-bold text-lg bg-red-900/50 border border-red-500/30">!</div>
        <div v-else class="w-5 h-5 rounded border-2 border-dashed border-white/10 flex items-center justify-center">
          <svg class="w-3 h-3 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
        </div>
        <!-- 图标 -->
        <div class="flex items-center justify-center -mr-1">
          <!-- 类型图标 -->
          <span :class="[getModTypeClass, 'flex items-center justify-center']">
            <svg v-show="modType=='LanguagePack'" width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M28.2857 37H39.7143M42 42L39.7143 37L42 42ZM26 42L28.2857 37L26 42ZM28.2857 37L34 24L39.7143 37H28.2857Z" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 6L17 9" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 11H28" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 16C10 16 11.7895 22.2609 16.2632 25.7391C20.7368 29.2174 28 32 28 32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M24 11C24 11 22.2105 19.2174 17.7368 23.7826C13.2632 28.3478 6 32 6 32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="modType=='XML'" width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M16 13L4 25.4322L16 37" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M32 13L44 25.4322L32 37" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M28 4L21 44" stroke="currentColor" stroke-width="4" stroke-linecap="round"/></svg>
            <svg v-show="modType=='Assembly'" width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="6" y="6" width="36" height="36" rx="3" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M19 16V32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M29 16V32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 19H32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 29H32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="modType=='Texture'" width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M39 6H9C7.34315 6 6 7.34315 6 9V39C6 40.6569 7.34315 42 9 42H39C40.6569 42 42 40.6569 42 39V9C42 7.34315 40.6569 6 39 6Z" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M18 23C20.7614 23 23 20.7614 23 18C23 15.2386 20.7614 13 18 13C15.2386 13 13 15.2386 13 18C13 20.7614 15.2386 23 18 23Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M27.7901 26.2194C28.6064 25.1269 30.2528 25.1538 31.0329 26.2725L39.8077 38.8561C40.7322 40.182 39.7835 42.0001 38.1671 42.0001H16L27.7901 26.2194Z" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="modType=='Audio'" width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M30 34.5C30 32.567 31.567 31 33.5 31H41V34.4C41 36.3882 39.3882 38 37.4 38H33.5C31.567 38 30 36.433 30 34.5Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/><path d="M6 38.5C6 36.567 7.567 35 9.5 35H16V38.4C16 40.3882 14.3882 42 12.4 42H9.5C7.567 42 6 40.433 6 38.5Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/><path d="M16 18.044V18.044L41 12.125" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 38V10L41 4V33.6924" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="modType=='Mixed'" width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="16" y="16" width="27" height="27" rx="2" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><rect x="5" y="5" width="27" height="27" rx="2" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M27 16L16 27" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M32 21L21 32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="modType=='Unknown'" width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M39 6H9C7.34315 6 6 7.34315 6 9V39C6 40.6569 7.34315 42 9 42H39C40.6569 42 42 40.6569 42 39V9C42 7.34315 40.6569 6 39 6Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/><path d="M24 28.625V24.625C27.3137 24.625 30 21.9387 30 18.625C30 15.3113 27.3137 12.625 24 12.625C20.6863 12.625 18 15.3113 18 18.625" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path fill-rule="evenodd" clip-rule="evenodd" d="M24 37.625C25.3807 37.625 26.5 36.5057 26.5 35.125C26.5 33.7443 25.3807 32.625 24 32.625C22.6193 32.625 21.5 33.7443 21.5 35.125C21.5 36.5057 22.6193 37.625 24 37.625Z" fill="currentColor"/></svg>
          </span>
          <!-- 来源图标 -->
          <svg v-if="modData.source==='workshop'" width="18" height="18" class="fill-current -m-0.5" viewBox="0 0 640 640" xmlns="http://www.w3.org/2000/svg"><path d="M261.6 373.1C280.2 380.8 288.9 402 281.2 420.5C273.5 439 252.2 447.7 233.6 439.9L205.1 428.1C210.1 438.7 218.9 447.5 230.5 452.3C255.7 462.8 284.6 450.9 295.1 425.8C300.2 413.7 300.2 400.3 295.2 388.1C290.1 376 280.7 366.5 268.5 361.4C256.4 356.4 243.5 356.6 232.1 360.9L261.6 373.1zM544 160C544 124.7 515.3 96 480 96L160 96C124.7 96 96 124.7 96 160L96 304.7L212.6 352.8C224.6 344.6 238.8 340.7 253.3 341.5L308.7 261.3L308.7 260.2C308.7 212 348 172.7 396.3 172.7C444.6 172.7 483.9 212 483.9 260.2C483.9 309.4 443 348.9 394.3 347.7L315.3 404C316.9 442.5 286.2 472.8 249.6 472.8C217.8 472.8 191.1 450.1 185.1 420.1L96 383.2L96 480C96 515.3 124.7 544 160 544L480 544C515.3 544 544 515.3 544 480L544 160zM337.9 260.2C337.9 292.5 364 318.6 396.3 318.6C428.6 318.6 454.7 292.5 454.7 260.2C454.7 227.9 428.6 201.8 396.3 201.8C364 201.8 337.9 227.9 337.9 260.2zM440.3 260.1C440.3 284.3 420.6 304 396.4 304C372.2 304 352.5 284.3 352.5 260.1C352.5 235.9 372.2 216.2 396.4 216.2C420.6 216.2 440.3 235.9 440.3 260.1z"/></svg>
          <svg v-else-if="modData.source==='github'" width="18" height="18" class="fill-current -m-0.5" viewBox="0 0 640 640" xmlns="http://www.w3.org/2000/svg"><path d="M544 160C544 124.7 515.3 96 480 96L160 96C124.7 96 96 124.7 96 160L96 480C96 515.3 124.7 544 160 544L480 544C515.3 544 544 515.3 544 480L544 160zM361.8 471.7C361.8 469.9 361.8 465.7 361.9 460.1C362 448.7 362 431.3 362 416.4C362 400.8 356.8 390.9 350.7 385.7C387.7 381.6 426.7 376.5 426.7 312.6C426.7 294.4 420.2 285.3 409.6 273.6C411.3 269.3 417 251.6 407.9 228.6C394 224.3 362.2 246.5 362.2 246.5C335.6 239 305.6 239 279 246.5C279 246.5 247.2 224.3 233.3 228.6C224.2 251.5 229.8 269.2 231.6 273.6C221 285.3 216 294.4 216 312.6C216 376.2 253.3 381.6 290.3 385.7C285.5 390 281.2 397.4 279.7 408C270.2 412.3 245.9 419.7 231.4 394.1C222.3 378.3 205.9 377 205.9 377C189.7 376.8 204.8 387.2 204.8 387.2C215.6 392.2 223.2 411.4 223.2 411.4C232.9 441.1 279.3 431.1 279.3 431.1C279.3 440.1 279.4 452.8 279.4 461.7C279.4 466.5 279.5 470.3 279.5 471.7C279.5 476 276.5 481.2 268 479.7C202 457.6 155.8 394.8 155.8 321.4C155.8 229.6 226 159.9 317.8 159.9C409.6 159.9 484 229.6 484 321.4C484.1 394.8 439.3 457.7 373.3 479.7C364.9 481.2 361.8 476 361.8 471.7zM271.3 416.9C271.1 415.4 272.4 414.1 274.3 413.7C276.2 413.5 278 414.3 278.2 415.6C278.5 416.9 277.2 418.2 275.2 418.6C273.3 419 271.5 418.2 271.3 416.9zM262.2 420.1C260 420.3 258.5 419.2 258.5 417.7C258.5 416.4 260 415.3 262 415.3C263.9 415.1 265.7 416.2 265.7 417.7C265.7 419 264.2 420.1 262.2 420.1zM247.9 417.9C246 417.5 244.7 416 245.1 414.7C245.5 413.4 247.5 412.8 249.2 413.2C251.2 413.8 252.5 415.3 252 416.6C251.6 417.9 249.6 418.5 247.9 417.9zM235.4 410.6C233.9 409.3 233.5 407.4 234.5 406.5C235.4 405.4 237.3 405.6 238.8 407.1C240.1 408.4 240.6 410.4 239.7 411.2C238.8 412.3 236.9 412.1 235.4 410.6zM226.9 400.6C225.8 399.1 225.8 397.4 226.9 396.7C228 395.8 229.7 396.5 230.6 398C231.7 399.5 231.7 401.3 230.6 402.1C229.7 402.7 228 402.1 226.9 400.6zM220.6 391.8C219.5 390.5 219.3 389 220.2 388.3C221.1 387.4 222.6 387.9 223.7 388.9C224.8 390.2 225 391.7 224.1 392.4C223.2 393.3 221.7 392.8 220.6 391.8zM214.6 385.4C213.3 384.8 212.7 383.7 213.1 382.8C213.5 382.2 214.6 381.9 215.9 382.4C217.2 383.1 217.8 384.2 217.4 385C217 385.9 215.7 386.1 214.6 385.4z"/></svg>
          <svg v-else-if="['core','dlc'].includes(modData.source)" width="14" height="14" class="fill-current" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg"><circle cx="100" cy="100" r="90" fill="currentColor" stroke="currentColor" stroke-width="2"/><circle cx="100" cy="100" r="70" fill="#000" /><polygon points="100,48 118.27,74.85 149.46,83.93 129.57,109.61 130.57,142.07 100,131.09 69.43,142.07 70.43,109.61 50.54,83.93 81.73,74.85" fill="currentColor" stroke="currentColor" stroke-width="5"/><circle cx="100" cy="48" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="149.46" cy="83.93" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="130.57" cy="142.07" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="69.43" cy="142.07" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="50.54" cy="83.93" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/></svg>
          <svg v-else="modData.source==='local'" width="18" height="18" class="fill-current -m-0.5" viewBox="100 -20 420 640" xmlns="http://www.w3.org/2000/svg"><path d="M512 512L128 512C92.7 512 64 483.3 64 448L64 160C64 124.7 92.7 96 128 96L266.7 96C280.5 96 294 100.5 305.1 108.8L343.5 137.6C349 141.8 355.8 144 362.7 144L512 144C547.3 144 576 172.7 576 208L576 448C576 483.3 547.3 512 512 512zM248 304C234.7 304 224 314.7 224 328C224 341.3 234.7 352 248 352L392 352C405.3 352 416 341.3 416 328C416 314.7 405.3 304 392 304L248 304z"/></svg>
        </div>
      </div>
      <!-- 缩略图 -->
      <div v-else class="relative">
        <img v-if="!modData.is_missing && modData.thumb_url" :src="modData.thumb_url"
          :class="`w-10 h-8 rounded object-cover border border-accent-${listColor}/30 pointer-events-none`">
        <div v-else-if="modData.is_missing" class="w-8 h-8 rounded flex items-center justify-center text-red-500 font-bold text-lg bg-red-900/50 border border-red-500/30">!</div>
        <div v-else class="w-10 h-10 rounded border-2 border-dashed border-white/10 flex items-center justify-center">
          <svg class="w-6 h-6 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
        </div>
        
        <div class="absolute -top-2 -left-1 flex items-center justify-center ">
          <!-- 类型图标 -->
          <span :class="[getModTypeClass, 'flex items-center justify-center bg-glass-medium/60 rounded-sm mr-0.5']">
            <svg v-show="modType=='LanguagePack'" width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M28.2857 37H39.7143M42 42L39.7143 37L42 42ZM26 42L28.2857 37L26 42ZM28.2857 37L34 24L39.7143 37H28.2857Z" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 6L17 9" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 11H28" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 16C10 16 11.7895 22.2609 16.2632 25.7391C20.7368 29.2174 28 32 28 32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M24 11C24 11 22.2105 19.2174 17.7368 23.7826C13.2632 28.3478 6 32 6 32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="modType=='XML'" width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M16 13L4 25.4322L16 37" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M32 13L44 25.4322L32 37" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M28 4L21 44" stroke="currentColor" stroke-width="4" stroke-linecap="round"/></svg>
            <svg v-show="modType=='Assembly'" width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="6" y="6" width="36" height="36" rx="3" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M19 16V32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M29 16V32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 19H32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 29H32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="modType=='Texture'" width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M39 6H9C7.34315 6 6 7.34315 6 9V39C6 40.6569 7.34315 42 9 42H39C40.6569 42 42 40.6569 42 39V9C42 7.34315 40.6569 6 39 6Z" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M18 23C20.7614 23 23 20.7614 23 18C23 15.2386 20.7614 13 18 13C15.2386 13 13 15.2386 13 18C13 20.7614 15.2386 23 18 23Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M27.7901 26.2194C28.6064 25.1269 30.2528 25.1538 31.0329 26.2725L39.8077 38.8561C40.7322 40.182 39.7835 42.0001 38.1671 42.0001H16L27.7901 26.2194Z" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="modType=='Audio'" width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M30 34.5C30 32.567 31.567 31 33.5 31H41V34.4C41 36.3882 39.3882 38 37.4 38H33.5C31.567 38 30 36.433 30 34.5Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/><path d="M6 38.5C6 36.567 7.567 35 9.5 35H16V38.4C16 40.3882 14.3882 42 12.4 42H9.5C7.567 42 6 40.433 6 38.5Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/><path d="M16 18.044V18.044L41 12.125" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M16 38V10L41 4V33.6924" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="modType=='Mixed'" width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="16" y="16" width="27" height="27" rx="2" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><rect x="5" y="5" width="27" height="27" rx="2" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M27 16L16 27" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M32 21L21 32" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <svg v-show="modType=='Unknown'" width="15" height="15" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M39 6H9C7.34315 6 6 7.34315 6 9V39C6 40.6569 7.34315 42 9 42H39C40.6569 42 42 40.6569 42 39V9C42 7.34315 40.6569 6 39 6Z" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/><path d="M24 28.625V24.625C27.3137 24.625 30 21.9387 30 18.625C30 15.3113 27.3137 12.625 24 12.625C20.6863 12.625 18 15.3113 18 18.625" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path fill-rule="evenodd" clip-rule="evenodd" d="M24 37.625C25.3807 37.625 26.5 36.5057 26.5 35.125C26.5 33.7443 25.3807 32.625 24 32.625C22.6193 32.625 21.5 33.7443 21.5 35.125C21.5 36.5057 22.6193 37.625 24 37.625Z" fill="currentColor"/></svg>
          </span>
          <!-- 来源图标 -->
          <span class="flex items-center justify-center bg-glass-medium/70 rounded-sm">
            <svg v-if="modData.source==='workshop'" width="18" height="18" class="fill-current -m-0.5" viewBox="0 0 640 640" xmlns="http://www.w3.org/2000/svg"><path d="M261.6 373.1C280.2 380.8 288.9 402 281.2 420.5C273.5 439 252.2 447.7 233.6 439.9L205.1 428.1C210.1 438.7 218.9 447.5 230.5 452.3C255.7 462.8 284.6 450.9 295.1 425.8C300.2 413.7 300.2 400.3 295.2 388.1C290.1 376 280.7 366.5 268.5 361.4C256.4 356.4 243.5 356.6 232.1 360.9L261.6 373.1zM544 160C544 124.7 515.3 96 480 96L160 96C124.7 96 96 124.7 96 160L96 304.7L212.6 352.8C224.6 344.6 238.8 340.7 253.3 341.5L308.7 261.3L308.7 260.2C308.7 212 348 172.7 396.3 172.7C444.6 172.7 483.9 212 483.9 260.2C483.9 309.4 443 348.9 394.3 347.7L315.3 404C316.9 442.5 286.2 472.8 249.6 472.8C217.8 472.8 191.1 450.1 185.1 420.1L96 383.2L96 480C96 515.3 124.7 544 160 544L480 544C515.3 544 544 515.3 544 480L544 160zM337.9 260.2C337.9 292.5 364 318.6 396.3 318.6C428.6 318.6 454.7 292.5 454.7 260.2C454.7 227.9 428.6 201.8 396.3 201.8C364 201.8 337.9 227.9 337.9 260.2zM440.3 260.1C440.3 284.3 420.6 304 396.4 304C372.2 304 352.5 284.3 352.5 260.1C352.5 235.9 372.2 216.2 396.4 216.2C420.6 216.2 440.3 235.9 440.3 260.1z"/></svg>
            <svg v-else-if="modData.source==='github'" width="18" height="18" class="fill-current -m-0.5" viewBox="0 0 640 640" xmlns="http://www.w3.org/2000/svg"><path d="M544 160C544 124.7 515.3 96 480 96L160 96C124.7 96 96 124.7 96 160L96 480C96 515.3 124.7 544 160 544L480 544C515.3 544 544 515.3 544 480L544 160zM361.8 471.7C361.8 469.9 361.8 465.7 361.9 460.1C362 448.7 362 431.3 362 416.4C362 400.8 356.8 390.9 350.7 385.7C387.7 381.6 426.7 376.5 426.7 312.6C426.7 294.4 420.2 285.3 409.6 273.6C411.3 269.3 417 251.6 407.9 228.6C394 224.3 362.2 246.5 362.2 246.5C335.6 239 305.6 239 279 246.5C279 246.5 247.2 224.3 233.3 228.6C224.2 251.5 229.8 269.2 231.6 273.6C221 285.3 216 294.4 216 312.6C216 376.2 253.3 381.6 290.3 385.7C285.5 390 281.2 397.4 279.7 408C270.2 412.3 245.9 419.7 231.4 394.1C222.3 378.3 205.9 377 205.9 377C189.7 376.8 204.8 387.2 204.8 387.2C215.6 392.2 223.2 411.4 223.2 411.4C232.9 441.1 279.3 431.1 279.3 431.1C279.3 440.1 279.4 452.8 279.4 461.7C279.4 466.5 279.5 470.3 279.5 471.7C279.5 476 276.5 481.2 268 479.7C202 457.6 155.8 394.8 155.8 321.4C155.8 229.6 226 159.9 317.8 159.9C409.6 159.9 484 229.6 484 321.4C484.1 394.8 439.3 457.7 373.3 479.7C364.9 481.2 361.8 476 361.8 471.7zM271.3 416.9C271.1 415.4 272.4 414.1 274.3 413.7C276.2 413.5 278 414.3 278.2 415.6C278.5 416.9 277.2 418.2 275.2 418.6C273.3 419 271.5 418.2 271.3 416.9zM262.2 420.1C260 420.3 258.5 419.2 258.5 417.7C258.5 416.4 260 415.3 262 415.3C263.9 415.1 265.7 416.2 265.7 417.7C265.7 419 264.2 420.1 262.2 420.1zM247.9 417.9C246 417.5 244.7 416 245.1 414.7C245.5 413.4 247.5 412.8 249.2 413.2C251.2 413.8 252.5 415.3 252 416.6C251.6 417.9 249.6 418.5 247.9 417.9zM235.4 410.6C233.9 409.3 233.5 407.4 234.5 406.5C235.4 405.4 237.3 405.6 238.8 407.1C240.1 408.4 240.6 410.4 239.7 411.2C238.8 412.3 236.9 412.1 235.4 410.6zM226.9 400.6C225.8 399.1 225.8 397.4 226.9 396.7C228 395.8 229.7 396.5 230.6 398C231.7 399.5 231.7 401.3 230.6 402.1C229.7 402.7 228 402.1 226.9 400.6zM220.6 391.8C219.5 390.5 219.3 389 220.2 388.3C221.1 387.4 222.6 387.9 223.7 388.9C224.8 390.2 225 391.7 224.1 392.4C223.2 393.3 221.7 392.8 220.6 391.8zM214.6 385.4C213.3 384.8 212.7 383.7 213.1 382.8C213.5 382.2 214.6 381.9 215.9 382.4C217.2 383.1 217.8 384.2 217.4 385C217 385.9 215.7 386.1 214.6 385.4z"/></svg>
            <svg v-else-if="['core','dlc'].includes(modData.source)" width="14" height="14" class="fill-current" viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg"><circle cx="100" cy="100" r="90" fill="currentColor" stroke="currentColor" stroke-width="2"/><circle cx="100" cy="100" r="70" fill="#000" /><polygon points="100,48 118.27,74.85 149.46,83.93 129.57,109.61 130.57,142.07 100,131.09 69.43,142.07 70.43,109.61 50.54,83.93 81.73,74.85" fill="currentColor" stroke="currentColor" stroke-width="5"/><circle cx="100" cy="48" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="149.46" cy="83.93" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="130.57" cy="142.07" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="69.43" cy="142.07" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/><circle cx="50.54" cy="83.93" r="10" fill="currentColor" stroke="currentColor" stroke-width="3"/></svg>
            <svg v-else="modData.source==='local'" width="18" height="18" class="fill-current -m-0.5" viewBox="100 -20 420 640" xmlns="http://www.w3.org/2000/svg"><path d="M512 512L128 512C92.7 512 64 483.3 64 448L64 160C64 124.7 92.7 96 128 96L266.7 96C280.5 96 294 100.5 305.1 108.8L343.5 137.6C349 141.8 355.8 144 362.7 144L512 144C547.3 144 576 172.7 576 208L576 448C576 483.3 547.3 512 512 512zM248 304C234.7 304 224 314.7 224 328C224 341.3 234.7 352 248 352L392 352C405.3 352 416 341.3 416 328C416 314.7 405.3 304 392 304L248 304z"/></svg>
          </span>
        </div>

        <div class="absolute -bottom-2 -left-0.5 flex items-center justify-center ">
          <span class="text-[10px] text-text-dim truncate font-mono bg-glass-medium/70 rounded-sm">
            {{ modData.supported_versions.at(-1) }}
          </span>
        </div>
      </div>

      <!-- 文字信息 -->
      <div class="flex-1 min-w-0">
        <!-- 别名 -->
        <div v-if="modData.alias_name && !simple" class="text-[10px] text-text-dim truncate font-mono ">
          {{ modData.name }}
        </div>
        <!-- 主名称 -->
        <div class="text-[13px] font-medium truncate">
          {{ modData.alias_name ? modData.alias_name : (modData.name ? modData.name : item_id) }}
        </div>
        <!-- 标签 -->
        <div class="overflow-hidden" style="box-shadow: inset 8px 0 10px -8px rgba(0, 0, 0, 0.3), inset -8px 0 10px -8px rgba(0, 0, 0, 0.3);">
          <div v-if="modData?.tags && modData.tags.length && !simple" class="flex gap-0.5 w-full overflow-y-hidden overflow-x-scroll custom-scrollbar mt-0.5 outline-none ">
              <span v-for="tag in modData.tags" :key="tag" class="min-w-fit font-mono px-0.5 py-0 my-0 rounded-md bg-accent-primary/10 text-accent-primary text-[10px] font-bold border border-accent-primary/10 drop-shadow-xl/25">
                {{ tag }}
              </span>
          </div>
        </div>
        
      </div>
      
      <!-- 缺失警告 -->
      <div v-if="issueState" :class="[`rounded-4xl cursor-help text-xs font-bold
        hover:scale-110  text-shadow-2xs text-shadow-black hover:shadow-bg-deep/50 transition-all`,
        issueState === 'error' ? 'text-accent-danger' : issueState === 'warn'? 'text-accent-warn':'text-accent-primary']"
        v-tooltip="issueTooltip">
        <svg width="18" height="18" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-triangle-alert-icon lucide-triangle-alert">
          <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>
        </svg>
      </div>

      <!-- 分组颜色条 -->
      <div v-if="modGroups.length" class="w-1.5 -m-1 h-[-webkit-fill-available] relative">
        <div class="w-full absolute right-0 inset-y-0 flex flex-col scale-95">
          <div v-for="(g, index) in modGroups" :key="g.id" @click.prevent.stop="console.log(g)"
            :class="[`w-full flex-1 hover:scale-120 transition-all hover:border hover:border-white`,index===modGroups.length-1?'rounded-br-lg':'',index===0?'rounded-tr-lg':'']" 
            :style="{'backgroundColor': g.color}" v-tooltip="`分组：${g.name}`"
            v-preview="{component: GroupItem, props: {id: g.group_id, index: 0, groupData: g, expanded: true}}">
          </div><!-- 悬浮显示分组信息 -->
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useModStore } from '../../stores/modStore'
import { useContextMenuStore } from '../../stores/contextMenuStore'
import GroupItem from './GroupItem.vue'

const props = defineProps({
  item_id: { type: String, required: true },
  index: { type: Number, required: true },
  showIndex: { type: Boolean, default: true },
  simple: { type: Boolean, default: false },
  listColor: { type: String, default: 'primary'}, // 用于不同列表的颜色区分
  isSelected: { type: Boolean, default: false },
  isDragging: { type: Boolean, default: false }, // 用于外部控制样式
  isInSearch: { type: Boolean, default: false }, // 是否在搜索结果中
  searchMatch: { type: Boolean, default: false } // 是否是当前搜索焦点
})

defineEmits(['contextmenu'])

const store = useModStore()
const menuStore = useContextMenuStore()

// 使用 computed 缓存，只有当 id 变化时才重新获取对象
// 极大地减少了父组件重绘时的计算量
const modData = computed(() => store.takeModById(props.item_id))
const modGroups = computed(() => store.takeGroupsByModId(props.item_id))
// const modIcon = computed(() => store.getIconUrl(props.id))

const modType = computed(() => store.displayModType(modData.value))

// 构造提示文本
const issueTooltip = computed(() => {
    if (!issues.value) return null
    // 换行显示所有错误
    return issues.value.map(i => i.message).join('\n')
})

// 错误提示
const issueState = computed(() => store.getModIssueState(props.item_id))
const issues = computed(() => store.modIssues.get(props.item_id.toLowerCase()))
const getCardClass = computed(() => {
    const select = props.isSelected ? 'ring-2 ring-accent-special ' : ''
    if (issueState.value === 'error') return `${select} border-accent-danger/40 border bg-accent-danger/10 hover:bg-accent-danger/20`
    if (issueState.value === 'warn') return `${select} border-accent-warn/40 border bg-accent-warn/10 hover:bg-accent-warn/20`
    return `${select} bg-bg-surface border-white/10 hover:border-white/20 hover:bg-[#2d3a4f]` // 原有的选中样式
})

const getModTypeClass = computed(() => {
  if (modType.value === 'XML') return 'text-accent-success'
  else if (modType.value === 'Assembly') return 'text-accent-primary'
  else if (modType.value === 'Mixed') return 'text-accent-cool'
  else if (modType.value === 'LanguagePack') return 'text-accent-warn'
  else if (modType.value === 'Texture') return 'text-accent-special'
  else if (modType.value === 'Audio') return 'text-accent-highlight'
  else if (modType.value === 'Unknown') return 'text-accent-primary'
  return ''
})

const getCardStyle = (id) => {
  const base = {'--drag-color': `var(--color-accent-${props.listColor})`}
  const color = store.takeModById(id).sign_color
  if (!color) return base
  base['--mod-color'] = hexToRgb(color)
  if(!issueState.value) { // 防止覆盖错误样式
    base['backgroundColor'] = `rgba(${hexToRgb(color)},0.1)`
  }
  base['borderColor'] = `rgba(${hexToRgb(color)},0.3)`
  base['color'] = color
  return base
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

// 右键菜单
const handleContextMenu = (event) => {
  // console.log(issueState,issueState.value)
  const menuItems = [
    { label: '打开文件夹', action: () => openFolder() },
    { divider: true },
    { label: '删除', level: 'danger', action: () => deleteMod() },
  ]
  const currentIssues = store.modIssues.get(props.item_id.toLowerCase())
  // 如果有错误，添加忽略选项
  if (currentIssues && currentIssues.length > 0) {
      menuItems.push({ divider: true })
      // 子菜单列出所有错误
      menuItems.push({
          label: '忽略警告...',
          children: currentIssues.map(issue => ({
              label: `忽略问题：${store.ISSUE_TITLE_MAP[issue.type] || issue.type}`,
              level: issue.level,
              action: () => store.ignoreIssue(props.item_id, issue.type)
          }))
      })
  }
  // 如果已经忽略，添加启用提示
  if (modData.value.ignored_issues && modData.value.ignored_issues.length > 0) {
      menuItems.push({
          label: '恢复警告',
          level: 'warn',
          action: () => store.ignoreIssue(props.item_id)
      })
  }

  menuItems.push({
      label: '修改类型',
      children: Object.entries(store.modTypeMap).map(([key, value]) => ({
        label: value,
        action: () => store.updateModUserData(props.item_id, {user_mod_type: key})
      }))
  })
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