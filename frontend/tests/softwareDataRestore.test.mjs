import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compileScript, parse } from '@vue/compiler-sfc'

const { descriptor } = parse(readFileSync(new URL('../src/features/package-transfer/PackageTransferDialog.vue', import.meta.url), 'utf8'))
const { scriptSetupAst } = compileScript(descriptor, { id: 'software-data-restore' })
const names = ['isSoftwareBackup', 'canSubmit', 'submitLabel', 'handleSubmit']
const code = scriptSetupAst
  .filter(node => node.type === 'VariableDeclaration' && node.declarations.some(entry => names.includes(entry.id.name)))
  .map(node => descriptor.scriptSetup.content.slice(node.start, node.end)).join('\n')
const calls = []
let confirmed = false
const context = {
  computed: fn => ({ get value() { return fn() } }),
  t: (_key, fallback) => fallback,
  dialogMode: { value: 'data-import' },
  inspectData: { value: { is_software_backup: true } },
  submitting: { value: false }, selectedBundlePath: { value: 'backup.zip' },
  selectedDataImportModuleKeys: { value: [] }, hasSelectedProfileImport: { value: true },
  validateProfileRows: () => { throw new Error('恢复不应要求环境导入计划') },
  buildProfileImportPlan: () => { throw new Error('恢复不应创建环境导入计划') },
  useConfirmStore: () => ({ confirmAction: async () => confirmed }),
  appStore: { importDataBundle: async (path, payload) => { calls.push([path, payload]); return true } },
  closeDialog: () => calls.push('closed'),
}
const actions = runInNewContext(`${code}\n;({ ${names.join(', ')} })`, context)
assert.equal(actions.isSoftwareBackup.value, true)
assert.equal(actions.canSubmit.value, true)
assert.equal(actions.submitLabel.value, '开始恢复')
await actions.handleSubmit()
assert.equal(calls.length, 0)
assert.equal(context.submitting.value, false)
confirmed = true
await actions.handleSubmit()
assert.equal(calls[0][0], 'backup.zip')
assert.equal(calls[0][1].module_keys.length, 0)
assert.equal(calls[0][1].profile_import_plan.length, 0)
assert.equal(calls[1], 'closed')
context.inspectData.value = { is_software_backup: false }
assert.equal(actions.canSubmit.value, false)
console.log('软件数据恢复确认及模式分流测试通过')

const settingsDescriptor = parse(readFileSync(new URL('../src/features/settings/panel/SettingsDevTab.vue', import.meta.url), 'utf8')).descriptor
const settingsAst = compileScript(settingsDescriptor, { id: 'settings-data-restore' }).scriptSetupAst
const settingNames = ['softwareBackupTooltip', 'openDataBundleImportDialog']
const settingsCode = settingsAst
  .filter(node => node.type === 'VariableDeclaration' && node.declarations.some(entry => settingNames.includes(entry.id.name)))
  .map(node => settingsDescriptor.scriptSetup.content.slice(node.start, node.end)).join('\n')
const backup = { path: 'data/backups/all-data-backup.rimcrowdata.zip', size_bytes: 2048, modified_at: '2026-10-14T02:00:00+08:00' }
let inspection = { is_software_backup: true }
let opened = null
let error = ''
const settingsContext = {
  computed: fn => ({ get value() { return fn() } }),
  t: (_key, fallback, args = {}) => fallback.replace(/\{(\w+)\}/g, (_, key) => args[key]),
  dataBundleSchema: { value: { software_backup: null } },
  formatFileSize: bytes => `${bytes / 1024} KB`,
  runPendingAction: async (_action, runner) => runner(),
  toast: { error: message => { error = message } },
  appStore: {
    getDataBundleSchema: async () => ({}),
    getFilePath: async () => { throw new Error('恢复按钮不应弹出文件选择器') },
    inspectDataBundle: async path => { assert.equal(path, backup.path); return inspection },
    openPackageTransferDialog: (mode, preset) => { opened = { mode, preset } },
  },
}
const settingsActions = runInNewContext(`${settingsCode}\n;({ ${settingNames.join(', ')} })`, settingsContext)
assert.equal(settingsActions.softwareBackupTooltip.value, '')
settingsContext.dataBundleSchema.value.software_backup = backup
assert.match(settingsActions.softwareBackupTooltip.value, /上次导入前/)
assert.match(settingsActions.softwareBackupTooltip.value, /AI 定义/)
assert.match(settingsActions.softwareBackupTooltip.value, /2 KB/)
assert.match(settingsActions.softwareBackupTooltip.value, /2026/)
assert.match(settingsActions.softwareBackupTooltip.value, /all-data-backup/)
assert.match(settingsDescriptor.template.content, /v-if="dataBundleSchema.software_backup"/)
await settingsActions.openDataBundleImportDialog(backup.path)
assert.equal(opened.mode, 'data-import')
assert.equal(opened.preset.inspectData, inspection)
opened = null
inspection = null
await settingsActions.openDataBundleImportDialog(backup.path)
assert.equal(opened, null)
inspection = { is_software_backup: false }
await settingsActions.openDataBundleImportDialog(backup.path)
assert.equal(opened, null)
assert.match(error, /不是软件数据备份包/)
console.log('设置页恢复入口、提示信息及读取校验测试通过')
