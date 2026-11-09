import { t, translateMessagePayload } from '../../shared/i18n.js'

const HEARTBEAT_INTERVAL_MS = 5000

let heartbeatTimer = null
let eventStream = null
let closeRegistered = false
let heartbeatCleanup = null

const getConfiguredApiBaseUrl = () => {
  const url = new URL(window.location.href)
  return url.searchParams.get('api_base') || url.searchParams.get('rmm_api_base') || ''
}

const callBridgeEndpoint = async (baseUrl, path, payload = null, options = {}) => {
  const requestInit = {
    method: options.method || 'POST',
    headers: {},
    ...options,
  }

  if (payload !== null) {
    requestInit.headers = {
      'Content-Type': 'application/json',
      ...(requestInit.headers || {}),
    }
    requestInit.body = JSON.stringify(payload)
  }

  let response
  try {
    response = await fetch(`${baseUrl}${path}`, requestInit)
  } catch (error) {
    throw new Error(t('bridge.browser.connect_failed', '无法连接软件后端服务。可能是后端进程已退出、浏览器桥接端口不可用或本机安全软件拦截，请重启软件后重试。'))
  }
  if (!response.ok) {
    let message = t('bridge.browser.request_failed_with_status', '浏览器桥接请求失败，状态码：{status}。请确认后端服务仍在运行，或重启软件后重试。', { status: response.status })
    let errorPayload = null
    try {
      const payload = await response.json()
      if (payload && typeof payload === 'object') {
        errorPayload = payload
        message = translateMessagePayload(payload, message)
      }
    } catch {
      // 响应体不是 JSON 时保留状态码提示即可。
    }
    const error = new Error(message)
    if (errorPayload) Object.assign(error, errorPayload, { message, http_status: response.status })
    throw error
  }
  return response.json()
}

const createApiProxy = (baseUrl) => new Proxy({}, {
  get(_target, propKey) {
    if (typeof propKey !== 'string') return undefined
    return async (...args) => callBridgeEndpoint(baseUrl, `/api/call/${encodeURIComponent(propKey)}`, {
      args,
      kwargs: {},
    })
  }
})

const dispatchBackendEvent = (payload) => {
  if (!payload?.event) return
  window.dispatchEvent(new CustomEvent(payload.event, {
    detail: payload.data,
  }))
}

const registerCloseHooks = (baseUrl, clientId) => {
  if (closeRegistered) return
  closeRegistered = true

  const closeSession = () => {
    const body = JSON.stringify({ client_id: clientId })
    if (navigator.sendBeacon) {
      navigator.sendBeacon(`${baseUrl}/api/session/close`, new Blob([body], { type: 'application/json' }))
      return
    }
    fetch(`${baseUrl}/api/session/close`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      keepalive: true,
    }).catch(() => {})
  }

  window.addEventListener('pagehide', closeSession)
  window.addEventListener('beforeunload', closeSession)
}

const startHeartbeat = (baseUrl, clientId) => {
  if (heartbeatTimer) {
    window.clearInterval(heartbeatTimer)
  }
  if (heartbeatCleanup) {
    heartbeatCleanup()
    heartbeatCleanup = null
  }

  const sendHeartbeat = () => {
    callBridgeEndpoint(baseUrl, '/api/session/heartbeat', { client_id: clientId }).catch(() => {})
  }

  heartbeatTimer = window.setInterval(sendHeartbeat, HEARTBEAT_INTERVAL_MS)
  sendHeartbeat()

  const pingOnResume = () => {
    if (document.visibilityState === 'hidden') return
    sendHeartbeat()
  }

  window.addEventListener('focus', pingOnResume)
  window.addEventListener('pageshow', pingOnResume)
  document.addEventListener('visibilitychange', pingOnResume)

  heartbeatCleanup = () => {
    window.removeEventListener('focus', pingOnResume)
    window.removeEventListener('pageshow', pingOnResume)
    document.removeEventListener('visibilitychange', pingOnResume)
  }
}

const connectEventStream = (baseUrl, clientId) => {
  if (eventStream) {
    eventStream.close()
  }

  eventStream = new EventSource(`${baseUrl}/events?client_id=${encodeURIComponent(clientId)}`)
  eventStream.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data)
      dispatchBackendEvent(payload)
    } catch (error) {
      console.warn('解析后端事件失败:', error)
    }
  }
  eventStream.onerror = () => {}
}

const DESKTOP_API_READY_TIMEOUT_MS = 10000

const hasPopulatedDesktopApi = () => {
  const api = window.pywebview?.api
  return !!api && typeof api === 'object' && Object.keys(api).length > 0
}

// pywebview 在文档一开始就注入了 window.pywebview.api 空壳，真正的 API 方法要等
// finish.js 注入后才补齐并派发 pywebviewready。必须等方法就位再放行首屏，否则启动期
// 第一次 api 调用拿到的是 undefined，整个初始化流程会中断（mac 的 WKWebView 注入更晚，必现）。
const waitForPopulatedDesktopApi = (timeoutMs = DESKTOP_API_READY_TIMEOUT_MS) => new Promise((resolve) => {
  if (hasPopulatedDesktopApi()) {
    resolve(true)
    return
  }
  let timer = null
  const cleanup = () => {
    window.removeEventListener('pywebviewready', onReady)
    if (timer) window.clearTimeout(timer)
  }
  const onReady = () => {
    if (!hasPopulatedDesktopApi()) return
    cleanup()
    resolve(true)
  }
  window.addEventListener('pywebviewready', onReady)
  timer = window.setTimeout(() => {
    cleanup()
    resolve(hasPopulatedDesktopApi())
  }, timeoutMs)
})

// 启动编排统一用这个判断「后端桥是否可用」：桌面模式等 api 方法补齐，浏览器模式等会话建好。
export const waitForPywebviewApiReady = async () => {
  if (window.pywebview) return waitForPopulatedDesktopApi()
  if (window.__APP_BROWSER_SESSION_ID__) return true
  return new Promise((resolve) => {
    if (window.pywebview?.api) {
      resolve(true)
      return
    }
    window.addEventListener('pywebviewready', () => resolve(true), { once: true })
  })
}

export const setupPywebviewBridge = async () => {
  if (window.pywebview) {
    const apiReady = await waitForPopulatedDesktopApi()
    if (!apiReady) console.warn('pywebview API 在超时前仍未就绪，继续以桌面模式启动')
    window.__APP_RUNTIME_MODE__ = 'desktop'
    return 'desktop'
  }

  const baseUrl = getConfiguredApiBaseUrl()
  if (!baseUrl) {
    return null
  }

  let meta
  try {
    meta = await callBridgeEndpoint(baseUrl, '/api/meta', null, { method: 'GET' })
  } catch {
    return null
  }

  if (meta?.data?.runtime_mode !== 'browser') {
    return null
  }

  const session = await callBridgeEndpoint(baseUrl, '/api/session/open', {})
  const clientId = session?.data?.client_id
  if (!clientId) {
    throw new Error(t('bridge.browser.session_create_failed', '浏览器桥接会话创建失败，请重启软件后重试。'))
  }

  window.pywebview = {
    api: createApiProxy(baseUrl),
  }
  window.__APP_RUNTIME_MODE__ = 'browser'
  window.__APP_API_BASE_URL__ = baseUrl
  window.__APP_BROWSER_SESSION_ID__ = clientId

  startHeartbeat(baseUrl, clientId)
  connectEventStream(baseUrl, clientId)
  registerCloseHooks(baseUrl, clientId)

  window.dispatchEvent(new Event('pywebviewready'))
  return 'browser'
}
