"""FastAPI 進入點 — 組 app, 掛 routers, 提供 CLI 啟動。

啟動方式:
    # 開發模式 (auto-reload)
    python -m server.main --reload

    # 生產模式
    python -m server.main --host 0.0.0.0 --port 8000

    # 也可以用 uvicorn 直接啟動 (CI / docker compose 用這條)
    uvicorn server.main:app --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import argparse
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from core.config import PROJECT_ROOT, get_allowed_origins
from core.logging_setup import setup_logging
from core.runtime import setup_utf8_stdout
from core.selfcheck import print_startup_selfcheck

from .auth import install_auth, warn_if_open
from .jobs import get_default_store
from .ratelimit import install_limiter
from .routes import editor as editor_routes
from .routes import jobs as jobs_routes
from .routes import infocards as infocards_routes
from .routes import comics as comics_routes
from .routes import library as library_routes
from .routes import localization as localization_routes
from .routes import projects as projects_routes
from .routes import proposals as proposals_routes
from .routes import settings as settings_routes
from .routes import slides as slides_routes
from .routes import themes as themes_routes
from .routes import uploads as uploads_routes
from .routes import uploads_html as uploads_html_routes
from .routes import uploads_pptx as uploads_pptx_routes
from .routes import google_photos as google_photos_routes
from .routes import voices as voices_routes
from .routes import youtube as youtube_routes


# Windows 上 Python mimetypes.guess_type() 對 .js / .mjs 常回 text/plain
# (取決 HKLM\Software\Classes 是否有 .js 對應 Content Type 鍵, 不一定有),
# Starlette StaticFiles 用這函式決定 Content-Type, 導致瀏覽器 strict MIME check
# 拒載 ES module → React UI (web/dist) 整頁白畫面。
# 在 module 頂部強制覆寫常見前端 asset 的 MIME, 確保跨平台一致。
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("image/svg+xml", ".svg")


# PR-4c: 整套 logging 一次 init. 在 module-level 跑, uvicorn import server.main
# 時就會生效, 不必等 main() 才 setup
setup_logging()


# eduStudio 合併 C-4: 統一 app（Claude Design 設計、infoCard React19 build，base=/app/）。
# （U-5 2026-08-30: legacy `/ui` 前端已退場 — web/ 原始碼專案與 web/dist 產物皆移除，
#  `/ui` 與 `/studio` 一樣改 307 轉址到 `/app/`。）
WEB_EDUAPP = PROJECT_ROOT / "web" / "eduapp"
# eduStudio 合併 C-4 方案 A: 統一入口 landing（外觀可獨立替換，待 Claude Design 重做）。
LANDING_PAGE = PROJECT_ROOT / "server" / "static" / "landing.html"


def _run_startup_checks() -> None:
    """初始化可恢復的 runtime 狀態，供 FastAPI lifespan 與測試共用。

    為什麼保持同步：這些工作都是短時間的本機設定／檔案狀態檢查，沒有需要跨
    lifespan 保存的 async resource；抽成函式後可精確驗證啟動順序。
    """
    # `uvicorn server.main:app` 不會進 main()；hidden/redirected Windows process 若仍是
    # CP950，下面 selfcheck 的 Unicode 符號會讓啟動直接 UnicodeEncodeError。
    setup_utf8_stdout()
    # eager init store，把 jobs/ 既有 state 讀回 cache。
    store = get_default_store()
    print(f"[server] job store ready: {len(store.list())} 筆既有 job")
    # R-1：把因重啟中斷而卡住的 in-flight job 標 failed（可一鍵重試）。
    interrupted = store.resume_interrupted()
    if interrupted:
        print(f"[server] R-1: 標記 {len(interrupted)} 個重啟中斷的 job 為 failed: {interrupted}")
    # D-5：環境自檢；S-1：沒設 token 時提醒不可暴露公網。
    print_startup_selfcheck()
    warn_if_open()


@asynccontextmanager
async def _app_lifespan(_: FastAPI) -> AsyncIterator[None]:
    """FastAPI 建議的 lifespan；取代 deprecated startup event API。"""
    _run_startup_checks()
    yield


def create_app() -> FastAPI:
    """App factory — 測試時直接 import create_app() 取乾淨的 app instance。"""
    app = FastAPI(
        title="autoSolverVideo API",
        description=(
            "考卷檢討影片自動生成系統 — REST API。\n\n"
            "PR-2a 範圍:exam_pdf / slides_pdf 兩種 source。"
            "PR-2b 會新增 repo / document / url。"
        ),
        version="0.2.0",
        lifespan=_app_lifespan,
    )

    # CORS 收緊 (S-2): 預設只放行本機 origin, 部署時用 EDUSTUDIO_ALLOWED_ORIGINS 覆寫。
    # 同源 /app 不經過 CORS, 不受影響。設 "*" 可臨時全開除錯。
    allowed_origins = get_allowed_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # S-1: 單一共享 token 驗證層 (沒設 EDUSTUDIO_API_TOKEN 時為 no-op)。
    install_auth(app)

    # S-6: per-IP rate limit (每個 app 一個獨立 limiter)。
    install_limiter(app)

    app.include_router(jobs_routes.router)
    app.include_router(youtube_routes.router)
    app.include_router(slides_routes.router)
    app.include_router(uploads_routes.router)
    app.include_router(uploads_html_routes.router)  # HTML 動畫 → MP4 → 接既有上傳
    app.include_router(uploads_pptx_routes.router)  # PPTX 原檔就地補圖 (文字可編輯)
    app.include_router(google_photos_routes.router)  # Google 相簿 → 相片簡報/影片
    app.include_router(voices_routes.router)
    app.include_router(library_routes.router)
    app.include_router(editor_routes.router)
    app.include_router(proposals_routes.router)  # v4 階段 2 B iter 14
    app.include_router(themes_routes.router)     # iter 72: theme gallery
    app.include_router(projects_routes.router)   # eduStudio 合併 PR-M1: Project 薄層
    app.include_router(localization_routes.router)  # eduStudio 合併 B-2: translateGemma 收編
    app.include_router(infocards_routes.router)   # eduStudio 合併 C-4: infoCard 收編
    app.include_router(comics_routes.router)      # eduStudio: file-first 漫畫製作與連載 reader
    app.include_router(settings_routes.router)    # eduStudio 設定頁: 品牌/API/模型

    @app.post("/api/v1/events/ai", include_in_schema=False)
    async def ai_event_sink() -> Response:
        """相容瀏覽器/AI 外掛的背景 telemetry 呼叫，避免測試與操作 log 持續出現 404。

        為什麼回 204 而不是收資料：目前 eduStudio 沒有事件追蹤資料模型，也不應在未設計
        retention / privacy boundary 前落盤；這裡只把外部 instrumentation 的噪音收斂成 no-op。
        """
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # U-1: `/studio` 退場。原 infoCard 前端 client-side 直連 Gemini（繞過後端計費 +
    # review gate），其源碼不在本 repo，且視覺功能已於 U-2 在 `/app` 補齊對等（逐區
    # refine / 區域選擇）。故不再 serve 該 SPA，改一律 307 轉址到 `/app/`：關掉繞過
    # 漏洞、舊書籤/連結不 404。
    # U-5 (2026-08-30 劉老師拍板): `/ui`（原 autoSolver React 前端）同樣退場 —
    # web/ 原始碼專案與 build 產物已移除，功能已由 `/app` 對等覆蓋
    # （review gate / proposals / library / YouTube 發布，P2-4 四站 click-through 驗過）。
    # 307（暫時）而非 301/308：不被瀏覽器永久快取，保留反悔餘地。
    @app.get("/studio", include_in_schema=False)
    @app.get("/studio/{full_path:path}", include_in_schema=False)
    @app.get("/ui", include_in_schema=False)
    @app.get("/ui/{full_path:path}", include_in_schema=False)
    async def legacy_sunset(full_path: str = "") -> RedirectResponse:
        return RedirectResponse(url="/app/", status_code=307)

    # eduStudio 合併 C-4: 統一 app（Claude Design 設計）serve 在 /app/*（同 /ui 模式）。
    if WEB_EDUAPP.exists():
        eduapp_assets = WEB_EDUAPP / "assets"
        if eduapp_assets.exists():
            app.mount(
                "/app/assets",
                StaticFiles(directory=str(eduapp_assets)),
                name="eduapp-assets",
            )

        @app.get("/app/{full_path:path}", include_in_schema=False)
        async def eduapp_spa(full_path: str) -> FileResponse:
            target = (WEB_EDUAPP / full_path).resolve()
            try:
                target.relative_to(WEB_EDUAPP.resolve())
            except ValueError:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法路徑")
            if target.is_file():
                return FileResponse(target)
            return FileResponse(WEB_EDUAPP / "index.html")

    @app.get("/health", tags=["meta"])
    async def health(store=Depends(get_default_store)) -> dict:
        """server 健康狀態 + setup 診斷 (iter 36 加強).

        給 monitoring (Docker healthcheck / nagios) + 新用戶 onboarding sanity
        check (確認 GEMINI_API_KEY 設了 / proposals.json 存在 / 字型 OK)。
        """
        import os

        from core.config import (
            PIPELINE_CONFIG_PATH,
            PROPOSALS_PATH,
            TTS_CONFIG_PATH,
            get_fallback_font_path,
            get_font_path,
            get_gemini_api_key,
            get_mono_font_path,
        )
        from core.whisper_util import get_whisper_model_status

        return {
            "status": "ok",
            "service": "autoSolverVideo",
            # U-5: legacy /ui 退場後唯一前端 = /app（web/eduapp），兩鍵語意合一
            "ui_built": WEB_EDUAPP.exists(),
            "ui_eduapp_built": WEB_EDUAPP.exists(),
            # setup diagnostics — 給 onboarding / monitoring
            "gemini_api_key_set": bool(get_gemini_api_key()),
            "tts_config_exists": TTS_CONFIG_PATH.exists(),
            "pipeline_config_exists": PIPELINE_CONFIG_PATH.exists(),
            "proposals_json_exists": PROPOSALS_PATH.exists(),
            "jobs_count": len(store.list()),
            # 字型可達性 (檔案實際存在) — Linux Docker 環境若 Noto 沒裝這會 False
            "font_main_exists": os.path.exists(get_font_path()),
            "font_fallback_exists": os.path.exists(get_fallback_font_path()),
            "font_mono_exists": os.path.exists(get_mono_font_path()),
            "whisper": get_whisper_model_status(),
        }

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        """統一介面目前沒有品牌 favicon；明確回 204，避免瀏覽器持續製造 404 噪音。"""
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # 根路徑 = 統一入口 landing（合併 C-4 方案 A）。landing 缺檔則 fallback 舊行為。
    @app.get("/", include_in_schema=False)
    async def root():
        if LANDING_PAGE.is_file():
            return FileResponse(LANDING_PAGE)
        target = "/app/" if WEB_EDUAPP.exists() else "/editor"
        return RedirectResponse(url=target, status_code=307)

    return app


# uvicorn 直接 import 用的 module-level instance
app = create_app()


def main() -> None:
    setup_utf8_stdout()
    ap = argparse.ArgumentParser(description="啟動 autoSolverVideo API server")
    ap.add_argument("--host", default="127.0.0.1", help="預設 127.0.0.1 (避免被防火牆擋)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reload", action="store_true", help="開發模式 auto-reload")
    args = ap.parse_args()

    import uvicorn
    uvicorn.run(
        "server.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
