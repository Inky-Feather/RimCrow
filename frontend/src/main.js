import { createApp } from 'vue'
import { createPinia } from 'pinia' // 加这行
import './style.css'
import App from './App.vue'


const pinia = createPinia() // 加这行
const app = createApp(App)

app.use(pinia) // 加这行
app.mount('#app')
