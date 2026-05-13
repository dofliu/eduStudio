#!/usr/bin/env python3
"""
V0 考卷檢討影片生成器
流程:JSON -> TTS 音檔 -> 逐幀 PNG -> FFmpeg 合成 MP4
"""
import asyncio
import json
import os
import re
import subprocess
import sys
import wave
import struct
import math
import shutil
from pathlib import Path
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont
from mutagen.mp3 import MP3
from tts_backend import TTSBackend, load_tts_backend
from core.visuals import (
    CONTENT_BOTTOM,
    SUBTITLE_STRIP_COLOR,
)

# ---------- 設定 ----------
WIDTH, HEIGHT = 1920, 1080
BG_COLOR = (30, 58, 46)         # 深綠黑板
CHALK_WHITE = (232, 230, 216)   # 粉筆白 (舊步驟)
CHALK_HIGHLIGHT = (255, 217, 107)  # 粉筆黃 (最新步驟)
CHALK_TITLE = (180, 220, 200)   # 粉筆青 (標題)
CHALK_PROBLEM = (255, 200, 140) # 粉筆橙 (題目)
BORDER_COLOR = (60, 90, 75)     # 黑板邊框

FONT_PATH = os.environ.get("CLAUDE_FONT_PATH", "C:/Windows/Fonts/msjh.ttc")
FALLBACK_FONT_PATH = os.environ.get("CLAUDE_FALLBACK_FONT_PATH", "C:/Windows/Fonts/seguisym.ttf")
PAUSE_AFTER_EACH = 0.6

BASE_DIR = Path(__file__).parent
WORK_DIR = BASE_DIR / "work"
OUTPUT_DIR = BASE_DIR / "output"
PIPELINE_CONFIG_PATH = BASE_DIR / "pipeline_config.json"

# ---------- TTS ----------
# pronunciation.json 套用、分數展開、變數下標等前處理已下移到 tts_backend.py 的
# normalize_text(), 由 backend.synthesize() 自動套用。pipeline.py 只管編排。
_TTS_BACKEND = None
def _get_tts_backend():
    global _TTS_BACKEND
    if _TTS_BACKEND is None: _TTS_BACKEND = load_tts_backend()
    return _TTS_BACKEND

async def gen_tts(text, out_path):
    if not await _get_tts_backend().synthesize(text, out_path):
        raise RuntimeError(f"TTS Failed: {text[:50]}")

def mp3_duration(path): return MP3(str(path)).info.length

# ---------- 繪圖輔助 ----------
@lru_cache(None)
def _get_font(path, size): return ImageFont.truetype(path, size)

@lru_cache(None)
def _font_cps(path):
    try:
        from fontTools.ttLib import TTCollection, TTFont
        if path.lower().endswith(".ttc"):
            return frozenset().union(*(f.getBestCmap().keys() for f in TTCollection(path).fonts))
        return frozenset(TTFont(path).getBestCmap().keys())
    except: return frozenset()

def draw_text_mixed(draw, xy, text, main_font, fill):
    m_cps, f_cps = _font_cps(FONT_PATH), _font_cps(FALLBACK_FONT_PATH)
    x, y = xy
    fb_font = _get_font(FALLBACK_FONT_PATH, main_font.size)
    for ch in text:
        font = fb_font if (ord(ch) in f_cps and ord(ch) not in m_cps) else main_font
        draw.text((x, y), ch, font=font, fill=fill)
        x += int(font.getlength(ch))

def wrap_text(text, font, max_w):
    lines = []
    for raw in text.split("\n"):
        buf = ""
        for ch in raw:
            if font.getlength(buf + ch) > max_w and buf: lines.append(buf); buf = ch
            else: buf += ch
        if buf: lines.append(buf)
    return lines

def draw_text_wrapped(draw, xy, text, font, fill, max_w, line_h):
    wrapped = wrap_text(text, font, max_w)
    x, y = xy
    for ln in wrapped:
        draw_text_mixed(draw, (x, y), ln, font, fill)
        y += line_h
    return y

# ---------- 視覺設定 ----------
_PIPELINE_CONFIG = None
def _get_pipeline_config():
    global _PIPELINE_CONFIG
    if _PIPELINE_CONFIG is None:
        if PIPELINE_CONFIG_PATH.exists():
            _PIPELINE_CONFIG = json.loads(PIPELINE_CONFIG_PATH.read_text(encoding="utf-8"))
        else: _PIPELINE_CONFIG = {}
    return _PIPELINE_CONFIG

# ---------- 動態頭像 ----------
def _prepare_dynamic_avatar(cfg):
    if not cfg.get("enabled"): return
    WORK_DIR.mkdir(exist_ok=True)
    size, bw, shape = int(cfg.get("size", 220)), int(cfg.get("border_width", 3)), cfg.get("shape", "circle")
    tasks = [("path_closed", "avatar_closed.png")] + [(f"talking_{i}", f"avatar_talking_{i}.png", p) for i, p in enumerate(cfg.get("paths_talking", []))]
    for t in tasks:
        in_p = Path(t[2] if len(t)==3 else cfg.get(t[0], ""))
        if not in_p.exists(): continue
        photo = Image.open(in_p).convert("RGBA").resize((size, size), Image.LANCZOS)
        out = Image.new("RGBA", (size+bw*2, size+bw*2), (0,0,0,0))
        mask = Image.new("L", (size, size), 0); md = ImageDraw.Draw(mask)
        if shape == "circle": md.ellipse([0, 0, size, size], fill=255)
        else: md.rectangle([0, 0, size, size], fill=255)
        out.paste(photo, (bw, bw), mask=mask)
        if bw > 0:
            bd = ImageDraw.Draw(out); box = [bw//2, bw//2, size+bw*1.5, size+bw*1.5]
            if shape == "circle": bd.ellipse(box, outline=CHALK_WHITE, width=bw)
            else: bd.rectangle(box, outline=CHALK_WHITE, width=bw)
        out.save(WORK_DIR / t[1], "PNG")

def _build_avatar_concat(audio_p, out_txt, dur, cfg, q_work):
    wav_p = out_txt.with_suffix(".wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(audio_p), "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav_p)], check=True)
    p_closed = (WORK_DIR / "avatar_closed.png").absolute().as_posix().replace('\\', '/')
    threshold = cfg.get("volume_threshold", 500)
    talking = []
    i = 0
    while (WORK_DIR / f"avatar_talking_{i}.png").exists():
        talking.append((WORK_DIR / f"avatar_talking_{i}.png").absolute().as_posix().replace('\\', '/')); i += 1
    if not talking: talking = [p_closed]
    with wave.open(str(wav_p), 'rb') as w:
        samples = struct.unpack(f"<{w.getnframes()}h", w.readframes(w.getnframes()))
    chunk, lines, idx = 2400, [], 0
    for i in range(0, len(samples), chunk):
        s = samples[i:i+chunk]; rms = math.sqrt(sum(x*x for x in s)/len(s)) if s else 0
        img = talking[idx % len(talking)] if rms > threshold else p_closed
        if rms > threshold: idx += 1
        lines.append(f"file '{img}'\nduration 0.15")
    lines += [f"file '{p_closed}'\nduration {PAUSE_AFTER_EACH}", f"file '{p_closed}'"]
    out_txt.write_text("\n".join(lines), encoding="utf-8")
    wav_p.unlink(missing_ok=True)

def _overlay_teacher_photo(img):
    """Thin wrapper — 真正邏輯在 core.photo_overlay (iter 35 拆出)。

    保留底線 prefix 是為了 pipeline.py 內部其他地方繼續用既有 import path,
    BlackboardRenderer / SlideRenderer / PptxStyleRenderer 都會呼叫。
    """
    from core.photo_overlay import overlay_teacher_photo
    overlay_teacher_photo(
        img,
        config=_get_pipeline_config(),
        canvas_width=WIDTH,
        canvas_height=HEIGHT,
        border_color=CHALK_WHITE,
    )

# ---------- 渲染與合成 ----------
# Renderer 基類:Phase 1 引入,為了 v1.7 簡報講解模式鋪路。
# 每個 step 由 step.get("bg_type") 決定走哪個 Renderer,預設 "blackboard"。
class Renderer:
    def render(self, data, step_idx, out_p, q_work):
        raise NotImplementedError


class BlackboardRenderer(Renderer):
    def render(self, data, step_idx, out_p, q_work):
        img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR); draw = ImageDraw.Draw(img)
        for i in range(8): draw.rectangle([i, i, WIDTH-1-i, HEIGHT-1-i], outline=BORDER_COLOR)
        # 字體大小:縮小 30~35% 騰出空間給更多步驟與更大的 SVG
        title_f, prob_f, step_f = _get_font(FONT_PATH, 22), _get_font(FONT_PATH, 40), _get_font(FONT_PATH, 46)
        PROB_LH, STEP_LH = 52, 56  # 行高配合字體縮小
        STEP_Y_MAX = CONTENT_BOTTOM
        draw.rectangle([0, STEP_Y_MAX, WIDTH, HEIGHT], fill=(0, 0, 0, 180))
        y = draw_text_wrapped(draw, (60, 20), data.get("title", ""), title_f, CHALK_TITLE, WIDTH-160, 28)
        y = draw_text_wrapped(draw, (60, y), data.get("subtitle", ""), title_f, CHALK_TITLE, WIDTH-160, 28)
        sep_y = draw_text_wrapped(draw, (100, y+15), data["problem"], prob_f, CHALK_PROBLEM, WIDTH-200, PROB_LH) + 15
        draw.line([(80, sep_y), (WIDTH-80, sep_y)], fill=CHALK_TITLE, width=2)
        steps = data["steps"][:step_idx]

        # 先找出最新的視覺元素 (svg / image), 兩個 pass 分開避免 break 吃掉前面的 svg
        svg_code, svg_from_step, img_show = None, -1, None
        for idx in range(len(steps)-1, -1, -1):
            if steps[idx].get("diagram_svg"):
                svg_code = steps[idx]["diagram_svg"]; svg_from_step = idx; break
        if not svg_code:
            for idx in range(len(steps)-1, -1, -1):
                if steps[idx].get("image"):
                    img_show = steps[idx]["image"]; break
        if not svg_code and not img_show:
            img_show = data.get("image")

        # SVG 觸發狀態日誌 (協助你看 pipeline 到底有沒有抓到)
        total_svg = sum(1 for s in data["steps"] if s.get("diagram_svg"))
        if svg_code:
            print(f"[frame {step_idx:03d}] ✅ SVG from step {svg_from_step+1} (整題 {total_svg} 個 SVG)")
        elif img_show:
            print(f"[frame {step_idx:03d}] 🖼  image: {img_show}")
        else:
            print(f"[frame {step_idx:03d}] ⚪ no visual (整題 {total_svg} 個 SVG, 本步之前無)")

        # 若有視覺元素, 步驟文字限縮在左 55%, 讓右側 45% 給圖形獨用
        has_visual = bool(svg_code or img_show)
        step_max_w = int(WIDTH * 0.55) - 100 if has_visual else WIDTH - 300

        h_list = [max(1, len(wrap_text(s.get("display", ""), step_f, step_max_w)))*STEP_LH+24 for s in steps]
        vis, used, cur_y = [], 0, sep_y+30
        for i in range(len(steps)-1, -1, -1):
            if used + h_list[i] > (STEP_Y_MAX - cur_y) and vis: break
            vis.insert(0, i); used += h_list[i]
        for i in vis:
            c = CHALK_HIGHLIGHT if i==len(steps)-1 else CHALK_WHITE
            draw_text_mixed(draw, (80, cur_y), f"{i+1}.", step_f, c)
            cur_y = draw_text_wrapped(draw, (140, cur_y), steps[i].get("display", ""), step_f, c, step_max_w, STEP_LH) + 24

        if svg_code:
            try:
                import cairosvg
                tmp = q_work / f"svg_{step_idx:03d}.png"
                cairosvg.svg2png(bytestring=svg_code.encode("utf-8"), write_to=str(tmp), scale=3.0)
                img_show = str(tmp)
                print(f"[frame {step_idx:03d}] 🎨 cairosvg -> {tmp.name}")
            except Exception as e:
                import traceback
                print(f"SVG Error: {e}"); traceback.print_exc()
        if img_show and Path(img_show).exists():
            # 右側獨立區塊: 佔 WIDTH 的 40%, 垂直居中於題目線下方到字幕區之間
            col_x0 = int(WIDTH * 0.58)
            col_w = WIDTH - col_x0 - 60
            col_h = STEP_Y_MAX - (sep_y + 40)
            p_img = Image.open(img_show); p_img.thumbnail((col_w, col_h))
            px = col_x0 + (col_w - p_img.width) // 2
            py = sep_y + 40 + (col_h - p_img.height) // 2
            if not svg_code:
                draw.rectangle([px-10, py-10, px+p_img.width+10, py+p_img.height+10], fill="white", outline=CHALK_WHITE, width=4)
            img.paste(p_img, (px, py), mask=p_img.convert("RGBA").split()[-1] if p_img.mode in ("RGBA","LA") else None)
        _overlay_teacher_photo(img); img.save(out_p, "PNG")


def _resolve_asset(rel_or_abs: str) -> Path:
    p = Path(rel_or_abs)
    return p if p.is_absolute() else BASE_DIR / p


class SlideRenderer(Renderer):
    """投影片渲染器, 兩種 layout:

    - layout="full" (預設): 投影片 letterbox-fit 到 1920×1080
    - layout="split-left" (Phase 4): 左半放投影片縮小, 右半放 title + bullets
      文字註解; 解題型投影片用, 老師可在右側列出該頁要點/算式

    底部 180px 黑帶讓 SRT 字幕區與黑板模式視覺一致。
    """

    def render(self, data, step_idx, out_p, q_work):
        step = data["steps"][step_idx - 1]
        layout = (step.get("layout") or "full").strip().lower()
        if layout == "split-left":
            self._render_split_left(step, step_idx, out_p)
        else:
            self._render_full(step, step_idx, out_p)

    def _render_full(self, step, step_idx, out_p):
        """既有 layout: 投影片 letterbox-fit 進可視區 1920×900 (扣字幕帶 180px).

        修正前 letterbox 用整個 1920×1080, 再蓋黑帶在 y=900..1080, 會把 slide
        底部 16.7% 切掉 (例: x 軸標籤 / footer / 穩定區域字 全消失).
        現在 letterbox 進 1920×900, 並居中於該區, slide 完整可見.
        """
        canvas = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        # 可視區 = 整個畫面扣字幕帶, 常數由 core.visuals 集中提供
        visible_h = CONTENT_BOTTOM   # 900

        bg_rel = step.get("bg_image", "")
        bg_path = _resolve_asset(bg_rel) if bg_rel else None
        if bg_path and bg_path.exists():
            slide = Image.open(bg_path).convert("RGB")
            ratio = min(WIDTH / slide.width, visible_h / slide.height)
            sw, sh = max(1, int(slide.width * ratio)), max(1, int(slide.height * ratio))
            slide = slide.resize((sw, sh), Image.LANCZOS)
            # 居中於可視區 (不是整個 1080), 否則 slide 會被字幕帶蓋掉底部
            canvas.paste(slide, ((WIDTH - sw) // 2, (visible_h - sh) // 2))
            print(f"[frame {step_idx:03d}] 🖼 slide: {bg_path.name} ({sw}x{sh})")
        else:
            print(f"[frame {step_idx:03d}] ⚠ slide 找不到: {bg_rel!r} (純黑底 fallback)")

        draw = ImageDraw.Draw(canvas)
        draw.rectangle([0, CONTENT_BOTTOM, WIDTH, HEIGHT], fill=SUBTITLE_STRIP_COLOR)
        _overlay_teacher_photo(canvas)
        canvas.save(out_p, "PNG")

    def _render_split_left(self, step, step_idx, out_p):
        """Phase 4: 左半 (~940 寬) slide 縮放, 右半 (~920 寬) title + bullets.

        Layout 常數參考 1920×1080 扣 180 底部字幕帶 = 0..900 內容區:
          x=0..940     左半 slide 區 (含內距)
          x=950..960   分隔線
          x=970..1880  右半文字區 (title + bullets)
          y=900..1080  字幕黑帶 (跟 _render_full / BlackboardRenderer 同位置)
        """
        canvas = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))

        # 左半: slide image
        LEFT_X1, LEFT_Y1 = 20, 30
        LEFT_X2, LEFT_Y2 = 940, CONTENT_BOTTOM - 30
        left_w = LEFT_X2 - LEFT_X1
        left_h = LEFT_Y2 - LEFT_Y1

        bg_rel = step.get("bg_image", "")
        bg_path = _resolve_asset(bg_rel) if bg_rel else None
        if bg_path and bg_path.exists():
            slide = Image.open(bg_path).convert("RGB")
            ratio = min(left_w / slide.width, left_h / slide.height)
            sw, sh = max(1, int(slide.width * ratio)), max(1, int(slide.height * ratio))
            slide = slide.resize((sw, sh), Image.LANCZOS)
            sx = LEFT_X1 + (left_w - sw) // 2
            sy = LEFT_Y1 + (left_h - sh) // 2
            canvas.paste(slide, (sx, sy))
            print(f"[frame {step_idx:03d}] 🖼 split-left slide: {bg_path.name} ({sw}x{sh})")
        else:
            print(f"[frame {step_idx:03d}] ⚠ split-left slide 找不到: {bg_rel!r}")

        draw = ImageDraw.Draw(canvas)

        # 中間分隔線 (粉筆青, 對齊 BlackboardRenderer 配色)
        DIVIDER_X = 955
        draw.line(
            [(DIVIDER_X, 30), (DIVIDER_X, CONTENT_BOTTOM - 30)],
            fill=CHALK_TITLE, width=2,
        )

        # 右半: title + bullets (字級對齊 PptxStyleRenderer)
        RIGHT_X = DIVIDER_X + 25
        RIGHT_W = WIDTH - RIGHT_X - 30
        TITLE_FONT_SIZE = 52
        BULLET_FONT_SIZE = 32
        BULLET_LINE_H = 44
        title_font = _get_font(FONT_PATH, TITLE_FONT_SIZE)
        bullet_font = _get_font(FONT_PATH, BULLET_FONT_SIZE)

        y = 50
        title = (step.get("title") or step.get("display") or "").strip()
        if title:
            y = draw_text_wrapped(
                draw, (RIGHT_X, y), title, title_font,
                CHALK_HIGHLIGHT, RIGHT_W, TITLE_FONT_SIZE + 8,
            )
            # 標題底線
            draw.line(
                [(RIGHT_X, y + 6), (RIGHT_X + 220, y + 6)],
                fill=CHALK_HIGHLIGHT, width=3,
            )
            y += 36

        bullets = step.get("bullets") or []
        bullet_max_w = RIGHT_W - 32
        content_y_max = CONTENT_BOTTOM - 30
        for b in bullets:
            text = (b or "").strip()
            if not text:
                continue
            # 圓點 marker (對齊 bullet 第一行垂直中心)
            marker_y = y + (BULLET_FONT_SIZE - 12) // 2
            draw.ellipse(
                [(RIGHT_X, marker_y), (RIGHT_X + 12, marker_y + 12)],
                fill=CHALK_HIGHLIGHT,
            )
            y = draw_text_wrapped(
                draw, (RIGHT_X + 28, y), text, bullet_font,
                CHALK_WHITE, bullet_max_w, BULLET_LINE_H,
            )
            y += 14
            # bullets 太多時截斷, 不壓到字幕區 (使用者要拆兩張投影片)
            if y > content_y_max:
                break

        # 字幕黑帶, 與 _render_full / BlackboardRenderer 對齊
        draw.rectangle([0, CONTENT_BOTTOM, WIDTH, HEIGHT], fill=SUBTITLE_STRIP_COLOR)
        _overlay_teacher_photo(canvas)
        canvas.save(out_p, "PNG")


# 動態註冊 PptxStyleRenderer (PR-2b-ii):
# 為什麼用 lazy import: core.render.pptx_style 內部 try/except 會 import 回 pipeline
# 抓 _overlay_teacher_photo, 直接 module-level import 會 circular。延後到 module 完全
# load 後才註冊就沒事。
def _load_pptx_renderer():
    from core.render.pptx_style import PptxStyleRenderer
    return PptxStyleRenderer()


_RENDERERS = {
    "blackboard": BlackboardRenderer(),
    "slide": SlideRenderer(),
    "pptx_slide": _load_pptx_renderer(),
}


def render_frame(data, step_idx, out_p, q_work):
    step = data["steps"][step_idx - 1]
    bg_type = step.get("bg_type", "blackboard")
    renderer = _RENDERERS.get(bg_type)
    if renderer is None:
        raise ValueError(f"未知的 bg_type: {bg_type!r} (step {step_idx})")
    renderer.render(data, step_idx, out_p, q_work)

def build_clip(f_p, a_p, dur, out_p, q_work):
    cfg = _get_pipeline_config(); dyn, sfx = cfg.get("dynamic_avatar",{}), cfg.get("chalk_sfx",{})
    total = dur + PAUSE_AFTER_EACH
    inputs = ["-loop", "1", "-t", f"{total:.3f}", "-i", str(f_p), "-i", str(a_p)]
    sfx_idx, ava_idx, next_idx = -1, -1, 2
    if sfx.get("enabled") and Path(sfx.get("path","")).exists():
        inputs += ["-stream_loop", "-1", "-i", sfx["path"]]; sfx_idx = next_idx; next_idx += 1
    if dyn.get("enabled") and (WORK_DIR/"avatar_closed.png").exists():
        ava_txt = q_work / f"avatar_{a_p.stem}.txt"
        _build_avatar_concat(a_p, ava_txt, dur, dyn, q_work)
        inputs += ["-f", "concat", "-safe", "0", "-i", str(ava_txt)]; ava_idx = next_idx; next_idx += 1
    
    a_f = "[1:a]aresample=44100,loudnorm=I=-16:TP=-1.5:LRA=11[a_norm]"
    if sfx_idx != -1:
        a_f += f";[{sfx_idx}:a]volume={sfx['volume']},atrim=0:{total:.3f}[bg_sfx]"
        a_f += f";[a_norm][bg_sfx]amix=inputs=2:duration=first[a_mixed]"
        a_final = "[a_mixed]"
    else:
        a_final = "[a_norm]"
    a_f += f";{a_final}apad=pad_dur={PAUSE_AFTER_EACH}[out_a]"

    if ava_idx != -1:
        s, m, bw = int(dyn.get("size",220)), int(dyn.get("margin",40)), int(dyn.get("border_width",3))
        v_f = f"[{ava_idx}:v]format=rgba[ava];[0:v][ava]overlay=x={WIDTH-s-m-bw}:y={HEIGHT-s-m-bw}:eof_action=pass[out_v]"
    else: v_f = "[0:v]copy[out_v]"
    
    cmd = ["ffmpeg", "-y", "-loglevel", "error"] + inputs + [
        "-filter_complex", f"{a_f};{v_f}",
        "-map", "[out_v]", "-map", "[out_a]",
        "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-pix_fmt", "yuv420p",
        "-t", f"{total:.3f}", "-r", "30", str(out_p)
    ]
    subprocess.run(cmd, check=True)

def _build_hardsub_cmd(out_name: str, work_dir: Path) -> list[str]:
    """產生 ffmpeg 燒字幕指令 (PR-5c). 抽出函式給 unit test 用 (不必跑 ffmpeg).

    cwd 設為 OUTPUT_DIR 讓 subtitles filter 用相對檔名, 避開 Windows path 含
    冒號要 escape 的麻煩 (`D\:/foo/bar.srt`)。

    force_style 把字型固定 Microsoft JhengHei (Windows) / SimHei (跨平台後備),
    白字黑邊 BorderStyle=3 (字幕底有 box) 在多種背景都看得清楚。
    """
    return [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", f"{out_name}.mp4",
        "-vf", (
            f"subtitles={out_name}.srt:"
            "force_style='FontName=Microsoft JhengHei,FontSize=22,"
            "PrimaryColour=&H00FFFFFF&,OutlineColour=&H00000000&,"
            "BorderStyle=3,MarginV=40'"
        ),
        "-c:a", "copy",   # 音訊不重編碼, 節省時間
        f"{out_name}.hardsub.mp4",
    ]


def burn_subtitles(out_name: str) -> None:
    """把 SRT 燒進 MP4: ffmpeg subtitles filter 重新編碼影片軌, 音訊直 copy.

    輸出取代原 OUTPUT_DIR/{out_name}.mp4 (移檔), 字幕 SRT 仍然保留方便 YouTube
    上傳。失敗時保留原 mp4 不動, 印警告。
    """
    cmd = _build_hardsub_cmd(out_name, OUTPUT_DIR)
    try:
        subprocess.run(cmd, cwd=OUTPUT_DIR, check=True)
    except subprocess.CalledProcessError as e:
        print(f"⚠ 燒字幕失敗 (保留原版 mp4): {e}")
        # 清掉可能殘留的部分輸出
        (OUTPUT_DIR / f"{out_name}.hardsub.mp4").unlink(missing_ok=True)
        return
    # 取代原檔
    final = OUTPUT_DIR / f"{out_name}.mp4"
    hard = OUTPUT_DIR / f"{out_name}.hardsub.mp4"
    final.unlink(missing_ok=True)
    hard.replace(final)
    print(f"   字幕已燒入 {out_name}.mp4")


async def main(json_path, out_name, start_step=None):
    q_work = WORK_DIR / out_name; q_work.mkdir(parents=True, exist_ok=True)
    if start_step is None:
        # 全量渲染時, 徹底清除該題目錄下的所有舊產物, 避免用到上次的 frame / svg / clip
        # (過去只清 clip, 但 frame / svg_*.png 若殘留會讓 MP4 用到舊畫面, 看起來像 SVG 沒觸發)
        for pattern in ("clip_*.mp4", "frame_*.png", "svg_*.png", "audio_*.mp3"):
            for old in q_work.glob(pattern): old.unlink()
        print(f"[pipeline] cleared stale cache in {q_work}")

    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    _prepare_dynamic_avatar(_get_pipeline_config().get("dynamic_avatar",{}))
    audios, frames, clips, durs = [], [], [], []
    for i, s in enumerate(data["steps"]):
        ap, fp, cp = q_work/f"audio_{i:03d}.mp3", q_work/f"frame_{i:03d}.png", q_work/f"clip_{i:03d}.mp4"
        if start_step is None or i+1 == start_step or not ap.exists(): await gen_tts(s["narration"], ap)
        audios.append(ap); d = mp3_duration(ap); durs.append(d)
        if start_step is None or i+1 >= start_step or not fp.exists(): render_frame(data, i+1, fp, q_work)
        frames.append(fp)
        if start_step is None or i+1 >= start_step or not cp.exists(): build_clip(fp, ap, d, cp, q_work)
        clips.append(cp)
        
    # Py 3.10 不允許 f-string 表達式內含反斜線, 把 .replace('\\', '/') 拉出來算
    posix_clips = [p.absolute().as_posix().replace("\\", "/") for p in clips]
    list_f = q_work / "concat.txt"
    list_f.write_text("\n".join(f"file '{path}'" for path in posix_clips), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(list_f), "-c", "copy", str(OUTPUT_DIR / f"{out_name}.mp4")], check=True)

    # iter 37: SRT 生成邏輯抽到 core.srt, 純函式好測 (10 行 dense → import 一條)
    from core.srt import build_srt
    srt_text = build_srt(data["steps"], durs, pause_after_each=PAUSE_AFTER_EACH)
    (OUTPUT_DIR / f"{out_name}.srt").write_text(srt_text, encoding="utf-8")

    # PR-5c: 燒字幕 — 把外掛 SRT 直接畫進畫面, 取代原 mp4。
    # data["hardsub"] 由 runner.py 從 JobOptions.hardsub 帶過來; 預設 False。
    if data.get("hardsub"):
        burn_subtitles(out_name)

    print(f"✅ 完成: {out_name}.mp4")

if __name__ == "__main__":
    from core.runtime import setup_utf8_stdout
    setup_utf8_stdout()
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("json_path"); ap.add_argument("out_name", nargs="?", default="review"); ap.add_argument("--step", type=int); ap.add_argument("--tts")
    args = ap.parse_args()
    if args.tts: os.environ["TTS_PROVIDER"] = args.tts
    asyncio.run(main(args.json_path, args.out_name, start_step=args.step))
