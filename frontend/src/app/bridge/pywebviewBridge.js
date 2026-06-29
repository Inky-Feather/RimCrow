const HEARTBEAT_INTERVAL_MS = 5000

let heartbeatTimer = null
let eventStream = null
let closeRegistered = false
let heartbeatCleanup = null

const getConfiguredApiBaseUrl = () => {
  const url = new URL(window.location.href)
  return url.searchParams.get('rmm_api_base') || ''
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
    throw new Error('无法连接软件后端服务。可能是后端进程已退出、浏览器桥接端口不可用或本机安全软件拦截，请重启软件后重试。')
  }
  if (!response.ok) {
    let message = `浏览器桥接请求失败，状态码：${response.status}。请确认后端服务仍在运行，或重启软件后重试。`
    try {
      const payload = await response.json()
      if (payload?.message) message = payload.message
    } catch {
      // 响应体不是 JSON 时保留状态码提示即可。
    }
    throw new Error(message)
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

export const setupPywebviewBridge = async () => {
  if (window.pywebview?.api) {
    window.__RMM_RUNTIME_MODE__ = 'desktop'
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
    throw new Error('浏览器桥接会话创建失败，请重启软件后重试。')
  }

  window.pywebview = {
    api: createApiProxy(baseUrl),
  }
  window.__RMM_RUNTIME_MODE__ = 'browser'
  window.__RMM_API_BASE_URL__ = baseUrl
  window.__RMM_BROWSER_SESSION_ID__ = clientId

  startHeartbeat(baseUrl, clientId)
  connectEventStream(baseUrl, clientId)
  registerCloseHooks(baseUrl, clientId)

  window.dispatchEvent(new Event('pywebviewready'))
  return 'browser'
}
