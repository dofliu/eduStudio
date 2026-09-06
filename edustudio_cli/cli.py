"""eduStudio 命令列: 不開 /app 介面, 直接用 API 跑完「上傳 → 等待 → 看草稿 → 核准 → 下載 → 發布」。

    python -m edustudio_cli health
    python -m edustudio_cli video deck.pptx --project wind101 --wait --download out/
    python -m edustudio_cli video lecture.pdf --kind slides --wait
    python -m edustudio_cli video exam.pdf --kind exam --wait          # 停在 awaiting_review
    python -m edustudio_cli draft get <job> -o deck.json               # 改旁白
    python -m edustudio_cli draft put <job> deck.json
    python -m edustudio_cli jobs approve <job> --wait --download out/
    python -m edustudio_cli publish <job> final.mp4 --title "..." --privacy unlisted
    python -m edustudio_cli comics video wind101 W11_gearbox --voices aguang=edge:zh-TW-YunJheNeural --wait
    python -m edustudio_cli api GET /jobs                                 # 任意端點

連線: --server / EDUSTUDIO_URL (預設 http://127.0.0.1:8000); --token / EDUSTUDIO_API_TOKEN。
輸出: 結果 JSON 印到 stdout (給 shell / 排程抓); 進度訊息印到 stderr。exit code 0 成功, 1 API 錯, 2 參數錯, 3 超時。
review gate 不會被繞過: 考卷等需審查的 job 會停在 awaiting_review, 要你明確下 `jobs approve`
(或 video --approve, 代表你已看過草稿) 才會渲染。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from .client import EduStudioClient, EduStudioError, REVIEW_STATES, TERMINAL_STATES

KIND_ALIAS = {
    "exam": "exam_pdf", "exam_pdf": "exam_pdf",
    "slides": "slides_pdf", "slides_pdf": "slides_pdf",
    "document": "document", "doc": "document",
}


def _out(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _progress(rec: dict) -> None:
    _log(f"[{rec.get('id', '')}] state={rec.get('state')}" + (f" error={rec.get('error')}" if rec.get("error") else ""))


def make_client(args) -> EduStudioClient:
    return EduStudioClient(args.server, args.token, timeout=args.timeout)


def _parse_kv(items: list[str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise SystemExit(f"格式應為 key=value: {item!r}")
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _wait_and_maybe_download(c: EduStudioClient, job_id: str, args, *, allow_approve: bool) -> dict:
    """等到 awaiting_review / done / failed; awaiting_review 時依 --approve 決定要不要核准繼續。"""
    rec = c.wait(job_id, interval=args.interval, timeout=args.wait_timeout, on_update=_progress)
    if rec.get("state") in REVIEW_STATES:
        if allow_approve and getattr(args, "approve", False):
            _log(f"[{job_id}] awaiting_review → --approve 已指定, 視為你已審過草稿, 送出核准")
            c.approve(job_id)
            rec = c.wait(job_id, until=TERMINAL_STATES, interval=args.interval, timeout=args.wait_timeout, on_update=_progress)
        else:
            _log(f"[{job_id}] 停在 awaiting_review。看草稿: `draft get {job_id}`; 核准: `jobs approve {job_id} --wait`")
            return rec
    if rec.get("state") == "done" and getattr(args, "download", None):
        paths = c.download_all(job_id, args.download)
        _log("已下載: " + ", ".join(str(p) for p in paths))
        rec = {**rec, "downloaded": [str(p) for p in paths]}
    return rec


# ---------------------------------------------------------------- 子命令
def cmd_health(c: EduStudioClient, args) -> int:
    _out(c.health())
    return 0


def cmd_video(c: EduStudioClient, args) -> int:
    src = args.source
    is_url = src.startswith(("http://", "https://"))
    ext = "" if is_url else Path(src).suffix.lower()
    options = {"mock": True} if args.mock else {}
    if args.tts:
        options["tts_provider"] = args.tts

    if ext == ".pptx":
        pptx_job = c.upload_pptx(src, only_missing=not args.all_pages, options=options, project_id=args.project)
        _log(f"PPTX 補圖 job {pptx_job['job_id']} 建立, 等待補圖完成…")
        rec = c.wait(pptx_job["job_id"], until=TERMINAL_STATES, interval=args.interval, timeout=args.wait_timeout, on_update=_progress)
        if rec.get("state") != "done":
            _out(rec)
            return 1
        created = c.pptx_to_video(pptx_job["job_id"])
        _log(f"影片 job {created['job_id']} 建立 (由補圖簡報轉 PDF 走 slides 流程)")
    elif ext in (".html", ".htm") or (is_url and args.kind == "html"):
        if not args.duration:
            raise SystemExit("HTML 動畫沒有自然結尾, 請用 --duration 指定秒數")
        created = c.upload_html(src, duration=args.duration, title=args.title, options=options, project_id=args.project)
    elif is_url:
        created = c.create_job("url", {"url": src}, {**options, "require_review": False})
    else:
        kind = KIND_ALIAS.get((args.kind or "").lower())
        if not kind:
            if ext == ".pdf":
                raise SystemExit("PDF 請用 --kind exam | slides | document 指定用途 (考卷會停在 review)")
            kind = "document"
        created = c.upload(src, kind, options=options, project_id=args.project)

    job_id = created["job_id"]
    _log(f"job {job_id} 已建立 (status_url={created.get('status_url')})")
    if not args.wait:
        _out(created)
        return 0
    rec = _wait_and_maybe_download(c, job_id, args, allow_approve=True)
    _out(rec)
    return 0 if rec.get("state") != "failed" else 1


def cmd_jobs(c: EduStudioClient, args) -> int:
    if args.action == "list":
        jobs = c.list_jobs()
        _out([{k: j.get(k) for k in ("id", "source_type", "state", "created_at", "error")} for j in jobs] if args.brief else jobs)
    elif args.action == "get":
        _out(c.get_job(args.job_id))
    elif args.action == "wait":
        _out(_wait_and_maybe_download(c, args.job_id, args, allow_approve=False))
    elif args.action == "approve":
        rec = c.approve(args.job_id)
        _log(f"[{args.job_id}] 已核准 → {rec.get('state')}")
        if args.wait:
            rec = _wait_and_maybe_download(c, args.job_id, args, allow_approve=False)
        _out(rec)
    elif args.action == "log":
        _out(c.get_log(args.job_id, tail=args.tail))
    elif args.action == "download":
        paths = c.download_all(args.job_id, args.out, kinds=args.kinds.split(",") if args.kinds else ("mp4", "srt"))
        _out([str(p) for p in paths])
    elif args.action == "delete":
        c.delete_job(args.job_id)
        _out({"deleted": args.job_id})
    return 0


def cmd_draft(c: EduStudioClient, args) -> int:
    if args.action == "get":
        deck = c.get_draft(args.job_id)
        if args.out:
            Path(args.out).write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")
            _log(f"草稿已存到 {args.out}; 改完用 `draft put {args.job_id} {args.out}` 放回去")
            _out({"job_id": args.job_id, "saved": args.out})
        else:
            _out(deck)
    else:
        deck = json.loads(Path(args.file).read_text(encoding="utf-8"))
        _out(c.put_draft(args.job_id, deck))
    return 0


def cmd_publish(c: EduStudioClient, args) -> int:
    _out(c.publish_youtube(args.job_id, args.artifact, title=args.title, description=args.description,
                           tags=args.tags or [], privacy=args.privacy))
    return 0


def cmd_projects(c: EduStudioClient, args) -> int:
    if args.action == "list":
        _out(c.list_projects())
    elif args.action == "get":
        _out(c.get_project(args.project_id))
    else:
        _out(c.create_project(args.project_id, args.title))
    return 0


def cmd_comics(c: EduStudioClient, args) -> int:
    k = c.comics(args.project_id)
    a = args.action
    if a == "series":
        _out(k.list_series())
    elif a == "episodes":
        _out(k.list_episodes(args.series))
    elif a == "episode":
        _out(k.get_episode(args.story_id, args.version))
    elif a == "layout":
        _out(k.auto_layout(args.story_id, args.version))
    elif a == "locate":
        _out(k.locate_speakers(args.story_id, page_numbers=args.pages or (), mock=args.mock, version=args.version))
    elif a == "export":
        _out(k.export(args.story_id, args.kind, args.version))
    elif a == "video":
        created = k.render_video(args.story_id, version=args.version or "v0.1", voices=_parse_kv(args.voices),
                                 tts_provider=args.tts, mock=args.mock)
        _log(f"動態漫畫影片 job {created['job_id']} 建立; {created.get('preview_label') or '正式版 (CURRENT)'}")
        if args.wait:
            rec = _wait_and_maybe_download(c, created["job_id"], args, allow_approve=False)
            _out({**created, "state": rec.get("state"), "downloaded": rec.get("downloaded", [])})
            return 0 if rec.get("state") == "done" else 1
        _out(created)
    return 0


def cmd_api(c: EduStudioClient, args) -> int:
    body = json.loads(args.json) if args.json else None
    _out(c.request(args.method.upper(), args.path, json=body))
    return 0


# ---------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="edustudio", description="eduStudio API 命令列 (不需開 /app 介面)")
    ap.add_argument("--server", default=None, help="server URL (預設 $EDUSTUDIO_URL 或 http://127.0.0.1:8000)")
    ap.add_argument("--token", default=None, help="Bearer token (預設 $EDUSTUDIO_API_TOKEN)")
    ap.add_argument("--timeout", type=float, default=120.0, help="單次 HTTP 逾時秒數")
    ap.add_argument("--interval", type=float, default=3.0, help="輪詢間隔秒數")
    ap.add_argument("--wait-timeout", type=float, default=3600.0, help="--wait 最長等待秒數")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health", help="GET /health").set_defaults(fn=cmd_health)

    v = sub.add_parser("video", help="檔案 / 網址 → 講解影片 job (pdf / pptx / html / url / md / txt)")
    v.add_argument("source")
    v.add_argument("--kind", help="PDF 用途: exam | slides | document; URL 動畫用 html")
    v.add_argument("--project", default="", help="歸屬課程 project_id")
    v.add_argument("--title", default="")
    v.add_argument("--duration", type=float, default=0.0, help="HTML 動畫錄製秒數")
    v.add_argument("--tts", default=None, help="edge | f5 | google (覆寫 tts_config)")
    v.add_argument("--mock", action="store_true", help="離線 mock (不打 Gemini, 只驗流程)")
    v.add_argument("--all-pages", action="store_true", help="PPTX: 每頁都補圖 (預設只補缺圖頁)")
    v.add_argument("--wait", action="store_true", help="輪詢到 done / failed / awaiting_review")
    v.add_argument("--approve", action="store_true", help="到 awaiting_review 時自動核准 (代表你已審過; 考卷請先看草稿)")
    v.add_argument("--download", default=None, help="done 後把 mp4/srt 下載到此資料夾")
    v.set_defaults(fn=cmd_video)

    j = sub.add_parser("jobs", help="job 查詢 / 等待 / 核准 / 下載")
    js = j.add_subparsers(dest="action", required=True)
    p = js.add_parser("list"); p.add_argument("--brief", action="store_true")
    for name in ("get", "delete"):
        js.add_parser(name).add_argument("job_id")
    p = js.add_parser("wait"); p.add_argument("job_id"); p.add_argument("--download", default=None)
    p = js.add_parser("approve"); p.add_argument("job_id"); p.add_argument("--wait", action="store_true"); p.add_argument("--download", default=None)
    p = js.add_parser("log"); p.add_argument("job_id"); p.add_argument("--tail", type=int, default=200)
    p = js.add_parser("download"); p.add_argument("job_id"); p.add_argument("--out", default="."); p.add_argument("--kinds", default="mp4,srt")
    j.set_defaults(fn=cmd_jobs)

    d = sub.add_parser("draft", help="review 草稿: get (可存檔) / put (放回)")
    ds = d.add_subparsers(dest="action", required=True)
    p = ds.add_parser("get"); p.add_argument("job_id"); p.add_argument("-o", "--out", default=None)
    p = ds.add_parser("put"); p.add_argument("job_id"); p.add_argument("file")
    d.set_defaults(fn=cmd_draft)

    pub = sub.add_parser("publish", help="上傳 artifact 到 YouTube")
    pub.add_argument("job_id"); pub.add_argument("artifact", help="例 final.mp4")
    pub.add_argument("--title", required=True); pub.add_argument("--description", default="")
    pub.add_argument("--tags", nargs="*"); pub.add_argument("--privacy", default="unlisted", choices=["public", "unlisted", "private"])
    pub.set_defaults(fn=cmd_publish)

    pr = sub.add_parser("projects", help="課程 project")
    prs = pr.add_subparsers(dest="action", required=True)
    prs.add_parser("list")
    prs.add_parser("get").add_argument("project_id")
    p = prs.add_parser("create"); p.add_argument("project_id"); p.add_argument("title")
    pr.set_defaults(fn=cmd_projects)

    cm = sub.add_parser("comics", help="漫畫工作站 (series / episodes / 排版 / 定位 / 影片 / 匯出)")
    cm.add_argument("project_id")
    cms = cm.add_subparsers(dest="action", required=True)
    cms.add_parser("series")
    cms.add_parser("episodes").add_argument("--series", default=None)
    for name in ("episode", "layout"):
        p = cms.add_parser(name); p.add_argument("story_id"); p.add_argument("--version", default=None)
    p = cms.add_parser("locate"); p.add_argument("story_id"); p.add_argument("--version", default=None)
    p.add_argument("--pages", nargs="*", type=int); p.add_argument("--mock", action="store_true")
    p = cms.add_parser("export"); p.add_argument("story_id"); p.add_argument("kind", choices=["html", "pdf", "docx", "source"]); p.add_argument("--version", default=None)
    p = cms.add_parser("video"); p.add_argument("story_id"); p.add_argument("--version", default=None)
    p.add_argument("--voices", nargs="*", help="speaker=規格, 例 aguang=edge:zh-TW-YunJheNeural narrator=default")
    p.add_argument("--tts", default=None); p.add_argument("--mock", action="store_true")
    p.add_argument("--wait", action="store_true"); p.add_argument("--download", default=None)
    cm.set_defaults(fn=cmd_comics)

    api = sub.add_parser("api", help="任意端點: api GET /jobs | api POST /path --json '{...}'")
    api.add_argument("method"); api.add_argument("path"); api.add_argument("--json", default=None)
    api.set_defaults(fn=cmd_api)
    return ap


def main(argv: list[str] | None = None, client_factory: Callable[[argparse.Namespace], EduStudioClient] = make_client) -> int:
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass
    args = build_parser().parse_args(argv)
    try:
        return args.fn(client_factory(args), args)
    except EduStudioError as e:
        _log(f"API 錯誤: {e}")
        return 1
    except TimeoutError as e:
        _log(f"超時: {e}")
        return 3
    except SystemExit as e:
        if isinstance(e.code, str):
            _log(e.code)
            return 2
        raise
    except OSError as e:
        _log(f"連線 / 檔案錯誤: {e}")
        return 1
