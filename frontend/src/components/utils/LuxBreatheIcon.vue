<template>
  <!-- 外层容器：确保自动水平居中 -->
  <div class="w-full flex justify-center items-center py-10">
    
    <div class="relative group">
      <!-- 1. 背后氛围光晕 (暗色模式下的灵魂) -->
      <div class="absolute inset-0 rounded-full bg-accent-primary/10 blur-[30px] animate-lux-breathe-glow"></div>

      <!-- 2. 图标容器 -->
      <div class="relative z-10 flex items-center justify-center transition-transform duration-700 ease-in-out group-hover:scale-110">
        
        <!-- SVG 插入点 -->
        <div class="animate-lux-breathe-icon text-text-dim/30 drop-shadow-[0_0_10px_rgba(6,182,212,0.5)]">
          <slot>
            <!-- 默认占位图标 (奢华菱形) -->
            <svg width="60" height="60" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M24 4L44 24L24 44L4 24L24 4Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M24 14L34 24L24 34L14 24L24 14Z" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round" opacity="0.5"/>
            </svg>
          </slot>
        </div>

      </div>

      <!-- 3. 底部微妙的反光线 (增加质感) -->
      <div class="absolute -bottom-4 left-1/2 -translate-x-1/2 w-12 h-px bg-linear-to-r from-transparent via-accent-primary/40 to-transparent animate-lux-line"></div>
    </div>
    
  </div>
</template>

<style scoped>
/* 节奏：慢速 (4s) 是高级感的关键，快速则显廉价 */

@keyframes lux-breathe-icon {
  0%, 100% {
    transform: scale(0.90);
    opacity: 0.1;
    filter: blur(10px) brightness(0.8) drop-shadow(0 0 5px rgba(6, 182, 212, 0.2));
  }
  50% {
    transform: scale(1);
    opacity: 1;
    filter: blur(0px) brightness(1.2) drop-shadow(0 0 15px rgba(6, 182, 212, 0.6));
  }
  60% {
    transform: scale(1);
    opacity: 1;
    filter: blur(0px) brightness(1.2) drop-shadow(0 0 15px rgba(6, 182, 212, 0.6));
  }
}

@keyframes lux-breathe-glow {
  0%, 100% {
    transform: scale(0.8);
    opacity: 0.1;
  }
  50% {
    transform: scale(1.3);
    opacity: 0.3;
  }
}

@keyframes lux-line {
  0%, 100% { width: 10px; opacity: 0.1; }
  50% { width: 40px; opacity: 0.5; }
}

.animate-lux-breathe-icon {
  animation: lux-breathe-icon 8s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}

.animate-lux-breathe-glow {
  animation: lux-breathe-glow 8s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}

.animate-lux-line {
  animation: lux-line 8s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}
</style>