import { createApp } from 'vue'
import { createPinia } from 'pinia' // 注册 Pinia
import Toast from "vue-toastification";
// import "vue-toastification/dist/index.css";
import './styles/toast.scss'
import VueVirtualScroller from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import VueViewer from 'v-viewer'
import 'viewerjs/dist/viewer.css'
import 'vue3-colorpicker/style.css'
import './styles/style.css'
import App from './App.vue'
import {vPreview} from '../shared/directives/vPreview.js'
import {vTooltip} from '../shared/directives/vTooltip.js'
import { vSelectableList } from '../shared/directives/vSelection' // 引入指令
import { setupPywebviewBridge } from '../app/bridge/pywebviewBridge'

await setupPywebviewBridge()


const pinia = createPinia() 
const app = createApp(App)
const options = {
  transition: "Vue-Toastification__bounce",
  maxToasts: 20,
  newestOnTop: true
}

app.use(VueVirtualScroller)
app.use(VueViewer, {
  defaultOptions: {
    zIndex: 100000,
    focus: false,
    navbar: false,
    title: false,
    toolbar: true,
    tooltip: true,
    transition: false,
    hide: () => {
      const activeElement = document.activeElement
      if (activeElement?.closest?.('.viewer-container')) {
        activeElement.blur()
      }
    },
  },
})
app.use(Toast, options);
app.use(pinia) 



app.directive('preview', vPreview) // 注册预览面板指令
app.directive('tooltip', vTooltip) // 注册 Tooltip 指令
app.directive('selectable-list', vSelectableList) // 注册列表项选择指令

app.mount('#app')
