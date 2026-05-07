#!/usr/bin/env python3
"""
publish.py — 上傳 MP4 (含 SRT 字幕) 到 YouTube (CLI 版, v2.0)

第一次執行會跳瀏覽器走 OAuth, token 存於 youtube_token.json (已 .gitignore)。
之後 token 過期會自動 refresh, refresh 失敗才需要重新授權。

依賴 (已有): google-api-python-client, google-auth-oauthlib

使用:
    python publish.py --video videos/<exam>/q1.mp4 --title "標題" [其他選項]

YouTube quota: 一次 upload 約 1,600 units, 每日上限 10,000 (約 6 支/天)。
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

BASE_DIR = Path(__file__).parent
TOKEN_PATH = BASE_DIR / "youtube_token.json"

# upload 用 youtube.upload, captions 用 force-ssl 才能寫
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def find_client_secrets() -> Path:
    """OAuth 下載的原始檔名為 client_secret_<id>.apps.googleusercontent.com.json,
    用 glob 自動配對, user 不用改名。"""
    candidates = sorted(BASE_DIR.glob("client_secret*.json"))
    if not candidates:
        sys.exit(
            "❌ 找不到 client_secret*.json\n"
            "   請從 Google Cloud Console 下載 OAuth client 的 JSON, 放到專案根目錄。"
        )
    if len(candidates) > 1:
        print(f"⚠ 發現多個 client_secret 檔, 採用: {candidates[0].name}")
    return candidates[0]


def get_credentials() -> Credentials:
    creds = None
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        except Exception as e:
            print(f"⚠ 讀 token 失敗 ({e}), 重新授權")
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception as e:
            print(f"⚠ refresh 失敗 ({e}), 重新授權")

    cs = find_client_secrets()
    print(f"🔐 啟動 OAuth flow (使用 {cs.name})... 瀏覽器將開啟 Google 同意頁。")
    flow = InstalledAppFlow.from_client_secrets_file(str(cs), SCOPES)
    # port=0 取系統可用 port, 避免固定 port 衝突
    creds = flow.run_local_server(port=0, prompt="consent")
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    print(f"✅ 授權完成, token 存於 {TOKEN_PATH.name}")
    return creds


def upload_video(youtube, video_path: Path, *, title: str, description: str,
                 tags: list, privacy: str, category: str) -> str:
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
        chunksize=4 * 1024 * 1024,  # 4 MB chunks, 平衡進度更新與請求次數
    )
    request = youtube.videos().insert(
        part=",".join(body.keys()), body=body, media_body=media,
    )
    size_mb = video_path.stat().st_size / 1024 / 1024
    print(f"⬆ 上傳影片 ({video_path.name}, {size_mb:.1f} MB)...")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"   進度 {pct:3d}%", end="\r", flush=True)
    print(f"   進度 100%")
    return response["id"]


def upload_caption(youtube, video_id: str, srt_path: Path,
                   language: str = "zh-TW", name: str = "繁體中文") -> str:
    body = {
        "snippet": {
            "videoId": video_id,
            "language": language,
            "name": name,
            "isDraft": False,
        }
    }
    media = MediaFileUpload(str(srt_path), mimetype="application/octet-stream", resumable=True)
    request = youtube.captions().insert(part="snippet", body=body, media_body=media)
    response = request.execute()
    return response["id"]


def main():
    from core.runtime import setup_utf8_stdout
    setup_utf8_stdout()
    ap = argparse.ArgumentParser(description="上傳 MP4 + SRT 到 YouTube")
    ap.add_argument("--video", required=True, help="MP4 檔案路徑")
    ap.add_argument("--title", required=True, help="影片標題")
    ap.add_argument("--description", default="", help="影片說明")
    ap.add_argument("--tags", default="", help="標籤, 逗號分隔")
    ap.add_argument("--privacy", default="unlisted",
                    choices=["unlisted", "public", "private"],
                    help="隱私設定 (預設 unlisted)")
    ap.add_argument("--srt", help="SRT 字幕路徑 (預設找同檔名 .srt)")
    ap.add_argument("--no-srt", action="store_true", help="強制不上傳字幕")
    ap.add_argument("--category", default="27",
                    help="YouTube 類別 ID (預設 27=Education, 其他常見: 28=Science & Tech)")
    ap.add_argument("--out-json",
                    help="完成後把結果寫入這個 JSON (給 app.py / 自動化使用)")
    args = ap.parse_args()

    video_p = Path(args.video).resolve()
    if not video_p.exists():
        sys.exit(f"❌ 找不到影片: {video_p}")
    if video_p.suffix.lower() != ".mp4":
        print(f"⚠ 副檔名不是 .mp4 ({video_p.suffix}), 仍會嘗試上傳")

    srt_p = None
    if not args.no_srt:
        srt_p = Path(args.srt).resolve() if args.srt else video_p.with_suffix(".srt")
        if not srt_p.exists():
            print(f"⚠ 找不到字幕 {srt_p.name}, 跳過字幕上傳")
            srt_p = None

    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    result: dict = {
        "title": args.title,
        "privacy": args.privacy,
    }
    try:
        video_id = upload_video(
            youtube, video_p,
            title=args.title,
            description=args.description,
            tags=tags,
            privacy=args.privacy,
            category=args.category,
        )
    except HttpError as e:
        result["error"] = str(e)
        if args.out_json:
            Path(args.out_json).write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        sys.exit(f"❌ 影片上傳失敗: {e}")

    url = f"https://youtu.be/{video_id}"
    result.update({
        "video_id": video_id,
        "url": url,
        "uploaded_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    })
    print(f"\n✅ 影片上傳完成")
    print(f"   ID:      {video_id}")
    print(f"   隱私:    {args.privacy}")
    print(f"   連結:    {url}")

    if srt_p:
        try:
            print(f"\n⬆ 上傳字幕 ({srt_p.name})...")
            cap_id = upload_caption(youtube, video_id, srt_p)
            result["caption_id"] = cap_id
            print(f"✅ 字幕完成 (caption ID: {cap_id})")
        except HttpError as e:
            # 字幕失敗不致命, 影片本身已上傳, 學生看影片無字幕只是可惜
            result["caption_error"] = str(e)
            print(f"⚠ 字幕上傳失敗 (影片仍可使用): {e}")

    if args.out_json:
        Path(args.out_json).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print(f"\n🎬 {url}")


if __name__ == "__main__":
    main()
