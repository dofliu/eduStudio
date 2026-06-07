# 安全政策 · Security Policy

## ⚠️ 部署前必讀：請勿把 server 裸奔在公網

eduStudio 是設計給**個人 / 單位自架**的工具。請注意目前的安全假設：

- **後端內建單一共享 token 驗證，但預設關閉。** 設定環境變數 `EDUSTUDIO_API_TOKEN=<夠長的隨機
  密鑰>` 即啟用：瀏覽器走 `/app` 登入框種 cookie、CLI 帶 `Authorization: Bearer <token>`。**沒設
  → server 照跑但無驗證**（啟動會大聲警告），此時**任何能連到你 server 的人都能呼叫 API、看你的
  job 與產出、消耗你的 Gemini 額度**。**暴露到 localhost 以外前，務必先設 token。**
- 預設範例用 `--host 127.0.0.1`（只有本機可連），**請維持這個預設**，除非你清楚知道自己在做什麼。
- 即使設了 token，從區網/外部存取仍建議放在可信任的反向代理（Nginx/Caddy）後面、走 HTTPS
  （讓 cookie 帶 `Secure`）並可再疊一層存取控制（VPN / Cloudflare Access / Tailscale 等），
  **不要**直接把 `0.0.0.0:8000` 裸奔到公開網際網路。
- 保護好你的金鑰與機密檔：`.env`、`settings.json`、`client_secret*.json`、`youtube_token.json`、
  `tts_config.json` 都不應該外流（已被 `.gitignore` 保護，請勿強制提交）。

> 一句話：**把它當成你自己內網的私人工具**，不是面向公眾的服務。

---

## 支援的版本 / Supported versions

本專案目前處於活躍開發、尚未發佈穩定 release。安全修補僅針對 `main` 分支的最新狀態提供。

| 版本 | 支援 |
|------|------|
| `main`（最新） | ✅ |
| 舊 commit / fork | ❌（請更新到最新 `main`） |

---

## 回報漏洞 / Reporting a vulnerability

**請勿開公開 issue 來回報安全漏洞**，以免在修補前被利用。

請改用 **GitHub 私密漏洞回報**：
進入本 repo 的 **Security** 分頁 → **Report a vulnerability**
（[Private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)），
或私下聯絡 maintainer（[@dofliu](https://github.com/dofliu) · [DOF Lab](https://doflab.cc)）。

回報時請盡量附上：

- 受影響的元件 / 端點 / 檔案
- 重現步驟或 PoC
- 影響評估（能讀到什麼 / 改到什麼 / 是否可遠端觸發）
- 建議的修補方向（若有）

### 我們的承諾

- **3 個工作天內**回覆確認收到。
- 評估後告知是否受理與預計處理時程。
- 修補後，在你同意下於 release notes / advisory 致謝。

感謝你協助讓自架老師們用得更安心。🔐

---

## English summary

eduStudio is built for **self-hosting**. The backend has built-in **shared-token auth, off by
default**: set `EDUSTUDIO_API_TOKEN=<long random secret>` to enable it (browser logs in at `/app` →
cookie; CLI sends `Authorization: Bearer <token>`). **If it is unset the server runs with no auth**
(loud startup warning) and anyone who can reach it can call the API, see your jobs/outputs, and spend
your Gemini quota — **always set the token before exposing beyond localhost.** Keep the default
`127.0.0.1` bind; for remote access put it behind a trusted reverse proxy over HTTPS (so the cookie is
`Secure`). **Do not expose `0.0.0.0:8000` to the public internet.**

**Do not file public issues for vulnerabilities.** Use GitHub's **private vulnerability reporting**
(repo **Security** tab → *Report a vulnerability*) or contact the maintainer
([@dofliu](https://github.com/dofliu)). We aim to acknowledge within **3 business days**.
