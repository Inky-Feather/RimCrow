import assert from 'node:assert/strict'

import { useSteamWorkshopActions } from '../src/app/stores/app/steamWorkshopActions.js'

const githubSubscribeCalls = []
const steamSubscribeCalls = []

globalThis.window = {
  __APP_DEBUG_MODE__: false,
  pywebview: {
    api: {
      github_subscribe: async (payload) => {
        githubSubscribeCalls.push(payload)
        return { status: 'success', data: [] }
      },
      steam_subscribe: async (ids) => {
        steamSubscribeCalls.push(ids)
        return { status: 'success', data: { task_id: 'steam-task' } }
      },
    },
  },
}

const actions = useSteamWorkshopActions({ openUrl: () => {} })
const result = await actions.subscribeInstallSources([{
  package_id: 'author.gitmod',
  source_kind: 'git',
  source_origin: 'git_catalog',
  name: 'Git Mod',
  url: 'https://gitgud.io/team/active',
  install_type: 'source',
  default_branch: 'Dev',
}])

assert.equal(result.success, true)
assert.equal(githubSubscribeCalls.length, 1)
assert.equal(githubSubscribeCalls[0].url, 'https://gitgud.io/team/active')
assert.equal(githubSubscribeCalls[0].install_type, 'source')
assert.equal(githubSubscribeCalls[0].default_branch, 'Dev')
assert.equal(steamSubscribeCalls.length, 0)
