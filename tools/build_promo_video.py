#!/usr/bin/env python3
"""組裝 eduStudio 介紹影片 — 吃自己的狗糧版。

流程:
  1. 用 core.html_video(虛擬時鐘逐格擷取)把 docs/promo/scene*.html 各渲成 MP4
  2. ffmpeg 合成配樂音效(氛圍 pad + 節奏脈衝 + 轉場 whoosh + 重點 impact,全本地合成)
  3. ffmpeg xfade 依場景串接(fade/smoothleft/circleopen/fadeblack…,每刀不同)
  4. (可選 --narrate)edge-tts 逐景旁白,疊在對應時間點(需可連外的環境;雲端代理不支援)

用法(專案根目錄):
  python tools/build_promo_video.py --out output/edustudio_intro.mp4
  python tools/build_promo_video.py --skip-render          # 重用已渲好的場景 mp4
  python tools/build_promo_video.py --narrate              # 本機加旁白(edge-tts)

無頭 Chromium 版本與 playwright 不合時,設 EDUSTUDIO_CHROMIUM_PATH 指向瀏覽器執行檔。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.ffmpeg import run_media_cmd  # noqa: E402

PROMO = ROOT / "docs" / "promo"
FPS = 30
W, H = 1920, 1080
XF = 0.6  # 轉場重疊秒數

# (場景檔名, 秒數, 進入下一景的 xfade 轉場)
SCENES = [
    ("scene01_open",     7.0, "fade"),
    ("scene02_sources",  7.0, "smoothleft"),
    ("scene03_video",    8.0, "circleopen"),
    ("scene04_visual",   7.0, "smoothup"),
    ("scene05_comic",    7.0, "smoothleft"),
    ("scene06_localize", 7.0, "fadeblack"),   # 進審查關卡前切黑,做戲劇停頓
    ("scene07_review",   8.0, "circleopen"),
    ("scene08_publish",  7.0, "fade"),
    ("scene09_cta",      7.0, None),
]

# --narrate 用的逐景旁白(zh-TW);時長需 < 場景秒數-0.8
NARRATION = [
    "eduStudio,教學內容工作站。把備課素材,變成可以直接發布的教學內容。",
    "考卷、講義、文件、程式碼、音檔、相簿,一站全部吃進來。",
    "考卷 PDF,自動變成黑板風格的逐題解答影片,含旁白、字幕與章節。",
    "一句主題,產出教學簡報、資訊圖卡與海報,一鍵匯出 PPTX。",
    "連載式教學漫畫,角色鎖定、證據把關、六道品質關卡。",
    "翻譯、配音、會議摘要、雙語字幕,把內容帶到每一種語言。",
    "核心原則:絕不發布未經查證的 AI 數值。每個產出,都停在人工審查關卡。",
    "核准之後,一鍵上傳 YouTube,自動章節、你的品牌。",
    "開源、自架、你的資料你作主。eduStudio,現在就開始。",
]


def scene_offsets() -> tuple[list[float], float]:
    """回傳(各景在成片的起點秒數, 成片總長)。xfade 讓每景吃掉 XF 秒重疊。"""
    starts, t = [], 0.0
    for i, (_, dur, _) in enumerate(SCENES):
        starts.append(t)
        t += dur - (XF if i < len(SCENES) - 1 else 0.0)
    return starts, t


def render_scenes(tmp: Path, skip: bool) -> list[Path]:
    from core.html_video import render_html_to_mp4
    outs = []
    for name, dur, _ in SCENES:
        dst = tmp / f"{name}.mp4"
        outs.append(dst)
        if skip and dst.exists():
            print(f"[render] 重用 {dst.name}")
            continue
        print(f"[render] {name} ({dur:.0f}s)…", flush=True)
        render_html_to_mp4(PROMO / f"{name}.html", dst,
                           duration=dur, fps=FPS, width=W, height=H)
    return outs


def build_video(clips: list[Path], tmp: Path) -> Path:
    """xfade 串接全部場景(重新編碼一次,libx264 crf19)。"""
    starts, _total = scene_offsets()
    inputs: list[str] = []
    for c in clips:
        inputs += ["-i", str(c)]
    fg, prev = [], "[0:v]"
    for i in range(1, len(clips)):
        trans = SCENES[i - 1][2] or "fade"
        offset = starts[i]  # 下一景起點 = 此刀 xfade offset
        out = f"[v{i}]"
        fg.append(f"{prev}[{i}:v]xfade=transition={trans}:duration={XF}:offset={offset:.3f}{out}")
        prev = out
    fg.append(f"{prev}format=yuv420p[vout]")
    dst = tmp / "video_joined.mp4"
    run_media_cmd([
        "ffmpeg", "-y", "-loglevel", "error", *inputs,
        "-filter_complex", ";".join(fg), "-map", "[vout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-r", str(FPS),
        str(dst),
    ], step="ffmpeg xfade join", timeout=1200)
    return dst


def _sfx(tmp: Path, name: str, cmd_tail: list[str]) -> Path:
    p = tmp / name
    run_media_cmd(["ffmpeg", "-y", "-loglevel", "error", *cmd_tail, str(p)],
                  step=f"ffmpeg sfx {name}", timeout=300)
    return p


def build_audio(tmp: Path, total: float, cut_offsets: list[float], *,
                music: Path | None = None, music_gain_db: float = 0.0,
                no_sfx: bool = False, loudness: float | None = None) -> Path:
    """配樂音軌。預設為「安靜版」本地合成:暖 pad + 稀疏心跳 + 極輕 whoosh/impact。

    v2(2026-08-31 依劉老師回饋「太吵」重調):
    - 移除粉紅噪聲「空氣感」層 —— 60 秒持續嘶聲是吵感最大來源
    - 心跳低音 0.5s→2s 一顆、更軟、只在 S3~S6 出現(S7 戲劇段留給 pad 呼吸)
    - whoosh 音量 0.5→0.18、更暗更短;impact 0.9→0.5
    - 響度目標 -17→-23 LUFS(背景配樂等級,不再把整體推大聲)
    - pad 換暖聲底:每和弦兩音+極低第三音、低通 900、顫音更淺

    ``music`` 給真實音樂檔時,直接取代合成 pad+心跳(自動裁長度+淡入淡出,
    ``music_gain_db`` 微調音量);whoosh/impact 仍疊(除非 ``no_sfx``)。
    """
    d = f"{total:.3f}"
    starts, _ = scene_offsets()

    if music is not None:
        # 不足片長時用 1.5s 交叉淡接循環補滿(stream_loop 硬接會有聽得到的接縫)
        probe = run_media_cmd(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(music)],
            step="ffprobe music", timeout=60)
        mdur = float(probe.stdout.strip())
        cf = 1.5
        copies = 1
        while copies * mdur - (copies - 1) * cf < total + 0.5:
            copies += 1
        if copies == 1:
            base = _sfx(tmp, "music.wav", [
                "-i", str(music),
                "-af", (f"volume={music_gain_db}dB,afade=t=in:d=1.0,"
                        f"afade=t=out:st={total-3:.3f}:d=3"),
                "-t", d, "-ar", "48000", "-ac", "2",
            ])
        else:
            m_inputs: list[str] = []
            for _ in range(copies):
                m_inputs += ["-i", str(music)]
            mfg, prev = [], "[0:a]"
            for i in range(1, copies):
                outt = f"[m{i}]"
                mfg.append(f"{prev}[{i}:a]acrossfade=d={cf}:c1=tri:c2=tri{outt}")
                prev = outt
            mfg.append(f"{prev}volume={music_gain_db}dB,afade=t=in:d=1.0,"
                       f"afade=t=out:st={total-3:.3f}:d=3[mout]")
            base = tmp / "music.wav"
            run_media_cmd([
                "ffmpeg", "-y", "-loglevel", "error", *m_inputs,
                "-filter_complex", ";".join(mfg), "-map", "[mout]",
                "-t", d, "-ar", "48000", "-ac", "2", str(base),
            ], step="ffmpeg music loop", timeout=300)
        base_tags = ["[0:a]"]
        inputs = ["-i", str(base)]
        idx = 1
    else:
        # 暖 pad:Am(110+164.81) ↔ F(87.31+130.81) 8 秒互溶,第三音只留一點點光澤
        padexpr = (
            "0.15*((0.5+0.5*cos(PI*t/4))*(sin(2*PI*110*t)+0.9*sin(2*PI*164.81*t)+0.25*sin(2*PI*220*t))"
            "+(0.5-0.5*cos(PI*t/4))*(sin(2*PI*87.31*t)+0.9*sin(2*PI*130.81*t)+0.25*sin(2*PI*174.61*t)))"
            "*(0.96+0.04*sin(2*PI*0.18*t))"
        )
        pad = _sfx(tmp, "pad.wav", [
            "-f", "lavfi", "-i", f"aevalsrc={padexpr}:s=48000:d={d}",
            "-af", ("lowpass=f=900,aecho=0.6:0.35:140:0.18,"
                    "afade=t=in:d=2.5,afade=t=out:st=%.3f:d=3.5" % (total - 3.5)),
        ])
        # 心跳低音:每 2 秒一顆、圓潤緩衰減;S3 進、S7 前退乾淨
        kick = _sfx(tmp, "kick.wav", [
            "-f", "lavfi", "-i",
            f"aevalsrc=sin(2*PI*(42+50*exp(-16*mod(t\\,2)))*mod(t\\,2))*exp(-6*mod(t\\,2))*0.6:s=48000:d={d}",
            "-af", ("lowpass=f=140,afade=t=in:st=%.3f:d=2,afade=t=out:st=%.3f:d=2"
                    % (cut_offsets[1], starts[6] - 2.0)),
        ])
        base_tags = ["[0:a]", "[1:a]"]
        inputs = ["-i", str(pad), "-i", str(kick)]
        idx = 2

    fg, mix_tags = [], list(base_tags)
    if not no_sfx:
        # 極輕轉場氣音:短、暗、幾乎貼著畫面走
        whoosh = _sfx(tmp, "whoosh.wav", [
            "-f", "lavfi", "-i", "anoisesrc=color=pink:sample_rate=48000:duration=0.8",
            "-af", "lowpass=f=1600,highpass=f=200,afade=t=in:d=0.38,afade=t=out:st=0.4:d=0.4,volume=0.18",
        ])
        boom = _sfx(tmp, "boom.wav", [
            "-f", "lavfi", "-i",
            "aevalsrc=sin(2*PI*(36+60*exp(-6*t))*t)*exp(-3.6*t)*0.9:s=48000:d=1.4",
            "-af", "lowpass=f=200,volume=0.5",
        ])
        for off in cut_offsets:  # whoosh 提前 0.35s 進刀口
            inputs += ["-i", str(whoosh)]
            at = max(0.0, off - 0.35)
            fg.append(f"[{idx}:a]adelay={int(at*1000)}|{int(at*1000)}[w{idx}]")
            mix_tags.append(f"[w{idx}]")
            idx += 1
        for at in (1.05, starts[6] + 0.75, starts[8] + 0.75):  # S1 logo / S7 標語 / S9 logo
            inputs += ["-i", str(boom)]
            fg.append(f"[{idx}:a]adelay={int(at*1000)}|{int(at*1000)}[b{idx}]")
            mix_tags.append(f"[b{idx}]")
            idx += 1
    # 響度目標:合成 bed 走 -23(純陪襯);真實音樂主導預設 -16(YouTube 音樂內容慣例)。
    # ``loudness`` 可覆寫 —— 要「背景音樂感」壓 -20 上下。
    target_i = loudness if loudness is not None else (-16 if music is not None else -23)
    fg.append("".join(mix_tags) +
              f"amix=inputs={len(mix_tags)}:duration=first:normalize=0,"
              f"loudnorm=I={target_i}:TP=-1.5:LRA=11[aout]")
    dst = tmp / "bed.m4a"
    run_media_cmd([
        "ffmpeg", "-y", "-loglevel", "error", *inputs,
        "-filter_complex", ";".join(fg), "-map", "[aout]",
        "-c:a", "aac", "-b:a", "192k", "-t", d, str(dst),
    ], step="ffmpeg audio mix", timeout=600)
    return dst


def synth_narration(tmp: Path, voice: str) -> list[Path] | None:
    """edge-tts 逐景旁白;連不上(如雲端代理擋 WebSocket)回 None 並照常出無旁白版。"""
    try:
        import asyncio
        import edge_tts

        async def go():
            outs = []
            for i, line in enumerate(NARRATION):
                p = tmp / f"nar{i}.mp3"
                await edge_tts.Communicate(line, voice=voice, rate="+6%").save(str(p))
                outs.append(p)
            return outs
        return asyncio.run(go())
    except Exception as e:  # noqa: BLE001 — 明確降級,不擋出片
        print(f"[narrate] edge-tts 不可用({e.__class__.__name__}),改出無旁白版")
        return None


def mux(video: Path, bed: Path, narr: list[Path] | None, out: Path, total: float) -> None:
    starts, _ = scene_offsets()
    inputs = ["-i", str(video), "-i", str(bed)]
    if not narr:
        run_media_cmd([
            "ffmpeg", "-y", "-loglevel", "error", *inputs,
            "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy",
            "-movflags", "+faststart", "-t", f"{total:.3f}", str(out),
        ], step="ffmpeg mux", timeout=600)
        return
    fg, tags, idx = [], ["[1:a]"], 2
    for i, p in enumerate(narr):
        inputs += ["-i", str(p)]
        at = int((starts[i] + 0.55) * 1000)
        fg.append(f"[{idx}:a]adelay={at}|{at}[n{idx}]")
        tags.append(f"[n{idx}]")
        idx += 1
    fg.append("".join(tags) + f"amix=inputs={len(tags)}:duration=first:normalize=0,"
              "loudnorm=I=-16:TP=-1.5[aout]")
    run_media_cmd([
        "ffmpeg", "-y", "-loglevel", "error", *inputs,
        "-filter_complex", ";".join(fg),
        "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", "-t", f"{total:.3f}", str(out),
    ], step="ffmpeg mux narration", timeout=600)


def main() -> int:
    ap = argparse.ArgumentParser(description="組裝 eduStudio 介紹影片")
    ap.add_argument("--out", default=str(ROOT / "output" / "edustudio_intro.mp4"))
    ap.add_argument("--tmp", default=str(ROOT / "work" / "promo"))
    ap.add_argument("--skip-render", action="store_true", help="重用 tmp 內已渲好的場景 mp4")
    ap.add_argument("--narrate", action="store_true", help="edge-tts 旁白(需可連外)")
    ap.add_argument("--voice", default="zh-TW-HsiaoChenNeural")
    ap.add_argument("--music", type=Path, default=None,
                    help="用這個音樂檔取代合成配樂(自動裁長度+淡入淡出;建議免版稅曲)")
    ap.add_argument("--music-gain", type=float, default=0.0, help="音樂音量微調 dB(例 -6)")
    ap.add_argument("--loudness", type=float, default=None,
                    help="成品響度目標 LUFS(預設:音樂 -16 / 合成 bed -23;背景感用 -20)")
    ap.add_argument("--no-sfx", action="store_true", help="不疊轉場 whoosh / impact")
    ap.add_argument("--no-audio", action="store_true", help="出無聲版(自行後製配樂)")
    a = ap.parse_args()

    tmp = Path(a.tmp); tmp.mkdir(parents=True, exist_ok=True)
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)

    starts, total = scene_offsets()
    cut_offsets = starts[1:]
    print(f"[plan] {len(SCENES)} 景 · 總長 {total:.1f}s · 轉場 {XF}s ×{len(cut_offsets)}")

    clips = render_scenes(tmp, a.skip_render)
    video = build_video(clips, tmp)
    if a.no_audio:
        run_media_cmd(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
                       "-c", "copy", "-movflags", "+faststart", str(out)],
                      step="ffmpeg copy silent", timeout=300)
    else:
        bed = build_audio(tmp, total, cut_offsets,
                          music=a.music, music_gain_db=a.music_gain,
                          no_sfx=a.no_sfx, loudness=a.loudness)
        narr = synth_narration(tmp, a.voice) if a.narrate else None
        mux(video, bed, narr, out, total)
    print(f"[done] {out} ({out.stat().st_size/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
