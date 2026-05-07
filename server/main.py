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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.runtime import setup_utf8_stdout

from .jobs import get_default_store
from .routes import editor as editor_routes
from .routes import jobs as jobs_routes


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
    app.include_router(editor_routes.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok", "service": "autoSolverVideo"}

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
