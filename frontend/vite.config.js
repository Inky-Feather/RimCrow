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
          ) {
            return 'codemirror'
          }
        },
      },
    },
  },
  server: {
    // proxy: {
    //   '/api': {
    //     target: 'http://localhost:5000',
    //     changeOrigin: true,
    //     secure: false,
    //     rewrite: (path) => path.replace(/^\/api/, ''),
    //   },
    // },
    // host: '0.0.0.0',
    // port: 5173,
    // open: false,  
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
