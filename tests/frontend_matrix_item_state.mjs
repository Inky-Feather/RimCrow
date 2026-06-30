import assert from 'node:assert/strict'
import { getMatrixItemState } from '../frontend/src/features/workspace/lib/matrixItemState.js'

const workspaceStore = {
  getMatrixSameItems: () => [],
  getMatrixConflictItems: () => [],
  installedAllIds: new Set(),
  librariesMods: { workshop: [], self: [], local: [] },
}

const baseMod = {
  path_hash: 'mod-1',
  path: 'D:/Mods/mod-1',
  file_create_time: 1699999000000,
  file_modify_time: 1700000100000,
  download_status: { source: 'steam_sync_log', download_time: 1700000100000 },
  last_scanned_at: 1700000200000,
}

assert.equal(
  getMatrixItemState(baseMod, 0, workspaceStore, 1700000000000).isChange,
  true,
  '无游戏时间时，矩阵变更应按上次软件运行时间判断'
)

assert.equal(
  getMatrixItemState(baseMod, 1700000000000, workspaceStore, 1700000300000).isChange,
  true,
  '有游戏时间时，矩阵变更应优先按上次游戏运行时间判断'
)

assert.equal(
  getMatrixItemState(baseMod, 0, workspaceStore, 1700000300000).isChange,
  false,
  '无游戏时间且变化早于上次软件运行时，不应继续标记为变更'
)
