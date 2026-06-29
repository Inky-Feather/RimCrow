const DEFAULT_DURATION = 650
const MOVE_TOLERANCE = 8
const RING_SIZE = 20

let feedbackEl = null
let cleanupTimer = null

const getFeedbackEl = () => {
  if (feedbackEl) return feedbackEl
  feedbackEl = document.createElement('div')
  feedbackEl.className = 'long-press-feedback'
  feedbackEl.innerHTML = '<div class="long-press-feedback__ring"></div>'
  document.body.appendChild(feedbackEl)
  return feedbackEl
}

const setFeedbackPosition = (event) => {
  const el = getFeedbackEl()
  el.style.left = `${event.clientX - RING_SIZE / 2}px`
  el.style.top = `${event.clientY - RING_SIZE / 2}px`
}

const hideFeedback = (state = 'cancel') => {
  if (!feedbackEl) return
  clearTimeout(cleanupTimer)
  feedbackEl.classList.remove('is-pressing', 'is-complete', 'is-cancel')
  feedbackEl.classList.add(state === 'complete' ? 'is-complete' : 'is-cancel')
  cleanupTimer = setTimeout(() => {
    feedbackEl?.classList.remove('is-pressing', 'is-complete', 'is-cancel')
  }, state === 'complete' ? 280 : 160)
}

const showFeedback = (event, duration) => {
  const el = getFeedbackEl()
  clearTimeout(cleanupTimer)
  setFeedbackPosition(event)
  el.style.setProperty('--long-press-duration', `${duration}ms`)
  el.classList.remove('is-complete', 'is-cancel')
  // 重新触发布局动画，避免连续长按时复用上一轮进度。
  void el.offsetWidth
  el.classList.add('is-pressing')
}

export const showLongPressFeedback = (event, duration = DEFAULT_DURATION) => {
  showFeedback(event, Math.max(30, Number(duration) || DEFAULT_DURATION))
}

export const completeLongPressFeedback = () => hideFeedback('complete')
export const cancelLongPressFeedback = () => hideFeedback('cancel')

const normalizeOptions = (value) => {
  if (typeof value === 'function') return { onComplete: value }
  return value && typeof value === 'object' ? value : {}
}

const clearPress = (el, state = 'cancel') => {
  const press = el._longPressState
  if (!press?.active) return
  clearTimeout(press.timer)
  press.active = false
  hideFeedback(state)
}

export const vLongPressFeedback = {
  mounted(el, binding) {
    const state = {
      active: false,
      timer: null,
      pointerId: null,
      startX: 0,
      startY: 0,
      completed: false,
      options: normalizeOptions(binding.value),
    }

    const getDuration = () => Math.max(30, Number(state.options.duration || DEFAULT_DURATION))
    const isDisabled = () => !!(state.options.disabled || el.disabled || el.getAttribute('aria-disabled') === 'true')

    const handlePointerDown = (event) => {
      if (event.button !== undefined && event.button !== 0) return
      if (isDisabled()) return
      state.active = true
      state.completed = false
      state.pointerId = event.pointerId
      state.startX = event.clientX
      state.startY = event.clientY
      const duration = getDuration()
      showFeedback(event, duration)
      el.setPointerCapture?.(event.pointerId)
      state.timer = setTimeout(() => {
        if (!state.active) return
        state.completed = true
        state.active = false
        hideFeedback('complete')
        // 长按完成后吞掉同一次 pointerup 产生的 click，避免短按动作和长按动作叠加执行。
        el._longPressSkipClick = true
        state.options.onComplete?.(event)
      }, duration)
    }

    const handlePointerMove = (event) => {
      if (!state.active || state.pointerId !== event.pointerId) return
      setFeedbackPosition(event)
      const dx = Math.abs(event.clientX - state.startX)
      const dy = Math.abs(event.clientY - state.startY)
      if (dx > MOVE_TOLERANCE || dy > MOVE_TOLERANCE) {
        clearPress(el, 'cancel')
        state.options.onCancel?.(event)
      }
    }

    const handlePointerEnd = (event) => {
      if (state.pointerId !== event.pointerId) return
      if (state.active) {
        clearPress(el, 'cancel')
        state.options.onCancel?.(event)
      }
      el.releasePointerCapture?.(event.pointerId)
    }

    const handleClick = (event) => {
      if (!el._longPressSkipClick) return
      el._longPressSkipClick = false
      event.preventDefault()
      event.stopImmediatePropagation()
    }

    el._longPressState = state
    el._longPressHandlers = { handlePointerDown, handlePointerMove, handlePointerEnd, handleClick }
    el.addEventListener('pointerdown', handlePointerDown)
    el.addEventListener('pointermove', handlePointerMove)
    el.addEventListener('pointerup', handlePointerEnd)
    el.addEventListener('pointercancel', handlePointerEnd)
    el.addEventListener('click', handleClick, true)
  },

  updated(el, binding) {
    if (el._longPressState) {
      el._longPressState.options = normalizeOptions(binding.value)
    }
  },

  unmounted(el) {
    clearPress(el, 'cancel')
    const handlers = el._longPressHandlers
    if (!handlers) return
    el.removeEventListener('pointerdown', handlers.handlePointerDown)
    el.removeEventListener('pointermove', handlers.handlePointerMove)
    el.removeEventListener('pointerup', handlers.handlePointerEnd)
    el.removeEventListener('pointercancel', handlers.handlePointerEnd)
    el.removeEventListener('click', handlers.handleClick, true)
    delete el._longPressHandlers
    delete el._longPressState
    delete el._longPressSkipClick
  },
}
