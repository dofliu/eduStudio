# Google Cloud TTS 設定 (iter 92)

跟 F5 / edge-tts 並存的第三條 TTS 後端 — zh-TW 品質最穩, 個人月用量 ~$1-2 USD.

## 為什麼接 GCP TTS

| Backend | 中文品質 | 成本 | 適合場景 |
|---|---|---|---|
| **edge-tts** (現預設) | 不錯, 偶爾頓挫 | 免費 | 一般用 / 急用 |
| **F5-TTS** | 中等, 中國腔 | 免費, 本機 GPU | voice clone (你自己聲音) |
| **GCP Wavenet** | 好, zh-TW 自然 | $16 USD/1M chars | 對外發佈品質要求高 |

15 分鐘中文影片約 3000 字 → GCP 一支 ~$0.05 USD.

## 啟用步驟

### 1. GCP 帳號 + API

```bash
# 你已經有 Gemini API key, GCP 帳號該已建. 沒有就先到:
# https://console.cloud.google.com
```

在 GCP Console:
1. 建立 / 選一個 project (可跟 Gemini 共用)
2. **APIs & Services → Library**, 搜 "Cloud Text-to-Speech API", 啟用
3. **APIs & Services → Credentials → Create Credentials → Service Account**
   - 名字: `tts-service` (隨意)
   - Role: `Cloud Text-to-Speech Service Agent` (或 `Editor` 也行)
4. 進 service account → **Keys → Add Key → Create New Key → JSON**
5. 下載 JSON 存到本機任一安全位置（路徑下面以 `<你的金鑰路徑>` 代表，換成實際路徑）

### 2. 設環境變數

```bash
# Linux / macOS — 加進 ~/.bashrc 或 ~/.zshrc
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/gcp-tts.json"
```

```powershell
# Windows PowerShell — 加進 $PROFILE
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\path\to\gcp-tts.json"
```

### 3. 裝 SDK

```bash
pip install google-cloud-texttospeech
```

### 4. 切換 backend

編輯 `tts_config.json`:

```json
{
  "backend": "google",
  "google": {
    "voice": "cmn-TW-Wavenet-A",
    "language_code": "zh-TW",
    "speaking_rate": 1.0,
    "pitch": 0.0,
    "audio_encoding": "MP3"
  },
  "edge": {
    "voice": "zh-TW-HsiaoChenNeural",
    "rate": "-5%"
  }
}
```

GCP 失敗時自動 fallback 到 `edge` (跟 F5 一樣的 FallbackTTS 機制).

## 可選 voice

⚠ **命名注意**: 2026 GCP 把中文 prefix 改成 `cmn-` (Mandarin), 舊的
`zh-TW-Wavenet-A` 已經 404. `language_code` 仍可用 `zh-TW` (alias OK)
但 voice name 必須是 `cmn-*`.

### 台灣腔 (`cmn-TW`, 6 個)

| voice | 性別 | 風格 |
|---|---|---|
| `cmn-TW-Wavenet-A` | 女 | 自然 (預設) |
| `cmn-TW-Wavenet-B` | 男 | 中性 |
| `cmn-TW-Wavenet-C` | 男 | 深沉 |
| `cmn-TW-Standard-A` | 女 | 標準 (便宜 $4/1M) |
| `cmn-TW-Standard-B/C` | 男 | Standard 系列 |

⚠ 台灣腔目前**沒有** Chirp3-HD 跟 Studio. 想要 SOTA 品質只能用對岸腔 (下方).

### 對岸腔 Chirp3-HD (`cmn-CN`, 32+ voices)

2025 新一代 SOTA, 品質明顯高過 Wavenet, 但**腔調是大陸普通話**.
教學講書面語時差別小, 講閩南語人名 / 台式口語就會聽起來怪.

代表 voices (語氣自取):
- `cmn-CN-Chirp3-HD-Aoede` (女, 溫暖)
- `cmn-CN-Chirp3-HD-Charon` (男, 沉穩)
- `cmn-CN-Chirp3-HD-Zephyr` (女, 明亮)
- `cmn-CN-Chirp3-HD-Puck` (男, 活潑)
- 完整 32 個名字跑 `python tests/list_voices.py` 看

### 查當前清單

GCP 偶爾會 ship 新 voice / 砍舊 voice, 隨時可以查:

```powershell
python tests/list_voices.py
```

## 試聲音 (跳過 pipeline)

```python
from tts_backend import GoogleTTS
import asyncio
from pathlib import Path

g = GoogleTTS(voice="zh-TW-Wavenet-A")
ok = asyncio.run(g.synthesize("劉老師教材料力學", Path("test_tw_a.mp3")))
print(f"success: {ok}, file: {Path('test_tw_a.mp3').stat().st_size} bytes")
```

聽 4 個 Wavenet 比較選順耳的.

## 故障排除

- **`google.api_core.exceptions.PermissionDenied`**: service account 沒給 TTS Role, 回 IAM 加
- **`DefaultCredentialsError`**: `GOOGLE_APPLICATION_CREDENTIALS` env 沒設或路徑錯
- **`Quota exceeded`**: 新 project 預設 60 req/min, 個人用不會撞 — 撞到去 Quotas 申請調整
- **完全沒輸出但 FallbackTTS 回 True**: 表示 fallback 到 edge 了, 看 console 找 `[google-tts] failed:` 那行
