import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

let server
let i18nModule

before(async () => {
  globalThis.window = { pywebview: { api: {} } }
  server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)), server: { middlewareMode: true }, appType: 'custom' })
  i18nModule = await server.ssrLoadModule('/src/shared/i18n.js')
  globalThis.document = { documentElement: { lang: '' } }
})

after(async () => {
  await server?.close()
})

test('only the latest locale request may update the active locale', async () => {
  const pending = new Map()
  window.pywebview.api.locale_load_user_messages = language => new Promise(resolve => pending.set(language, resolve))

  const first = i18nModule.setLocale('de')
  const second = i18nModule.setLocale('en')
  pending.get('en')({ status: 'success', data: { language: 'en', messages: {} } })
  await second
  pending.get('de')({ status: 'success', data: { language: 'de', messages: {} } })
  await first

  assert.equal(i18nModule.getCurrentLocale(), 'en')
})

test('backend canonical language code is used by the active locale', async () => {
  window.pywebview.api.locale_load_user_messages = async () => ({ status: 'success', data: { language: 'pt-BR', messages: {} } })

  await i18nModule.setLocale('pt_br')

  assert.equal(i18nModule.getCurrentLocale(), 'pt-BR')
  assert.equal(document.documentElement.lang, 'pt-BR')
})

test('locale load errors keep the active locale and reach the caller', async () => {
  window.pywebview.api.locale_load_user_messages = async () => ({
    status: 'error',
    user_message: '读取用户语言文件失败。',
  })

  await assert.rejects(i18nModule.setLocale('de'), /读取用户语言文件失败/)
  assert.equal(i18nModule.getCurrentLocale(), 'pt-BR')
})

test('translation validation detects placeholders and format markers', () => {
  assert.equal(i18nModule.getTranslationValidationIssue('Hello {name}', 'Hallo'), 'placeholders')
  assert.equal(i18nModule.getTranslationValidationIssue('^^Title^^', 'Titel'), 'markers')
  assert.equal(i18nModule.getTranslationValidationIssue('Hello {name}', 'Hallo {name}'), '')
})

test('user overrides do not become builtin messages after reset', async () => {
  window.pywebview.api.locale_load_user_messages = async () => ({
    status: 'success',
    data: { language: 'zh-CN', messages: { common: { action: { save: 'TEMP_SAVE' } } } },
  })
  await i18nModule.setLocale('zh-CN')

  window.pywebview.api.locale_load_user_messages = async () => ({
    status: 'success',
    data: { language: 'zh-CN', messages: {} },
  })
  const data = await i18nModule.getLocaleMessagesForManagement('zh-CN')

  assert.equal(data.builtin.common.action.save, '保存')
  assert.equal(data.merged.common.action.save, '保存')
  assert.equal(data.user.common?.action?.save, undefined)
})
