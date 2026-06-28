/**
 * @file dragScroll.js
 * @description Vue 自定义指令，用于实现元素的拖拽滚动功能。
 *
 * ## 功能：
 * 1.  **鼠标拖拽滚动**：按住鼠标在元素上左右拖动以进行水平滚动。
 * 2.  **滚轮水平滚动** (可选): 可配置将垂直滚轮事件转换为水平滚动。
 * 3.  **键盘方向键滚动**：当元素聚焦时，可以使用左右方向键进行滚动。
 * 4.  **交互优化**：
 *     -   拖拽时鼠标样式变为 'grabbing'。
 *     -   拖拽时禁止文本选择，提升体验。
 *     -   当鼠标移出元素区域后，拖拽效果依然持续。
 *     -   忽略按钮、输入框等交互元素上的拖拽起始事件，保证其原生功能。
 *
 * ## 使用方法 (in a Vue component):
 *
 * ### 1. 注册指令
 * ```javascript
 * import dragScroll from '@/directives/dragScroll';
 *
 * export default {
 *   directives: {
 *     dragScroll
 *   }
 * }
 * ```
 *
 * ### 2. 在模板中使用
 *
 * #### 基础用法
 * <div v-drag-scroll>... content ...</div>
 *
 * #### 自定义滚动步长 (用于键盘滚动)
 * <div v-drag-scroll="50">... content ...</div>
 *
 * #### 高级配置 (对象形式)
 * <div v-drag-scroll="{ step: 50, wheelToHorizontal: true }">... content ...</div>
 *
 * ## 指令参数 (binding.value):
 * - **(无)**: 使用默认配置。
 * - **`Number`**: 自定义键盘滚动步长 (step)，单位为像素。
 * - **`Object`**:
 *   - `step` (Number): 键盘滚动步长。
 *   - `wheelToHorizontal` (Boolean): 是否将鼠标滚轮的垂直滚动转换为水平滚动。默认为 `false`。
 */
// drag-scroll.js
export default {
  mounted(el, binding) {
    const defaultOptions = {
      step: 30,
      wheelToHorizontal: false
    };

    const options = typeof binding.value === 'number' 
      ? { ...defaultOptions, step: binding.value } 
      : { ...defaultOptions, ...binding.value };

    // 初始化状态
    el._scrollState = {
      isDragging: false,
      startX: 0,
      startScrollLeft: 0,
      step: options.step,
      wheelToHorizontal: options.wheelToHorizontal
    };

    // --- 核心逻辑方法 ---

    el._scrollState.handleDragStart = (e) => {
      // 🟢 修复：如果点击的是按钮、输入框等交互元素，不触发拖拽，允许原生行为
      if (['BUTTON', 'INPUT', 'TEXTAREA', 'A'].includes(e.target.tagName)) {
        return; 
      }
      
      el._scrollState.isDragging = true;
      el._scrollState.startX = e.clientX;
      el._scrollState.startScrollLeft = el.scrollLeft;
      
      // 🟢 优化：只在拖拽开始时阻止默认行为（防止选中文字），但不阻止点击子元素
      // 注意：为了让 focus 生效，这里通常需要允许 mousedown 默认行为的一小部分，
      // 但为了体验，手动 focus，并阻止文本选择
      e.preventDefault(); 
      el.focus({ preventScroll: true }); // 手动聚焦，且防止浏览器自动跳动视口
      
      el.style.userSelect = 'none';
      el.style.cursor = 'grabbing';
    };

    el._scrollState.handleDragMove = (e) => {
      if (!el._scrollState.isDragging) return;
      const dx = e.clientX - el._scrollState.startX;
      el.scrollLeft = el._scrollState.startScrollLeft - dx;
    };

    el._scrollState.handleDragEnd = () => {
      if (!el._scrollState.isDragging) return;
      el._scrollState.isDragging = false;
      el.style.userSelect = '';
      el.style.cursor = 'grab';
    };

    el._scrollState.handleWheel = (e) => {
      if (el._scrollState.wheelToHorizontal) {
        e.preventDefault();
        el.scrollLeft += e.deltaY * 0.5; // 微调速度
      }
    };

    el._scrollState.handleKeydown = (e) => {
      const keyMap = { ArrowUp: -1, ArrowLeft: -1, ArrowDown: 1, ArrowRight: 1 };
      if (keyMap[e.key] !== undefined) {
        e.preventDefault();
        el.scrollLeft += keyMap[e.key] * el._scrollState.step;
      }
    };

    // --- 样式设置 ---
    el.style.cursor = 'grab';
    el.style.overflowX = 'auto'; // 确保本身是可滚动的
    el.style.overflowY = 'hidden';
    // 隐藏滚动条（可选，视需求而定）
    // el.style.scrollbarWidth = 'none'; 
    el.tabIndex = -1; // 允许聚焦

    // --- 绑定事件 ---
    el.addEventListener('mousedown', el._scrollState.handleDragStart);
    // 🟢 优化：Move 和 Up 绑在 window 上，防止鼠标移出元素后拖拽失效
    window.addEventListener('mousemove', el._scrollState.handleDragMove);
    window.addEventListener('mouseup', el._scrollState.handleDragEnd);
    
    el.addEventListener('wheel', el._scrollState.handleWheel, { passive: false });
    el.addEventListener('keydown', el._scrollState.handleKeydown);
    
    // 🟢 修复：删除了 mouseenter 自动聚焦的逻辑，改为点击时聚焦
  },

  unmounted(el) {
    if (!el._scrollState) return;

    el.removeEventListener('mousedown', el._scrollState.handleDragStart);
    window.removeEventListener('mousemove', el._scrollState.handleDragMove);
    window.removeEventListener('mouseup', el._scrollState.handleDragEnd);
    el.removeEventListener('wheel', el._scrollState.handleWheel);
    el.removeEventListener('keydown', el._scrollState.handleKeydown);

    delete el._scrollState;
  }
};