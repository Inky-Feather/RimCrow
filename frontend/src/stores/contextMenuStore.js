import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useContextMenuStore = defineStore('contextMenu', () => {
  const show = ref(false)
  const x = ref(0)
  const y = ref(0)
  const items = ref([]) // [{ label: '删除', action: () => {}, danger: true }]

  const open = (event, menuItems) => {
    event.preventDefault() // 阻止默认菜单
    x.value = event.clientX
    y.value = event.clientY
    items.value = menuItems
    show.value = true
  }

  const close = () => {
    show.value = false
  }

  return { show, x, y, items, open, close }
})