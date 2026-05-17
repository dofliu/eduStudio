"""列 GCP TTS 當前可用的中文 voice (zh / cmn 各種地區).

跑法: python tests/list_voices.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from google.cloud import texttospeech

client = texttospeech.TextToSpeechClient()

# 試 4 種可能的 language_code, 看 Google 現在用哪個
for lang in ("cmn-TW", "zh-TW", "cmn-CN", "zh-CN"):
    print(f"\n=== language_code = '{lang}' ===")
    try:
        voices = client.list_voices(language_code=lang).voices
    except Exception as e:
        print(f"  ERROR: {e}")
        continue
    if not voices:
        print("  (沒有 voice)")
        continue
    # 排序: Studio > Neural2 > Wavenet > Chirp > Standard
    def _tier(name: str) -> int:
        for i, k in enumerate(["Studio", "Neural2", "Wavenet", "Chirp", "Standard"]):
            if k in name:
                return i
        return 99
    for v in sorted(voices, key=lambda x: (_tier(x.name), x.name)):
        gender = v.ssml_gender.name
        rate = v.natural_sample_rate_hertz
        print(f"  {v.name:40} {gender:10} {rate} Hz")
