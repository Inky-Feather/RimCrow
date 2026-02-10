// src/utils/uiHelper.js

/**
 * 高亮/震动提示指定元素
 * @param {String|HTMLElement} target - 选择器或DOM元素
 * @param {Object} options - 配置项
 * @param {string} [options.mode='shake'] - 动画模式: 'shake'(震动), 'wobble'(摇摆), 'flash'(闪烁), 'pulse'(呼吸)
 * @param {string} [options.color] - RGB颜色值 (如 '255, 0, 0')，不传则使用CSS默认
 * @param {number} [options.duration=1000] - 动画持续时间(ms)，设为 0 则不自动移除
 * @param {boolean} [options.scroll=true] - 是否自动滚动
 */
export function highlightComponent(target, options = {}) {
  const { 
    mode = 'shake', // 默认改为更有冲击力的 shake
    duration = 1000, 
    color = null, 
    scroll = false 
  } = options

  let el = typeof target === 'string' ? document.querySelector(target) : target
  if (!el) return

  // 1. 清理旧状态 (防止多次触发叠加)
  if (el._flashTimer) {
    clearTimeout(el._flashTimer)
    // 移除所有可能的类名
    el.classList.remove('highlight-base', 'highlight-effect-shake', 'highlight-effect-wobble', 'highlight-effect-flash', 'highlight-effect-pulse')
    void el.offsetWidth // 强制重绘
  }

  // 2. 设置颜色变量
  if (color) {
    el.style.setProperty('--highlight-color', color)
  } else {
    el.style.removeProperty('--highlight-color')
  }

  // 3. 滚动定位
  if (scroll) {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  // 4. 添加动画类
  el.classList.add('highlight-base', `highlight-effect-${mode}`)

  // 5. 定时移除
  if (duration > 0) {
    el._flashTimer = setTimeout(() => {
      el.classList.remove('highlight-base', `highlight-effect-${mode}`)
      el.style.removeProperty('--highlight-color')
      delete el._flashTimer
    }, duration)
  }
}

export function shakeComponent(target, options = {}) {
  highlightComponent(target, {
    ...options,
    mode: 'shake'
  })
}

export function wobbleComponent(target, options = {}) {
  highlightComponent(target, {
    ...options,
    mode: 'wobble'
  })
}

export function flashComponent(target, options = {}) {
  highlightComponent(target, {
    ...options,
    mode: 'flash'
  })
}

export function pulseComponent(target, options = {}) {
  highlightComponent(target, {
    ...options,
    mode: 'pulse'
  })
}