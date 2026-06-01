<template>
  <div class="relative flex h-full min-h-100 w-full flex-col overflow-hidden bg-bg-deep rounded-md">
    
    <!-- 1. 上方空间 -->
    <div class="relative z-20 flex flex-col items-center justify-end ">
      <!-- 上方内容插槽 -->
      <div class="px-5 pb-2">
        <slot name="top" />
      </div>
    </div>

    <!-- 2. 中间分界线与发光核心 (高度为0，仅作为定位锚点) -->
    <div class="relative z-10 h-0 w-full flex items-center justify-center">
      
      <!-- 核心光效容器：absolute定位，以免占据文档流高度 -->
      <!-- translate-y-0 保证光效从分界线开始 -->
      <div class="absolute top-0 w-full flex items-center justify-center pointer-events-none isolate">
        
        <!-- 左侧光束 (Conic Gradient) -->
        <div
          :style="{ backgroundImage: `conic-gradient(var(--conic-position), var(--tw-gradient-stops))` }"
          class="animate-conic-gradient absolute right-1/2 top-0 h-56 w-120 origin-top-right overflow-visible bg-linear-to-b from-accent-primary via-transparent to-transparent text-text-main opacity-50 [--conic-position:from_70deg_at_center_top]"
        >
          <div class="absolute bottom-0 left-0 z-20 h-40 w-full bg-bg-deep mask-[linear-gradient(to_top,white,transparent)]"></div>
          <div class="absolute bottom-0 left-0 z-20 h-full w-40 bg-bg-deep mask-[linear-gradient(to_right,white,transparent)]"></div>
        </div>

        <!-- 右侧光束 (Conic Gradient) -->
        <div
          :style="{ backgroundImage: `conic-gradient(var(--conic-position), var(--tw-gradient-stops))` }"
          class="animate-conic-gradient absolute left-1/2 top-0 h-56 w-120 origin-top-left bg-linear-to-b from-transparent via-transparent to-accent-primary text-text-main opacity-50 [--conic-position:from_290deg_at_center_top]"
        >
          <div class="absolute bottom-0 right-0 z-20 h-full w-40 bg-bg-deep mask-[linear-gradient(to_left,white,transparent)]"></div>
          <div class="absolute bottom-0 right-0 z-20 h-40 w-full bg-bg-deep mask-[linear-gradient(to_top,white,transparent)]"></div>
        </div>

        <!-- 背景模糊与遮罩 -->
        <div class="absolute top-0 h-48 w-full scale-x-150 bg-bg-deep blur-2xl"></div>
        <div class="absolute top-0 z-50 h-48 w-full bg-transparent opacity-10 backdrop-blur-md"></div>
        
        <!-- 中心高亮光晕 (Spotlight) -->
        <div class="absolute animate-glowing-linelight top-0 z-50 h-36 w-full max-w-md -translate-y-1/2 rounded-full bg-accent-primary opacity-50 blur-3xl"></div>
        
        <!-- 动态聚光灯 -->
        <div class="absolute top-0 z-30 flex w-full justify-center overflow-hidden pointer-events-none">
          <div class="animate-spotlight h-70 w-2/5 -translate-y-1/2 rounded-full bg-accent-primary blur-2xl"></div>
        </div>
        <!-- 发光线条 (The Glowing Line) - 也就是界限 -->
        <!-- translate-y-[-1px] 确保它在分界线正中心 -->
        <div class="animate-glowing-line absolute top-0 z-50 h-0.5 w-120 -translate-y-px bg-accent-primary shadow-[0_0_20px_2px_rgba(var(--rgb-accent-primary),0.6)]"></div>
      </div>
    </div>

    <!-- 3. 下方空间 (Flex-1 自动填充剩余空间) -->
    <div class="relative z-20 flex flex-1 flex-col items-center px-5 pt-2">
      <!-- 下方内容插槽 -->
      <slot name="bottom" />
    </div>

  </div>
</template>

<script lang="ts" setup>
import { computed } from "vue";

// 接收动画参数
const props = withDefaults(
  defineProps<{
    delay?: number;
    duration?: number;
  }>(),
  {
    delay: 0.5,
    duration: 0.8,
  }
);

// 计算CSS变量
const durationInSeconds = computed(() => `${props.duration}s`);
const delayInSeconds = computed(() => `${props.delay}s`);
</script>

<style scoped>
/* 聚光灯动画：宽度变宽，模拟灯光打开 */
.animate-spotlight {
  animation: spotlight-anim ease-in-out v-bind(durationInSeconds) forwards;
  /* animation: bilink-anim ease 10s infinite; */
  animation-delay: v-bind(delayInSeconds);
  opacity: 0; /* 初始隐藏 */
}

/* 发光线条动画：宽度变宽 */
.animate-glowing-line {
  animation: glowing-line-anim ease-in-out v-bind(durationInSeconds) forwards;
  animation-delay: v-bind(delayInSeconds);
  width: 0; /* 初始宽度 */
  opacity: 0;
}

/* 发光线条光晕动画：宽度变宽 */
.animate-glowing-linelight {
  animation: glowing-linelight-anim ease-in-out v-bind(durationInSeconds) forwards;
  animation-delay: v-bind(delayInSeconds);
  width: 0; /* 初始宽度 */
}

/* 锥形渐变光束动画：宽度变宽，透明度增加 */
.animate-conic-gradient {
  animation: conic-gradient-anim ease-in-out v-bind(durationInSeconds) forwards;
  animation-delay: v-bind(delayInSeconds);
  width: 0; /* 初始宽度 */
  opacity: 0;
}

/* Keyframes */
@keyframes spotlight-anim {
  0% {
    width: 0;
    opacity: 0;
  }
  10% {
    opacity: 1;
  }
  100% {
    width: 16rem; /* 对应 w-64 */
    opacity: 1;
  }
}

@keyframes bilink-anim {
  0% {
    opacity: 0.1;
  }
  5% {
    opacity: 0.2;
  }
  50% {
    opacity: 1;
  }
  95% {
    opacity: 0.2;
  }
  100% {
    opacity: 0.1;
  }
}

@keyframes glowing-line-anim {
  0% {
    width: 0;
    opacity: 0;
  }
  10% {
    opacity: 1;
  }
  100% {
    width: 30rem;
    opacity: 1;
  }
}

@keyframes glowing-linelight-anim {
  0% {
    width: 0;
  }
  10% {
    width: 5%;
  }
  100% {
    width: 100%;
  }
}

@keyframes conic-gradient-anim {
  0% {
    width: 0;
    opacity: 0;
  }
  10% {
    opacity: 0.5;
  }
  100% {
    width: 30rem;
    opacity: 1;
  }
}
</style>
