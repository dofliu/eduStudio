"""core/html_video.py — 把 HTML 動畫網頁渲成 MP4 (eduStudio Video track 延伸)。

定位
----
專案既有的影片都是「逐 frame 算圖 (PIL / cairosvg) → ffmpeg 合成 MP4」。這個模組
補上另一條來源: 任意 **HTML 動畫網頁** (CSS / requestAnimationFrame / Web Animations
/ Canvas / SVG SMIL 皆可) → MP4, 產出落在 job 的 artifacts/ 後, 既有的 /library
列表與 YouTube 上傳 (server/routes/youtube.py) 即可直接接手, 不需改上傳端。

為什麼用「虛擬時鐘」逐 frame 截圖, 而不是即時錄影
------------------------------------------------
即時螢幕錄影 (page.video) 受機器負載影響, 動畫快慢/掉幀不可重現, 也對不準 fps。
這裡改用 timecut/timeweb 那套作法: 在頁面腳本執行「之前」注入一支 shim, 接管
performance.now / Date.now / requestAnimationFrame / setTimeout / setInterval,
再每一格手動把虛擬時間推進 1/fps 秒、觸發到期的 callback, 並把 CSS / WAAPI 動畫的
currentTime 對齊到虛擬時間 → 截一張圖。如此 30fps 就是精準 30fps, 與真實機器速度無關。

mock 模式
---------
mock=True 時不開瀏覽器, 直接用 ffmpeg 的 lavfi testsrc 產一支合法 MP4 (時長正確)。
給 CI / 沒裝 Playwright 瀏覽器的環境跑 smoke test, 對齊專案各處的 mock 慣例。

依賴
----
- ffmpeg 在 PATH (專案各處 render 已假設)。
- playwright + 已安裝的 Chromium (見 requirements-optional.txt)。本執行環境已預裝。
"""
from __future__ import annotations

import logging
import os
import shutil
from core.ffmpeg import run_media_cmd
import tempfile
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# 自架者可用環境變數指定 Chromium 執行檔 (例如 playwright 版本與預裝瀏覽器不符時,
# 或想用系統 chromium)。沒設就用 playwright 自帶的 chromium。
_CHROMIUM_PATH_ENV = "EDUSTUDIO_CHROMIUM_PATH"

# 注入頁面的虛擬時鐘 shim。必須在頁面任何腳本之前執行 (add_init_script),
# 才能在第三方動畫庫抓到 rAF / Date 參考之前先把它們換掉。
# window.__advanceFrame(ms) 把虛擬時間往前推, 觸發到期 timer + rAF, 並對齊
# 所有 CSS / Web Animations 的 currentTime。回傳推進後的虛擬時間。
_VIRTUAL_CLOCK_JS = r"""
(() => {
  if (window.__eduVClockInstalled) return;
  window.__eduVClockInstalled = true;

  let now = 0;                       // 虛擬時間 (ms), 從 0 起算
  const RealDate = Date;

  // performance.now —— 多數動畫庫用它做時間基準
  try { window.performance.now = () => now; } catch (e) {}

  // Date.now / new Date() (無參數) 走虛擬時間; 帶參數的 new Date(x) 維持原樣
  function VDate(...args) {
    if (args.length === 0) return new RealDate(now);
    return new RealDate(...args);
  }
  VDate.now = () => now;
  VDate.parse = RealDate.parse;
  VDate.UTC = RealDate.UTC;
  VDate.prototype = RealDate.prototype;
  window.Date = VDate;

  // requestAnimationFrame 佇列 —— 每格手動 flush
  let rafs = [];
  let rafSeq = 0;
  window.requestAnimationFrame = (cb) => { const id = ++rafSeq; rafs.push([id, cb]); return id; };
  window.cancelAnimationFrame = (id) => { rafs = rafs.filter(([i]) => i !== id); };

  // setTimeout / setInterval —— 換成虛擬時間排程
  let timers = [];
  let timerSeq = 0;
  const realSetTimeout = window.setTimeout.bind(window);
  window.setTimeout = (fn, delay, ...args) => {
    const id = ++timerSeq;
    timers.push({ id, fn, due: now + (Number(delay) || 0), args, every: null });
    return id;
  };
  window.setInterval = (fn, delay, ...args) => {
    const id = ++timerSeq;
    const d = Math.max(1, Number(delay) || 0);
    timers.push({ id, fn, due: now + d, args, every: d });
    return id;
  };
  window.clearTimeout = (id) => { timers = timers.filter((t) => t.id !== id); };
  window.clearInterval = window.clearTimeout;

  window.__advanceFrame = (deltaMs) => {
    now += deltaMs;

    // 1) 到期 timer (含區間 timer 補幀), 設上限避免區間=0 之類的死迴圈
    for (let guard = 0; guard < 10000; guard++) {
      const due = timers
        .filter((t) => t.due <= now)
        .sort((a, b) => a.due - b.due);
      if (due.length === 0) break;
      const t = due[0];
      if (t.every == null) {
        timers = timers.filter((x) => x !== t);
      } else {
        t.due += t.every;
      }
      try { t.fn(...t.args); } catch (e) {}
    }

    // 2) requestAnimationFrame callback (本格快照後才推進, 故先收集再清空)
    const batch = rafs;
    rafs = [];
    for (const [, cb] of batch) {
      try { cb(now); } catch (e) {}
    }

    // 3) CSS / Web Animations / SMIL —— 暫停後把 currentTime 對齊虛擬時間
    try {
      const anims = (document.getAnimations ? document.getAnimations() : []);
      for (const a of anims) {
        try { a.pause(); a.currentTime = now; } catch (e) {}
      }
    } catch (e) {}

    return now;
  };
})();
"""


def _ensure_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise FileNotFoundError("ffmpeg 找不到, 請確認已安裝並在 PATH")
    return exe


def _resolve_source_url(source: str | Path) -> str:
    """把本機 .html 路徑轉成 file:// URL; http(s) URL 原樣回傳。"""
    s = str(source)
    parsed = urlparse(s)
    if parsed.scheme in ("http", "https"):
        return s
    if parsed.scheme == "file":
        return s
    p = Path(s)
    if not p.exists():
        raise FileNotFoundError(f"HTML 來源不存在: {s}")
    return p.resolve().as_uri()


def _render_mock(out_path: Path, *, duration: float, fps: int, width: int, height: int) -> Path:
    """不開瀏覽器, 用 ffmpeg lavfi 產一支合法 MP4 (時長正確)。給測試 / 無瀏覽器環境。"""
    ffmpeg = _ensure_ffmpeg()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg, "-y", "-loglevel", "error",
        "-f", "lavfi",
        "-i", f"testsrc=duration={duration}:size={width}x{height}:rate={fps}",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        str(out_path),
    ]
    run_media_cmd(cmd, step="ffmpeg mock render")
    logger.info("html_video mock render → %s (%.1fs)", out_path.name, duration)
    return out_path


def _capture_frames(
    source_url: str,
    frames_dir: Path,
    *,
    total_frames: int,
    fps: int,
    width: int,
    height: int,
    settle_ms: int,
    on_progress: Callable[[int], None] | None,
) -> None:
    """用 Playwright + 虛擬時鐘逐格截圖到 frames_dir/frame_000001.png ..."""
    from playwright.sync_api import sync_playwright

    delta = 1000.0 / fps
    launch_kwargs: dict = {"args": ["--no-sandbox", "--disable-gpu"]}
    exe = os.environ.get(_CHROMIUM_PATH_ENV)
    if exe:
        launch_kwargs["executable_path"] = exe
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_kwargs)
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            # shim 必須早於頁面腳本, 才能換掉 rAF / Date
            page.add_init_script(_VIRTUAL_CLOCK_JS)
            page.goto(source_url, wait_until="load")
            # 給字型 / 圖片 / 第一批 rAF 一點落定時間 (真實 ms, 非虛擬), 再開始定格
            if settle_ms > 0:
                page.wait_for_timeout(settle_ms)

            for i in range(total_frames):
                page.screenshot(path=str(frames_dir / f"frame_{i + 1:06d}.png"))
                # 截完本格才推進虛擬時間 → frame 1 = t0 初始狀態
                page.evaluate("(d) => window.__advanceFrame && window.__advanceFrame(d)", delta)
                if on_progress and total_frames > 0:
                    # 80% 配給截圖階段, 留 20% 給 ffmpeg 合成
                    on_progress(int((i + 1) / total_frames * 80))
        finally:
            browser.close()


def rasterize_svg(
    svg: str,
    out_path: str | Path,
    *,
    width: int,
    height: int,
    device_scale_factor: float = 1.0,
) -> Path:
    """把一段 SVG (或任意自含 HTML 片段) 用 Chromium 光柵化成 PNG。

    給「零 API 成本」的場景圖路線用: LLM / 人手寫的細節 SVG → PNG → 當漫畫 scene asset
    (Comic Core 的 asset 只收 PNG/JPG/WEBP)。字型 / 濾鏡 / 漸層由瀏覽器處理, 與 render_html_to_mp4
    共用同一顆 Chromium (EDUSTUDIO_CHROMIUM_PATH 可覆寫)。
    """
    from playwright.sync_api import sync_playwright

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    launch_kwargs: dict = {"args": ["--no-sandbox", "--disable-gpu"]}
    exe = os.environ.get(_CHROMIUM_PATH_ENV)
    if exe:
        launch_kwargs["executable_path"] = exe
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_kwargs)
        try:
            page = browser.new_page(
                viewport={"width": width, "height": height},
                device_scale_factor=device_scale_factor,
            )
            page.set_content(
                f"<!doctype html><html><body style='margin:0;width:{width}px;height:{height}px;"
                f"overflow:hidden;background:#000'>{svg}</body></html>",
                wait_until="load",
            )
            page.screenshot(path=str(out_path))
        finally:
            browser.close()
    return out_path


def render_html_to_mp4(
    source: str | Path,
    out_path: str | Path,
    *,
    duration: float,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
    settle_ms: int = 400,
    mock: bool = False,
    on_progress: Callable[[int], None] | None = None,
) -> Path:
    """把 HTML 動畫網頁渲成 MP4。

    Args:
        source: 本機 .html 檔路徑, 或 http(s):// URL。
        out_path: 輸出 .mp4 路徑。
        duration: 影片長度 (秒)。HTML 動畫沒有「結束」的概念, 由 caller 指定要錄多長。
        fps: 影格率 (預設 30)。
        width / height: 視窗 / 影片解析度 (預設 1920x1080)。
        settle_ms: 開錄前等頁面落定的真實毫秒 (字型/圖片/初次 layout)。
        mock: True 時跳過瀏覽器, 用 ffmpeg testsrc 產合法 MP4 (測試用)。
        on_progress: 進度 callback (0~100), 截圖佔 0~80, 合成佔 80~100。

    Returns:
        out_path (Path)。

    Raises:
        FileNotFoundError: ffmpeg 或本機 HTML 來源不存在。
        ValueError: duration / fps 不合法。
    """
    out_path = Path(out_path)
    if duration <= 0:
        raise ValueError(f"duration 必須 > 0, 收到 {duration}")
    if fps <= 0:
        raise ValueError(f"fps 必須 > 0, 收到 {fps}")

    if mock:
        return _render_mock(out_path, duration=duration, fps=fps, width=width, height=height)

    ffmpeg = _ensure_ffmpeg()
    source_url = _resolve_source_url(source)
    total_frames = max(1, int(round(duration * fps)))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="edu_html_frames_") as tmp:
        frames_dir = Path(tmp)
        logger.info(
            "html_video render 開始: %s → %s (%d frames @ %dfps, %dx%d)",
            source_url, out_path.name, total_frames, fps, width, height,
        )
        _capture_frames(
            source_url, frames_dir,
            total_frames=total_frames, fps=fps, width=width, height=height,
            settle_ms=settle_ms, on_progress=on_progress,
        )

        cmd = [
            ffmpeg, "-y", "-loglevel", "error",
            "-framerate", str(fps),
            "-i", str(frames_dir / "frame_%06d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            # 寬高補成偶數 (libx264 + yuv420p 要求), 任意解析度都安全
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            str(out_path),
        ]
        # 共用 runner(T3-3): timeout + returncode 檢查; 訊息維持「ffmpeg 合成失敗」
        run_media_cmd(cmd, step="ffmpeg 合成", text=False)

    if on_progress:
        on_progress(100)
    logger.info("html_video render 完成 → %s", out_path)
    return out_path
