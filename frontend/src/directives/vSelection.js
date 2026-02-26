import { useModStore } from '../stores/modStore'

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
    this.modStore = useModStore()
    
    // 配置
    this.config = {
      data: [],         // 必须传入有序的 ID 列表，用于计算范围
      clickClass: 'select-trigger',  // 触发点击选择的类
      swipeClass: 'swipe-trigger',  // 触发滑动选择的类
      idAttribute: 'data-id',  // 存储ID的属性名
      // 可自定义选框样式，支持 Tailwind 类名
      boxClass: 'absolute z-9999 rounded border-2 border-dashed border-accent-special bg-accent-special/20 pointer-events-none transition-none',
      disabled: false  // 特定情况下禁止选择
    }
    this.updateConfig(binding.value)

    // 运行时状态
    this.isMouseDown = false
    this.isDragging = false // 是否发生了拖拽位移
    this.startPos = { x: 0, y: 0 }
    
    // 滑动(框选)模式状态
    this.isSwiping = false
    this.swipeStartIndex = -1
    this.selectionSnapshot = new Set() // 记录滑动开始前的选中状态
    // 视觉选框元素
    this.selectionBoxEl = null

    // 性能优化状态
    this.lastHoveredId = null // 【优化1】记录上一次经过的ID
    this.rafId = null         // 【优化2】rAF 句柄
    // 点击/连选状态
    this.anchorId = null // Shift 连选的锚点 ID (上一次点击的 ID)

    // 绑定上下文
    this.onMouseDown = this.onMouseDown.bind(this)
    this.onMouseMove = this.onMouseMove.bind(this)
    this.onMouseUp = this.onMouseUp.bind(this)
    this.onKeyDown = this.onKeyDown.bind(this) // 键盘监听

    // 事件绑定
    this.el.addEventListener('mousedown', this.onMouseDown)
    this.el.addEventListener('keydown', this.onKeyDown) // 绑定键盘事件
    // 绑定到 document 以处理移出容器后的释放
    document.addEventListener('mousemove', this.onMouseMove) 
    document.addEventListener('mouseup', this.onMouseUp)
  }

  updateConfig(value) {
    if (!value) return
    this.config = { ...this.config, ...value }
  }

  // --- 辅助方法 ---
  // 获取事件目标对应的 Item ID
  getItemId(target) {
    const el = target.closest(`[${this.config.idAttribute}]`)
    return el ? el.getAttribute(this.config.idAttribute) : null
  }
  // 获取 ID 在数据中的索引位置
  getIndexById(id) {
    if (!this.config.data) return -1
    return this.config.data.indexOf(id)
  }

  // --- 视觉选框逻辑 (新增) ---
  createSelectionBox() {
    if (this.selectionBoxEl) return
    this.selectionBoxEl = document.createElement('div')
    this.selectionBoxEl.className = this.config.boxClass
    this.selectionBoxEl.style.display = 'none'
    // 修改点：挂载到列表容器内部
    this.el.appendChild(this.selectionBoxEl)
  }

  updateSelectionBox(currentX, currentY) {
    if (!this.selectionBoxEl) return
    // 【优化2】使用 rAF 避免在一帧内多次重排
    if (this.rafId) cancelAnimationFrame(this.rafId)

    this.rafId = requestAnimationFrame(() => {
        // 获取容器当前的实时位置
        const rect = this.el.getBoundingClientRect()
        const scrollTop = this.el.scrollTop
        const scrollLeft = this.el.scrollLeft

        const startX = (this.startPos.x - rect.left) + this.startScrollLeft
        const startY = (this.startPos.y - rect.top) + this.startScrollTop
        
        const curX = (currentX - rect.left) + scrollLeft
        const curY = (currentY - rect.top) + scrollTop

        // 计算矩形几何属性
        // left/top 取最小坐标，width/height 取坐标差绝对值
        const left = Math.min(startX, curX)
        const top = Math.min(startY, curY)
        const width = Math.abs(curX - startX)
        const height = Math.abs(curY - startY)

        // 更新样式 (使用 transform 可能会更流畅，但 top/left 在选框场景下足够且不易出错)
        if (this.selectionBoxEl) {
            this.selectionBoxEl.style.display = 'block'
            // 使用 transform 可能会比 top/left 性能更好一点，但在 fixed 场景下 top/left 兼容性更好且直观
            this.selectionBoxEl.style.left = `${left}px`
            this.selectionBoxEl.style.top = `${top}px`
            this.selectionBoxEl.style.width = `${width}px`
            this.selectionBoxEl.style.height = `${height}px`
        }
    })
  }

  removeSelectionBox() {
    if (this.rafId) cancelAnimationFrame(this.rafId) // 清理未执行的动画帧
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
    // Ctrl + A 或 Meta + A
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
      e.preventDefault() // 阻止默认的全选文本行为
      // 如果列表为空，直接返回
      if (!this.config.data || this.config.data.length === 0) return
      // 执行全选，传入的是当前列表的所有 ID
      // 这里的 data 必须是最新的 filtered/sorted 列表 ID 数组
      this.modStore.selectMods([...this.config.data], this.modStore.lastSelectedMod?.package_id)
      console.log(`[vSelection] Selected all ${this.config.data.length} items.`)
    }
  }
  // --- 核心逻辑 ---
  // 处理鼠标按下事件
  onMouseDown(e) {
    if (this.config.disabled || e.button !== 0) return

    // 修正输入框焦点
    if (document.activeElement instanceof HTMLElement &&
       (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA')) {
        document.activeElement.blur()
    }

    const target = e.target
    const itemId = this.getItemId(target)
    // 点空白处清空选择。
    if (!itemId && target === this.el) {
        this.modStore.clearSelection() 
    }
    if (!itemId) return

    this.isMouseDown = true
    this.isDragging = false
    this.startPos = { x: e.clientX, y: e.clientY }
    // 修改点：记录按下瞬间的滚动位置
    this.startScrollTop = this.el.scrollTop
    this.startScrollLeft = this.el.scrollLeft

    // 判断触发类型
    const isSwipeTarget = target.closest(`.${this.config.swipeClass}`)
    const isClickTarget = target.closest(`.${this.config.clickClass}`)

    // console.log('isSwipeTarget', isSwipeTarget, 'isClickTarget', isClickTarget)
    // 处理滑动逻辑 (Swipe)
    // 只有命中 swipeClass 时才启动滑动模式
    if (isSwipeTarget) {
      // === 模式 A: 启动滑动框选 ===
      e.preventDefault() // 防止文字选中
      this.isSwiping = true
      this.swipeStartIndex = this.getIndexById(itemId)
      this.lastHoveredId = itemId // 【优化1】初始化最后经过ID
      
      // 初始化视觉选框
      this.createSelectionBox()
      // 记录快照：如果按住 Ctrl，保留原有选中；否则清空
      if (e.ctrlKey || e.metaKey) {
        this.selectionSnapshot = new Set(this.modStore.selectedIds)
      } else {
        this.selectionSnapshot = new Set()
      }
      
      // 立即执行一次范围计算 (单点框选)
      this.updateSwipeRange(itemId)

    } else if (isClickTarget) {
      // === 模式 B: 准备点击选择 ===
      // 这里不立即执行反选逻辑，而是根据情况决定是否立即选中
      
      const isSelected = this.modStore.selectedIds.includes(itemId)
      const isMulti = e.ctrlKey || e.metaKey
      const isRange = e.shiftKey

      if (!isMulti && !isRange && !isSelected) {
        // 场景：单选未选中的项 -> 立即选中（为了让用户能立刻拖拽它）
        this.modStore.selectMods([itemId], itemId)
        this.anchorId = itemId 
      }
      
      // 对于已选中的项、或者 Ctrl/Shift 操作，逻辑推迟到 MouseUp
      // 这样做是为了区分 "点击" 和 "拖拽"
    }
  }
  // 处理鼠标移动事件
  onMouseMove(e) {
    if (!this.isMouseDown) return

    // 1. 检测拖拽阈值 (防止手抖误判为拖拽)
    if (!this.isDragging) {
      const dx = e.clientX - this.startPos.x
      const dy = e.clientY - this.startPos.y
      if (dx * dx + dy * dy > 25) { // 5px 阈值
        this.isDragging = true
      }
    }

    // 2. 处理滑动框选逻辑
    if (this.isSwiping) {
      e.preventDefault()
      // A. 更新视觉选框
      this.updateSelectionBox(e.clientX, e.clientY)

      // B. 更新选中数据
      const itemId = this.getItemId(e.target)
      
      // 只有当 ID 变化时才触发昂贵的计算逻辑
      if (itemId && itemId !== this.lastHoveredId) {
        this.lastHoveredId = itemId
        this.updateSwipeRange(itemId)
      }
    }
  }
  // 处理鼠标松开事件
  onMouseUp(e) {
    if (!this.isMouseDown) return
    // 移除视觉选框 (无论是否在滑动模式都尝试移除，确保清洁)
    this.removeSelectionBox()
    this.lastHoveredId = null // 重置
    // 如果是滑动模式，松开即结束
    if (this.isSwiping) {
      this.isSwiping = false
      this.isMouseDown = false
      return
    }
    // 如果发生了拖拽，则不处理点击选择逻辑 (交给 SortableJS 或其他拖拽库处理)
    if (this.isDragging) {
      this.isMouseDown = false
      return
    }
    // === 处理纯点击逻辑 (Click End) ===
    // 只有在没有发生拖拽且没在滑动时才触发
    
    // 获取目标 ID (因为绑定在 document 上，需要重新判断 target 是否在容器内)
    // 注意：e.target 可能在松开时已经不在 el 内了，但在正常的点击操作中，Down和Up通常在同一元素上
    const itemId = this.getItemId(e.target)
    if (!itemId || !this.el.contains(e.target)) {
        this.isMouseDown = false
        return
    }

    const isMulti = e.ctrlKey || e.metaKey
    const isRange = e.shiftKey
    const isSelected = this.modStore.selectedIds.includes(itemId)

    if (isRange) {
      // --- Shift 连选 (Windows 风格) ---
      // 从 anchorId 到 currentId
      this.handleRangeSelect(itemId, isMulti)
      
    } else if (isMulti) {
      // --- Ctrl 多选 (反转状态) ---
      const newSet = new Set(this.modStore.selectedIds)
      if (isSelected) newSet.delete(itemId)
      else newSet.add(itemId)
      
      this.modStore.selectMods(Array.from(newSet), itemId)
      this.anchorId = itemId // 更新锚点

    } else {
      // --- 单选 ---
      // 场景：点击已选中的项。
      // 在 MouseDown 时为了允许拖拽，没有取消其他项。
      // 现在确认是点击（非拖拽），所以清除其他项，只留这一个。
      this.modStore.selectMods([itemId], itemId)
      this.anchorId = itemId
    }

    this.isMouseDown = false
  }

  // --- 逻辑实现函数 ---

  /**
   * 滑动框选核心算法
   * 逻辑：当前选中 = 快照 U (Start 到 Current 的范围)
   */
  updateSwipeRange(currentId) {
    const currentIndex = this.getIndexById(currentId)
    if (currentIndex === -1 || this.swipeStartIndex === -1) return

    const min = Math.min(this.swipeStartIndex, currentIndex)
    const max = Math.max(this.swipeStartIndex, currentIndex)

    // 基于快照创建新的选中集合
    const newSelection = new Set(this.selectionSnapshot)
    
    // 将范围内的 ID 添加进去
    for (let i = min; i <= max; i++) {
      const id = this.config.data[i]
      if (id) newSelection.add(id)
    }
    // 数据防抖：只有结果真的变了才提交 Store
    // 避免因为不必要的 Store 更新导致整个列表重绘
    const currentStoreSet = new Set(this.modStore.selectedIds)
    if (this.setsAreEqual(newSelection, currentStoreSet)) {
        return
    }
    this.modStore.selectMods(Array.from(newSelection), currentId)
  }

  // 辅助：Set 比较
  setsAreEqual(a, b) {
    if (a.size !== b.size) return false;
    for (const item of a) if (!b.has(item)) return false;
    return true;
  }
  /**
   * Shift 连选处理
   */
  handleRangeSelect(targetId, keepOthers = false) {
    if (!this.anchorId || !this.config.data.includes(this.anchorId)) {
        // 如果没有锚点，退化为单选并建立锚点
        this.modStore.selectMods([targetId], targetId)
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
        newSet = new Set(this.modStore.selectedIds) // Ctrl+Shift: 保留之前的
    } else {
        newSet = new Set() // 纯 Shift: 清空其他的
    }
    for (let i = min; i <= max; i++) {
        newSet.add(this.config.data[i])
    }
    this.modStore.selectMods(Array.from(newSet), targetId)
    // 注意：Shift 连选通常不更新 Anchor，Anchor 依然停留在最初点击的那个位置
    // 这样可以连续调整范围 (例如: 点击1, Shift点10 -> 选中1-10; 保持Shift点5 -> 选中1-5)
  }

  destroy() {
    this.removeSelectionBox() // 销毁时清理遗留DOM
    this.el.removeEventListener('mousedown', this.onMouseDown)
    this.el.removeEventListener('keydown', this.onKeyDown) // 移除键盘监听
    document.removeEventListener('mousemove', this.onMouseMove)
    document.removeEventListener('mouseup', this.onMouseUp)
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