export const buildWorkshopSteamUri = (workshopId) => {
  const normalizedId = String(workshopId || '').trim()
  return normalizedId ? `steam://url/CommunityFilePage/${normalizedId}` : ''
}

export const buildWorkshopWebUrl = (workshopId) => {
  const normalizedId = String(workshopId || '').trim()
  return normalizedId ? `https://steamcommunity.com/sharedfiles/filedetails/?id=${normalizedId}` : ''
}

export const dispatchSteamUri = async (uri) => {
  const normalizedUri = String(uri || '').trim()
  if (!normalizedUri) return false

  try {
    if (window.pywebview?.api?.open_system_uri) {
      const res = await window.pywebview.api.open_system_uri(normalizedUri)
      return res?.status === 'success'
    }
  } catch (error) {
    console.warn('通过后端分发 Steam URI 失败，回退到 window.open:', error)
  }

  window.open(normalizedUri, '_blank')
  return true
}
