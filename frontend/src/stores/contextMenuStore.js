// stores/contextMenuStore.js
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useContextMenuStore = defineStore('contextMenu', () => {
  const show = ref(false)
  const x = ref(0)
  const y = ref(0)
  const items = ref([])
  
  // 保存触发菜单时的自定义数据（例如右键点击的那个列表项ID）
  const payload = ref(null)
  const menuId = ref(0) // 用于强制刷新

  const open = (event, menuItems, data = null) => {
    // 阻止默认浏览器右键
    event.preventDefault()
    event.stopPropagation() // 阻止冒泡
    
    x.value = event.clientX
    y.value = event.clientY
    items.value = menuItems
    payload.value = data
    menuId.value = Date.now() // 每次打开更新 ID
    show.value = true
  }

  const close = () => {
    show.value = false
  }

  return { show, menuId, x, y, items, payload, open, close }
})