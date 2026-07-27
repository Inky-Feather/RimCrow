import defaultLogoUrl from '../../../../icon.svg'
import { t } from '../i18n.js'

const privateLogoModules = import.meta.glob('./private-assets/*.svg', { eager: true, import: 'default' })
const privateLogoUrl = Object.values(privateLogoModules)[0] || ''
export const brandProfile = {
  project: {
    name: 'RimCrow',
    get description() { return t('brand.project.description', 'RimCrow 用于整理模组、调整排序和管理 RimWorld 本地环境。') },
  },
  branding: {
    logoUrl: privateLogoUrl || defaultLogoUrl,
    get logoAlt() {
      return privateLogoUrl
        ? t('brand.logo.private_alt', 'Inky Feather 标识')
        : t('brand.logo.default_alt', 'RimCrow 默认图标')
    },
    renderMode: privateLogoUrl ? 'mask' : 'image',
  },
}

export default brandProfile
