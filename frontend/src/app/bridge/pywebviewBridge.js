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

  const response = await fetch(`${baseUrl}${path}`, requestInit)
  if (!response.ok) {
    throw new Error(`Bridge request failed: ${response.status}`)
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
      console.warn('Failed to parse backend event payload:', error)
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
    throw new Error('Browser bridge session open failed')
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
