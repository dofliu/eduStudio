"""S-1 單一共享 token 驗證層。

設計 (2026-06-07 拍板):
- 共享密鑰來自環境變數 EDUSTUDIO_API_TOKEN。
- **沒設 → server 照跑但啟動大聲警告**「未驗證, 勿暴露公網」(保留 localhost 自用方便,
  既有測試不受影響)。
- 設了 → 一個 HTTP middleware 擋下所有請求(read+write+靜態+媒體都擋, 因威脅含「讀你的
  job/影片」), 除了少數豁免路徑。
- **瀏覽器走 session cookie**: /auth 比對 token 後種 HttpOnly; SameSite=Strict (https 加
  Secure) cookie。媒體(mp4/png)同源自動帶 cookie, 解決 <video>/<img> 無法帶 Authorization
  header 的硬限制。
- **CLI / curl 走 Bearer**: 同時接受 Authorization: Bearer <token>。
- 不做帳號系統 (單一共享 token 即可)。

為何用 middleware 而非 per-router Depends: 靜態 mount (StaticFiles) 與 SPA fallback 不是
router, Depends 蓋不到; middleware 能一致覆蓋每個請求(含媒體與前端資產)。
"""
from __future__ import annotations

import hmac
import os

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

TOKEN_ENV = "EDUSTUDIO_API_TOKEN"
COOKIE_NAME = "es_auth"

# 這些路徑即使開了驗證也要可達, 否則使用者無法登入 / 監控無法探活。
# /auth: 登入端點本身。/health: 給 Docker healthcheck / 監控(只回布林診斷, 不含密鑰)。
# /api/v1/events: 相容外部瀏覽器/AI instrumentation 的 no-op event sink；不讀取、不落盤。
_EXEMPT_PREFIXES = ("/auth", "/health", "/api/v1/events")


def get_api_token() -> str | None:
    """共享密鑰 (環境變數)。每次請求即時讀, 方便測試 monkeypatch。"""
    tok = os.environ.get(TOKEN_ENV)
    return tok if tok else None


def auth_enabled() -> bool:
    return get_api_token() is not None


def _token_matches(provided: str | None, expected: str) -> bool:
    """常數時間比對, 避免 timing side-channel。"""
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header and header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


def is_authenticated(request: Request, expected: str) -> bool:
    """Bearer header (CLI/自動化) 或 cookie (瀏覽器) 任一通過即可。"""
    if _token_matches(_extract_bearer(request), expected):
        return True
    if _token_matches(request.cookies.get(COOKIE_NAME), expected):
        return True
    return False


def _wants_html(request: Request) -> bool:
    """判斷是不是瀏覽器在開頁面(要回登入框), 而非 API/媒體(要回 401 JSON)。"""
    if request.method != "GET":
        return False
    accept = request.headers.get("accept", "")
    return "text/html" in accept


def login_page_html(next_url: str = "/app/", error: str = "") -> str:
    """極簡、self-contained 的登入頁(不動 React build)。"""
    err_block = (
        f'<p class="err">{error}</p>' if error else ""
    )
    # next_url 只用在 hidden field; 防 HTML 注入做最小轉義。
    safe_next = next_url.replace('"', "%22").replace("<", "").replace(">", "")
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>eduStudio — 登入</title>
<style>
  body {{ font-family: system-ui, sans-serif; background:#0f172a; color:#e2e8f0;
         display:flex; min-height:100vh; align-items:center; justify-content:center; margin:0; }}
  .card {{ background:#1e293b; padding:2rem 2.25rem; border-radius:12px; width:320px;
          box-shadow:0 10px 30px rgba(0,0,0,.4); }}
  h1 {{ font-size:1.15rem; margin:0 0 .25rem; }}
  p.sub {{ color:#94a3b8; font-size:.85rem; margin:.25rem 0 1.25rem; }}
  label {{ display:block; font-size:.8rem; color:#94a3b8; margin-bottom:.35rem; }}
  input {{ width:100%; box-sizing:border-box; padding:.6rem .7rem; border-radius:8px;
          border:1px solid #334155; background:#0f172a; color:#e2e8f0; font-size:.95rem; }}
  button {{ width:100%; margin-top:1rem; padding:.6rem; border:0; border-radius:8px;
           background:#6366f1; color:#fff; font-weight:600; font-size:.95rem; cursor:pointer; }}
  button:hover {{ background:#4f46e5; }}
  .err {{ color:#f87171; font-size:.82rem; margin:0 0 .75rem; }}
</style>
</head>
<body>
  <form class="card" method="post" action="/auth">
    <h1>🎓 eduStudio</h1>
    <p class="sub">這個 server 已啟用存取保護，請輸入 access token。</p>
    {err_block}
    <label for="token">Access token</label>
    <input id="token" name="token" type="password" autofocus autocomplete="current-password">
    <input type="hidden" name="next" value="{safe_next}">
    <button type="submit">登入</button>
  </form>
</body>
</html>"""


def _is_exempt(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in _EXEMPT_PREFIXES)


def install_auth(app) -> None:
    """掛上驗證 middleware 與 /auth 登入端點。沒設 token 時 middleware 為 no-op。"""

    @app.middleware("http")
    async def _auth_middleware(request: Request, call_next):
        expected = get_api_token()
        # 未設 token → 完全放行(localhost 自用), 不影響既有行為與測試。
        if expected is None:
            return await call_next(request)

        # CORS 預檢與豁免路徑(登入端點/健康檢查)放行。
        if request.method == "OPTIONS" or _is_exempt(request.url.path):
            return await call_next(request)

        if is_authenticated(request, expected):
            return await call_next(request)

        # 未通過: 瀏覽器開頁面 → 回登入框; API/媒體 → 401。
        if _wants_html(request):
            next_url = request.url.path
            if request.url.query:
                next_url += "?" + request.url.query
            return HTMLResponse(login_page_html(next_url=next_url), status_code=200)
        return JSONResponse(
            {"detail": "未授權: 需要 access token (cookie 或 Authorization: Bearer)"},
            status_code=401,
        )

    @app.post("/auth", include_in_schema=False)
    async def auth_login(request: Request) -> Response:
        expected = get_api_token()
        # 表單(瀏覽器)或 JSON 都接受。
        token = None
        next_url = "/app/"
        ctype = request.headers.get("content-type", "")
        if "application/json" in ctype:
            try:
                body = await request.json()
                token = (body or {}).get("token")
                next_url = (body or {}).get("next") or next_url
            except Exception:
                token = None
        else:
            form = await request.form()
            token = form.get("token")
            next_url = form.get("next") or next_url

        # next 只允許站內相對路徑, 防 open redirect。
        if not isinstance(next_url, str) or not next_url.startswith("/") or next_url.startswith("//"):
            next_url = "/app/"

        if expected is None:
            # 沒開驗證, 直接放行回去。
            return RedirectResponse(url=next_url, status_code=303)

        if not _token_matches(token, expected):
            return HTMLResponse(
                login_page_html(next_url=next_url, error="token 不正確，請再試一次。"),
                status_code=401,
            )

        resp = RedirectResponse(url=next_url, status_code=303)
        resp.set_cookie(
            key=COOKIE_NAME,
            value=expected,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            path="/",
        )
        return resp

    @app.post("/auth/logout", include_in_schema=False)
    async def auth_logout() -> Response:
        resp = RedirectResponse(url="/app/", status_code=303)
        resp.delete_cookie(COOKIE_NAME, path="/")
        return resp


def warn_if_open() -> None:
    """啟動時若沒設 token, 大聲警告。"""
    if not auth_enabled():
        print(
            "\n" + "=" * 64 + "\n"
            "[security] ⚠ EDUSTUDIO_API_TOKEN 未設定 — server 無存取驗證!\n"
            "[security]   任何能連到此 server 的人都能呼叫 API、看你的 job/影片、\n"
            "[security]   消耗你的 Gemini 額度。localhost 自用 OK；\n"
            "[security]   **切勿在未設 token 的情況下暴露到內網/公網**。\n"
            "[security]   設定方式: 在 .env 或環境變數加 EDUSTUDIO_API_TOKEN=<你的密鑰>\n"
            + "=" * 64 + "\n"
        )
    else:
        print("[security] ✓ EDUSTUDIO_API_TOKEN 已設定，存取驗證已啟用。")
