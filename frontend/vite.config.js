import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  base: './', // 【必须】使用相对路径
  plugins: [
    vue(),
    tailwindcss(),
  ],
  build: {
    rollupOptions: {
      output: {
        onlyExplicitManualChunks: true,
        manualChunks(id) {
          const normalizedId = id.replace(/\\/g, '/')
          if (!normalizedId.includes('/node_modules/')) return
          if (
            normalizedId.includes('/node_modules/vue/')
            || normalizedId.includes('/node_modules/@vue/')
            || normalizedId.includes('/node_modules/pinia/')
          ) {
            return
          }
          if (
            normalizedId.includes('/node_modules/vue-codemirror6/')
            || normalizedId.includes('/node_modules/codemirror/')
            || normalizedId.includes('/node_modules/@codemirror/')
            || normalizedId.includes('/node_modules/@lezer/')
            || normalizedId.includes('/node_modules/@replit/codemirror-lang-csharp/')
            // @codemirror/view 的运行时依赖必须同包，否则打包后会形成 codemirror 与业务 chunk 的循环引用。
            || normalizedId.includes('/node_modules/style-mod/')
            || normalizedId.includes('/node_modules/w3c-keyname/')
            || normalizedId.includes('/node_modules/crelt/')
            || normalizedId.includes('/node_modules/@marijn/find-cluster-break/')
          ) {
            return 'codemirror'
          }
        },
      },
    },
  },
  server: {
    // 开发模式只给本机桌面壳和本地浏览器使用，固定回环地址更稳定。
    host: '127.0.0.1',
    // 5173 在部分 Windows 机器上会落入系统保留端口范围，改成明确可用的固定端口。
    port: 5173,
    strictPort: true,
  },
  css: {
    preprocessorOptions: {
      scss: {
        // 核心配置在这里：
        // api: 'modern-compiler', // (可选) 如果使用的是非常新的 sass 版本
        silenceDeprecations: ['import'],  // 忽略导入警告（因为 vue-toastification 的SCSS中使用了 @import,新版 sass 不支持）
      }
    }
  }
})
