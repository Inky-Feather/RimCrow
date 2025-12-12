import { createApp } from 'vue'
import { createPinia } from 'pinia' // 注册 Pinia
import './style.css'
import App from './App.vue'


const pinia = createPinia() // 加这行
const app = createApp(App)

app.use(pinia) // 加这行
app.mount('#app')
