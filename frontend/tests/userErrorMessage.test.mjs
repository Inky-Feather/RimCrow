import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildUserErrorMessage, stripLogHint, shouldOfferNetworkSettings } from '../src/shared/lib/userErrorMessage.js'
import { showUserErrorToast, toast, checkResult } from '../src/shared/lib/common.js'

test('uses explicit user message and removes log-only hints', () => {
  assert.equal(
    buildUserErrorMessage({
      user_message: '下载失败。请检查网络连接和代理设置。请查看系统日志。',
    }),
    '下载失败。请检查网络连接和代理设置。'
  )
})

test('uses message_key before fallback when backend provides translation metadata', () => {
  const message = buildUserErrorMessage({
    message_key: 'errors.network.timeout',
    message_params: { service: 'GitHub' },
    user_message: '网络请求超时。',
  }, '操作未完成。', (key, defaultText, params) => {
    if (key === 'errors.network.timeout') return `${params.service} 连接超时。`
    return defaultText
  })

  assert.equal(message, 'GitHub 连接超时。')
})

test('does not infer user-facing text from raw technical messages', () => {
  const message = buildUserErrorMessage({
    message: 'requests.exceptions.ProxyError: Tunnel connection failed: 407 Proxy Authentication Required',
  }, '操作未完成。请检查网络连接、配置、路径权限或稍后重试。')

  assert.equal(message, '操作未完成。请检查网络连接、配置、路径权限或稍后重试。')
  assert.doesNotMatch(message, /ProxyError|Tunnel|407/)
})

test('stripLogHint keeps useful text when removing empty log guidance', () => {
  assert.equal(
    stripLogHint('扫描失败。请稍后重试，详细原因已写入系统日志。'),
    '扫描失败。请稍后重试。'
  )
})

test('offers network settings only for connection failures and ambiguous remote update checks', () => {
  for (const error_code of [
    'NETWORK.CONNECTION', 'NETWORK.TIMEOUT', 'NETWORK.PROXY', 'NETWORK.PROXY_AUTH',
    'NETWORK.TLS', 'NETWORK.INVALID_RESPONSE', 'GIT.REQUEST_FAILED', 'UPDATE.CHECK_FAILED',
  ]) {
    assert.equal(shouldOfferNetworkSettings({ error_code }), true, error_code)
  }
  for (const error_code of [
    'SYSTEM.PERMISSION', 'SYSTEM.INVALID_INPUT', 'NETWORK.AUTH_FAILED', 'NETWORK.NOT_FOUND',
    'NETWORK.RATE_LIMIT', 'NETWORK.SERVICE_UNAVAILABLE', 'NETWORK.REQUEST_INVALID',
    'AI.AUTH_FAILED', 'AI.RATE_LIMIT', 'GIT.ACCESS_DENIED', 'UPDATE.ACTION_FAILED',
    'NETWORK.HOSTS_PERMISSION', '',
  ]) {
    assert.equal(shouldOfferNetworkSettings({ error_code }), false, error_code)
  }
  assert.equal(shouldOfferNetworkSettings({ message: 'NETWORK.TIMEOUT 网络超时' }), false)
  assert.equal(shouldOfferNetworkSettings(null), false)
})

test('network toast keeps the error and log action, offers advice and dispatches navigation', () => {
  const originalToast = toast.error
  const originalWindow = globalThis.window
  const events = []
  globalThis.window = { dispatchEvent: event => events.push(event) }
  let captured
  toast.error = (content, options) => { captured = { content, options } }
  try {
    showUserErrorToast({ error_code: 'NETWORK.TIMEOUT', error_id: 'error-123', user_message: '请求超时。' }, '', { timeout: 3000 })
    assert.equal(captured.content.props.message, '请求超时。')
    assert.equal(captured.content.props.errorId, 'error-123')
    assert.equal(captured.options.timeout, 8000)
    assert.equal(captured.options.closeOnClick, false)
    const emitted = []
    const render = captured.content.component.setup(captured.content.props, { emit: event => emitted.push(event) })
    const children = render().children
    assert.match(children[1].children[0].children, /网络优化工具/)
    assert.equal(children[2].children, '查看对应系统日志')
    const networkButton = children[1].children[1]
    assert.equal(networkButton.children, '打开网络连接设置')
    networkButton.props.onClick()
    assert.equal(events[0].type, 'rimcrow-open-network-settings')
    assert.deepEqual(emitted, ['close-toast'])

    showUserErrorToast({ error_code: 'NETWORK.PROXY' }, '', { timeout: false })
    assert.equal(captured.options.timeout, false)
    showUserErrorToast({ error_code: 'NETWORK.CONNECTION' }, '', { timeout: 12000 })
    assert.equal(captured.options.timeout, 12000)

    checkResult({ status: 'error', error_code: 'UPDATE.CHECK_FAILED', user_message: '检查更新失败。' }, '检查更新')
    assert.equal(captured.content.props.showNetworkSettings, true)

    showUserErrorToast({ error_code: 'SYSTEM.PERMISSION', user_message: '权限不足。' })
    assert.equal(captured.content, '权限不足。')
    showUserErrorToast({ error_code: 'AI.AUTH_FAILED', error_id: 'ai-error', user_message: '认证失败。' })
    assert.equal(captured.content.props.showNetworkSettings, false)
  } finally {
    toast.error = originalToast
    if (originalWindow === undefined) delete globalThis.window
    else globalThis.window = originalWindow
  }
})
