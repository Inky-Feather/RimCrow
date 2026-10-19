import { computed, shallowRef } from 'vue'
/**
 * 核心逻辑类，用于管理单个列表的交互状态
 */
class SelectionManager {
  constructor(el, binding) {
    this.el = el
    // 确保容器是 relative 定位，以便 absolute 选框参考
    if (getComputedStyle(this.el).position === 'static') {
      this.el.style.position = 'relative'
    }
    
    // 配置
    this.config = {
      data: [],         // 有序 ID 数组；响应式数组可原地更新，普通数组需替换引用。
      selectedIds: [],       // 当前选中的 ID 列表
      onSelect: null,        // 选中触发的回调 (ids, anchorId) => {}
      onClear: null,         // 清空触发的回调 () => {}

      enableKeyboardNav: false, 	// 键盘导航配置
      onNavigate: null, // 回调：(nextId, nextIndex, direction) => {}
      clickClass: 'select-trigger',  // 触发点击选择的类
      swipeClass: 'swipe-trigger',  // 触发划动选择的类
      clickMode: 'single', // 点击行为：single=单选，toggle=切换多选
      idAttribute: 'data-id',  // 存储ID的属性名
      getItemId: null, // 可选：自定义从 DOM 事件目标解析 ID，便于虚拟列表或复杂卡片复用
      getItemScope: null, // 可选：返回 ID 所属选择域，用于分组列表这类需要隔离连续选择的场景
      selectAllRequiresScope: false, // 可选：没有当前选择域时禁用 Ctrl+A，避免误选整棵虚拟列表
      ignoreClass: 'no-select', // 可选：命中该类名的区域直接放行，不参与点击/框选
      shouldIgnoreEvent: null, // 可选：(event) => boolean，用于调用方处理更复杂的忽略规则
      // 可自定义选框样式，支持 Tailwind 类名
      boxClass: 'absolute z-20 rounded border-2 border-dashed border-accent-special bg-accent-special/20 pointer-events-none transition-none',
      disabled: false  // 特定情况下禁止选择
    }
    this.data = shallowRef([])
    // 索引只依赖列表数据，选择变化不扫描列表；保留传入数组自身的响应式依赖。
    this.dataIndexMap = computed(() => new Map(this.data.value.map((id, index) => [String(id), index])))
    this.updateConfig(binding.value)

    // 运行时状态
    this.isMouseDown = false
    this.isDragging = false // 是否发生了拖拽位移
    this.isSwiping = false  // 是否正在划动框选
    this.startPos = { x: 0, y: 0 }
    // 划动(框选)模式状态
    this.swipeStartIndex = -1
    this.selectionSnapshot = new Set() // 记录划动开始前的选中状态
    // 视觉选框元素
    this.selectionBoxEl = null

    // 性能优化状态
    this.lastHoveredId = null // 【优化1】记录上一次经过的ID
    this.rafId = null         // 【优化2】rAF 句柄
    this.pendingPoint = null
    this.pendingItemId = null
    this.gestureIndex = null
    // 点击/连选状态
    this.anchorId = null // Shift 连选的锚点 ID (上一次点击的 ID)
    this.currentFocusId = null // 记录当前的光标位置，混合键鼠操作时非常重要
    // 目标类别缓存
    this.isSwipeTarget = false
    this.isClickTarget = false
    this.mouseDownItemId = null

    // 绑定上下文
    this.onMouseDown = this.onMouseDown.bind(this)
    this.onMouseMove = this.onMouseMove.bind(this)
    this.onMouseUp = this.onMouseUp.bind(this)
    this.onKeyDown = this.onKeyDown.bind(this) // 键盘监听
    // 原生拖拽可能不派发 mouseup；启动时结束点击候选，避免松手后继续框选或误改单选。
    this.cancelGesture = this.cancelGesture.bind(this)
    this.onGestureKeyDown = e => { if (e.key === 'Escape') this.cancelGesture() }

    // 事件绑定
    this.el.addEventListener('mousedown', this.onMouseDown)
    this.el.addEventListener('keydown', this.onKeyDown) // 绑定键盘事件
    this.el.addEventListener('dragstart', this.cancelGesture)
  }

  updateConfig(value) {
    if (!value) return
    this.config = { ...this.config, ...value }
    this.data.value = Array.isArray(this.config.data) ? this.config.data : []
    if (this.isMouseDown && (this.config.disabled || this.gestureIndex !== this.dataIndexMap.value)) this.cancelGesture()
  }

  // --- 辅助方法 ---
  // 获取事件目标对应的 Item ID
  getItemId(target) {
    if (!target || !this.el.contains(target)) return null
    if (typeof this.config.getItemId === 'function') {
      return this.config.getItemId(target, this.el)
    }
    const el = target.closest?.(`[${this.config.idAttribute}]`)
    return el && this.el.contains(el) ? el.getAttribute(this.config.idAttribute) : null
  }
  // 获取 ID 在数据中的索引位置
  getIndexById(id) {
    if (!this.config.data) return -1
    return this.dataIndexMap.value.get(String(id)) ?? -1
  }
  getItemScope(id) {
    if (!id || typeof this.config.getItemScope !== 'function') return null
    const scope = this.config.getItemScope(id)
    return scope == null ? null : String(scope)
  }
  filterIdsToScope(ids = [], scope = null) {
    if (scope == null || typeof this.config.getItemScope !== 'function') return [...ids]
    return ids.filter(id => this.getItemScope(id) === scope)
  }
  getScopedData(scope = null) {
    return this.filterIdsToScope(this.config.data || [], scope)
  }

  // --- 视觉选框逻辑 ---
  createSelectionBox() {
    if (this.selectionBoxEl) return
    this.selectionBoxEl = document.createElement('div')
    this.selectionBoxEl.className = this.config.boxClass
    this.selectionBoxEl.style.display = 'none'
    // 挂载到列表容器内部
    this.el.appendChild(this.selectionBoxEl)
  }

  updateSelectionBox(currentX, currentY) {
    if (!this.selectionBoxEl) return
    const rect = this.el.getBoundingClientRect()
    const startX = this.startPos.x - rect.left + this.startScrollLeft
    const startY = this.startPos.y - rect.top + this.startScrollTop
    // 指针离开列表时将选框限制在容器内，避免撑大滚动区域。
    const curX = Math.max(0, Math.min(currentX - rect.left, this.el.clientWidth)) + this.el.scrollLeft
    const curY = Math.max(0, Math.min(currentY - rect.top, this.el.clientHeight)) + this.el.scrollTop
    const style = this.selectionBoxEl.style
    style.display = 'block'
    style.left = `${Math.min(startX, curX)}px`
    style.top = `${Math.min(startY, curY)}px`
    style.width = `${Math.abs(curX - startX)}px`
    style.height = `${Math.abs(curY - startY)}px`
  }

  removeSelectionBox() {
    if (this.rafId) cancelAnimationFrame(this.rafId) // 清理未执行的动画帧
    this.rafId = null
    if (this.selectionBoxEl) {
      // 检查是否还在 DOM 中再移除
      if (this.el.contains(this.selectionBoxEl)) {
        this.el.removeChild(this.selectionBoxEl)
      }
      this.selectionBoxEl = null
    }
  }
  // --- 全选逻辑 ---
  onKeyDown(e) {
    if (this.config.disabled) return
    // 1. 全选逻辑 (Ctrl+A)
    // Ctrl + A 或 Meta + A
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
      e.preventDefault() // 阻止默认的全选文本行为
      // 如果列表为空，直接返回
      if (!this.config.data || this.config.data.length === 0) return
      // 执行全选，传入的是当前列表的所有 ID。
      // 如果调用方提供选择域，则 Ctrl+A 只选中当前锚点/焦点所在域，避免分组列表一次选中所有分组。
      // 调用回调函数，而不是操作 Store
      const scope = this.getItemScope(this.currentFocusId || this.anchorId)
      if (this.config.selectAllRequiresScope && scope == null) return
      const ids = this.getScopedData(scope)
      if (this.config.onSelect) this.config.onSelect(ids, this.currentFocusId || this.anchorId)
      return
    }
    // 2. 键盘上下导航逻辑
    if (this.config.enableKeyboardNav && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
      e.preventDefault() // 阻止默认的页面滚动
      if (!this.config.data || this.config.data.length === 0) return

      const direction = e.key === 'ArrowDown' ? 1 : -1
      // 确定当前光标从哪里开始找：优先 currentFocusId -> 然后 anchorId -> 最后取选中的最后一个
      let startId = this.currentFocusId || this.anchorId || this.config.selectedIds[this.config.selectedIds.length - 1]
      let currentIndex = this.getIndexById(startId)
      // 如果列表什么都没选中，根据方向决定是从头还是从尾开始
      if (currentIndex === -1) {
          currentIndex = direction === 1 ? -1 : this.config.data.length
      }
      let nextIndex = currentIndex + direction
      // 边界保护
      if (nextIndex < 0) nextIndex = 0
      if (nextIndex >= this.config.data.length) nextIndex = this.config.data.length - 1
      // 没发生位移（到底/到顶了）
      if (nextIndex === currentIndex && startId) return 
      const nextId = this.config.data[nextIndex]
      if (e.shiftKey) {
          // 【高级特性】：Shift + 方向键，实现原生系统的键盘连续拉黑框选
          this.handleRangeSelect(nextId, false)
      } else {
          // 普通方向键：变成单选
          if (this.config.onSelect) this.config.onSelect([nextId], nextId)
          this.anchorId = nextId // 不按 Shift 时，更新锚点
      }
      // 更新光标状态
      this.currentFocusId = nextId
      // 触发外部的回调，让外部组件（例如虚拟列表适配器）处理滚动对齐。
      // 指令只负责“选择语义”，不直接绑定某一个虚拟滚动库。
      if (this.config.onNavigate) {
          this.config.onNavigate(nextId, nextIndex, direction)
      }
    }
  }
  // --- 核心逻辑 ---
  // 处理鼠标按下事件
  onMouseDown(e) {
    if (this.config.disabled || e.button !== 0) return
    this.cancelGesture()
    // 通用忽略入口：复杂卡片里经常有按钮、输入框、颜色选择器等控件。
    // 调用方可以用 no-select 类名或 shouldIgnoreEvent 回调明确告诉指令“这里不是选择行为”。
    if (e.target.closest?.(`.${this.config.ignoreClass}`)) return
    if (typeof this.config.shouldIgnoreEvent === 'function' && this.config.shouldIgnoreEvent(e)) return

    // 修正输入框焦点
    if (document.activeElement instanceof HTMLElement && (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA')) {
      document.activeElement.blur()
    }

    const target = e.target
    const itemId = this.getItemId(target)
    // 点空白处清空选择。
    if (!itemId && target === this.el) {
      if (this.config.onClear) this.config.onClear()
      return
    }
    // 判断触发类型
    this.isSwipeTarget = !!target.closest(`.${this.config.swipeClass}`)
    this.isClickTarget = !!target.closest(`.${this.config.clickClass}`)
    // 如果不在触发区域内，直接放行（允许浏览器正常选文字等）
    if (!this.isSwipeTarget && !this.isClickTarget) return

    if (!itemId) return

    const isMulti = e.ctrlKey || e.metaKey
    const isRange = e.shiftKey

    // 阻止浏览器原生文字选中，防止破坏拖拽与连选判定
    if (this.isSwipeTarget || isRange || isMulti) {
      e.preventDefault()
    }
    this.isMouseDown = true
    this.gestureIndex = this.dataIndexMap.value
    // 只有手势期间监听全局移动和释放，避免每个空闲列表都处理 mousemove。
    document.addEventListener('mousemove', this.onMouseMove)
    document.addEventListener('mouseup', this.onMouseUp)
    window.addEventListener('blur', this.cancelGesture)
    window.addEventListener('keydown', this.onGestureKeyDown)
    this.isDragging = false
    this.isSwiping = false // 此时还没开始拖动，不算划动框选
    this.startPos = { x: e.clientX, y: e.clientY }
    this.mouseDownItemId = itemId
    // 记录按下瞬间的滚动位置
    this.startScrollTop = this.el.scrollTop
    this.startScrollLeft = this.el.scrollLeft

    // 如果当前区域支持划动，则先记录框选起点。
    // 注意：这里不立刻进入划动模式，而是等鼠标真正移动超过阈值后再切换，
    // 这样 clickClass 和 swipeClass 复用同一块区域时，点击与拖拽都能正常工作。
    if (this.isSwipeTarget) {
      this.swipeStartIndex = this.getIndexById(itemId)
      this.pendingItemId = itemId
      // 分组列表等场景会给 ID 配置选择域；跨域多选会让“从当前分组移除”等操作语义变得模糊。
      // 因此划动时只继承同一选择域内已有项，不把其它分组的选择带进来。
      this.selectionSnapshot = isMulti ? new Set(this.filterIdsToScope(this.config.selectedIds, this.getItemScope(itemId))) : new Set()
    }

    // 命中点击区域时，进入“点击候选”状态。
    // 如果该区域同时也支持划动，则把最终动作延迟到 mouseup 判定，避免抢占拖拽框选。
    if (this.isClickTarget) {
      // === 模式 B: 准备点击选择 ===
      // 这里不立即执行反选逻辑，而是根据情况决定是否立即选中
      
      const currentIds = this.config.selectedIds
      if (currentIds.length === 1 && currentIds[0] === itemId) {
        // 什么都不做，只更新一下系统光标锚点即可，绝不触发 onSelect
        this.anchorId = itemId
      } else {
        const isSelected = this.config.selectedIds.includes(itemId)
        if (this.config.clickMode === 'single' && !this.isSwipeTarget && !isMulti && !isRange && !isSelected) {
          // 场景：单选未选中的项 -> 立即选中（为了让用户能立刻拖拽它）
          if (this.config.onSelect) this.config.onSelect([itemId], itemId)
          this.anchorId = itemId 
        }
      }
      // 同步鼠标点击的最后一项为 Focus
      this.currentFocusId = itemId 
      // 对于已选中的项、或者 Ctrl/Shift 操作，逻辑推迟到 MouseUp
      // 这样做是为了区分 "点击" 和 "拖拽"
    }
  }
  // 处理鼠标移动事件
  onMouseMove(e) {
    if (!this.isMouseDown) return
    if (e.buttons === 0 || this.config.disabled || this.gestureIndex !== this.dataIndexMap.value) {
      this.cancelGesture()
      return
    }

    // 1. 检测拖拽阈值 (防止手抖误判为拖拽)
    if (!this.isDragging) {
      const dx = e.clientX - this.startPos.x
      const dy = e.clientY - this.startPos.y
      if (dx * dx + dy * dy > 25) { // 5px 阈值
        this.isDragging = true
        if (this.isSwipeTarget && !this.isSwiping) {
          // 超过阈值后才真正进入划动模式，兼容“点击”和“拖拽”复用同一区域的场景。
          this.isSwiping = true
          this.createSelectionBox()
          this.anchorId = this.mouseDownItemId
        }
      }
    }

    // 2. 处理划动框选逻辑
    if (this.isSwiping) {
      e.preventDefault()
      this.pendingPoint = { x: e.clientX, y: e.clientY }
      const itemId = this.getItemId(e.target)
      if (itemId && this.getItemScope(itemId) === this.getItemScope(this.mouseDownItemId)) {
        this.pendingItemId = itemId
      }
      if (!this.rafId) this.rafId = requestAnimationFrame(() => this.flushSwipe())
    }
  }

  flushSwipe() {
    if (this.rafId) cancelAnimationFrame(this.rafId)
    this.rafId = null
    if (!this.isSwiping) return
    if (this.config.disabled || this.gestureIndex !== this.dataIndexMap.value) {
      this.cancelGesture()
      return
    }
    // 选框和范围共用一帧，鼠标松开时也可同步提交最后一个有效落点。
    if (this.pendingPoint) this.updateSelectionBox(this.pendingPoint.x, this.pendingPoint.y)
    const itemId = this.pendingItemId
    if (itemId && itemId !== this.lastHoveredId && this.getIndexById(itemId) !== -1) {
      this.lastHoveredId = itemId
      this.updateSwipeRange(itemId)
    }
  }

  cancelGesture() {
    this.removeSelectionBox()
    this.pendingPoint = null
    this.pendingItemId = null
    this.lastHoveredId = null
    this.isSwiping = false
    this.isMouseDown = false
    this.isDragging = false
    this.isSwipeTarget = false
    this.isClickTarget = false
    this.swipeStartIndex = -1
    this.selectionSnapshot = new Set()
    this.mouseDownItemId = null
    this.gestureIndex = null
    document.removeEventListener('mousemove', this.onMouseMove)
    document.removeEventListener('mouseup', this.onMouseUp)
    window.removeEventListener('blur', this.cancelGesture)
    window.removeEventListener('keydown', this.onGestureKeyDown)
  }
  // 处理鼠标松开事件
  onMouseUp(e) {
    if (!this.isMouseDown) return
    if (this.config.disabled || this.gestureIndex !== this.dataIndexMap.value) {
      this.cancelGesture()
      return
    }
    if (this.isSwiping) {
      const itemId = this.getItemId(e.target)
      if (itemId && this.getItemScope(itemId) === this.getItemScope(this.mouseDownItemId)) this.pendingItemId = itemId
      this.flushSwipe()
    }
    const wasSwiping = this.isSwiping
    const wasDragging = this.isDragging
    const wasClickTarget = this.isClickTarget
    const mouseDownItemId = this.mouseDownItemId
    this.cancelGesture()
    // 如果是划动模式，松开即结束
    if (wasSwiping || wasDragging) {
      return
    }
    // === 处理纯点击逻辑 (Click End) ===
    // 只有在没有发生拖拽且没在划动时才触发
    // 获取目标 ID (因为绑定在 document 上，需要重新判断 target 是否在容器内)
    // 注意：e.target 可能在松开时已经不在 el 内了，但在正常的点击操作中，Down和Up通常在同一元素上
    if (!wasClickTarget) return
    const itemId = mouseDownItemId || this.getItemId(e.target)
    if (!itemId || !this.el.contains(e.target)) {
        return
    }

    const isMulti = e.ctrlKey || e.metaKey
    const isRange = e.shiftKey
    // 读取传入的 selectedIds
    const isSelected = this.config.selectedIds.includes(itemId)

    if (isRange) {
      // --- Shift 连选 (Windows 风格) ---
      // 从 anchorId 到 currentId
      this.handleRangeSelect(itemId, isMulti)
      
    } else if (isMulti || this.config.clickMode === 'toggle') {
      // --- Ctrl 多选 / 默认切换多选 ---
      const newSet = new Set(this.filterIdsToScope(this.config.selectedIds, this.getItemScope(itemId)))
      if (isSelected) newSet.delete(itemId)
      else newSet.add(itemId)
      if (newSet.size === 0) {
        if (this.config.onSelect) this.config.onSelect([], null)
        this.anchorId = null
      } else {
        if (this.config.onSelect) this.config.onSelect(Array.from(newSet), itemId)
        this.anchorId = itemId // 更新锚点
      }

    } else {
      // --- 单选 ---
      // 场景：点击已选中的项。
      // 在 MouseDown 时为了允许拖拽，没有取消其他项。
      // 现在确认是点击（非拖拽），所以清除其他项，只留这一个。
      if (this.config.onSelect) this.config.onSelect([itemId], itemId)
      this.anchorId = itemId
    }

    // 同步鼠标点击的最后一项为 Focus，这样键鼠混用时方向键才不会跳跃
    this.currentFocusId = itemId 
  }

  // --- 逻辑实现函数 ---

  /**
   * 划动框选核心算法
   * 逻辑：当前选中 = 快照 U (Start 到 Current 的范围)
   */
  updateSwipeRange(currentId) {
    if (this.getItemScope(this.mouseDownItemId) !== this.getItemScope(currentId)) return
    const currentIndex = this.getIndexById(currentId)
    if (currentIndex === -1 || this.swipeStartIndex === -1) return
    const focusChanged = this.currentFocusId !== currentId
    this.currentFocusId = currentId

    const min = Math.min(this.swipeStartIndex, currentIndex)
    const max = Math.max(this.swipeStartIndex, currentIndex)

    // 基于快照创建新的选中集合
    const newSelection = new Set(this.selectionSnapshot)
    
    // 将范围内的 ID 添加进去
    for (let i = min; i <= max; i++) {
      const id = this.config.data[i]
      if (id) newSelection.add(id)
    }
    // 焦点变化仍需通知调用方；联锁展开后的集合去重由业务 Store 处理。
    if (!focusChanged && this.setsAreEqual(newSelection, new Set(this.config.selectedIds))) {
        return
    }
    if (this.config.onSelect) this.config.onSelect(Array.from(newSelection), currentId)
  }

  // 辅助：Set 比较
  setsAreEqual(a, b) {
    if (a.size !== b.size) return false;
    for (const item of a) if (!b.has(item)) return false;
    return true;
  }
  
  // Shift 连选处理
  handleRangeSelect(targetId, keepOthers = false) {
    const targetScope = this.getItemScope(targetId)
    if (this.anchorId && this.getItemScope(this.anchorId) !== targetScope) {
        // 跨选择域 Shift 连选不做“穿透式范围选择”，否则分组 A 到分组 B 会把中间所有分组都选进去。
        // 这里退化为单选并重建锚点，符合“分组之间相互隔离”的操作语义。
        if (this.config.onSelect) this.config.onSelect([targetId], targetId)
        this.anchorId = targetId
        return
    }
    if (!this.anchorId || !this.dataIndexMap.value.has(String(this.anchorId))) {
        // 如果没有锚点，退化为单选并建立锚点
        if (this.config.onSelect) this.config.onSelect([targetId], targetId)
        this.anchorId = targetId
        return
    }
    // 基于索引范围计算，避免线性搜索
    // 这是一个优化，因为通常会在列表中按索引访问元素
    // 而不是按值搜索。这在大数据集时尤其重要。
    const start = this.getIndexById(this.anchorId)
    const end = this.getIndexById(targetId)
    // 检查索引是否有效
    if (start === -1 || end === -1) return
    const min = Math.min(start, end)
    const max = Math.max(start, end)
    let newSet
    if (keepOthers) {
        newSet = new Set(this.filterIdsToScope(this.config.selectedIds, targetScope))  // Ctrl+Shift
    } else {
        newSet = new Set() // 纯 Shift: 清空其他的
    }
    for (let i = min; i <= max; i++) {
        newSet.add(this.config.data[i])
    }
    if (this.config.onSelect) this.config.onSelect(Array.from(newSet), targetId)
    // 注意：Shift 连选通常不更新 Anchor，Anchor 依然停留在最初点击的那个位置
    // 这样可以连续调整范围 (例如: 点击1, Shift点10 -> 选中1-10; 保持Shift点5 -> 选中1-5)
  }

  destroy() {
    this.cancelGesture()
    this.el.removeEventListener('mousedown', this.onMouseDown)
    this.el.removeEventListener('keydown', this.onKeyDown) // 移除键盘监听
    this.el.removeEventListener('dragstart', this.cancelGesture)
  }
}

// Vue 指令定义
export const vSelectableList = {
  mounted(el, binding) {
    // 自动添加 tabindex 属性，确保元素可聚焦，从而接收键盘事件
    // 如果用户手动设置了 tabindex，则保留用户的设置
    if (!el.hasAttribute('tabindex')) {
      el.setAttribute('tabindex', '0')
    }
    // 添加 outline-none 类，防止聚焦时出现浏览器默认的黑框
    // 注意：这依赖于项目里有 tailwind 或类似的工具类
    el.classList.add('outline-none')
    el.__selectionManager__ = new SelectionManager(el, binding)
  },
  updated(el, binding) {
    // 数据更新时同步更新配置（主要是列表ID数据的更新）
    if (el.__selectionManager__) {
      el.__selectionManager__.updateConfig(binding.value)
    }
  },
  beforeUnmount(el) {
    if (el.__selectionManager__) {
      el.__selectionManager__.destroy()
      delete el.__selectionManager__
    }
  }
}
