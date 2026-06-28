import { createApp } from 'vue'
import { createPinia } from 'pinia' // 注册 Pinia
import Toast from "vue-toastification";
// import "vue-toastification/dist/index.css";
import './toast.scss'
import VueVirtualScroller from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import './style.css'
import App from './App.vue'
import {vPreview} from './directives/vPreview.js'
import {vTooltip} from './directives/vTooltip.js'
import { vSelectableList } from './directives/vSelection' // 引入指令
import { setupPywebviewBridge } from './runtime/pywebviewBridge'

await setupPywebviewBridge()


const pinia = createPinia() 
const app = createApp(App)
const options = {
  transition: "Vue-Toastification__bounce",
  maxToasts: 20,
  newestOnTop: true
}

app.use(VueVirtualScroller)
app.use(Toast, options);
app.use(pinia) 



app.directive('preview', vPreview) // 注册预览面板指令
app.directive('tooltip', vTooltip) // 注册 Tooltip 指令
app.directive('selectable-list', vSelectableList) // 注册列表项选择指令

app.mount('#app')
