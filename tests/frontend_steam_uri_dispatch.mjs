import assert from 'node:assert/strict'
import {
  buildSteamOpenUrl,
  buildWorkshopSteamUri,
  buildWorkshopWebUrl,
  dispatchSteamUri,
  openWorkshopPage,
} from '../frontend/src/shared/lib/steamUri.js'

assert.equal(buildWorkshopSteamUri(' 12345 '), 'steam://url/CommunityFilePage/12345')
assert.equal(buildWorkshopWebUrl('12345'), 'https://steamcommunity.com/sharedfiles/filedetails/?id=12345')
assert.equal(buildSteamOpenUrl(' https://steamcommunity.com/dev/apikey '), 'steam://openurl/https://steamcommunity.com/dev/apikey')

const calls = []
global.window = {
  pywebview: {
    api: {
      open_system_uri: async (uri) => {
        calls.push(['api', uri])
        return { status: 'success' }
      },
    },
  },
  open: (uri, target) => calls.push(['window', uri, target]),
}

assert.equal(await dispatchSteamUri('steam://run/294100'), true)
assert.deepEqual(calls, [['api', 'steam://run/294100']])

delete window.pywebview.api.open_system_uri
assert.equal(await dispatchSteamUri('steam://open/main'), true)
assert.deepEqual(calls.at(-1), ['window', 'steam://open/main', '_blank'])

await openWorkshopPage('1001', true)
assert.deepEqual(calls.at(-1), ['window', 'steam://url/CommunityFilePage/1001', '_blank'])

await openWorkshopPage('1001', false)
assert.deepEqual(calls.at(-1), ['window', 'https://steamcommunity.com/sharedfiles/filedetails/?id=1001', '_blank'])
