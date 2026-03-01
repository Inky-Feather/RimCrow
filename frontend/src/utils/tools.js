
import { createToastInterface } from 'vue-toastification'
import { useAppStore } from '../stores/appStore'

const toast = createToastInterface()
// 通用结果检查
  export function checkResult(res, workname, showSuccess = false) {
    const appStore = useAppStore()
    if (appStore.settings.debug_mode) console.log('checkResult', workname, res)
    if (res.status === 'success') {
      if(showSuccess) toast.success(`${workname}成功`, {timeout: 1000})
      return true;
    }
    if (res.status === 'warning') toast.warning(`${workname}注意: \n${res.message}`)
    else toast.error(`${workname}失败: \n${res.message}`)
    return false
  }