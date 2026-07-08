import { Copy, ExternalLink } from 'lucide-vue-next'
import { toast } from '../../../shared/lib/common'
import { IconSteam } from '../../../shared/lib/constants'
import { t } from '../../../shared/i18n'

const normalizeText = (value = '') => String(value || '').trim()

const takeFirstText = (...values) => {
  for (const value of values) {
    const normalized = normalizeText(value)
    if (normalized) return normalized
  }
  return ''
}

export const copyTextToClipboard = async (text = '', label = t('common.field.content', '内容')) => {
  const value = String(text || '')
  if (!value) {
    toast.warning(t('toast.common.copy_empty', '没有可复制的{label}', { label }))
    return false
  }
  try {
    await navigator.clipboard.writeText(value)
    toast.success(t('toast.common.copied_label', '{label}已复制', { label }), { timeout: 600 })
    return true
  } catch (error) {
    console.warn('复制文本失败:', error)
    toast.error(t('toast.common.copy_label_failed', '{label}复制失败', { label }))
    return false
  }
}

export const normalizeModMenuSource = (mod = {}) => {
  const source = mod || {}
  return {
    name: takeFirstText(source.alias_name, source.display_name, source.mod_name, source.name, source.title),
    packageId: takeFirstText(source.package_id_raw, source.package_id, source.id),
    workshopId: takeFirstText(source.workshop_id, source.workshopId, source.publishedfileid),
    path: takeFirstText(source.path, source.mod_path),
    url: takeFirstText(source.url, source.web_url, source.workshop_url),
  }
}

export const buildModInfoCopyMenuItem = (mod = {}, options = {}) => {
  const info = normalizeModMenuSource(mod)
  const fields = [
    { key: 'name', label: t('common.field.name', '名称'), value: info.name },
    { key: 'packageId', label: t('common.field.package_id', '包名'), value: info.packageId },
    { key: 'workshopId', label: t('common.field.workshop_id', '工坊 ID'), value: info.workshopId },
    { key: 'path', label: t('common.field.path', '路径'), value: info.path },
  ].filter(field => !options.fields || options.fields.includes(field.key))

  return {
    label: options.label || t('ui.mod.action.copy_info', '复制模组信息'),
    icon: Copy,
    disabled: !fields.some(field => !!field.value),
    children: fields.map(field => ({
      label: t('ui.mod.action.copy_field', '复制{field}', { field: field.label }),
      icon: Copy,
      disabled: !field.value,
      action: () => copyTextToClipboard(field.value, field.label),
    })),
  }
}

export const buildModExternalMenuItem = (mod = {}, appStore, options = {}) => {
  const info = normalizeModMenuSource(mod)
  return {
    label: options.label || t('common.action.visit_page', '访问页面'),
    icon: ExternalLink,
    disabled: !info.url && !info.workshopId,
    children: [
      {
        label: t('ui.mod.action.visit_url', '访问网页'),
        icon: ExternalLink,
        disabled: !info.url,
        action: () => appStore.openUrl(info.url),
      },
      {
        label: t('ui.mod.action.visit_workshop', '访问创意工坊'),
        icon: IconSteam,
        disabled: !info.workshopId,
        action: () => appStore.openSteamWorkshopById(info.workshopId),
      },
    ],
  }
}
