#!/usr/bin/env python3
"""tools/photos_auth.py — 一次性授權 Google 相簿 (Photos Picker API)。

在**本機**執行一次 (需要能開瀏覽器):

    python -m tools.photos_auth

會用專案根目錄的 client_secret*.json 跑 OAuth, 跳瀏覽器讓你登入 + 同意
`photospicker.mediaitems.readonly` scope, 成功後把 token 存成 photos_token.json
(已 gitignore)。之後 server 端就能自動讀取 + refresh, 不需再手動授權。

前置:
- Google Cloud Console 已啟用 Google Photos Picker API。
- OAuth 同意畫面已加入 scope, 且 (測試中狀態下) 你的帳號在 Test users。
- client_secret*.json (電腦/桌面型用戶端) 已放到專案根目錄。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 讓 `python -m tools.photos_auth` 與直接執行都能 import 專案模組
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    from core.google_photos import PHOTOS_SCOPES, PHOTOS_TOKEN_PATH, get_photos_credentials

    print(f"🔐 開始授權 Google 相簿 (scope: {PHOTOS_SCOPES[0]})")
    print("   瀏覽器將開啟 Google 同意頁, 請登入並允許存取。")
    try:
        get_photos_credentials(allow_interactive=True)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"❌ 授權失敗: {e}")
        return 1
    print(f"✅ 授權完成, token 已存於 {PHOTOS_TOKEN_PATH.name}")
    print("   現在可以在 /app 用「Google 相簿」來源產生相片簡報了。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
