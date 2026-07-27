import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildUserErrorMessage, stripLogHint } from '../src/shared/lib/userErrorMessage.js'

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
