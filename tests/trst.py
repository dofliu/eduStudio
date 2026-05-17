"""GCP TTS 試聲音 — 從 tests/ 或 repo root 都能跑.

跑法:
    python tests/trst.py

前置:
    1. pip install google-cloud-texttospeech  (你已裝)
    2. 設 env: $env:GOOGLE_APPLICATION_CREDENTIALS = "D:\\keys\\gcp-tts.json"
    3. tts_config.json 不必改 — 這 script 直接 new GoogleTTS, 不走 load_tts_backend
"""
import asyncio
import os
import sys
from pathlib import Path

# 把 repo root 加進 sys.path, 不論從哪裡跑都找得到 tts_backend
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 順便驗 env 設了沒, 沒設先 print 提醒 (避免下個錯不知道是這個)
creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
if not creds:
    print("⚠ GOOGLE_APPLICATION_CREDENTIALS 環境變數沒設.")
    print("   PowerShell: $env:GOOGLE_APPLICATION_CREDENTIALS = 'D:\\keys\\gcp-tts.json'")
    print("   (你可以仍繼續跑試誤, 但十之八九會 fail)\n")
else:
    print(f"✓ creds: {creds}")
    if not Path(creds).exists():
        print(f"⚠ 但檔案不存在! 檢查路徑.\n")

from tts_backend import GoogleTTS  # noqa: E402

# 試聽清單 — 2026 GCP 命名是 cmn-TW / cmn-CN (不是 zh-TW)
# 台灣腔: cmn-TW 只有 Wavenet + Standard 共 6 個 (沒 Chirp3-HD)
# 對岸腔: cmn-CN 有 Chirp3-HD (新 SOTA, 品質>Wavenet 但腔調是大陸)
VOICES = [
    # 台灣腔 (cmn-TW, language_code="zh-TW" 也吃)
    ("cmn-TW-Wavenet-A", "zh-TW", "🇹🇼 台灣女聲, Wavenet (預設候選)"),
    ("cmn-TW-Wavenet-B", "zh-TW", "🇹🇼 台灣男聲, Wavenet"),
    ("cmn-TW-Wavenet-C", "zh-TW", "🇹🇼 台灣男聲 #2, Wavenet"),
    ("cmn-TW-Standard-A", "zh-TW", "🇹🇼 台灣女聲, Standard (便宜 $4/1M)"),
    # 對岸腔 Chirp3-HD (品質高一截, 但腔調是大陸普通話)
    ("cmn-CN-Chirp3-HD-Aoede", "cmn-CN", "🇨🇳 對岸女聲, Chirp3-HD (高品質)"),
    ("cmn-CN-Chirp3-HD-Charon", "cmn-CN", "🇨🇳 對岸男聲, Chirp3-HD (高品質)"),
]

TEST_TEXT = "劉老師教材料力學. 應力等於力除以面積, 單位是百萬帕斯卡."
OUT_DIR = ROOT / "tts_samples"
OUT_DIR.mkdir(exist_ok=True)


async def main() -> None:
    for voice, lang, desc in VOICES:
        g = GoogleTTS(voice=voice, language_code=lang)
        out = OUT_DIR / f"sample_{voice}.mp3"
        ok = await g.synthesize(TEST_TEXT, out)
        if ok:
            size_kb = out.stat().st_size / 1024
            print(f"✓ {voice:30} → {out.name} ({size_kb:.1f} KB)  {desc}")
        else:
            print(f"✗ {voice:30} FAILED — 看上面 [google-tts] 行  {desc}")


if __name__ == "__main__":
    asyncio.run(main())
    print(f"\n試聽: {OUT_DIR}")
