// eduStudio 統一 /app 前端 build（自包含於 repo，不再依賴外部 infoCard）。
// root=edustudio/，react plugin 轉 JSX，產物輸出到 ../web/eduapp，server serve 在 /app。
// build 一律要帶 --base=/app/（漏了 /app 整頁空白 404）：
//   cd frontend && npx vite build --base=/app/
import path from 'path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  root: 'edustudio',
  plugins: [react()],
  build: {
    outDir: path.resolve(process.cwd(), '../web/eduapp'),
    emptyOutDir: true,
    chunkSizeWarningLimit: 3000,
  },
});
