import { createApp } from 'vue'
import { createPinia } from 'pinia' // 注册 Pinia
import Toast from "vue-toastification";
// import "vue-toastification/dist/index.css";
import './toast.scss'
import './style.css'
import App from './App.vue'
import {vPreview} from './directives/vPreview.js'
import {vTooltip} from './directives/vTooltip.js'


const pinia = createPinia() 
const app = createApp(App)
const options = {
  transition: "Vue-Toastification__bounce",
  maxToasts: 20,
  newestOnTop: true
}


app.use(Toast, options);
app.use(pinia) 

app.directive('preview', vPreview) // 注册预览面板指令
app.directive('tooltip', vTooltip) // 注册 Tooltip 指令

app.mount('#app')
