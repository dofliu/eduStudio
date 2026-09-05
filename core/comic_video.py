"""core/comic_video.py — 漫畫 episode → 動態漫畫影片 (motion comic MP4 + SRT)。

定位
----
Comic Core (core.comics) 產出的是「一頁一張場景圖 + 對白不烙進圖裡 + 留白給泡泡」的
連載漫畫。這個模組把同一份 manifest 直接變成一支有旁白的教學影片, **不需要影片生成
模型**: 角色不做連續動作, 動感全部來自運鏡 (Ken Burns)、分格切換、對白泡泡跟著旁白
逐句浮現。生圖成本只跟頁數成正比, 跟影片秒數無關; 影片照樣輸出 30fps H.264,
因為每一格都是瀏覽器算出來的, 不是模型生成的。

管線
----
1. 逐句 TTS (沿用 tts_backend, 老師的聲音 / edge / google 都行) → 每句音長就是時間軸。
2. build_timeline: 片頭卡 → 每頁 [進場停頓 → 逐句泡泡 → 收尾停頓] → 片尾卡。
3. build_motion_comic_html: 自含 HTML 播放器 (圖片內嵌 data URI, JS 依 performance.now
   驅動), 與 core.html_video 的虛擬時鐘相容 → 逐格截圖成精準 fps 的 MP4。
4. 音軌: 每句 mp3 依 start 做 adelay 混音, 與影片 mux; 另出 SRT。

Fail-closed 對齊 Comic Core: 每頁必須連結 scene asset 才能渲染; 非 CURRENT 版本或含
mock 素材的影片一律烙「草稿預覽」水印, 不會被誤當正式產出。

同一份 HTML 也可直接用瀏覽器開啟即時預覽 (無聲), 不用等渲染。
"""
from __future__ import annotations

import asyncio
import base64
import html
import json
import logging
import mimetypes
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from core.comics import ComicStore, ComicGateError, EpisodeManifest, Series
from core.ffmpeg import run_media_cmd
from core.srt import fmt_srt_time

logger = logging.getLogger(__name__)

# ---------------- 時間軸常數 (秒) ----------------
INTRO_S = 2.6          # 片頭卡 (標題 + 學習目標)
OUTRO_S = 2.4          # 片尾卡 (teaching story boundary)
PAGE_LEAD_S = 0.9      # 每頁圖先亮相, 再開始說話
BUBBLE_GAP_S = 0.45    # 句與句之間的停頓
PAGE_TAIL_S = 0.8      # 最後一句講完後停留
TRANSITION_S = 0.6     # 頁與頁交叉淡接
MIN_SPEECH_S = 1.2     # 沒音檔時的估算下限

# 對白參考寬度: Comic Core 的 font_size 是以 768px 寬的頁面圖為基準
_REFERENCE_PAGE_WIDTH = 768.0

TTSFn = Callable[[str, Path], Awaitable[bool]]


# ---------------- 資料結構 ----------------
@dataclass
class BubbleCue:
    dialogue_id: str
    speaker_id: str
    speaker_name: str
    text: str
    start: float
    end: float
    x: float
    y: float
    w: float
    h: float
    font_size: float = 16.0
    tail_x: float | None = None
    tail_y: float | None = None
    is_narrator: bool = False
    audio_path: str | None = None


@dataclass
class PageSegment:
    page_no: int
    start: float
    end: float
    image_path: str
    alt_text: str = ""
    camera: str = "medium shot"
    beat: str = ""
    cues: list[BubbleCue] = field(default_factory=list)


@dataclass
class ComicTimeline:
    title: str
    series_title: str
    story_id: str
    version: str
    objectives: list[str]
    pages: list[PageSegment]
    intro_end: float
    outro_start: float
    total: float
    preview_label: str = ""
    narrator_avatar: str = ""   # 旁白角色 (例: 老師本人的漫畫形象) 去背 PNG 路徑; 空=不顯示

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ComicVideoResult:
    mp4: Path
    srt: Path
    html: Path
    timeline: ComicTimeline


# ---------------- 估算 / 時間軸 ----------------
_CJK_RE = re.compile("[\u3000-\u9fff\uf900-\ufaff\uff00-\uffef]")


def estimate_speech_seconds(text: str) -> float:
    """沒有 TTS 音檔時 (mock / 純預覽) 估算一句要講多久。

    中文約 0.28 秒/字, 其他字元 0.075 秒/字 (英文單字約 5 字母 ≈ 0.4 秒), 下限 MIN_SPEECH_S。
    """
    cjk = len(_CJK_RE.findall(text))
    other = max(0, len(text.strip()) - cjk)
    return max(MIN_SPEECH_S, cjk * 0.28 + other * 0.075 + 0.35)


def build_timeline(
    episode: EpisodeManifest,
    series: Series | None,
    *,
    image_paths: dict[int, Path],
    durations: dict[str, float],
    audio_paths: dict[str, Path] | None = None,
    layouts: dict[int, list] | None = None,
    preview_label: str = "",
    narrator_avatar: Path | None = None,
) -> ComicTimeline:
    """把 episode 的頁與對白排成絕對時間軸。

    Args:
        image_paths: page_no → 場景圖路徑 (每頁必備)。
        durations: dialogue_id → 音長 (秒); 缺的用 estimate_speech_seconds 補。
        audio_paths: dialogue_id → mp3 路徑 (可缺)。
        layouts: page_no → 已解析座標的 Dialogue 列表 (ComicStore.resolve_dialogue_layout);
            缺的用 manifest 內的座標。
        preview_label: 非空時影片烙水印。
    """
    audio_paths = audio_paths or {}
    layouts = layouts or {}
    speaker_names = {c.character_id: c.name for c in series.characters} if series else {}

    t = INTRO_S
    pages: list[PageSegment] = []
    for page in sorted(episode.pages, key=lambda p: p.page_no):
        if page.page_no not in image_paths:
            raise ComicGateError(f"第 {page.page_no} 頁沒有 scene asset, 無法渲染影片")
        dialogues = layouts.get(page.page_no) or page.dialogues
        seg_start = t
        t += PAGE_LEAD_S
        cues: list[BubbleCue] = []
        for d in dialogues:
            dur = durations.get(d.dialogue_id)
            if dur is None or dur <= 0:
                dur = estimate_speech_seconds(d.text)
            audio = audio_paths.get(d.dialogue_id)
            cues.append(BubbleCue(
                dialogue_id=d.dialogue_id,
                speaker_id=d.speaker_id,
                speaker_name=speaker_names.get(d.speaker_id, "" if d.speaker_id == "narrator" else d.speaker_id),
                text=d.text,
                start=round(t, 3),
                end=round(t + dur, 3),
                x=d.x, y=d.y, w=d.w, h=d.h,
                font_size=d.font_size,
                tail_x=d.tail_x, tail_y=d.tail_y,
                is_narrator=d.speaker_id == "narrator",
                audio_path=str(audio) if audio else None,
            ))
            t += dur + BUBBLE_GAP_S
        if not cues:
            t += 2.0  # 沒對白的頁: 純看圖
        t += PAGE_TAIL_S
        pages.append(PageSegment(
            page_no=page.page_no,
            start=round(seg_start, 3),
            end=round(t, 3),
            image_path=str(image_paths[page.page_no]),
            alt_text=page.alt_text,
            camera=page.camera,
            beat=page.beat,
            cues=cues,
        ))

    outro_start = t
    total = t + OUTRO_S
    return ComicTimeline(
        title=episode.title,
        series_title=series.title if series else "",
        story_id=episode.story_id,
        version=episode.version,
        objectives=list(episode.learning_objectives[:3]),
        pages=pages,
        intro_end=INTRO_S,
        outro_start=round(outro_start, 3),
        total=round(total, 3),
        preview_label=preview_label,
        narrator_avatar=str(narrator_avatar) if narrator_avatar else "",
    )


# ---------------- SRT ----------------
def build_comic_srt(timeline: ComicTimeline) -> str:
    """每句對白一條 cue; 角色句前綴「名字：」, 旁白不加前綴。"""
    lines: list[str] = []
    n = 1
    for page in timeline.pages:
        for cue in page.cues:
            text = cue.text.strip()
            if cue.speaker_name and not cue.is_narrator:
                text = f"{cue.speaker_name}：{text}"
            lines.append(f"{n}\n{fmt_srt_time(cue.start)} --> {fmt_srt_time(cue.end)}\n{text}\n")
            n += 1
    return "\n".join(lines) + ("\n" if lines else "")


# ---------------- HTML 播放器 ----------------
def _image_data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _image_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as im:
            return im.size
    except Exception:  # noqa: BLE001 — 尺寸只影響排版, 讀不到就當直式漫畫頁
        return (768, 1086)


_PLAYER_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:%(w)dpx;height:%(h)dpx;overflow:hidden;background:#0b1016}
body{font-family:"Noto Sans TC","Noto Sans CJK TC","Microsoft JhengHei","PingFang TC","WenQuanYi Zen Hei",system-ui,sans-serif;color:#e9f1f7}
#stage{position:relative;width:%(w)dpx;height:%(h)dpx;overflow:hidden;background:#0b1016}
.card{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;align-items:flex-start;padding:0 %(pad)dpx;opacity:0;background:radial-gradient(120%% 90%% at 20%% 20%%,#16303f 0%%,#0b1016 70%%)}
.card small{font-size:%(fs_small)dpx;letter-spacing:.18em;color:#42c7a5;text-transform:uppercase}
.card h1{font-size:%(fs_h1)dpx;line-height:1.15;margin:.25em 0 .35em;font-weight:800;max-width:82%%}
.card.has-avatar h1,.card.has-avatar ul,.card.has-avatar .boundary{max-width:60%%}
.card ul{list-style:none;font-size:%(fs_body)dpx;color:#c4d3df;line-height:1.7}
.card ul li::before{content:"▸ ";color:#f3a847}
.card .boundary{border-left:6px solid #f3a847;background:rgba(243,168,71,.12);padding:.6em 1em;color:#ffdca7;font-size:%(fs_body)dpx;max-width:78%%;line-height:1.6}
.card .brand{position:absolute;right:%(pad)dpx;bottom:%(pad_s)dpx;color:#7f93a4;font-size:%(fs_small)dpx;letter-spacing:.12em}
.page{position:absolute;inset:0;opacity:0;will-change:opacity}
.page .bg{position:absolute;inset:-6%%;background-size:cover;background-position:center;filter:blur(38px) brightness(.45) saturate(1.15);transform:scale(1.08)}
.page .frame{position:absolute;overflow:hidden;border-radius:10px;box-shadow:0 30px 80px rgba(0,0,0,.55);background:#000}
.page .frame img{position:absolute;inset:0;width:100%%;height:100%%;display:block;transform-origin:center center;will-change:transform}
.bubble{position:absolute;opacity:0;transform-origin:center bottom;background:#fff;color:#141b22;border-radius:18px;padding:.5em .8em .55em;line-height:1.42;font-weight:600;box-shadow:0 10px 30px rgba(0,0,0,.35);will-change:transform,opacity;word-break:break-word}
.bubble .who{display:block;font-size:.62em;font-weight:800;letter-spacing:.08em;color:#fff;background:#1f6feb;border-radius:999px;padding:.12em .7em;margin:-1.35em 0 .35em -.2em;width:max-content;box-shadow:0 4px 10px rgba(0,0,0,.25)}
.bubble .dot{display:inline-block;width:.45em;height:.45em;border-radius:50%%;background:#f3a847;margin-left:.45em;vertical-align:middle;opacity:0}
.bubble .tail{position:absolute;width:0;height:0;border:14px solid transparent}
.bubble .tail.down{bottom:-26px;border-top-color:#fff;border-bottom:0}
.bubble .tail.up{top:-26px;border-bottom-color:#fff;border-top:0}
.bubble.dim{opacity:.72}
.caption{position:absolute;left:%(pad)dpx;right:%(pad)dpx;bottom:%(pad_s)dpx;opacity:0;background:rgba(8,14,20,.82);border-left:6px solid #42c7a5;color:#eaf2f8;padding:.55em 1em;font-size:%(fs_cap)dpx;line-height:1.5;border-radius:8px;backdrop-filter:blur(6px);will-change:opacity,transform}
.card .avatar{position:absolute;right:%(pad)dpx;bottom:0;height:88%%;width:auto;object-fit:contain;filter:drop-shadow(0 18px 24px rgba(0,0,0,.45))}
.caption.with-avatar{padding-left:calc(%(fs_cap)dpx*2.9)}
.caption .cap-avatar{position:absolute;left:.55em;bottom:.35em;height:calc(100%% + .9em);width:auto;max-width:calc(%(fs_cap)dpx*2.2);object-fit:contain;object-position:bottom;filter:drop-shadow(0 6px 8px rgba(0,0,0,.5))}
.hud{position:absolute;top:%(pad_s)dpx;right:%(pad)dpx;font-size:%(fs_small)dpx;letter-spacing:.2em;color:rgba(233,241,247,.7);opacity:0}
.hud b{color:#42c7a5}
.watermark{position:absolute;left:%(pad)dpx;top:%(pad_s)dpx;font-size:%(fs_small)dpx;letter-spacing:.14em;color:#ffdca7;background:rgba(243,168,71,.18);border:1px solid rgba(243,168,71,.6);padding:.35em .9em;border-radius:6px;z-index:50}
"""

_PLAYER_JS = r"""
(() => {
  const T = window.__COMIC_TIMELINE__;
  const stage = document.getElementById('stage');
  const intro = document.getElementById('intro');
  const outro = document.getElementById('outro');
  const hud = document.getElementById('hud');
  const hudPage = document.getElementById('hud-page');
  const caption = document.getElementById('caption');
  const captionText = document.getElementById('caption-text');
  const pageEls = T.pages.map(p => document.getElementById('page-' + p.page_no));
  const imgEls = T.pages.map(p => document.querySelector('#page-' + p.page_no + ' img'));
  const cueEls = {};
  document.querySelectorAll('.bubble').forEach(el => { cueEls[el.dataset.id] = el; });
  const TR = T.transition_s, LEAD = T.page_lead_s, GAP = T.bubble_gap_s;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const easeOut = x => 1 - Math.pow(1 - x, 3);
  const easeBack = x => { const c1 = 1.4, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); };
  const fadeIO = (t, s, e, f) => Math.min(clamp((t - s) / f, 0, 1), clamp((e - t) / f, 0, 1));

  // 運鏡: 依 camera 決定推近幅度; 依頁序決定平移方向, 避免每頁一樣
  function kenBurns(p, i, cam) {
    cam = (cam || '').toLowerCase();
    let z0 = 1.03, z1 = 1.09;
    if (/close|特寫|near/.test(cam)) { z0 = 1.06; z1 = 1.16; }
    else if (/wide|establish|全景|遠景|aerial/.test(cam)) { z0 = 1.0; z1 = 1.05; }
    const dir = (i % 4);
    const dx = (dir === 0 ? -1 : dir === 1 ? 1 : dir === 2 ? -0.6 : 0.6) * 1.6;
    const dy = (dir < 2 ? -0.8 : 0.8);
    const z = z0 + (z1 - z0) * p;
    return `translate(${dx * (p - 0.5)}%, ${dy * (p - 0.5)}%) scale(${z})`;
  }

  function render(t) {
    // 片頭 / 片尾
    intro.style.opacity = t < T.intro_end + 0.2 ? fadeIO(t, 0, T.intro_end + 0.2, 0.5) : 0;
    outro.style.opacity = t > T.outro_start - 0.2 ? fadeIO(t, T.outro_start - 0.2, T.total + 1, 0.6) : 0;
    let current = null, activeCaption = null;
    T.pages.forEach((p, i) => {
      const el = pageEls[i];
      const inRange = t >= p.start - TR && t <= p.end + TR;
      if (!inRange) { el.style.opacity = 0; el.style.visibility = 'hidden'; return; }
      el.style.visibility = 'visible';
      const op = fadeIO(t, p.start - TR * 0.4, p.end + TR * 0.4, TR);
      el.style.opacity = op;
      const prog = clamp((t - p.start) / Math.max(0.001, p.end - p.start), 0, 1);
      imgEls[i].style.transform = kenBurns(prog, i, p.camera);
      if (t >= p.start && t < p.end) current = p;
      p.cues.forEach(c => {
        if (c.is_narrator) {   // 旁白沒有泡泡元素, 走底部 caption; 必須先判斷再查 cueEls
          if (t >= c.start && t <= c.end + GAP) activeCaption = c;
          return;
        }
        const el2 = cueEls[c.dialogue_id];
        if (!el2) return;
        if (t < c.start) { el2.style.opacity = 0; el2.style.transform = 'scale(.85)'; return; }
        const k = clamp((t - c.start) / 0.28, 0, 1);
        const active = t <= c.end + GAP;
        el2.style.opacity = (k < 1 ? k : 1) * (active ? 1 : 0.72);
        el2.style.transform = `scale(${0.85 + 0.15 * easeBack(k)})`;
        const dot = el2.querySelector('.dot');
        if (dot) { dot.style.opacity = active ? (0.55 + 0.45 * Math.sin(t * 9)) : 0; }
      });
    });
    if (activeCaption) {
      if (caption.dataset.id !== activeCaption.dialogue_id) {
        caption.dataset.id = activeCaption.dialogue_id;
        captionText.textContent = activeCaption.text;
      }
      const k = clamp((t - activeCaption.start) / 0.3, 0, 1);
      caption.style.opacity = k;
      caption.style.transform = `translateY(${(1 - easeOut(k)) * 14}px)`;
    } else { caption.style.opacity = 0; }
    if (current) {
      hud.style.opacity = 1;
      hudPage.textContent = String(current.page_no).padStart(2, '0');
    } else { hud.style.opacity = 0; }
  }
  window.__comicRender = render;
  render(0);
  const loop = () => { render(performance.now() / 1000); requestAnimationFrame(loop); };
  requestAnimationFrame(loop);
})();
"""


def _frame_rect(img_w: int, img_h: int, stage_w: int, stage_h: int) -> tuple[int, int, int, int]:
    """場景圖以 contain 置中 (上下留 6%, 左右留 4%), 回傳 (left, top, width, height)。"""
    max_w, max_h = stage_w * 0.92, stage_h * 0.88
    scale = min(max_w / img_w, max_h / img_h)
    w, h = int(img_w * scale), int(img_h * scale)
    return (stage_w - w) // 2, (stage_h - h) // 2, w, h


def _bubble_html(cue: BubbleCue, frame_w: int, stage_w: int) -> str:
    # 依 frame 相對 768 參考寬縮放字級, 影片上不能小於 22px
    fs = max(22.0, min(48.0, cue.font_size * frame_w / _REFERENCE_PAGE_WIDTH * 1.25))
    style = (
        f"left:{cue.x * 100:.2f}%;top:{cue.y * 100:.2f}%;width:{cue.w * 100:.2f}%;"
        f"min-height:{cue.h * 100:.2f}%;font-size:{fs:.1f}px"
    )
    tail = ""
    if cue.tail_x is not None and cue.tail_y is not None and cue.w > 0:
        rel = min(0.85, max(0.15, (cue.tail_x - cue.x) / cue.w))
        side = "down" if cue.tail_y >= cue.y + cue.h else "up"
        tail = f'<i class="tail {side}" style="left:calc({rel * 100:.1f}% - 14px)"></i>'
    who = (
        f'<span class="who">{html.escape(cue.speaker_name)}<i class="dot"></i></span>'
        if cue.speaker_name else ""
    )
    return (
        f'<div class="bubble" data-id="{html.escape(cue.dialogue_id)}" style="{style}">'
        f'{who}{html.escape(cue.text)}{tail}</div>'
    )


def build_motion_comic_html(
    timeline: ComicTimeline,
    *,
    width: int = 1920,
    height: int = 1080,
    embed_images: bool = True,
) -> str:
    """產出自含的動態漫畫播放器 HTML (供 core.html_video 逐格截圖, 或瀏覽器直接預覽)。"""
    pad = int(width * 0.06)
    pad_s = int(height * 0.045)
    css = _PLAYER_CSS % {
        "w": width, "h": height, "pad": pad, "pad_s": pad_s,
        "fs_small": max(14, int(height * 0.018)),
        "fs_h1": int(height * 0.075),
        "fs_body": int(height * 0.03),
        "fs_cap": int(height * 0.032),
    }

    pages_html: list[str] = []
    for i, page in enumerate(timeline.pages):
        img_path = Path(page.image_path)
        iw, ih = _image_size(img_path)
        left, top, fw, fh = _frame_rect(iw, ih, width, height)
        src = _image_data_uri(img_path) if embed_images else html.escape(img_path.as_uri())
        bubbles = "".join(_bubble_html(c, fw, width) for c in page.cues if not c.is_narrator)
        pages_html.append(
            f'<section class="page" id="page-{page.page_no}" style="z-index:{10 + i}">'
            f'<div class="bg" style="background-image:url({src})"></div>'
            f'<div class="frame" style="left:{left}px;top:{top}px;width:{fw}px;height:{fh}px">'
            f'<img src="{src}" alt="{html.escape(page.alt_text)}">{bubbles}</div></section>'
        )

    objectives = "".join(f"<li>{html.escape(o)}</li>" for o in timeline.objectives)
    avatar_src = ""
    if timeline.narrator_avatar and Path(timeline.narrator_avatar).is_file():
        avatar_src = _image_data_uri(Path(timeline.narrator_avatar)) if embed_images else html.escape(Path(timeline.narrator_avatar).as_uri())
    card_avatar = f'<img class="avatar" src="{avatar_src}" alt="">' if avatar_src else ""
    cap_avatar = f'<img class="cap-avatar" src="{avatar_src}" alt="">' if avatar_src else ""
    cap_class = "caption with-avatar" if avatar_src else "caption"
    watermark = (
        f'<div class="watermark">{html.escape(timeline.preview_label)}</div>' if timeline.preview_label else ""
    )
    data = {
        **timeline.to_dict(),
        "transition_s": TRANSITION_S,
        "page_lead_s": PAGE_LEAD_S,
        "bubble_gap_s": BUBBLE_GAP_S,
    }
    # 圖片路徑不需要進前端 JSON
    for p in data["pages"]:
        p.pop("image_path", None)
        for c in p["cues"]:
            c.pop("audio_path", None)
    # <script> 內的 JSON: 把 < 全部轉成 \u003c, 對白裡就算有 </script> 也不會跳出腳本
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")

    return f"""<!doctype html>
<html lang="zh-TW"><head><meta charset="utf-8"><title>{html.escape(timeline.title)}</title>
<style>{css}</style></head>
<body><div id="stage">
<div class="card{' has-avatar' if avatar_src else ''}" id="intro"><small>{html.escape(timeline.series_title)} · {html.escape(timeline.story_id)}</small>
<h1>{html.escape(timeline.title)}</h1><ul>{objectives}</ul>{card_avatar}<div class="brand">eduStudio · 動態漫畫</div></div>
{''.join(pages_html)}
<div class="card{' has-avatar' if avatar_src else ''}" id="outro" style="z-index:40"><small>Teaching story</small>
<h1>學到什麼?</h1><ul>{objectives}</ul>
<div class="boundary">本片為教學故事；技術與安全處置仍以 OEM、site procedure 與正式授權為準。</div>
{card_avatar}<div class="brand">eduStudio · {html.escape(timeline.version)}</div></div>
<div class="{cap_class}" id="caption" style="z-index:45">{cap_avatar}<span id="caption-text"></span></div>
<div class="hud" id="hud" style="z-index:45">PAGE <b id="hud-page">01</b></div>
{watermark}
</div>
<script>window.__COMIC_TIMELINE__ = {payload};</script>
<script>{_PLAYER_JS}</script>
</body></html>"""


# ---------------- TTS ----------------
def _media_duration(path: Path) -> float:
    from core.video_concat import get_video_duration

    return get_video_duration(path)


async def synthesize_dialogues(
    episode: EpisodeManifest,
    out_dir: Path,
    tts: TTSFn,
    *,
    tts_by_speaker: dict[str, TTSFn] | None = None,
    on_progress: Callable[[int], None] | None = None,
) -> tuple[dict[str, Path], dict[str, float]]:
    """逐句 TTS 到 out_dir/<dialogue_id>.mp3; 回傳 (音檔路徑, 音長秒數)。

    tts_by_speaker 可依 speaker_id 指定不同聲線 (角色配音); 沒對到的用 tts。
    任何一句失敗即 raise (對齊 pipeline.gen_tts: 不能無聲出片還當成功)。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    tts_by_speaker = tts_by_speaker or {}
    items = [(d.dialogue_id, d.speaker_id, d.text) for p in episode.pages for d in p.dialogues if d.text.strip()]
    paths: dict[str, Path] = {}
    durs: dict[str, float] = {}
    for i, (did, speaker, text) in enumerate(items):
        target = out_dir / f"{did}.mp3"
        if not await tts_by_speaker.get(speaker, tts)(text, target):
            raise RuntimeError(f"TTS 失敗: {did} 「{text[:30]}」")
        paths[did] = target
        durs[did] = _media_duration(target)
        if on_progress and items:
            on_progress(int((i + 1) / len(items) * 100))
    return paths, durs


# ---------------- 音軌 + mux ----------------
def mux_audio(
    video_path: Path,
    timeline: ComicTimeline,
    out_path: Path,
    *,
    ffmpeg: str = "ffmpeg",
) -> Path:
    """把每句 mp3 依 start 延遲後混成一軌, 與無聲影片 mux。沒任何音檔則補靜音軌。"""
    clips = [(c.audio_path, c.start) for p in timeline.pages for c in p.cues if c.audio_path]
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", str(video_path)]
    if clips:
        for path, _ in clips:
            cmd += ["-i", str(path)]
        parts = []
        for i, (_, start) in enumerate(clips, start=1):
            ms = int(round(start * 1000))
            parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[a{i}]")
        mix_in = "".join(f"[a{i}]" for i in range(1, len(clips) + 1))
        parts.append(
            f"{mix_in}amix=inputs={len(clips)}:duration=longest:normalize=0[mix];"
            f"[mix]apad=whole_dur={timeline.total:.3f}[outa]"
        )
        cmd += ["-filter_complex", ";".join(parts), "-map", "0:v", "-map", "[outa]"]
    else:
        cmd += [
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-map", "0:v", "-map", "1:a",
        ]
    cmd += [
        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
        "-t", f"{timeline.total:.3f}", "-movflags", "+faststart",
        str(out_path),
    ]
    run_media_cmd(cmd, step="ffmpeg 動態漫畫混音", text=False)
    return out_path


# ---------------- 編排 ----------------
def preview_label_for(episode: EpisodeManifest) -> str:
    """非 CURRENT 或含 mock 素材 → 影片烙水印 (fail-closed: 不能被當成正式產出)。"""
    used = {p.image_asset_id for p in episode.pages if p.image_asset_id}
    if any(a.asset_id in used and a.provenance == "mock_placeholder" for a in episode.assets):
        return "MOCK 素材 · 僅測流程 · 不可發布"
    if episode.state != "CURRENT":
        return f"草稿預覽 · {episode.state} · 尚未通過審核"
    return ""


def _default_narrator_avatar(store: ComicStore, episode: EpisodeManifest, series: Series | None) -> Path | None:
    """series 裡 character_id == 'narrator' 的角色若掛了 anchor asset (在這集的 assets 裡), 拿第一張當旁白形象。"""
    if not series:
        return None
    narrator = next((c for c in series.characters if c.character_id == "narrator"), None)
    if not narrator:
        return None
    for asset_id in narrator.anchor_assets:
        try:
            return store.resolve_asset(episode, asset_id)
        except Exception:  # noqa: BLE001 — 找不到就換下一張 / 不顯示
            continue
    return None


def _default_tts() -> TTSFn:
    from tts_backend import load_tts_backend

    backend = load_tts_backend()
    return backend.synthesize


def build_tts_by_speaker(voices: dict[str, str] | None) -> dict[str, TTSFn]:
    """把「speaker_id → 聲音規格」轉成 tts_by_speaker。

    規格字串:
    - "default"            → tts_config.json 設定的後端 (老師的 F5 聲音 / edge / google), 等同不指定
    - "edge:<voice>"       → Edge TTS 指定聲線, 例 edge:zh-TW-YunJheNeural (男) / edge:zh-TW-HsiaoYuNeural (女)
    - "edge:<voice>@<rate>"→ 加語速, 例 edge:zh-TW-YunJheNeural@-10%
    - "google:<voice>"     → Google Cloud TTS 指定聲線, 例 google:cmn-TW-Wavenet-B

    典型用法: narrator 留 default (老師本人的聲音講旁白), 角色各配一個 edge 聲線。
    """
    if not voices:
        return {}
    from tts_backend import EdgeTTS, GoogleTTS

    out: dict[str, TTSFn] = {}
    for speaker, spec in voices.items():
        spec = (spec or "").strip()
        if not spec or spec == "default":
            continue
        kind, _, rest = spec.partition(":")
        if kind == "edge" and rest:
            voice, _, rate = rest.partition("@")
            out[speaker] = EdgeTTS(voice=voice, rate=rate or "-5%").synthesize
        elif kind == "google" and rest:
            out[speaker] = GoogleTTS(voice=rest).synthesize
        else:
            raise ValueError(f"不支援的聲音規格 {spec!r} (speaker={speaker}); 用 default / edge:<voice> / google:<voice>")
    return out


def render_comic_video(
    store: ComicStore,
    project_id: str,
    story_id: str,
    version: str,
    *,
    out_dir: Path,
    stem: str | None = None,
    tts: TTSFn | None = None,
    tts_by_speaker: dict[str, TTSFn] | None = None,
    narrator_avatar: Path | None = None,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
    mock: bool = False,
    on_progress: Callable[[int], None] | None = None,
) -> ComicVideoResult:
    """漫畫 episode → out_dir/<stem>.mp4 + .srt + .html。

    Args:
        tts: (text, out_path) → bool 的 async 函式; None 時用 tts_backend.load_tts_backend()。
        tts_by_speaker: speaker_id → TTSFn, 角色配音 (沒對到的角色用 tts)。
        narrator_avatar: 旁白角色的去背 PNG (例: 老師本人的漫畫形象); 顯示在片頭 / 片尾卡與旁白字幕條旁。
            None 時自動找 series 裡 character_id 為 narrator 的角色的第一張 anchor asset。
        mock: True 時不跑 TTS、不開瀏覽器 (估算音長 + ffmpeg testsrc), 給 CI / 無瀏覽器環境。
        on_progress: 0~100; TTS 0~25, 截圖 25~85, 混音 85~100。

    Raises:
        ComicGateError: 有頁面沒連結 scene asset。
        RuntimeError: TTS 失敗。
    """
    from core.html_video import render_html_to_mp4

    episode = store.get_episode(project_id, story_id, version)
    try:
        series: Series | None = store.get_series(project_id, episode.series_id)
    except Exception:  # noqa: BLE001 — 沒 series 也能出片, 只是沒角色名
        series = None

    missing = [p.page_no for p in episode.pages if not p.image_asset_id]
    if missing or not episode.pages:
        raise ComicGateError(f"以下頁面尚未連結 scene asset, 無法渲染影片: {missing or '全部'}")
    image_paths = {p.page_no: store.resolve_asset(episode, p.image_asset_id) for p in episode.pages}
    layouts = {p.page_no: store.resolve_dialogue_layout(episode, p) for p in episode.pages}

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = stem or f"{episode.story_id}_{episode.version}_motion_comic"
    work = out_dir / f"{stem}_work"
    work.mkdir(parents=True, exist_ok=True)

    def prog(lo: int, hi: int) -> Callable[[int], None] | None:
        if not on_progress:
            return None
        return lambda pct: on_progress(lo + int((hi - lo) * pct / 100))

    audio_paths: dict[str, Path] = {}
    durations: dict[str, float] = {}
    if not mock:
        audio_paths, durations = asyncio.run(
            synthesize_dialogues(
                episode, work / "tts", tts or _default_tts(),
                tts_by_speaker=tts_by_speaker, on_progress=prog(0, 25),
            )
        )
    if on_progress:
        on_progress(25)

    timeline = build_timeline(
        episode, series,
        image_paths=image_paths, durations=durations, audio_paths=audio_paths,
        layouts=layouts, preview_label=preview_label_for(episode),
        narrator_avatar=narrator_avatar or _default_narrator_avatar(store, episode, series),
    )

    html_path = out_dir / f"{stem}.html"
    html_path.write_text(build_motion_comic_html(timeline, width=width, height=height), encoding="utf-8")
    srt_path = out_dir / f"{stem}.srt"
    srt_path.write_text(build_comic_srt(timeline), encoding="utf-8")

    silent = work / "video_silent.mp4"
    render_html_to_mp4(
        html_path, silent,
        duration=timeline.total, fps=fps, width=width, height=height,
        mock=mock, on_progress=prog(25, 85),
    )
    mp4_path = out_dir / f"{stem}.mp4"
    mux_audio(silent, timeline, mp4_path)
    if on_progress:
        on_progress(100)
    logger.info("動態漫畫渲染完成 → %s (%.1fs, %d 頁)", mp4_path.name, timeline.total, len(timeline.pages))
    return ComicVideoResult(mp4=mp4_path, srt=srt_path, html=html_path, timeline=timeline)
