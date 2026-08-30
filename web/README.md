# web/ — 前端 build 輸出目錄

此目錄只放 build 產物(皆已 gitignore, 不進版控):

- `web/eduapp/` — 唯一正式前端 `/app` 的產物。由 `frontend/` 建置:
  `cd frontend && npm install && npx vite build --base=/app/`

歷史note: 原本這裡還有 legacy `/ui` 前端(React 18)的原始碼專案與 `web/dist` 產物,
已於 2026-08-30 (U-5) 退場移除 — `/ui` 與 `/studio` 現一律 307 轉址到 `/app/`。
需要舊碼考古用 git 歷史(如 `git log -- web/src`)。
