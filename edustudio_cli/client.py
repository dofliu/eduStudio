"""EduStudioClient — 把 eduStudio REST API 包成 Python 方法。

設計
----
- 只依賴 requests (fastapi 相依已帶進來); 不 import server/core, 可以裝在另一台機器上遠端操作。
- 每個方法對應一個端點, 回傳 server 的 JSON (dict); 4xx/5xx 一律 raise EduStudioError(status, detail)。
- `session` 可注入任何有 `.request(method, url, ...)` 的物件 (requests.Session / FastAPI TestClient),
  測試不用起 server。
- token: 建構參數 > 環境變數 EDUSTUDIO_API_TOKEN; base_url 預設環境變數 EDUSTUDIO_URL 或 localhost:8000。

Review gate 不在 client 端繞: `approve()` 就是 POST /jobs/{id}/approve, 語意等同介面上按「核准」,
呼叫端要自己先看過 draft。
"""
from __future__ import annotations

import base64
import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Callable, Iterable

DEFAULT_URL = "http://127.0.0.1:8000"
TERMINAL_STATES = ("done", "failed")
REVIEW_STATES = ("awaiting_review",)


class EduStudioError(RuntimeError):
    """server 回 4xx/5xx。status 是 HTTP 狀態碼, detail 是 server 的錯誤訊息 (FastAPI 的 detail 欄)。"""

    def __init__(self, status: int, detail: str, *, method: str = "", path: str = ""):
        super().__init__(f"{method} {path} → HTTP {status}: {detail}")
        self.status = status
        self.detail = detail
        self.method = method
        self.path = path


def _detail(resp) -> str:
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001 — 非 JSON 錯誤頁
        return (getattr(resp, "text", "") or "")[:500]
    if isinstance(body, dict):
        d = body.get("detail", body)
        return d if isinstance(d, str) else str(d)
    return str(body)[:500]


class EduStudioClient:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        *,
        timeout: float = 120.0,
        session: Any = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("EDUSTUDIO_URL") or DEFAULT_URL).rstrip("/")
        self.token = token if token is not None else os.environ.get("EDUSTUDIO_API_TOKEN")
        self.timeout = timeout
        if session is None:
            import requests

            session = requests.Session()
        self._session = session

    # ------------------------------------------------------------------ 低階
    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        data: dict | None = None,
        files: dict | None = None,
        params: dict | None = None,
        expect_json: bool = True,
    ) -> Any:
        """呼叫任意端點 (逃生門)。expect_json=False 時回 raw bytes (下載檔案用)。"""
        url = self.base_url + (path if path.startswith("/") else "/" + path)
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        kwargs: dict[str, Any] = {"headers": headers, "params": params}
        if json is not None:
            kwargs["json"] = json
        if data is not None:
            kwargs["data"] = data
        if files is not None:
            kwargs["files"] = files
        # requests 吃 timeout; FastAPI TestClient (有 .app) 不吃 → 不傳
        if not hasattr(self._session, "app"):
            kwargs["timeout"] = self.timeout
        resp = self._session.request(method, url, **kwargs)
        if resp.status_code >= 400:
            raise EduStudioError(resp.status_code, _detail(resp), method=method, path=path)
        if not expect_json:
            return resp.content
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def get(self, path: str, **kw) -> Any:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw) -> Any:
        return self.request("POST", path, **kw)

    # ------------------------------------------------------------------ 健康 / 狀態
    def health(self) -> dict:
        return self.get("/health")

    def status(self) -> dict:
        return self.get("/status")

    # ------------------------------------------------------------------ jobs
    def create_job(self, source_type: str, source: dict, options: dict | None = None) -> dict:
        """POST /jobs — source 例: {"path": "..."} 或 {"url": "..."} (檔案要在 server 那台機器上)。"""
        return self.post("/jobs", json={"source_type": source_type, "source": source, "options": options or {}})

    def list_jobs(self) -> list[dict]:
        return self.get("/jobs").get("jobs", [])

    def get_job(self, job_id: str) -> dict:
        return self.get(f"/jobs/{job_id}")

    def delete_job(self, job_id: str) -> None:
        self.request("DELETE", f"/jobs/{job_id}")

    def get_draft(self, job_id: str) -> dict:
        """AI 產出的草稿 (deck.json / exam.json), review 階段給人看與改。"""
        return self.get(f"/jobs/{job_id}/draft")

    def put_draft(self, job_id: str, deck: dict) -> dict:
        return self.request("PUT", f"/jobs/{job_id}/draft", json={"deck": deck})

    def review_flags(self, job_id: str) -> Any:
        return self.get(f"/jobs/{job_id}/review-flags")

    def approve(self, job_id: str) -> dict:
        """等同介面上按「核准」— 進 render。呼叫前請先 get_draft() 看過內容 (硬規則: AI 數值要人看)。"""
        return self.post(f"/jobs/{job_id}/approve")

    def render_section(self, job_id: str, section_id: str) -> dict:
        return self.post(f"/jobs/{job_id}/sections/{section_id}/render")

    def get_log(self, job_id: str, tail: int = 200) -> Any:
        return self.get(f"/jobs/{job_id}/log", params={"tail": tail})

    def wait(
        self,
        job_id: str,
        *,
        until: Iterable[str] = TERMINAL_STATES + REVIEW_STATES,
        interval: float = 3.0,
        timeout: float = 3600.0,
        on_update: Callable[[dict], None] | None = None,
    ) -> dict:
        """輪詢到 state 進入 until 之一 (預設 done / failed / awaiting_review)。超時 raise TimeoutError。"""
        until = tuple(until)
        deadline = time.monotonic() + timeout
        last_state = None
        while True:
            rec = self.get_job(job_id)
            if on_update and rec.get("state") != last_state:
                on_update(rec)
                last_state = rec.get("state")
            if rec.get("state") in until:
                return rec
            if time.monotonic() >= deadline:
                raise TimeoutError(f"job {job_id} 在 {timeout:.0f}s 內未到 {until} (目前 {rec.get('state')})")
            time.sleep(interval)

    # ------------------------------------------------------------------ artifacts
    def artifacts(self, job_id: str) -> list[dict]:
        return self.get_job(job_id).get("artifacts", [])

    def download_artifact(self, job_id: str, name: str, dest: str | Path) -> Path:
        """下載單一 artifact; dest 是資料夾或檔名。"""
        dest = Path(dest)
        target = dest / name if dest.is_dir() or not dest.suffix else dest
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.request("GET", f"/jobs/{job_id}/artifacts/{name}", expect_json=False))
        return target

    def download_all(self, job_id: str, dest_dir: str | Path, kinds: Iterable[str] = ("mp4", "srt")) -> list[Path]:
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        kinds = set(kinds)
        out = []
        for a in self.artifacts(job_id):
            if not kinds or a.get("kind") in kinds:
                out.append(self.download_artifact(job_id, a["name"], dest_dir / a["name"]))
        return out

    # ------------------------------------------------------------------ 上傳建 job
    @staticmethod
    def _file_tuple(path: str | Path) -> tuple:
        p = Path(path)
        return (p.name, p.read_bytes(), mimetypes.guess_type(p.name)[0] or "application/octet-stream")

    def upload(self, file_path: str | Path, source_type: str, *, options: dict | None = None, project_id: str = "") -> dict:
        """POST /upload — PDF / MD / TXT 上傳建 job。source_type: exam_pdf / slides_pdf / document。"""
        import json as _json

        data = {"source_type": source_type, "options_json": _json.dumps(options or {}), "project_id": project_id}
        return self.post("/upload", data=data, files={"file": self._file_tuple(file_path)})

    def upload_html(
        self,
        source: str | Path,
        *,
        duration: float,
        title: str = "",
        fps: int = 30,
        width: int = 1920,
        height: int = 1080,
        options: dict | None = None,
        project_id: str = "",
    ) -> dict:
        """POST /upload/html — 自含 HTML 動畫 (檔案) 或 http(s) URL → MP4。"""
        import json as _json

        data = {
            "title": title, "duration": str(duration), "fps": str(fps), "width": str(width), "height": str(height),
            "options_json": _json.dumps(options or {}), "project_id": project_id,
        }
        src = str(source)
        if src.startswith(("http://", "https://")):
            data["url"] = src
            return self.post("/upload/html", data=data)
        return self.post("/upload/html", data=data, files={"file": self._file_tuple(source)})

    def upload_pptx(self, file_path: str | Path, *, only_missing: bool = True, options: dict | None = None, project_id: str = "") -> dict:
        """POST /upload/pptx — 缺圖頁補圖 (原文字可編輯)。之後 pptx_to_video() 轉講解影片。"""
        import json as _json

        data = {"only_missing": "true" if only_missing else "false", "options_json": _json.dumps(options or {}), "project_id": project_id}
        return self.post("/upload/pptx", data=data, files={"file": self._file_tuple(file_path)})

    def pptx_to_video(self, pptx_job_id: str) -> dict:
        """POST /jobs/{id}/to-video — 補圖簡報 → slides_pdf 影片 job (回新 job 的 job_id)。"""
        return self.post(f"/jobs/{pptx_job_id}/to-video")

    # ------------------------------------------------------------------ YouTube
    def publish_youtube(
        self, job_id: str, artifact: str, *, title: str, description: str = "",
        tags: Iterable[str] = (), privacy: str = "unlisted", category: str = "27",
    ) -> dict:
        body = {"title": title, "description": description, "tags": list(tags), "privacy": privacy, "category": category}
        return self.post(f"/jobs/{job_id}/artifacts/{artifact}/publish", json=body)

    def youtube_status(self, job_id: str, artifact: str) -> dict:
        return self.get(f"/jobs/{job_id}/artifacts/{artifact}/youtube_status")

    # ------------------------------------------------------------------ projects
    def list_projects(self) -> Any:
        return self.get("/projects")

    def get_project(self, project_id: str) -> dict:
        return self.get(f"/projects/{project_id}")

    def create_project(self, project_id: str, title: str, target_languages: Iterable[str] = ()) -> dict:
        return self.post("/projects", json={"project_id": project_id, "title": title, "target_languages": list(target_languages)})

    def comics(self, project_id: str) -> "ComicsClient":
        return ComicsClient(self, project_id)


class ComicsClient:
    """/projects/{pid}/comics 底下的漫畫工作流 (Series Bible → 分鏡 → 生圖 → 排版 → 影片 / 匯出 / 發布)。"""

    def __init__(self, client: EduStudioClient, project_id: str) -> None:
        self.c = client
        self.pid = project_id
        self.base = f"/projects/{project_id}/comics"

    def _v(self, version: str | None) -> dict:
        return {"version": version} if version else {}

    # series
    def list_series(self) -> Any:
        return self.c.get(f"{self.base}/series")

    def create_series(self, series_id: str, title: str, *, characters: list[dict] | None = None, **fields) -> dict:
        return self.c.post(f"{self.base}/series", json={"series_id": series_id, "title": title, "characters": characters or [], **fields})

    def get_series(self, series_id: str) -> dict:
        return self.c.get(f"{self.base}/series/{series_id}")

    def update_series(self, series_id: str, series: dict) -> dict:
        return self.c.request("PUT", f"{self.base}/series/{series_id}", json=series)

    # episodes
    def list_episodes(self, series_id: str | None = None) -> Any:
        return self.c.get(f"{self.base}/episodes", params={"series_id": series_id} if series_id else None)

    def create_episode(self, series_id: str, story_id: str, title: str, **fields) -> dict:
        return self.c.post(f"{self.base}/episodes", json={"series_id": series_id, "story_id": story_id, "title": title, **fields})

    def get_episode(self, story_id: str, version: str | None = None) -> dict:
        return self.c.get(f"{self.base}/episodes/{story_id}", params=self._v(version))

    def update_episode(self, story_id: str, updates: dict, version: str | None = None) -> dict:
        return self.c.request("PATCH", f"{self.base}/episodes/{story_id}", json={"updates": updates}, params=self._v(version))

    def generate(self, story_id: str, what: str, *, mock: bool = False, model: str | None = None, version: str | None = None, **extra) -> Any:
        """what ∈ script / storyboard / images。"""
        return self.c.post(f"{self.base}/episodes/{story_id}/generate/{what}", json={"mock": mock, "model": model, **extra}, params=self._v(version))

    def compose_prompts(self, story_id: str, version: str | None = None) -> dict:
        return self.c.post(f"{self.base}/episodes/{story_id}/compose-prompts", params=self._v(version))

    def upload_asset(self, story_id: str, file_path: str | Path, *, kind: str, provenance: str = "user_upload",
                     asset_id: str | None = None, version: str | None = None) -> dict:
        p = Path(file_path)
        mime = mimetypes.guess_type(p.name)[0] or "image/png"
        data_url = f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"
        body = {"filename": p.name, "data_url": data_url, "kind": kind, "provenance": provenance, "asset_id": asset_id}
        return self.c.post(f"{self.base}/episodes/{story_id}/assets", json=body, params=self._v(version))

    def auto_layout(self, story_id: str, version: str | None = None) -> dict:
        return self.c.post(f"{self.base}/episodes/{story_id}/auto-layout", params=self._v(version))

    def locate_speakers(self, story_id: str, *, page_numbers: Iterable[int] = (), mock: bool = False, version: str | None = None) -> dict:
        return self.c.post(f"{self.base}/episodes/{story_id}/locate-speakers",
                           json={"mock": mock, "page_numbers": list(page_numbers)}, params=self._v(version))

    def validation(self, story_id: str, version: str | None = None) -> dict:
        return self.c.get(f"{self.base}/episodes/{story_id}/validation", params=self._v(version))

    def set_state(self, story_id: str, target: str, reason: str = "", version: str | None = None) -> dict:
        return self.c.post(f"{self.base}/episodes/{story_id}/state", json={"target": target, "reason": reason}, params=self._v(version))

    def export(self, story_id: str, kind: str, version: str | None = None) -> dict:
        """kind ∈ html / pdf / docx / source。"""
        return self.c.post(f"{self.base}/episodes/{story_id}/exports/{kind}", params=self._v(version))

    def render_video(self, story_id: str, *, version: str = "v0.1", voices: dict[str, str] | None = None,
                     fps: int = 30, width: int = 1920, height: int = 1080, tts_provider: str | None = None, mock: bool = False) -> dict:
        """動態漫畫影片 (背景 job)。回 {job_id, status_url, download_url, preview_label}; 用 client.wait(job_id) 等。"""
        body = {"version": version, "fps": fps, "width": width, "height": height, "tts_provider": tts_provider,
                "mock": mock, "voices": voices or {}}
        return self.c.post(f"{self.base}/episodes/{story_id}/video", json=body)

    def publish(self, story_id: str, published_by: str, channel: str = "internal_reader", version: str | None = None) -> dict:
        return self.c.post(f"{self.base}/episodes/{story_id}/publish", json={"published_by": published_by, "channel": channel}, params=self._v(version))
