# 上線部署指引 — Production Deployment

> 適用對象：要把 eduStudio **暴露在 localhost 以外**（內網或公網）的自架者。
> 純粹自己在本機跑（`127.0.0.1`、不開放給別人連）可以略過大半，但仍建議讀「設驗證密鑰」一節。
>
> 相關文件：機密處置與漏洞回報看 [SECURITY.md](../SECURITY.md)；反向代理 + TLS 範例 conf
> 見下方「反向代理 + TLS」一節（[`deploy/nginx.conf.example`](../deploy/nginx.conf.example) /
> [`deploy/Caddyfile.example`](../deploy/Caddyfile.example)）；容器化基礎看
> [Dockerfile](../Dockerfile) / [docker-compose.yml](../docker-compose.yml)。

---

## 一鍵起 production 容器

base compose 是「localhost 自己玩」的預設；上線疊一層
[`docker-compose.prod.yml`](../docker-compose.prod.yml)（收緊 port 綁定、log rotation、restart、
提權防護）：

```bash
cp .env.example .env
# 編輯 .env：至少填 GEMINI_API_KEY，並設好 EDUSTUDIO_API_TOKEN / EDUSTUDIO_ALLOWED_ORIGINS（見下方 checklist）
cp tts_config.example.json tts_config.json

docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

docker compose logs -f server          # 看啟動 banner / 是否有「未驗證」警告
```

prod override 做了什麼：

| 項目 | base（自用） | prod override |
| --- | --- | --- |
| port 綁定 | `127.0.0.1:8000:8000`（只 loopback；2026-08 起 base 也不再綁所有介面，要上內網請走 prod + 反向代理） | `127.0.0.1:8000:8000`（只 loopback，外部走反向代理） |
| restart policy | `unless-stopped` | `always`（daemon 重啟也拉回） |
| container log | 無上限 | json-file，`max-size 10m` × `max-file 5`（落盤 + rotation） |
| 提權 | 預設 | `no-new-privileges:true` |

> server 本身已**不跑 `--reload`**（[Dockerfile](../Dockerfile) `CMD` 直接 `python -m server.main`，
> 不 watch 程式碼），production image 不會因檔案變動重啟。

---

## 上線前安全 checklist（把 Phase 1 串起來）

把後端掛到 localhost 以外**之前**，逐項確認。對應的硬底層在 Phase 1 已內建，這裡是「要記得開/設」的部分：

- [ ] **設驗證密鑰**（S-1）。`.env` 設一段夠長的隨機 `EDUSTUDIO_API_TOKEN`。
      **沒設 = 零驗證**，任何連得到 port 8000 的人都能觸發 job、燒你的 Gemini 額度、讀你的影片——
      啟動時 server 會大聲警告。產生方法：`python -c "import secrets; print(secrets.token_urlsafe(32))"`。
      - 瀏覽器：開 `/app` 會出登入框，輸入此 token 後種 cookie。
      - CLI / curl / skill：帶 header `Authorization: Bearer <token>`。
- [ ] **收緊 CORS**（S-2）。`.env` 設 `EDUSTUDIO_ALLOWED_ORIGINS` 為你的正式網域（逗號分隔）。
      **別留 `*`**。同源 `/app` 不受 CORS 影響；只有要從別的網域 fetch API 才需要加白名單。
- [ ] **放在反向代理 + TLS 後面**（SECURITY.md）。prod override 已把 server 綁死 `127.0.0.1`，
      請在 host 上用 nginx / caddy 做 TLS（https）+ 必要的存取控制，再把流量轉給 `127.0.0.1:8000`。
      **別把 server 裸綁 `0.0.0.0` 掛上公網**（無 TLS = token 與內容明文過網）。可複製範例 conf 見
      下方「[反向代理 + TLS](#反向代理--tls)」一節。
- [ ] **rate limit 維持開啟**（S-6）。預設每 IP 30/min，套在燒額度端點（`/api/generate`、`/api/refine`、
      建 job、上傳）。內網要調用量大可調 `EDUSTUDIO_RATE_LIMIT_PER_MIN`；設 `0` 才關閉——公開環境別關。
- [ ] **保護機密檔**（S-5 / SECURITY.md）。`.env`、`tts_config.json`、`client_secret*.json`、
      `youtube_token.json` 為明文（已 gitignore）。`chmod 600` 收權限、**別放共享磁碟/雲端同步、
      別進未加密備份**（要備份請用磁碟層級加密）。外洩立即撤銷重發。
- [ ] **設月預算提醒**（選用）。`EDUSTUDIO_MONTHLY_BUDGET`（USD）只影響成本面板顯示，不會真的擋呼叫，
      但能讓你一眼看出 Gemini 用量燒到哪。

> 上傳硬化（S-4：副檔名/MIME 白名單）與 path-traversal 防護（S-3）是**程式碼內建、無需設定**，
> 自架者不必額外做什麼。

---

## 反向代理 + TLS

prod override 把 server 綁死 `127.0.0.1:8000`，**它本身不會也不該直接面對公網**。要讓外面連得進來，
在 host 上擺一層反向代理終結 TLS（https），再把流量轉給 `127.0.0.1:8000`。`deploy/` 下有兩份可複製範本：

| 範本 | 適合 | TLS 取得方式 |
| --- | --- | --- |
| [`deploy/nginx.conf.example`](../deploy/nginx.conf.example) | 已在用 nginx / 要細緻控制 | certbot（Let's Encrypt），需一次性簽發 |
| [`deploy/Caddyfile.example`](../deploy/Caddyfile.example) | 想最省事 | **自動簽發 + 續期**，零手動憑證設定 |

兩份都不是免改即用——至少要改網域（`edustudio.example.com` → 你的網域），nginx 版還要填憑證路徑
（或讓 certbot 代填）。挑一份照頭部註解裝即可。範本已預先處理好這幾個容易踩的點：

- **上傳上限對齊**：`client_max_body_size 200m`（nginx）／ `max_size 200MB`（Caddy），對齊 server 的
  `MAX_UPLOAD_SIZE`（[`server/routes/uploads.py`](../server/routes/uploads.py) = 200 MB）。代理層預設值很小
  （nginx 1 MB），不放寬會在傳大 PDF/影片時**還沒到 app 就回 413**。
- **長請求逾時**：影片 render 與同步 Gemini 呼叫（`/api/generate`、`/api/refine`）可能跑數分鐘，範本把
  讀取逾時放寬到 600s，避免代理層預設 60s 把長請求切成 504。
- **轉發標頭**：帶 `X-Forwarded-For`（讓 per-IP rate limit S-6 看到真實來源）與 `X-Forwarded-Proto=https`
  （讓 session cookie 的 `Secure` 旗標判定正確）。`Authorization` header 與 cookie（S-1 驗證所依）皆透傳。
- **HSTS**：確認全站 https 後再開（範本已內建），讓瀏覽器之後只走 https。

> 反代不是驗證的替代品：它擋的是「明文過網」，**仍要設 `EDUSTUDIO_API_TOKEN`（S-1）**才有身分驗證。
> 兩者一起才是「暴露在外也安全」。

---

## 運維備忘

- **資料持久化**：job state、影片、上傳檔都靠 volume mount 出來（見 base compose `volumes:`），
  重建 image 不丟資料。`docker compose down -v` 會連 volume 一起砍（jobs 清空），慎用。
- **server 重啟不丟工作**：啟動時會把上次中斷的 in-flight job 標 FAILED 並提示重試（R-1）；
  等人工審查的 job（`AWAITING_REVIEW`）會原狀保留。
- **review gate 不可繞**：`require_review=True` 的 job 一定要經 `/approve` 人工核可才會 render——
  這是內容正確性的最後防線，**別停用**。
- **磁碟**：`work/`（中間 frame/audio/clip）與 `slides/`（切頁 PNG）會長期累積，定期清理舊 job。
- **健康檢查**：`/health` 回 200 即綠（compose healthcheck 已掛）；`docker compose ps` 看狀態。

---

## 還沒涵蓋（後續項目）

- **跨平台實測**（D-1，GATE）：Linux / Windows / macOS 各驗一遍 `docker compose up --build`。
- **F5 GPU passthrough**（D-4，GATE）：nvidia-docker 跑 F5-TTS；沒 GPU 自動退 edge/google TTS。
