export const buildWorkshopSteamUri = (workshopId) => {
  const id = String(workshopId || '').trim()
  return id ? `steam://url/CommunityFilePage/${id}` : ''
}

export const buildWorkshopWebUrl = (workshopId) => {
  const id = String(workshopId || '').trim()
  return id ? `https://steamcommunity.com/sharedfiles/filedetails/?id=${id}` : ''
}

export const buildSteamOpenUrl = (url) => {
  const target = String(url || '').trim()
  return target ? `steam://openurl/${target}` : ''
}

export const dispatchSteamUri = async (uri) => {
  const targetUri = String(uri || '').trim()
  if (!targetUri) return false

  const openSystemUri = globalThis.window?.pywebview?.api?.open_system_uri
  if (typeof openSystemUri === 'function') {
    try {
      const res = await openSystemUri(targetUri)
      if (res?.status === 'success') return true
    } catch {
      // 桥接失败时退回浏览器打开，保留源码开发环境可用性。
    }
  }

  if (typeof globalThis.window?.open === 'function') {
    globalThis.window.open(targetUri, '_blank')
    return true
  }
  return false
}

export const openWorkshopPage = (workshopId, openInSteam = true) => {
  const targetUrl = openInSteam ? buildWorkshopSteamUri(workshopId) : buildWorkshopWebUrl(workshopId)
  return dispatchSteamUri(targetUrl)
}
