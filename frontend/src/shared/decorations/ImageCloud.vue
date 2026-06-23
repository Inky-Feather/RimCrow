<template>
  <canvas
    ref="canvasRef"
    :width="size"
    :height="size"
    :class="props.class"
    role="img"
    aria-label="Interactive 3D Image Cloud"
    @mousedown="handleMouseDown"
    @mousemove="handleMouseMove"
    @mouseup="handleMouseUp"
    @mouseleave="handleMouseUp"
  />
</template>

<script lang="ts" setup>
import { ref, onMounted, onBeforeUnmount, reactive, watch } from "vue";

// --- 内部类型定义 ---
interface SphereImage {
  x: number;
  y: number;
  z: number;
  id: number;
}

interface Props {
  images: string[];     // 图片地址列表
  size?: number;        // 画布大小
  imageSize?: number;   // 单个图片显示大小
  class?: string;
}

const props = withDefaults(defineProps<Props>(), {
  size: 300,
  imageSize: 40,
  class: ""
});

// --- 状态管理 ---
const canvasRef = ref<HTMLCanvasElement | null>(null);
const animationFrameRef = ref<number>(0);
const imageCanvases = ref<HTMLCanvasElement[]>([]);
const imagesLoaded = ref<boolean[]>([]);
const imagePositions = ref<SphereImage[]>([]);
let imageLoadBatch = 0;

const rotation = reactive({ x: 0, y: 0 });
const isDragging = ref(false);
const lastMousePos = reactive({ x: 0, y: 0 });
const mousePos = reactive({ x: 0, y: 0 });
const targetRotation = ref<{
  x: number; y: number; startX: number; startY: number; 
  distance: number; startTime: number; duration: number;
} | null>(null);

function easeOutCubic(t: number): number { return 1 - Math.pow(1 - t, 3); }

// --- 初始化图片 (离屏绘制) ---
watch(() => props.images, (newUrls) => {
  const batchId = ++imageLoadBatch;
  const urls = Array.isArray(newUrls) ? newUrls.filter(Boolean) : [];
  const radius = props.imageSize / 2;
  
  imagesLoaded.value = new Array(urls.length).fill(false);
  imagePositions.value = [];
  if (!urls.length) {
    imageCanvases.value = [];
    return;
  }

  imageCanvases.value = urls.map((url, idx) => {
    const offscreen = document.createElement("canvas");
    offscreen.width = props.imageSize;
    offscreen.height = props.imageSize;
    const offCtx = offscreen.getContext("2d");
    
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      if (batchId !== imageLoadBatch) return;
      if (!offCtx) return;
      // 绘制圆形裁剪
      offCtx.clearRect(0, 0, props.imageSize, props.imageSize);
      offCtx.beginPath();
      offCtx.arc(radius, radius, radius, 0, Math.PI * 2);
      offCtx.clip();
      offCtx.drawImage(img, 0, 0, props.imageSize, props.imageSize);
      imagesLoaded.value[idx] = true;
    };
    img.onerror = () => {
      if (batchId !== imageLoadBatch) return;
      imagesLoaded.value[idx] = false;
    };
    img.src = url;
    return offscreen;
  });

  // 分布算法 (斐波那契球体)
  const count = urls.length;
  const newPositions: SphereImage[] = [];
  const offset = 2 / count;
  const increment = Math.PI * (3 - Math.sqrt(5));

  for (let i = 0; i < count; i++) {
    const y = i * offset - 1 + offset / 2;
    const r = Math.sqrt(1 - y * y);
    const phi = i * increment;
    newPositions.push({
      x: Math.cos(phi) * r * 100,
      y: y * 100,
      z: Math.sin(phi) * r * 100,
      id: i,
    });
  }
  imagePositions.value = newPositions;
}, { immediate: true });

// --- 交互处理 ---
function handleMouseDown(e: MouseEvent) {
  const canvas = canvasRef.value;
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;

  // 点击检测：是否点击了某个图片，如果是则触发自动旋转聚焦
  const cosX = Math.cos(rotation.x);
  const sinX = Math.sin(rotation.x);
  const cosY = Math.cos(rotation.y);
  const sinY = Math.sin(rotation.y);

  imagePositions.value.forEach((icon) => {
    const rotatedX = icon.x * cosY - icon.z * sinY;
    const rotatedZ = icon.x * sinY + icon.z * cosY;
    const rotatedY = icon.y * cosX + rotatedZ * sinX;

    const screenX = props.size / 2 + rotatedX;
    const screenY = props.size / 2 + rotatedY;

    const scale = (rotatedZ + 200) / 300;
    const radius = (props.imageSize / 2) * scale;
    const dx = x - screenX;
    const dy = y - screenY;

    if (dx * dx + dy * dy < radius * radius) {
      targetRotation.value = {
        x: -Math.atan2(icon.y, Math.sqrt(icon.x * icon.x + icon.z * icon.z)),
        y: Math.atan2(icon.x, icon.z),
        startX: rotation.x,
        startY: rotation.y,
        distance: 0, // 仅做标志
        startTime: performance.now(),
        duration: 1000,
      };
    }
  });

  isDragging.value = true;
  lastMousePos.x = e.clientX;
  lastMousePos.y = e.clientY;
}

function handleMouseMove(e: MouseEvent) {
  const canvas = canvasRef.value;
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  mousePos.x = e.clientX - rect.left;
  mousePos.y = e.clientY - rect.top;

  if (isDragging.value) {
    rotation.y += (e.clientX - lastMousePos.x) * 0.005;
    rotation.x += (e.clientY - lastMousePos.y) * 0.005;
    lastMousePos.x = e.clientX;
    lastMousePos.y = e.clientY;
    targetRotation.value = null; // 拖拽时取消自动旋转
  }
}

const handleMouseUp = () => isDragging.value = false;

// --- 渲染循环 ---
onMounted(() => {
  const canvas = canvasRef.value;
  const ctx = canvas?.getContext("2d");
  if (!ctx || !canvas) return;

  const animate = () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;

    // 自动惯性旋转
    if (targetRotation.value) {
      const { startX, startY, x: tx, y: ty, startTime, duration } = targetRotation.value;
      const progress = Math.min(1, (performance.now() - startTime) / duration);
      const eased = easeOutCubic(progress);
      rotation.x = startX + (tx - startX) * eased;
      rotation.y = startY + (ty - startY) * eased;
      if (progress >= 1) targetRotation.value = null;
    } else if (!isDragging.value) {
      // 随鼠标位置微动
      rotation.x += (mousePos.y - centerY) * 0.00005;
      rotation.y += (mousePos.x - centerX) * 0.00005;
    }

    const positions = imagePositions.value;
    const cosX = Math.cos(rotation.x);
    const sinX = Math.sin(rotation.x);
    const cosY = Math.cos(rotation.y);
    const sinY = Math.sin(rotation.y);

    // 每帧只计算一次旋转结果，同时按深度从后往前绘制。
    const frameItems = positions
      .map((icon, index) => {
        const rotatedX = icon.x * cosY - icon.z * sinY;
        const rotatedZ = icon.x * sinY + icon.z * cosY;
        const rotatedY = icon.y * cosX + rotatedZ * sinX;
        return { index, rotatedX, rotatedY, rotatedZ };
      })
      .sort((a, b) => a.rotatedZ - b.rotatedZ);

    frameItems.forEach(({ index, rotatedX, rotatedY, rotatedZ }) => {
      if (!imageCanvases.value[index] || !imagesLoaded.value[index]) {
        return;
      }

      const scale = (rotatedZ + 200) / 300;
      const opacity = Math.max(0.1, Math.min(1, (rotatedZ + 150) / 200));

      ctx.save();
      ctx.translate(centerX + rotatedX, centerY + rotatedY);
      ctx.scale(scale, scale);
      ctx.globalAlpha = opacity;

      const offset = -(props.imageSize / 2);
      ctx.drawImage(imageCanvases.value[index], offset, offset);
      ctx.restore();
    });

    animationFrameRef.value = requestAnimationFrame(animate);
  };
  animate();
});

onBeforeUnmount(() => cancelAnimationFrame(animationFrameRef.value));
</script>
