import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 為什麼 base="/ui/":
//   FastAPI 會把 build 出來的 web/dist 掛到 /ui/* path, asset 都需要在 /ui/ 底下找
// 為什麼 outDir="dist" + emptyOutDir:
//   build 直接寫到 web/dist/, FastAPI StaticFiles 直接讀
// 為什麼 dev server proxy:
//   開發時 vite (5173) 跟 FastAPI (8000) 是兩個 process, 把 API call 轉發到 8000
export default defineConfig({
  plugins: [react()],
  base: '/ui/',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    port: 5173,
    proxy: {
      '/jobs': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
    },
  },
});
