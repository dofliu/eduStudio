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
from .song_render import _valid_segment, is_song_schema


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
    "song": ["歌曲 MV", "AI 生圖", "Dof Lab"],
}


def _seconds_to_hhmmss(seconds: float) -> str:
    """YouTube 章節時間軸格式: H:MM:SS (≥1h) 或 M:SS (<1h)。"""
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _estimate_narration_seconds(text: str) -> float:
    """以 narration 字數近似一段旁白秒數 (中文 ~3.5 字/秒 + 0.6 秒尾巴停頓,
    對應 PAUSE_AFTER_EACH), 最小 2 秒。

    deck.json / exam.json 不直接存 mp3 duration, 只能近似。要精確的話渲染後
    掃 artifacts/ 的 mp3 / mp4 讀真實秒數, 但那要載重型依賴, 先給近似版。
    """
    char_count = len(re.sub(r"\s+", "", text or ""))
    return max(2.0, char_count / 3.5 + 0.6)


def _build_chapter_lines(durs: list[tuple[str, float]]) -> list[str]:
    """把 (label, 秒數) 序列轉成 YouTube 章節時間軸行。

    YouTube 章節規則: 第一個 timestamp 必須是 0:00, 後續按累積秒數遞增。
    """
    lines: list[str] = []
    cum = 0.0
    for i, (label, d) in enumerate(durs):
        ts = "0:00" if i == 0 else _seconds_to_hhmmss(cum)
        lines.append(f"{ts}  {label}")
        cum += d
    return lines


def _step_durations_for_problem(problem: dict) -> list[tuple[str, float]]:
    """從一題的 steps 抽出 (label, 估算秒數) 序列 (exam schema)。"""
    out: list[tuple[str, float]] = []
    for step in problem.get("steps", []):
        narration = step.get("narration") or step.get("display") or ""
        label = (
            step.get("_section")
            or (step.get("display") or "")[:20]
            or "段落"
        )
        out.append((label.strip(), _estimate_narration_seconds(narration)))
    return out


def _is_deck_schema(deck: dict) -> bool:
    """type guard (硬規則 #9): 存盤的 deck.json 對 repo/document/url 是 deck
    schema (頂層 sections list, 無 problems); exam_pdf / slides_pdf 或已壓平的
    才有 problems。不靠 'problems' in deck 字串硬判, 用型別 + 結構判。
    """
    return isinstance(deck.get("sections"), list) and not isinstance(
        deck.get("problems"), list
    )


def _slide_durations_for_section(section: dict) -> list[tuple[str, float]]:
    """deck 單一 section 的 slides → (label, 估算秒數)。

    label 取 slide.title, 退 narration 前 20 字, 再退 '段落'。
    """
    out: list[tuple[str, float]] = []
    for slide in section.get("slides", []):
        narration = slide.get("narration") or ""
        label = (slide.get("title") or narration[:20] or "段落").strip()
        out.append((label, _estimate_narration_seconds(narration)))
    return out


def _section_durations_for_deck(sections: list) -> list[tuple[str, float]]:
    """整份 deck 的 sections → (章節名, 該章 slides 總估算秒數)。

    給整份影片 (final.mp4) 用 — 每個 section 是一個 YouTube 章節, 章節長度 =
    該 section 所有 slide 旁白估算秒數總和。_cover / _outro 也是有序內容 (有真實
    title), 不過濾以免時間軸與實際影片漂移。
    """
    out: list[tuple[str, float]] = []
    for i, section in enumerate(sections):
        title = (section.get("title") or f"第 {i + 1} 章").strip()
        total = sum(
            _estimate_narration_seconds(sl.get("narration") or "")
            for sl in section.get("slides", [])
        )
        out.append((title, max(2.0, total)))
    return out


def _song_chapter_durs(segments: list) -> list[tuple[str, float]]:
    """song segments → (歌詞首句, 該章長度) 序列, 餵 _build_chapter_lines.

    歌曲 segment 已有對齊好的絕對 start/end 時間戳 (M0 手填 / M1 對齊), 跟 deck
    的字數估算不同 — 直接用絕對時間戳才不會被段間 / 前奏空拍 (instrumental gap)
    累積漂移。轉成 _build_chapter_lines 要的「該章長度」= 下一章 start - 本章 start,
    讓累積後的時間戳剛好回到絕對 start (沿用既有章節時間軸組裝路徑)。

    YouTube 章節規則第一個 timestamp 必須 0:00; 首段非從 0 開始 (有前奏) → 前面
    補一個「🎵 前奏」章節吃掉前奏 gap, 否則首句歌詞被迫標 0:00 會與實際對不上。
    無效 segment (比照 song_segments_to_srt 的 _valid_segment) 跳過; 全無效 → []。
    """
    valid = [s for s in segments if _valid_segment(s)]
    if not valid:
        return []

    labels_starts: list[tuple[str, float]] = []
    first_start = float(valid[0]["start"])
    if first_start >= 1.0:
        labels_starts.append(("🎵 前奏", 0.0))
    for seg in valid:
        line = next(
            (ln.strip() for ln in seg["lines"]
             if isinstance(ln, str) and ln.strip()),
            "段落",
        )
        labels_starts.append((line[:30], float(seg["start"])))

    out: list[tuple[str, float]] = []
    for i, (label, start) in enumerate(labels_starts):
        if i + 1 < len(labels_starts):
            dur = labels_starts[i + 1][1] - start
        else:
            # 最後一章沒有「下一章 start」, 用最後 segment 的 end-start;
            # 只影響不存在的下一個時間戳, 取正值即可。
            last = valid[-1]
            dur = float(last["end"]) - float(last["start"])
        out.append((label, max(0.0, dur)))
    return out


def _song_youtube_meta(deck: dict, *, source_type: str) -> dict:
    """song schema (track_type=='song' + segments) 的預填 metadata.

    song 是整首單一影片 (無單章 render), problem_id 忽略; 章節時間軸用每段歌詞
    首句 + 對齊好的絕對 start 時間 (繞過字數估算, 比照 song_segments_to_srt)。
    category 用 10 (Music) 而非教學的 27 — MV 是音樂內容, 利於 YouTube 分類。
    """
    title = (
        deck.get("song_title")
        or deck.get("deck_title")
        or deck.get("exam_title")
        or "歌曲 MV"
    ).strip()
    tags = DEFAULT_TAGS_BY_SOURCE.get(source_type, [])

    durs = _song_chapter_durs(deck.get("segments") or [])
    parts: list[str] = []
    if durs:
        parts.append("📍 歌詞章節")
        parts.extend(_build_chapter_lines(durs))
        parts.append("")
    parts.append("---")
    parts.append("由 Dof Lab 教學影片自動生成平台製作。")

    return {
        "title": title[:100],
        "description": "\n".join(parts)[:5000],
        "tags": tags,
        "privacy": "unlisted",
        "category": "10",
    }


def _deck_youtube_meta(deck: dict, artifact_id: str, *,
                       source_type: str) -> dict:
    """deck schema (sections/slides) 的預填 metadata。

    artifact_id (= mp4 stem) 對得到某 section.id → 單章影片, 章節 = 該章 slides;
    對不到 (例 final.mp4 整份影片) → 章節 = 各 section。
    """
    deck_title = (
        deck.get("deck_title") or deck.get("exam_title") or "教學影片"
    ).strip()
    sections = deck.get("sections") or []
    tags = DEFAULT_TAGS_BY_SOURCE.get(source_type, [])

    section = next((s for s in sections if s.get("id") == artifact_id), None)
    if section is not None:
        section_title = (section.get("title") or artifact_id).strip()
        title = f"{deck_title} | {section_title}".strip(" |")
        durs = _slide_durations_for_section(section)
    else:
        title = deck_title
        durs = _section_durations_for_deck(sections)

    parts: list[str] = []
    if durs:
        parts.append("📍 章節時間軸")
        parts.extend(_build_chapter_lines(durs))
        parts.append("")
    parts.append("---")
    parts.append("由 Dof Lab 教學影片自動生成平台製作。")

    return {
        "title": title[:100],
        "description": "\n".join(parts)[:5000],
        "tags": tags,
        "privacy": "unlisted",
        "category": "27",
    }


def auto_youtube_meta(deck: dict, problem_id: str, *,
                      source_type: str = "exam_pdf") -> dict:
    """根據 deck.json 與指定 problem (= artifact) 產預填 metadata。

    Returns dict with keys: title, description, tags, privacy, category。

    repo / document / url 的 deck.json 是 deck schema (sections/slides, 無 problems),
    走 _deck_youtube_meta 產 section / slide 章節; exam / slides_pdf 走以下 problems 路徑。
    song 的 song.json 是 song schema (track_type=='song' + segments), 走 _song_youtube_meta
    產歌詞章節 (整首單一影片, problem_id 忽略)。
    """
    if is_song_schema(deck):
        return _song_youtube_meta(deck, source_type=source_type)
    if _is_deck_schema(deck):
        return _deck_youtube_meta(deck, problem_id, source_type=source_type)

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
        parts.extend(_build_chapter_lines(durs))
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


def _build_youtube_client():
    """建 YouTube API client（共用 OAuth）；token 不存在丟 OAuthBootstrapRequired。"""
    if not YOUTUBE_TOKEN_PATH.exists():
        raise OAuthBootstrapRequired(
            f"找不到 {YOUTUBE_TOKEN_PATH.name}。請先在本機完成一次 OAuth 授權。"
        )
    from publish import get_credentials
    from googleapiclient.discovery import build

    try:
        creds = get_credentials()
    except SystemExit as e:
        raise OAuthBootstrapRequired(str(e)) from e
    return build("youtube", "v3", credentials=creds)


def upload_captions(video_id: str, captions: list[dict]) -> list[dict]:
    """為「已上傳的影片」加多語字幕軌（發布站多語字幕）。

    captions: [{language, name, srt_path}]。逐軌上傳，單軌失敗只記該軌 error 不中斷其他。
    回 [{language, caption_id?|error?}]。OAuth token 不存在丟 OAuthBootstrapRequired。
    """
    from publish import upload_caption

    youtube = _build_youtube_client()
    results: list[dict] = []
    for cap in captions:
        lang = cap.get("language", "")
        srt_path = cap.get("srt_path")
        try:
            cid = upload_caption(youtube, video_id, srt_path,
                                 language=lang, name=cap.get("name", lang))
            results.append({"language": lang, "caption_id": cid})
        except Exception as e:
            results.append({"language": lang, "error": str(e)})
    return results
