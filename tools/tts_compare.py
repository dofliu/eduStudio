#!/usr/bin/env python3
"""
tts_compare.py — 同一段文字餵給 edge + f5 兩個 backend, 各產一個 mp3 給你直接比較。

不會動到 tts_config.json (用獨立 backend 物件), 也不會走完整 pipeline,
單純比對「聲音本身」的差異, 不含影片渲染。

使用:
    python tools/tts_compare.py "想測試的文字"
    python tools/tts_compare.py --text-file 要測的文字.txt

輸出:
    work/tts_compare/edge.mp3
    work/tts_compare/f5.mp3
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 本檔在 tools/ 底下, 加 parent 到 sys.path 才能 import 上層模組
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tts_backend import EdgeTTS, F5TTS  # noqa: E402


DEFAULT_TEXT = (
    "各位同學, 接下來我們要看的這個概念非常重要。"
    "大家可以想像, 像是日常生活中我們在做選擇時, 會根據不同條件做判斷, "
    "程式裡的邏輯運算其實也是一樣的道理。"
    "等一下我會帶大家看一個具體的例子, 並解釋為什麼這樣設計。"
)


def load_cfg() -> dict:
    p = ROOT / "tts_config.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


async def run(text: str, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = load_cfg()
    edge_cfg = cfg.get("edge", {})
    f5_cfg = cfg.get("f5", {})

    edge_p = out_dir / "edge.mp3"
    f5_p = out_dir / "f5.mp3"

    print(f"=== 文字 ({len(text)} 字) ===\n{text}\n")

    print("=== EDGE ===")
    edge = EdgeTTS(
        voice=edge_cfg.get("voice", "zh-TW-HsiaoChenNeural"),
        rate=edge_cfg.get("rate", "-5%"),
    )
    print(f"voice={edge.voice}, rate={edge.rate}")
    if await edge.synthesize(text, edge_p):
        print(f"✓ {edge_p.relative_to(ROOT)} ({edge_p.stat().st_size/1024:.1f} KB)")
    else:
        print("✗ Edge 失敗")

    print("\n=== F5 ===")
    if not f5_cfg:
        print("⚠ tts_config.json 沒有 f5 區塊, 跳過")
        return
    ref_audio = ROOT / f5_cfg.get("ref_audio", "voices/teacher_ref.wav").lstrip("./")
    if not ref_audio.exists():
        # 試一下原樣路徑
        ref_audio = Path(f5_cfg.get("ref_audio", ""))
    if not ref_audio.exists():
        print(f"⚠ ref_audio 不存在: {ref_audio}, 跳過")
        return

    f5 = F5TTS(
        ref_audio=str(ref_audio),
        ref_text=f5_cfg.get("ref_text", ""),
        model=f5_cfg.get("model", "F5TTS_v1_Base"),
        remove_silence=f5_cfg.get("remove_silence", True),
        speed=float(f5_cfg.get("speed", 1.0)),
        lead_trim_sec=float(f5_cfg.get("lead_trim_sec", 0.3)),
    )
    print(f"ref_audio={ref_audio.name}, speed={f5.speed}, lead_trim={f5.lead_trim_sec}s")
    print("(F5 第一次跑會載 model, 需 10~20 秒)")
    if await f5.synthesize(text, f5_p):
        print(f"✓ {f5_p.relative_to(ROOT)} ({f5_p.stat().st_size/1024:.1f} KB)")
    else:
        print("✗ F5 失敗 (見上方錯誤訊息)")

    print(f"\n用任意播放器開 {out_dir.relative_to(ROOT)}/ 比較兩支 mp3")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("text", nargs="?", default=None, help="要測試的文字 (空白用內建範例)")
    ap.add_argument("--text-file", help="從檔案讀文字")
    ap.add_argument("--out-dir", default="work/tts_compare", help="輸出目錄")
    args = ap.parse_args()

    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8").strip()
    elif args.text:
        text = args.text
    else:
        text = DEFAULT_TEXT

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir

    asyncio.run(run(text, out_dir))


if __name__ == "__main__":
    main()
