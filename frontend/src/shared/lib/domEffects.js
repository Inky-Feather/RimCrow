/**
 * 给元素添加一次性的强调动画，用于提示用户关注某个控件。
 * @param {String|HTMLElement} target - 选择器或DOM元素
 * @param {Object} options - 配置项
 * @param {string} [options.mode='shake'] - 动画模式: 'shake'(震动), 'wobble'(摇摆), 'flash'(闪烁), 'pulse'(呼吸)
 * @param {string} [options.color] - RGB颜色值 (如 '255, 0, 0')，不传则使用CSS默认
 * @param {number} [options.duration=1000] - 动画持续时间(ms)，设为 0 则不自动移除
 * @param {boolean} [options.scroll=true] - 是否自动滚动
 */
export function highlightComponent(target, options = {}) {
  const {
    mode = 'shake',
    duration = 1000,
    color = null,
    scroll = false,
  } = options

  const element = typeof target === 'string' ? document.querySelector(target) : target
  if (!element) return

  // 1. 清理旧状态 (防止多次触发叠加)
  if (element._flashTimer) {
    clearTimeout(element._flashTimer)
    // 移除所有可能的类名
    element.classList.remove(
      'highlight-base',
      'highlight-effect-shake',
      'highlight-effect-wobble',
      'highlight-effect-flash',
      'highlight-effect-pulse',
    )
    void element.offsetWidth // 强制重绘
  }

  // 2. 设置颜色变量
  if (color) {
    element.style.setProperty('--highlight-color', color)
  } else {
    element.style.removeProperty('--highlight-color')
  }

  // 3. 滚动定位
  if (scroll) {
    element.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  // 4. 添加动画类
  element.classList.add('highlight-base', `highlight-effect-${mode}`)

  // 5. 定时移除
  if (duration > 0) {
    element._flashTimer = setTimeout(() => {
      element.classList.remove('highlight-base', `highlight-effect-${mode}`)
      element.style.removeProperty('--highlight-color')
      delete element._flashTimer
    }, duration)
  }
}

// 常用动画模式保留独立入口，组件调用时更直观。
export function shakeComponent(target, options = {}) {
  highlightComponent(target, { ...options, mode: 'shake' })
}

export function wobbleComponent(target, options = {}) {
  highlightComponent(target, { ...options, mode: 'wobble' })
}

export function flashComponent(target, options = {}) {
  highlightComponent(target, { ...options, mode: 'flash' })
}

export function pulseComponent(target, options = {}) {
  highlightComponent(target, { ...options, mode: 'pulse' })
}
