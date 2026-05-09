"""YouTube 上傳的 server 端 helper (PR-3f)。

Track A 的 publish.py 是 CLI tool, 直接 sys.exit 不適合 server context。這層
把它包成: 純函式 + 進度 callback + 例外丟出 (不 sys.exit)。

預填生成器 auto_youtube_meta() 從 deck.json + step durations 算出:
- title = "{deck_title} - {section_title}" (per-artifact)
- description 含自動章節時間軸 (YouTube 章節格式: 00:00 章節名)
- tags 預設一組學科關鍵字

OAuth 處理:
- 第一次需要 user 手動跑 `python publish.py ...` 至少一次, 把 token 寫入 youtube_token.json
- token 存在後 server 內 refresh 即可
- token 缺失或損毀時, publish_artifact 會丟 OAuthBootstrapRequired (route 層回 412)

References:
- publish.py 提供 upload_video / upload_caption / get_credentials (已 re-export 為 core API)
- YouTube quota: 一次 upload ~1,600 units, 每日 10,000 (約 6 支/天)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import PROJECT_ROOT


YOUTUBE_TOKEN_PATH = PROJECT_ROOT / "youtube_token.json"


class OAuthBootstrapRequired(RuntimeError):
    """token 不存在或無法 refresh, 需要 user 手動 CLI 跑一次 publish.py 授權。"""


# ---------- 預填產生器 ----------

DEFAULT_TAGS_BY_SOURCE = {
    "exam_pdf": ["考卷解析", "教學影片", "Dof 老師"],
    "slides_pdf": ["教學簡報", "課程影片", "Dof 老師"],
    "repo": ["程式碼講解", "技術教學", "Dof 老師"],
    "document": ["文件講解", "教學影片", "Dof 老師"],
    "url": ["文章導讀", "技術教學", "Dof 老師"],
}


def _seconds_to_hhmmss(seconds: float) -> str:
    """YouTube 章節時間軸格式: H:MM:SS (≥1h) 或 M:SS (<1h)。"""
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _step_durations_for_problem(problem: dict) -> list[tuple[str, float]]:
    """從一題的 steps 抽出 (label, mp3_duration_seconds) 序列。

    現階段 deck.json / exam.json 不直接存 mp3 duration, 只能近似 — 用 narration
    字數估算 (中文每秒 ~3.5 字, 含停頓)。實際章節時間軸要更精確的話, 渲染後
    可以掃 artifacts/ 的 mp3 / mp4 讀真實秒數, 但那要載重型依賴, 先給近似版。
    """
    out: list[tuple[str, float]] = []
    for step in problem.get("steps", []):
        narration = step.get("narration") or step.get("display") or ""
        # 中文 ~3.5 字/秒, 每段加 0.6 秒尾巴停頓 (對應 PAUSE_AFTER_EACH)
        char_count = len(re.sub(r"\s+", "", narration))
        dur = max(2.0, char_count / 3.5 + 0.6)
        label = (
            step.get("_section")
            or (step.get("display") or "")[:20]
            or "段落"
        )
        out.append((label.strip(), dur))
    return out


def auto_youtube_meta(deck: dict, problem_id: str, *,
                      source_type: str = "exam_pdf") -> dict:
    """根據 deck.json 與指定 problem (= artifact) 產預填 metadata。

    Returns dict with keys: title, description, tags, privacy, category。
    """
    deck_title = (deck.get("exam_title") or deck.get("deck_title") or "教學影片").strip()

    # 找對應 problem
    problem: dict | None = None
    for p in deck.get("problems", []):
        if p.get("id") == problem_id:
            problem = p
            break
    if problem is None:
        # 找不到時還是回基本的 meta, 不爆
        return {
            "title": deck_title,
            "description": "",
            "tags": DEFAULT_TAGS_BY_SOURCE.get(source_type, []),
            "privacy": "unlisted",
            "category": "27",
        }

    section_label = (
        problem.get("number")
        or problem.get("problem", "")[:30]
        or problem.get("id", "")
    ).strip()
    title = f"{deck_title} | {section_label}".strip(" |")

    # 描述: 題目原文 + 章節時間軸
    parts: list[str] = []
    problem_text = (problem.get("problem") or "").strip()
    if problem_text:
        parts.append(problem_text)
        parts.append("")  # 空行

    # 章節時間軸 (YouTube 認的格式: 第一個必須 0:00)
    durs = _step_durations_for_problem(problem)
    if durs:
        parts.append("📍 章節時間軸")
        cum = 0.0
        for i, (label, d) in enumerate(durs):
            ts = _seconds_to_hhmmss(cum)
            # 第一個強制 0:00 (YouTube 章節規則)
            if i == 0:
                ts = "0:00"
            parts.append(f"{ts}  {label}")
            cum += d
        parts.append("")

    parts.append("---")
    parts.append("由 Dof Lab 教學影片自動生成平台製作。")

    return {
        "title": title[:100],   # YouTube 標題上限 100 字元
        "description": "\n".join(parts)[:5000],  # YouTube 描述上限 5000
        "tags": DEFAULT_TAGS_BY_SOURCE.get(source_type, []),
        "privacy": "unlisted",
        "category": "27",
    }


# ---------- 上傳主流程 ----------

@dataclass
class PublishResult:
    video_id: str
    url: str
    caption_id: str | None = None
    caption_error: str | None = None


def publish_artifact(
    video_path: Path,
    *,
    title: str,
    description: str,
    tags: list[str],
    privacy: str = "unlisted",
    category: str = "27",
    srt_path: Path | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> PublishResult:
    """上傳一支 MP4 (含 SRT) 到 YouTube。

    on_progress(percent: int) 在上傳每個 chunk 後呼叫, server 端可寫進
    YoutubeUpload.progress_percent 給前端輪詢。

    OAuth token 不存在 / 無法 refresh 時丟 OAuthBootstrapRequired。
    上傳失敗 (HttpError 等) 直接讓例外往外丟, 由呼叫端處理。
    """
    if not video_path.exists():
        raise FileNotFoundError(f"找不到影片: {video_path}")

    # token 檢查 — 沒就直接丟例外不啟動 OAuth flow (server 不該跳瀏覽器)
    if not YOUTUBE_TOKEN_PATH.exists():
        raise OAuthBootstrapRequired(
            f"找不到 {YOUTUBE_TOKEN_PATH.name}。請在本機跑一次:\n"
            f"  python publish.py --video <任一 mp4> --title 測試 --privacy private\n"
            f"完成 OAuth 授權, token 會自動存下來。"
        )

    # 走 publish.py 的 get_credentials — token 存在但過期會 refresh, refresh
    # 失敗會跳瀏覽器。Server 這邊應該很少觸發瀏覽器, 因為定期 refresh。
    # 若真的觸發, 在 background task 中卡住, 表示 user 要重跑 CLI 一次。
    from publish import get_credentials, upload_caption, upload_video
    from googleapiclient.discovery import build

    try:
        creds = get_credentials()
    except SystemExit as e:
        # publish.find_client_secrets() 找不到會 sys.exit
        raise OAuthBootstrapRequired(str(e)) from e

    youtube = build("youtube", "v3", credentials=creds)

    # 包一層 upload_video, 把 chunk progress 接到 callback
    # 為什麼自己寫一份: publish.upload_video 直接 print 進度, 不能拿到 callback
    from googleapiclient.http import MediaFileUpload

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=4 * 1024 * 1024,
    )
    request = youtube.videos().insert(
        part=",".join(body.keys()), body=body, media_body=media,
    )
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status and on_progress:
            on_progress(int(status.progress() * 100))
    if on_progress:
        on_progress(100)

    video_id = response["id"]
    url = f"https://youtu.be/{video_id}"
    result = PublishResult(video_id=video_id, url=url)

    # 字幕失敗不致命
    if srt_path and srt_path.exists():
        try:
            cap_id = upload_caption(youtube, video_id, srt_path)
            result.caption_id = cap_id
        except Exception as e:
            result.caption_error = str(e)

    return result
