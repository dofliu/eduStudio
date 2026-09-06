"""eduStudio MCP server — 把 :class:`edustudio_cli.EduStudioClient` 包成 MCP (Model Context Protocol) tools。

讓 Claude Code / Claude Desktop / 任何 MCP client 直接操作 eduStudio server (上傳簡報、查 job、改旁白、
核准、渲染動態漫畫影片、上傳 YouTube),不開 /app 介面。跟 CLI 一樣**只走 REST API**,不碰 server 與前端程式碼。

啟動 (stdio, 給 MCP client 當子程序拉起):

    python -m edustudio_cli.mcp_server                       # 讀 EDUSTUDIO_URL / EDUSTUDIO_API_TOKEN
    python -m edustudio_cli.mcp_server --server http://box:8000 --token ...
    python -m edustudio_cli mcp                              # 同上 (CLI 子命令)

Claude Code `.mcp.json`:

    {"mcpServers": {"edustudio": {"command": "python", "args": ["-m", "edustudio_cli.mcp_server"],
                                  "env": {"EDUSTUDIO_URL": "http://127.0.0.1:8000", "EDUSTUDIO_API_TOKEN": "..."}}}}

需要 MCP Python SDK (`pip install mcp`);同時相容 mcp 1.x (FastMCP) 與 2.x (MCPServer)。
每個 tool 都回單一 JSON 物件 (清單類回 {"count", "items"}),錯誤走 is_error 並帶 HTTP 狀態碼 + detail。
review gate 在這裡**依然存在**:需審查的 job 停在 `awaiting_review`,只有 `approve_job` 會放行,
而且它應該只在人看過草稿之後被呼叫 (見 INSTRUCTIONS)。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Callable

from .client import ComicsClient, EduStudioClient, EduStudioError

try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _ServerBase
except ImportError:  # pragma: no cover - mcp 1.x
    try:
        from mcp.server.fastmcp import FastMCP as _ServerBase  # type: ignore[no-redef]
    except ImportError as exc:  # pragma: no cover
        raise ImportError("eduStudio MCP server 需要 MCP Python SDK: pip install mcp") from exc

try:
    from mcp.types import ToolAnnotations as _ToolAnnotations
except ImportError:  # pragma: no cover
    _ToolAnnotations = None  # type: ignore[assignment]

# 用 SDK 的 ToolError 拋錯, 錯誤文字才會原樣傳給模型 (其他例外 SDK 只回「Error executing tool」並把細節留在 server log)
try:  # mcp >= 2.0
    from mcp.server.mcpserver.exceptions import ToolError as _ToolError
except ImportError:  # pragma: no cover - mcp 1.x
    try:
        from mcp.server.fastmcp.exceptions import ToolError as _ToolError  # type: ignore[no-redef]
    except ImportError:
        _ToolError = RuntimeError  # type: ignore[misc,assignment]

SERVER_NAME = "edustudio"

INSTRUCTIONS = """eduStudio 是老師用的教學內容產線 (PDF / PPTX / HTML 動畫 / 漫畫 → 有旁白字幕的影片)。
典型流程:
  1. upload_pptx / upload_video_source / upload_html_animation 建 job (回 job_id)。
  2. wait_job 等到 done / failed / awaiting_review。
  3. 停在 awaiting_review 的 job 是「人工審查關卡」:用 get_draft 取草稿 (deck JSON, 含每頁旁白),
     需要時 put_draft 改回去;**只有在使用者明確表示已看過草稿、同意渲染時才呼叫 approve_job**,
     不要自動核准。
  4. 核准後再 wait_job (until done/failed),done 後 download_artifacts 拿 MP4 + SRT,或 publish_youtube。
漫畫 (comics_*) 走 project → series → episode;comics_render_video 把 episode 渲成動態漫畫影片 (也是 job)。
所有 tool 的錯誤訊息都帶 HTTP 狀態碼與 server 回的 detail。檔案路徑都是「跑這個 MCP server 的機器」上的路徑。
"""

KIND_ALIAS = {
    "exam": "exam_pdf", "exam_pdf": "exam_pdf",
    "slides": "slides_pdf", "slides_pdf": "slides_pdf",
    "document": "document", "doc": "document",
}
BRIEF_JOB_KEYS = ("id", "source_type", "state", "created_at", "error")


def _ann(**hints: bool):
    """ToolAnnotations — mcp 2.x 用 snake_case (read_only_hint), 1.x 用 camelCase (readOnlyHint)。"""
    if _ToolAnnotations is None:
        return None
    try:
        return _ToolAnnotations(**hints)
    except Exception:  # pragma: no cover - mcp 1.x
        camel = {"".join(w.capitalize() if i else w for i, w in enumerate(k.split("_"))): v for k, v in hints.items()}
        try:
            return _ToolAnnotations(**camel)
        except Exception:
            return None


_READ = dict(annotations=_ann(read_only_hint=True))
_DESTRUCTIVE = dict(annotations=_ann(destructive_hint=True))


def normalize(result: Any) -> dict:
    """tool 回傳一律是 dict: dict 原樣; list → {"count", "items"}; 其他 → {"result"}。"""
    if isinstance(result, dict):
        return result
    if isinstance(result, (list, tuple)):
        return {"count": len(result), "items": list(result)}
    return {"result": result}


def _fail(exc: Exception) -> str:
    if isinstance(exc, EduStudioError):
        return f"eduStudio API {exc.status}: {exc.detail}"
    return f"{type(exc).__name__}: {exc}"


def build_server(client: EduStudioClient | None = None, *, name: str = SERVER_NAME,
                 client_factory: Callable[[], EduStudioClient] | None = None):
    """建 MCP server 並註冊所有 tool。

    `client` 可直接注入 (測試用 TestClient-backed client);沒給時第一次用到才建
    (`client_factory` 或預設讀 EDUSTUDIO_URL / EDUSTUDIO_API_TOKEN),所以 server 沒起來也能啟動 MCP、列 tool。
    """
    server = _ServerBase(name, instructions=INSTRUCTIONS)
    state: dict[str, Any] = {"client": client}

    def c() -> EduStudioClient:
        if state["client"] is None:
            state["client"] = (client_factory or EduStudioClient)()
        return state["client"]

    def k(project_id: str) -> ComicsClient:
        return c().comics(project_id)

    def guarded(fn):
        """把 client 例外變成有 HTTP 狀態碼的 tool error (MCP 會回 is_error=True 給模型),
        並把回傳值統一成單一 JSON 物件 (SDK 會把 list 拆成多個 content block, 對模型不好讀)。"""
        import functools

        @functools.wraps(fn)
        def wrapper(*a, **kw):
            try:
                return normalize(fn(*a, **kw))
            except (EduStudioError, OSError, TimeoutError, ValueError) as exc:
                raise _ToolError(_fail(exc)) from None
        return wrapper

    def tool(**kw):
        def deco(fn):
            server.tool(**kw)(guarded(fn))
            return fn
        return deco

    # ------------------------------------------------------------------ server / jobs
    @tool(**_READ)
    def edustudio_health() -> dict[str, Any]:
        """eduStudio server 健康檢查 (GET /health, 不需 token)。連不上會直接報錯。"""
        return c().health()

    @tool(**_READ)
    def edustudio_status() -> dict[str, Any]:
        """server 狀態總覽 (GET /api/status): 版本、model 設定、TTS backend、jobs 統計等。"""
        return c().status()

    @tool(**_READ)
    def list_jobs(brief: bool = True) -> dict[str, Any]:
        """列出所有影片 job。brief=True 只回 id / source_type / state / created_at / error。"""
        jobs = c().list_jobs()
        return [{key: j.get(key) for key in BRIEF_JOB_KEYS} for j in jobs] if brief else jobs

    @tool(**_READ)
    def get_job(job_id: str) -> dict[str, Any]:
        """單一 job 完整記錄 (state / options / artifacts / error / 進度)。"""
        return c().get_job(job_id)

    @tool(**_READ)
    def wait_job(job_id: str, until: list[str] | None = None, timeout: float = 900.0, interval: float = 2.0) -> dict[str, Any]:
        """輪詢 job 直到 state 進入 until 之一 (預設 done / failed / awaiting_review),回最終記錄。
        超過 timeout 秒回錯誤 (job 仍在跑,可再呼叫一次)。核准後要等渲染完成請用 until=["done","failed"]。"""
        kw: dict[str, Any] = {"timeout": timeout, "interval": max(0.05, interval)}
        if until:
            kw["until"] = tuple(until)
        return c().wait(job_id, **kw)

    @tool(**_READ)
    def get_job_log(job_id: str, tail: int = 100) -> dict[str, Any]:
        """job 的 pipeline log 最後 tail 行 (除錯 failed job 用)。"""
        return c().get_log(job_id, tail=tail)

    @tool(**_READ)
    def list_artifacts(job_id: str) -> dict[str, Any]:
        """job 產出的檔案清單 (final.mp4 / final.srt / 每章 mp4 ...)。"""
        return c().artifacts(job_id)

    @tool()
    def download_artifacts(job_id: str, dest_dir: str, kinds: list[str] | None = None) -> dict[str, Any]:
        """把 job 的產出 (預設 mp4 + srt) 下載到本機 dest_dir,回實際寫入的路徑。kinds 例 ["mp4","srt","pptx"]。"""
        paths = c().download_all(job_id, dest_dir, kinds=tuple(kinds) if kinds else ("mp4", "srt"))
        return {"job_id": job_id, "dest_dir": str(Path(dest_dir).resolve()), "files": [str(p) for p in paths]}

    @tool(**_DESTRUCTIVE)
    def delete_job(job_id: str) -> dict[str, Any]:
        """刪除 job 與其產出 (不可復原)。"""
        c().delete_job(job_id)
        return {"deleted": job_id}

    # ------------------------------------------------------------------ 建 job
    @tool()
    def upload_video_source(file_path: str, kind: str, project_id: str = "", mock: bool = False,
                            require_review: bool | None = None, options: dict | None = None) -> dict[str, Any]:
        """上傳 PDF / MD / TXT 建影片 job。kind: exam (考卷, 預設需審查) / slides (簡報 PDF) / document (講義)。
        options 是 JobOptions 覆寫 (例 {"tts_provider": "edge", "target_language": "zh-TW"});mock=True 走離線假資料。
        回 {job_id, ...},接著用 wait_job。"""
        source_type = KIND_ALIAS.get(kind.lower())
        if not source_type:
            raise ValueError(f"kind 需為 exam / slides / document, 不是 {kind!r}")
        opts = dict(options or {})
        if mock:
            opts["mock"] = True
        if require_review is not None:
            opts["require_review"] = require_review
        return c().upload(file_path, source_type, options=opts, project_id=project_id)

    @tool()
    def upload_pptx(file_path: str, project_id: str = "", only_missing: bool = True, options: dict | None = None) -> dict[str, Any]:
        """上傳 PPTX 建「補圖」job (缺圖頁由 AI 生圖, 原文字保留可編輯)。完成後用 pptx_to_video 轉成講解影片。
        only_missing=False 會為每一頁都生圖。"""
        return c().upload_pptx(file_path, only_missing=only_missing, options=options, project_id=project_id)

    @tool()
    def pptx_to_video(pptx_job_id: str) -> dict[str, Any]:
        """把 done 的 PPTX 補圖 job 轉成簡報講解影片 job (自動旁白 + 字幕),回新 job 的 job_id。"""
        return c().pptx_to_video(pptx_job_id)

    @tool()
    def upload_html_animation(source: str, duration: float, title: str = "", fps: int = 30, width: int = 1920,
                              height: int = 1080, mock: bool = False, project_id: str = "") -> dict[str, Any]:
        """自含 HTML 動畫 (本機檔案路徑或 http(s) URL) → MP4 (Playwright 逐格截圖)。duration 秒。mock=True 用 ffmpeg 測試訊號。"""
        opts = {"mock": True} if mock else None
        return c().upload_html(source, duration=duration, title=title, fps=fps, width=width, height=height,
                               options=opts, project_id=project_id)

    # ------------------------------------------------------------------ review gate
    @tool(**_READ)
    def get_draft(job_id: str) -> dict[str, Any]:
        """取 awaiting_review job 的草稿 deck (sections / slides / 每頁 narration)。改完用 put_draft 存回。"""
        return c().get_draft(job_id)

    @tool()
    def put_draft(job_id: str, deck: dict) -> dict[str, Any]:
        """覆寫草稿 deck (整份 JSON, 通常是 get_draft 的結果改過旁白/順序)。不會觸發渲染。"""
        return c().put_draft(job_id, deck)

    @tool(**_READ)
    def review_flags(job_id: str) -> dict[str, Any]:
        """草稿的自動檢查旗標 (可疑 OCR、過長旁白、缺圖等),幫人審查用。"""
        return c().review_flags(job_id)

    @tool()
    def approve_job(job_id: str) -> dict[str, Any]:
        """核准 awaiting_review 的 job 開始渲染 — 這就是介面上的「核准」按鈕。
        只在使用者明確確認已看過草稿後呼叫;之後用 wait_job(until=["done","failed"]) 等渲染。"""
        return c().approve(job_id)

    @tool()
    def render_section(job_id: str, section_id: str) -> dict[str, Any]:
        """只重渲一個章節 (改了某章旁白後不用整份重跑)。"""
        return c().render_section(job_id, section_id)

    # ------------------------------------------------------------------ YouTube
    @tool()
    def publish_youtube(job_id: str, artifact: str, title: str, description: str = "", tags: list[str] | None = None,
                        privacy: str = "unlisted", category: str = "27") -> dict[str, Any]:
        """把 job 的某個 mp4 (artifact 檔名, 例 final.mp4) 上傳 YouTube (需 server 端先設好 OAuth)。privacy: unlisted / private / public。"""
        return c().publish_youtube(job_id, artifact, title=title, description=description, tags=tags or (),
                                   privacy=privacy, category=category)

    @tool(**_READ)
    def youtube_status(job_id: str, artifact: str) -> dict[str, Any]:
        """查該 artifact 的 YouTube 上傳狀態 / 影片網址。"""
        return c().youtube_status(job_id, artifact)

    # ------------------------------------------------------------------ projects
    @tool(**_READ)
    def list_projects() -> dict[str, Any]:
        """列出專案 (一門課 = 一個 project 工作空間)。"""
        return c().list_projects()

    @tool(**_READ)
    def get_project(project_id: str) -> dict[str, Any]:
        """專案詳情 (標題、目標語言、素材)。"""
        return c().get_project(project_id)

    @tool()
    def create_project(project_id: str, title: str, target_languages: list[str] | None = None) -> dict[str, Any]:
        """建立專案。project_id 用英數 (例 wind101)。"""
        return c().create_project(project_id, title, target_languages or ())

    # ------------------------------------------------------------------ comics
    @tool(**_READ)
    def comics_list_series(project_id: str) -> dict[str, Any]:
        """專案下的漫畫系列 (Series Bible: 角色、畫風鎖定)。"""
        return k(project_id).list_series()

    @tool()
    def comics_create_series(project_id: str, series_id: str, title: str, characters: list[dict] | None = None,
                             fields: dict | None = None) -> dict[str, Any]:
        """建漫畫系列。characters 例 [{"character_id": "aguang", "name": "阿光", "voice": "edge:zh-TW-YunJheNeural"}];
        fields 是其他 SeriesBible 欄位 (art_style, tone ...)。"""
        return k(project_id).create_series(series_id, title, characters=characters, **(fields or {}))

    @tool(**_READ)
    def comics_get_series(project_id: str, series_id: str) -> dict[str, Any]:
        """系列完整內容 (角色表、visual_lock、anchor_assets)。"""
        return k(project_id).get_series(series_id)

    @tool()
    def comics_update_series(project_id: str, series_id: str, series: dict) -> dict[str, Any]:
        """整份覆寫系列 (PUT)。先 comics_get_series 改再存。"""
        return k(project_id).update_series(series_id, series)

    @tool(**_READ)
    def comics_list_episodes(project_id: str, series_id: str | None = None) -> dict[str, Any]:
        """列 episode (單話);可用 series_id 過濾。"""
        return k(project_id).list_episodes(series_id)

    @tool()
    def comics_create_episode(project_id: str, series_id: str, story_id: str, title: str, fields: dict | None = None) -> dict[str, Any]:
        """建 episode。fields 例 {"page_count": 6, "learning_objectives": ["..."], "characters": ["aguang", "xiaoru"]}。"""
        return k(project_id).create_episode(series_id, story_id, title, **(fields or {}))

    @tool(**_READ)
    def comics_get_episode(project_id: str, story_id: str, version: str | None = None) -> dict[str, Any]:
        """episode manifest (state / pages / dialogues / assets / QA)。"""
        return k(project_id).get_episode(story_id, version)

    @tool()
    def comics_update_episode(project_id: str, story_id: str, updates: dict, version: str | None = None) -> dict[str, Any]:
        """部分更新 episode (PATCH),例 {"pages": [...]} 或 {"state": "STORYBOARD"}。"""
        return k(project_id).update_episode(story_id, updates, version)

    @tool()
    def comics_generate(project_id: str, story_id: str, what: str, mock: bool = False, model: str | None = None,
                        version: str | None = None) -> dict[str, Any]:
        """呼叫 AI 生成 episode 內容。what: script (劇本) / storyboard (分鏡+對白) / images (逐頁生圖, 需 GEMINI_API_KEY)。
        mock=True 走假資料 (產出會烙水印)。"""
        return k(project_id).generate(story_id, what, mock=mock, model=model, version=version)

    @tool()
    def comics_upload_asset(project_id: str, story_id: str, file_path: str, kind: str = "scene",
                            provenance: str = "user_upload", asset_id: str | None = None, version: str | None = None) -> dict[str, Any]:
        """上傳圖檔當 episode 素材 (kind: scene / character_anchor ...)。之後用 comics_update_episode 把 page.image_asset_id 指到 asset_id。"""
        return k(project_id).upload_asset(story_id, file_path, kind=kind, provenance=provenance, asset_id=asset_id, version=version)

    @tool()
    def comics_auto_layout(project_id: str, story_id: str, version: str | None = None) -> dict[str, Any]:
        """自動排對話泡泡位置 (避開人臉 / 已標的 speaker_positions)。"""
        return k(project_id).auto_layout(story_id, version)

    @tool()
    def comics_locate_speakers(project_id: str, story_id: str, page_numbers: list[int] | None = None,
                               mock: bool = False, version: str | None = None) -> dict[str, Any]:
        """用視覺模型找每頁各角色的位置 (speaker_positions),再排泡泡。page_numbers 空 = 全部頁。"""
        return k(project_id).locate_speakers(story_id, page_numbers=page_numbers or (), mock=mock, version=version)

    @tool(**_READ)
    def comics_validation(project_id: str, story_id: str, version: str | None = None) -> dict[str, Any]:
        """六道 QA gate 結果 (哪裡還沒過、為何不能 READY)。"""
        return k(project_id).validation(story_id, version)

    @tool()
    def comics_set_state(project_id: str, story_id: str, target: str, reason: str = "", version: str | None = None) -> dict[str, Any]:
        """推進 episode 狀態 (DRAFT → STORYBOARD → ... → READY → PUBLISHED);gate 沒過會 4xx。"""
        return k(project_id).set_state(story_id, target, reason, version)

    @tool()
    def comics_export(project_id: str, story_id: str, kind: str, version: str | None = None) -> dict[str, Any]:
        """匯出 episode。kind: html / pdf / docx / source。"""
        return k(project_id).export(story_id, kind, version)

    @tool()
    def comics_render_video(project_id: str, story_id: str, voices: dict[str, str] | None = None, fps: int = 30,
                            width: int = 1920, height: int = 1080, tts_provider: str | None = None,
                            mock: bool = False, version: str = "v0.1") -> dict[str, Any]:
        """把 episode 渲成有旁白的動態漫畫影片 (背景 job)。voices 對應 character_id → 聲音
        (例 {"aguang": "edge:zh-TW-YunJheNeural", "narrator": "default"});回 {job_id, ...},用 wait_job(until=["done","failed"]) 等。"""
        return k(project_id).render_video(story_id, version=version, voices=voices, fps=fps, width=width, height=height,
                                          tts_provider=tts_provider, mock=mock)

    @tool()
    def comics_publish(project_id: str, story_id: str, published_by: str, channel: str = "internal_reader",
                       version: str | None = None) -> dict[str, Any]:
        """發布 READY 的 episode (記錄發布者與通道)。"""
        return k(project_id).publish(story_id, published_by, channel, version)

    # ------------------------------------------------------------------ escape hatch
    @tool()
    def api_request(method: str, path: str, json_body: Any = None, params: dict | None = None) -> dict[str, Any]:
        """直接打任意 eduStudio REST 端點 (見 server 的 /docs)。method GET/POST/PUT/PATCH/DELETE, path 例 "/jobs"。
        其他 tool 沒包到的功能用這個。"""
        return c().request(method.upper(), path, json=json_body, params=params)

    return server


def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m edustudio_cli.mcp_server", description="eduStudio MCP server")
    p.add_argument("--server", default=None, help="eduStudio server URL (預設 $EDUSTUDIO_URL 或 http://127.0.0.1:8000)")
    p.add_argument("--token", default=None, help="API token (預設 $EDUSTUDIO_API_TOKEN)")
    p.add_argument("--timeout", type=float, default=float(os.environ.get("EDUSTUDIO_TIMEOUT", "300")), help="單次 HTTP 逾時秒數")
    p.add_argument("--transport", default="stdio", choices=("stdio", "streamable-http", "sse"),
                   help="MCP transport (預設 stdio; http 類給遠端 MCP client)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)

    def factory() -> EduStudioClient:
        return EduStudioClient(args.server, args.token, timeout=args.timeout)

    server = build_server(client_factory=factory)
    # stdio 模式下 stdout 是 MCP 通道, 任何提示只能走 stderr
    print(f"[edustudio-mcp] transport={args.transport} server={args.server or os.environ.get('EDUSTUDIO_URL', 'http://127.0.0.1:8000')}",
          file=sys.stderr)
    server.run(transport=args.transport)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
