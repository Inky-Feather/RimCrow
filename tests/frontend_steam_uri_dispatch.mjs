import assert from 'node:assert/strict'
import {
  buildWorkshopSteamUri,
  buildWorkshopWebUrl,
  dispatchSteamUri,
} from '../frontend/src/shared/lib/steamUri.js'

assert.equal(
  buildWorkshopSteamUri('294100'),
  'steam://url/CommunityFilePage/294100',
  'Workshop Steam URI 应按统一格式生成'
)

assert.equal(
  buildWorkshopWebUrl('294100'),
  'https://steamcommunity.com/sharedfiles/filedetails/?id=294100',
  'Workshop 网页 URL 应按统一格式生成'
)

{
  const calls = []
  globalThis.window = {
    pywebview: {
      api: {
        open_system_uri: async (uri) => {
          calls.push(uri)
          return { status: 'success' }
        },
      },
    },
    open: () => {
      throw new Error('后端 API 可用时不应回退到 window.open')
    },
  }

  const ok = await dispatchSteamUri('steam://open/main')
  assert.equal(ok, true, '后端分发成功时应返回 true')
  assert.deepEqual(calls, ['steam://open/main'], '应优先调用后端 open_system_uri')
}

{
  const calls = []
  globalThis.window = {
    pywebview: null,
    open: (...args) => {
      calls.push(args)
    },
  }

  const ok = await dispatchSteamUri('steam://url/CommunityFilePage/123456')
  assert.equal(ok, true, 'fallback 分发成功时应返回 true')
  assert.deepEqual(
    calls,
    [['steam://url/CommunityFilePage/123456', '_blank']],
    '无后端桥接时应回退到 window.open'
  )
}
