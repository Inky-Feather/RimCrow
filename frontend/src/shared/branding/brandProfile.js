import defaultLogoUrl from '../../../../icon.svg'

const privateLogoModules = import.meta.glob('./private-assets/*.svg', { eager: true, import: 'default' })
const privateLogoUrl = Object.values(privateLogoModules)[0] || ''
export const brandProfile = {
  project: {
    name: 'RimCrow',
    description: 'RimCrow 用于整理模组、调整排序和管理 RimWorld 本地环境。',
  },
  branding: {
    logoUrl: privateLogoUrl || defaultLogoUrl,
    logoAlt: privateLogoUrl ? 'Inky Feather 标识' : 'RimCrow 默认图标',
    renderMode: privateLogoUrl ? 'mask' : 'image',
  },
}

export default brandProfile
