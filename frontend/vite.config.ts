// eduStudio 統一 /app 前端 build（自包含於 repo，不再依賴外部 infoCard）。
// root=edustudio/，react plugin 轉 JSX，產物輸出到 ../web/eduapp，server serve 在 /app。
//
// U-6: base 已寫死成 '/app/'，所以 `vite build` / `npm run build` 直接產出正確的
// /app 路徑（不必再記得在 CLI 帶 --base=/app/，漏了會整頁空白 404）。
import path from 'path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  root: 'edustudio',
  base: '/app/',
  plugins: [react()],
  build: {
    outDir: path.resolve(process.cwd(), '../web/eduapp'),
    emptyOutDir: true,
    chunkSizeWarningLimit: 3000,
  },
});
