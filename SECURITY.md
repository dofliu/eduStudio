# 安全政策 · Security Policy

## ⚠️ 部署前必讀：請勿把 server 裸奔在公網

eduStudio 是設計給**個人 / 單位自架**的工具。請注意目前的安全假設：

- **目前後端尚未內建身分驗證**（單一共享 token 驗證層為規劃中項目）。在它就緒之前，**任何能連到
  你 server 的人都能呼叫 API、看你的 job 與產出、消耗你的 Gemini 額度**。
- 預設範例用 `--host 127.0.0.1`（只有本機可連），**請維持這個預設**，除非你清楚知道自己在做什麼。
- 若要從區網/外部存取，**務必**放在可信任的反向代理（Nginx/Caddy）後面並自行加上存取控制
  （HTTP Basic Auth / VPN / Cloudflare Access / Tailscale 等），**不要**直接把
  `0.0.0.0:8000` 暴露到公開網際網路。
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

eduStudio is built for **self-hosting**. **The backend currently ships without built-in
authentication** — until a shared-token auth layer lands, anyone who can reach your server can call
the API, see your jobs/outputs, and spend your Gemini quota. Keep the default `127.0.0.1` bind; if you
need remote access, put it behind a trusted reverse proxy with access control (Basic Auth / VPN /
Cloudflare Access / Tailscale). **Do not expose `0.0.0.0:8000` to the public internet.**

**Do not file public issues for vulnerabilities.** Use GitHub's **private vulnerability reporting**
(repo **Security** tab → *Report a vulnerability*) or contact the maintainer
([@dofliu](https://github.com/dofliu)). We aim to acknowledge within **3 business days**.
