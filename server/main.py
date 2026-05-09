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
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from core.config import PROJECT_ROOT
from core.runtime import setup_utf8_stdout

from .jobs import get_default_store
from .routes import editor as editor_routes
from .routes import jobs as jobs_routes
from .routes import slides as slides_routes
from .routes import youtube as youtube_routes


# 對齊 vite.config.ts 的 build outDir
WEB_DIST = PROJECT_ROOT / "web" / "dist"


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
    )

    # 開發階段全開 CORS, 部署時要收緊到實際前端 origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(jobs_routes.router)
    app.include_router(youtube_routes.router)
    app.include_router(slides_routes.router)
    app.include_router(editor_routes.router)

    # React UI (PR-3e): web/dist 若存在就服務 /ui/*, 否則繼續用 vanilla /editor
    # 用 StaticFiles mount /ui/assets 處理已知 asset 檔, 其餘 /ui/* 走 SPA fallback
    # (deep link 例如 /ui/jobs/abc 直接刷新時 fallback 到 index.html, 由 React Router 處理)
    if WEB_DIST.exists():
        assets_dir = WEB_DIST / "assets"
        if assets_dir.exists():
            app.mount(
                "/ui/assets",
                StaticFiles(directory=str(assets_dir)),
                name="ui-assets",
            )

        @app.get("/ui/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str) -> FileResponse:
            # 防 path traversal
            target = (WEB_DIST / full_path).resolve()
            try:
                target.relative_to(WEB_DIST.resolve())
            except ValueError:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法路徑")
            # 找得到實檔 (例如 /ui/vite.svg) 就回那個檔, 找不到就 fallback index.html
            if target.is_file():
                return FileResponse(target)
            return FileResponse(WEB_DIST / "index.html")

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {
            "status": "ok",
            "service": "autoSolverVideo",
            "ui_built": WEB_DIST.exists(),
        }

    # 根路徑優先導 React UI, 沒 build 就退到 vanilla editor
    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        target = "/ui/" if WEB_DIST.exists() else "/editor"
        return RedirectResponse(url=target, status_code=307)

    @app.on_event("startup")
    async def _startup() -> None:
        # eager init store, 把 jobs/ 既有 state 讀回 cache
        store = get_default_store()
        print(f"[server] job store ready: {len(store.list())} 筆既有 job")

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
