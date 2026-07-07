"""core/google_photos.py — Google Photos Picker API 薄層 (連相簿選照片)。

為什麼是 Picker API (不是 Library API)
--------------------------------------
Google 於 2025-04-01 移除 `photoslibrary.readonly` 等 scope; Library API 的
`mediaItems.search` 現只能讀「app 自己建立」的內容, **讀不到使用者既有相簿/照片**。
官方指定改用 **Google Photos Picker API**: app 建一個 picking session, 使用者在
Google 託管的選取器裡挑照片, app 只拿到被挑中的那些。

流程
----
1. sessions.create → 拿 pickerUri (給使用者開) + session id。
2. 使用者開 pickerUri 挑照片。
3. 輪詢 sessions.get 直到 mediaItemsSet=true。
4. mediaItems.list?sessionId=... → 拿被挑中的 mediaItem (含 baseUrl)。
5. 下載 baseUrl + "=d" (需帶 OAuth bearer, AuthorizedSession 自動帶)。

OAuth: 沿用 publish.py 的 InstalledAppFlow + token 檔模式, 但**獨立 scope + 獨立
token 檔 (photos_token.json)**, 不污染 youtube_token.json。缺 token → 丟
OAuthBootstrapRequired (route 層回 412, 提示先在本機 CLI 授權)。

HTTP 層以 `session` 參數注入 (AuthorizedSession-like), 方便單元測試不需真 OAuth。
"""
from __future__ import annotations

import logging
from pathlib import Path

from core.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

PHOTOS_SCOPES = ["https://www.googleapis.com/auth/photospicker.mediaitems.readonly"]
PHOTOS_TOKEN_PATH = PROJECT_ROOT / "photos_token.json"
_API_ROOT = "https://photospicker.googleapis.com/v1"


class OAuthBootstrapRequired(RuntimeError):
    """photos_token.json 不存在 / 無法 refresh — 需 admin 在本機 CLI 跑一次授權。

    與 core.youtube.OAuthBootstrapRequired 同語意 (route 層回 412)。獨立類別讓
    caller 能區分是哪個 Google 服務缺授權。
    """


# ---------------- OAuth ----------------

def get_photos_credentials(*, allow_interactive: bool = False):
    """讀 photos_token.json → refresh → 回 Credentials。

    allow_interactive=False (server 情境): 缺 token / refresh 失敗 → 丟
    OAuthBootstrapRequired。True (CLI bootstrap): 缺 token 時跑本機瀏覽器授權。
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = None
    if PHOTOS_TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(PHOTOS_TOKEN_PATH), PHOTOS_SCOPES)
        except Exception as e:  # noqa: BLE001
            logger.warning("讀 photos_token 失敗: %s", e)
            creds = None

    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            PHOTOS_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception as e:  # noqa: BLE001
            logger.warning("photos token refresh 失敗: %s", e)

    if not allow_interactive:
        raise OAuthBootstrapRequired(
            "尚未授權 Google 相簿。請在本機執行一次: python -m tools.photos_auth"
        )

    # CLI bootstrap: 跳本機瀏覽器授權
    from google_auth_oauthlib.flow import InstalledAppFlow
    from publish import find_client_secrets

    cs = find_client_secrets()
    flow = InstalledAppFlow.from_client_secrets_file(str(cs), PHOTOS_SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    PHOTOS_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _authed_session(session=None):
    if session is not None:
        return session
    from google.auth.transport.requests import AuthorizedSession
    return AuthorizedSession(get_photos_credentials())


# ---------------- Picker session ----------------

def create_session(*, session=None) -> dict:
    """建立一個 picking session。回 {id, pickerUri, mediaItemsSet, pollingConfig, ...}。"""
    s = _authed_session(session)
    r = s.post(f"{_API_ROOT}/sessions", json={})
    r.raise_for_status()
    return r.json()


def get_session(session_id: str, *, session=None) -> dict:
    """讀 session 狀態 (輪詢 mediaItemsSet 用)。"""
    s = _authed_session(session)
    r = s.get(f"{_API_ROOT}/sessions/{session_id}")
    r.raise_for_status()
    return r.json()


def list_media_items(session_id: str, *, session=None, page_size: int = 100) -> list[dict]:
    """列出該 session 被挑中的 mediaItems (自動翻頁)。"""
    s = _authed_session(session)
    items: list[dict] = []
    page_token = None
    while True:
        params = {"sessionId": session_id, "pageSize": page_size}
        if page_token:
            params["pageToken"] = page_token
        r = s.get(f"{_API_ROOT}/mediaItems", params=params)
        r.raise_for_status()
        body = r.json()
        items.extend(body.get("mediaItems", []))
        page_token = body.get("nextPageToken")
        if not page_token:
            break
    return items


def _download_url(base_url: str) -> str:
    """Picker baseUrl → 原圖下載 URL (=d)。已含 param 就用 & 接。"""
    sep = "&" if "=" in base_url.rsplit("/", 1)[-1] else "="
    return f"{base_url}{sep}d"


def download_media_bytes(base_url: str, *, session=None) -> bytes:
    """下載單張照片原圖 bytes (baseUrl=d, 需帶 OAuth bearer)。"""
    s = _authed_session(session)
    r = s.get(_download_url(base_url))
    r.raise_for_status()
    return r.content


def download_selected(session_id: str, out_dir: str | Path, *, session=None) -> list[Path]:
    """把 session 選中的照片全部下載到 out_dir, 回落地路徑清單 (只收圖片, 跳過影片)。"""
    s = _authed_session(session)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, item in enumerate(list_media_items(session_id, session=s), start=1):
        mf = item.get("mediaFile") or {}
        mime = mf.get("mimeType") or ""
        base_url = mf.get("baseUrl")
        if not base_url or not mime.startswith("image/"):
            continue  # 影片 / 無 baseUrl 跳過
        ext = ".jpg" if "jpeg" in mime or "jpg" in mime else "." + (mime.split("/")[-1] or "jpg")
        dst = out_dir / f"photo_{i:03d}{ext}"
        try:
            dst.write_bytes(download_media_bytes(base_url, session=s))
            paths.append(dst)
        except Exception as e:  # noqa: BLE001
            logger.warning("照片下載失敗 (item %d): %s", i, e)
    return paths
