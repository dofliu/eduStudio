#!/usr/bin/env python3
"""
app.py — 考卷檢討影片系統 Web UI

使用:
    python3 app.py <exam.json>
    # 預設網址 http://localhost:5000

功能:
- 列出考卷中所有題目 + 渲染狀態
- 逐題編輯每個 step 的 display / narration
- 單題觸發 pipeline 渲染
- 內嵌播放完成的影片
"""
import argparse
import json
import os
import re
import subprocess
import threading
import sys
from pathlib import Path
from datetime import datetime

from flask import Flask, request, jsonify, render_template_string, redirect, url_for, send_from_directory, abort

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB

BASE_DIR = Path(__file__).parent
EXAMS_DIR = BASE_DIR / "exams"
PDFS_DIR = BASE_DIR / "pdfs"
SLIDES_DIR = BASE_DIR / "slides"
SOLVE_SCRIPT = BASE_DIR / "solve.py"
SLIDE_INGEST_SCRIPT = BASE_DIR / "slide_ingest.py"
PUBLISH_SCRIPT = BASE_DIR / "publish.py"

# ------------------ Track A 棄用旗標 (PR-3i) ------------------
# Track A (這個 Flask app) 進入 v3.1 棄用準備期, 預設根路徑 redirect 到 Track B.
# 環境變數 KEEP_TRACK_A=1 可保留原行為 (給仍依賴 /upload 上傳 / 即時渲染進度頁的場景)。
KEEP_TRACK_A = os.environ.get("KEEP_TRACK_A", "").lower() in ("1", "true", "yes")
TRACK_B_URL = os.environ.get("TRACK_B_URL", "http://localhost:8000/app/")  # U-5: /ui 退場, 導 /app
TRACK_A_BANNER_HTML = f"""
<div style="background:#fef3c7;border-bottom:2px solid #f59e0b;padding:8px 16px;font-size:13px;color:#78350f;text-align:center">
  ⚠ <strong>Track A (Flask v1) 已進入棄用準備期 (v3.1)</strong> — 主要編輯流程已搬到
  <a href="{TRACK_B_URL}" style="color:#7c2d12;font-weight:600;text-decoration:underline">Track B (port 8000)</a>。
  本介面保留作 PDF 上傳 / 即時渲染進度等過渡功能, 預期於 v3.2 完全退場。
</div>
"""

# 全域狀態 (啟動時設定)
EXAM_PATH: Path | None = None     # 目前編輯中的 exam.json;None 代表未選
VIDEO_ROOT: Path | None = None    # 所有考卷影片的根目錄,例如 ./videos
RENDER_LOCK = threading.Lock()
RENDER_STATUS: dict = {}   # {pid: "idle" | "rendering" | "done" | "error"}
SOLVE_STATUS: dict = {}    # {stem: {"state": "solving"|"done"|"error", "msg": str, "source_type": "exam"|"slide"}}
PUBLISH_STATUS: dict = {}  # {f"{stem}/{pid}": {"state": "uploading"|"done"|"error", "msg": str, "result": {...}?}}


def current_exam_dir() -> Path:
    """當前編輯考卷對應的子目錄,例如 ./videos/real_exam/"""
    return VIDEO_ROOT / EXAM_PATH.stem


# ------------------ 啟動時的 migration / 設定 ------------------
# 把 repo root 散落的 exam JSONs 搬到 exams/ 集中管理。
# 判準:JSON 有 problems 這個 key (list) → 當作 exam
CONFIG_JSON_NAMES = {"tts_config.json", "pipeline_config.json", "pronunciation.json"}


def _looks_like_exam_json(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return isinstance(data, dict) and isinstance(data.get("problems"), list)


def migrate_root_exams() -> list[Path]:
    """啟動時掃 repo root 的 *.json,把 exam 類型的搬進 exams/。回傳搬移後的新路徑"""
    EXAMS_DIR.mkdir(exist_ok=True)
    moved: list[Path] = []
    for p in BASE_DIR.glob("*.json"):
        if p.name in CONFIG_JSON_NAMES:
            continue
        if not _looks_like_exam_json(p):
            continue
        dst = EXAMS_DIR / p.name
        if dst.exists():
            # 同名已存在,避免覆蓋;加時間戳
            dst = EXAMS_DIR / f"{p.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        p.rename(dst)
        moved.append(dst)
        print(f"[migrate] {p.name} -> {dst.relative_to(BASE_DIR)}")
    return moved


# ------------------ 檔名清理 ------------------
# 允許中文、英數、底線、橫線、空白;禁止路徑字元跟 Windows 保留字
_FNAME_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_WIN_RESERVED = {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)],
                 *[f"LPT{i}" for i in range(1, 10)]}


def sanitize_exam_name(name: str) -> str:
    name = name.strip()
    name = _FNAME_BAD.sub("", name)
    name = re.sub(r"\.\.+", "", name)
    name = name.strip(". ")   # 結尾點/空白在 Windows 會出事
    if name.upper() in _WIN_RESERVED:
        name = f"_{name}"
    return name[:80]

# ------------------ 聲音目錄 ------------------
# 渲染時用哪支聲音 = tts_config.json 的 edge.voice。UI 改選項就更新 json。
TTS_CONFIG_PATH = Path(__file__).parent / "tts_config.json"
VOICE_SAMPLE_DIR = Path(__file__).parent / "voices" / "samples"

# (voice id, 顯示名稱, 試聽檔名)
# 'f5:*' 開頭代表 F5-TTS 聲音複製 (本機推論, 用 voices/teacher_ref.wav)。
# 切換時 backend 會自動寫進 tts_config.json:
#   edge 系: backend=edge, edge.voice=<voice_id>
#   F5  系: backend=f5 (使用 tts_config.json 既有的 f5 區塊)
VOICES = [
    ("zh-TW-HsiaoChenNeural", "小陳 (台女,新聞風)",     "voice_tw_hsiaochen_F.mp3"),
    ("zh-TW-HsiaoYuNeural",   "小雨 (台女,較甜)",       "voice_tw_hsiaoyu_F.mp3"),
    ("zh-CN-YunxiNeural",     "雲希 (陸男,年輕)",       "voice_cn_yunxi_M.mp3"),
    ("zh-CN-YunyangNeural",   "雲揚 (陸男,主播穩)",     "voice_cn_yunyang_M.mp3"),
    ("zh-CN-XiaoxiaoNeural",  "曉曉 (陸女,大陸通用)",   "voice_cn_xiaoxiao_F.mp3"),
    ("f5:teacher",            "劉老師 (F5 聲音複製)",   "voice_f5_teacher_M.mp3"),
]
VOICE_IDS = {v[0] for v in VOICES}


def read_current_voice() -> str:
    """回傳目前 tts_config 對應的 voice id。"""
    if not TTS_CONFIG_PATH.exists():
        return VOICES[0][0]
    try:
        cfg = json.loads(TTS_CONFIG_PATH.read_text(encoding="utf-8"))
        if cfg.get("backend") == "f5":
            return "f5:teacher"
        return cfg.get("edge", {}).get("voice") or VOICES[0][0]
    except Exception:
        return VOICES[0][0]


def write_current_voice(voice_id: str):
    """切聲音 = 同時切 backend 跟對應的設定。"""
    if voice_id not in VOICE_IDS:
        return False
    cfg = {}
    if TTS_CONFIG_PATH.exists():
        cfg = json.loads(TTS_CONFIG_PATH.read_text(encoding="utf-8"))

    if voice_id.startswith("f5:"):
        cfg["backend"] = "f5"
        # f5 區塊 (ref_audio, ref_text, speed...) 維持不動, 由 tts_config.json 直接編
    else:
        cfg["backend"] = "edge"
        cfg.setdefault("edge", {})["voice"] = voice_id

    TTS_CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return True


def load_exam() -> dict:
    return json.loads(EXAM_PATH.read_text(encoding="utf-8"))


def save_exam(data: dict):
    EXAM_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_stem(stem: str) -> bool:
    return "/" not in stem and "\\" not in stem and ".." not in stem


def find_exam_path(stem: str) -> Path | None:
    if not _safe_stem(stem):
        return None
    p = EXAMS_DIR / f"{stem}.json"
    return p if p.exists() else None


def load_exam_by_stem(stem: str) -> dict | None:
    p = find_exam_path(stem)
    if not p:
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_exam_by_stem(stem: str, data: dict) -> bool:
    p = find_exam_path(stem)
    if not p:
        return False
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def get_problem_youtube(exam_data: dict, pid: str) -> dict | None:
    for prob in exam_data.get("problems", []):
        if prob.get("id") == pid:
            return prob.get("youtube")
    return None


def set_problem_youtube(stem: str, pid: str, youtube: dict) -> bool:
    """寫回 exam JSON 的 problem[i].youtube 欄位 (publish.py 上傳完成後 app.py 呼叫)。"""
    data = load_exam_by_stem(stem)
    if data is None:
        return False
    for prob in data.get("problems", []):
        if prob.get("id") == pid:
            prob["youtube"] = youtube
            save_exam_by_stem(stem, data)
            return True
    return False


def problem_status(pid: str) -> dict:
    mp4 = current_exam_dir() / f"{pid}.mp4"
    render_state = RENDER_STATUS.get(pid, "idle")
    return {
        "rendered": mp4.exists(),
        "mp4_size": mp4.stat().st_size if mp4.exists() else 0,
        "mp4_mtime": datetime.fromtimestamp(mp4.stat().st_mtime).strftime("%m/%d %H:%M") if mp4.exists() else "",
        "state": render_state,
    }


# ------------------ 模板 ------------------

BASE_CSS = """
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  * { box-sizing: border-box; }
  body {
    font-family: "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif;
    margin: 0; padding: 0; background: #f7f7f5; color: #222;
  }
  .container { max-width: 960px; margin: 0 auto; padding: 24px; }
  .container-wide { max-width: 1100px; margin: 0 auto; padding: 24px; }
  h1 { font-size: 22px; font-weight: 500; margin: 0; }
  h2 { font-size: 18px; font-weight: 500; margin: 0; }
  .muted { color: #888; font-size: 13px; }
  .tiny { font-size: 12px; color: #888; }
  .row { display: flex; align-items: center; gap: 12px; }
  .header-row { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 20px; }
  .card {
    background: white; border: 1px solid #e4e2dc; border-radius: 8px;
    padding: 14px 18px; margin-bottom: 12px;
  }
  .card:hover { border-color: #b5b3a9; }
  .btn {
    display: inline-block; padding: 7px 14px; border-radius: 6px;
    font-size: 13px; text-decoration: none; border: none; cursor: pointer;
    font-family: inherit;
  }
  .btn-primary { background: #185fa5; color: white; }
  .btn-primary:hover { background: #0c447c; }
  .btn-success { background: #0f6e56; color: white; }
  .btn-success:hover { background: #085041; }
  .btn-gray { background: #5f5e5a; color: white; }
  .btn-gray:hover { background: #444441; }
  .btn-link { background: transparent; color: #185fa5; padding: 4px 0; }
  .btn-link:hover { text-decoration: underline; }
  .tiny-btn {
    background: #f1efe8; border: 1px solid #d4d2cc; border-radius: 4px;
    font-size: 11px; cursor: pointer; padding: 2px 4px; margin-top: 4px;
  }
  .tiny-btn:hover { background: #e4e2dc; border-color: #b5b3a9; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; }

  .badge-done { background: #e1f5ee; color: #085041; }
  .badge-rendering { background: #faeeda; color: #633806; }
  .badge-draft { background: #f1efe8; color: #444441; }
  .banner {
    padding: 12px 16px; border-radius: 6px; margin-bottom: 16px;
    display: flex; justify-content: space-between; align-items: center;
  }
  .banner-success { background: #e1f5ee; border: 1px solid #9fe1cb; color: #085041; }
  .banner-warning { background: #faeeda; border: 1px solid #fac775; color: #633806; }
  .step-row {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 12px; border: 1px solid #e4e2dc; border-radius: 6px;
    background: white; margin-bottom: 10px;
  }
  .step-row:hover { border-color: #85b7eb; }
  .step-num { width: 30px; padding-top: 8px; text-align: center; font-size: 12px; color: #888; font-weight: 500; }
  .step-col { flex: 1; }
  textarea {
    width: 100%; padding: 8px; border: 1px solid #d3d1c7;
    border-radius: 4px; font-size: 13px; font-family: inherit;
    resize: vertical;
  }
  textarea:focus { outline: none; border-color: #378add; }
  .mono { font-family: "SF Mono", Menlo, Consolas, monospace; background: #eaf3de; }
  .problem-box { background: #f1efe8; padding: 14px; border-radius: 6px; margin-bottom: 16px; }
  .col-labels { display: flex; gap: 10px; font-size: 12px; color: #888; padding: 0 4px 4px; }
  .col-labels > :first-child { width: 30px; }
  .col-labels > :not(:first-child) { flex: 1; }
  .footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid #e4e2dc; font-size: 12px; color: #888; }
  a { color: #185fa5; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .problem-title { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
  .problem-body { font-size: 13px; color: #555; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .actions { display: flex; gap: 8px; margin-left: 12px; }
</style>
""" + TRACK_A_BANNER_HTML

VOICE_PICKER_HTML = """
<div style="background:white;border:1px solid #e4e2dc;border-radius:8px;padding:10px 14px;margin-bottom:16px;display:flex;align-items:center;gap:12px">
  <span style="font-size:13px;color:#555">🗣 聲音</span>
  <form method="POST" action="/set_voice" style="margin:0;flex:1;display:flex;align-items:center;gap:8px">
    <select name="voice" onchange="this.form.submit()" style="padding:5px 8px;border:1px solid #d3d1c7;border-radius:4px;font-size:13px;font-family:inherit;min-width:240px">
      {% for vid, label, _ in voices %}
        <option value="{{ vid }}" {% if vid == current_voice %}selected{% endif %}>{{ label }}</option>
      {% endfor %}
    </select>
    <noscript><button type="submit" class="btn btn-gray" style="padding:4px 10px">套用</button></noscript>
  </form>
  <audio controls src="/voice_sample/{{ current_voice }}" style="height:32px"></audio>
  <span class="tiny">試聽(下次渲染才生效)</span>
</div>
"""

INDEX_HTML = BASE_CSS + """
<div class="container">
  <div class="header-row">
    <div>
      <h1>{{ data.exam_title }}</h1>
      <div class="muted" style="margin-top:4px">{{ data.problems|length }} 題 · {{ exam_path }}</div>
    </div>
    <div style="display:flex;gap:8px">
      <a href="/exams" class="btn btn-gray">📄 考卷列表</a>
      <a href="/library" class="btn btn-gray">📚 Library</a>
      <form method="POST" action="/render_all" style="margin:0">
        <button class="btn btn-success">🎬 批次渲染全部</button>
      </form>
    </div>
  </div>
""" + VOICE_PICKER_HTML + """

  {% for p in data.problems %}
  {% set st = statuses[p.id] %}
  <div class="card" style="display:flex; align-items:center; justify-content:space-between">
    <div style="flex:1; min-width:0">
      <div class="problem-title">
        <strong>{{ p.number }}</strong>
        <span class="tiny">{{ p.score }} 分 · {{ p.steps|length }} 步驟</span>
        {% if st.state == "rendering" %}
          <span class="badge badge-rendering">渲染中…</span>
        {% elif st.rendered %}
          <span class="badge badge-done">✓ 已產生 ({{ (st.mp4_size / 1024 / 1024) | round(1) }} MB · {{ st.mp4_mtime }})</span>
        {% else %}
          <span class="badge badge-draft">待渲染</span>
        {% endif %}
      </div>
      <div class="problem-body">{{ p.problem }}</div>
    </div>
    <div class="actions">
      <a href="/edit/{{ p.id }}" class="btn btn-primary">編輯</a>
      {% if st.rendered %}
      <a href="/video/{{ p.id }}" target="_blank" class="btn btn-gray">▶ 觀看</a>
      {% endif %}
    </div>
  </div>
  {% endfor %}

  <div class="footer">
    工作流程:編輯 → 存檔 → 單題渲染 / 批次渲染 → 觀看或下載
  </div>
</div>
"""

EDIT_HTML = BASE_CSS + """
<div class="container-wide">
  <div class="header-row">
    <div>
      <a href="/" class="btn-link">← 回考卷</a>
      <h1 style="margin-top:6px">{{ prob.number }} <span class="muted" style="font-size:14px">({{ prob.score }} 分)</span></h1>
    </div>
    <div style="display:flex; gap:8px">
      <button form="editForm" type="submit" name="action" value="save" class="btn btn-primary">💾 儲存</button>
      <button form="editForm" type="submit" name="action" value="save_and_render" class="btn btn-success">🎬 儲存並渲染</button>
    </div>
  </div>
""" + VOICE_PICKER_HTML + """

  {% if status.rendered %}
  <div class="banner banner-success">
    <span>✓ 已產生影片 · {{ (status.mp4_size / 1024 / 1024) | round(1) }} MB · {{ status.mp4_mtime }}</span>
    <a href="/video/{{ prob.id }}" target="_blank">開啟影片 →</a>
  </div>
  {% endif %}

  {% if status.state == "rendering" %}
  <div class="banner banner-warning">
    ⏳ 渲染中,請稍後重新整理頁面…
  </div>
  {% endif %}

  <form id="editForm" method="POST" action="/save/{{ prob.id }}">
    <div class="problem-box">
      <div class="tiny">題目原文</div>
      <textarea name="problem" rows="2" style="margin-top:6px">{{ prob.problem }}</textarea>
    </div>

    <div class="col-labels">
      <span></span>
      <span>💬 display (黑板顯示)</span>
      <span>🗣 narration (旁白口語)</span>
    </div>

    {% for step in prob.steps %}
    <div class="step-row">
      <div class="step-num">
        #{{ loop.index }}
        <button type="submit" name="action" value="render_from_{{ loop.index0 }}" class="tiny-btn" title="從此步驟開始重新渲染">🎬</button>
      </div>
      {% if step.bg_type == "slide" and step.bg_image %}
      {# 簡報模式: 投影片縮圖, 點擊開大圖 #}
      <div style="flex:0 0 160px">
        <a href="/slide_image/{{ slide_stem }}/{{ step.bg_image.split('/')[-1] }}" target="_blank" title="點擊看大圖">
          <img src="/slide_image/{{ slide_stem }}/{{ step.bg_image.split('/')[-1] }}"
               style="width:160px;border:1px solid #d3d1c7;border-radius:4px;display:block">
        </a>
        <div class="tiny" style="margin-top:4px;text-align:center">
          {{ step.layout or "full" }}
        </div>
      </div>
      {% endif %}
      <div class="step-col">
        <textarea name="display_{{ loop.index0 }}" rows="2" class="mono">{{ step.display }}</textarea>
      </div>
      <div class="step-col">
        <textarea name="narration_{{ loop.index0 }}" rows="2">{{ step.narration }}</textarea>
      </div>
    </div>
    {% endfor %}

    <input type="hidden" name="step_count" value="{{ prob.steps|length }}"/>
  </form>

  <div class="footer">
    提示:display 是板書,簡潔即可(公式、關鍵數字)。narration 是口語旁白,自然一點、含停頓標點。
  </div>
</div>
"""

# ------------------ Routes ------------------

@app.route("/")
def index():
    # PR-3i: 預設 redirect 到 Track B (React UI), KEEP_TRACK_A=1 仍走原 Flask UI
    if not KEEP_TRACK_A:
        return redirect(TRACK_B_URL, code=302)
    if EXAM_PATH is None:
        return redirect(url_for("exams_list"))
    data = load_exam()
    statuses = {p["id"]: problem_status(p["id"]) for p in data["problems"]}
    return render_template_string(
        INDEX_HTML,
        data=data, statuses=statuses, exam_path=str(EXAM_PATH),
        voices=VOICES, current_voice=read_current_voice(),
    )


@app.route("/edit/<pid>")
def edit(pid):
    if EXAM_PATH is None: return redirect(url_for("exams_list"))
    data = load_exam()
    prob = next((p for p in data["problems"] if p["id"] == pid), None)
    if not prob:
        abort(404)
    return render_template_string(
        EDIT_HTML, prob=prob, status=problem_status(pid),
        voices=VOICES, current_voice=read_current_voice(),
        slide_stem=EXAM_PATH.stem,
    )


@app.route("/save/<pid>", methods=["POST"])
def save(pid):
    if EXAM_PATH is None: return redirect(url_for("exams_list"))
    data = load_exam()
    prob = next((p for p in data["problems"] if p["id"] == pid), None)
    if not prob:
        abort(404)
    prob["problem"] = request.form["problem"].strip()
    n = int(request.form["step_count"])
    existing_steps = prob.get("steps", [])
    new_steps = []
    for i in range(n):
        d = request.form.get(f"display_{i}", "").strip()
        nar = request.form.get(f"narration_{i}", "").strip()
        if d or nar:
            # 保留原 step 的其他欄位 (如 diagram_svg, _section, image) 避免表單送出時洗掉
            base = dict(existing_steps[i]) if i < len(existing_steps) and isinstance(existing_steps[i], dict) else {}
            base["display"] = d
            base["narration"] = nar
            new_steps.append(base)
    prob["steps"] = new_steps
    save_exam(data)

    # 根據按下的按鈕決定是否接著渲染
    action = request.form.get("action")
    if action == "save_and_render":
        return redirect(url_for("render", pid=pid))
    elif action and action.startswith("render_from_"):
        try:
            step_idx = int(action.replace("render_from_", ""))
            return redirect(url_for("render", pid=pid, step=step_idx))
        except ValueError:
            pass
    return redirect(url_for("edit", pid=pid))


@app.route("/render/<pid>", methods=["POST", "GET"])
def render(pid):
    if EXAM_PATH is None: return redirect(url_for("exams_list"))
    if RENDER_STATUS.get(pid) == "rendering":
        return redirect(url_for("edit", pid=pid))

    start_step = request.args.get("step")
    RENDER_STATUS[pid] = "rendering"

    def worker():
        try:
            with RENDER_LOCK:  # 避免 pipeline.py 的 /home/claude/work 被多個任務搶用
                cmd = [
                    sys.executable, str(Path(__file__).parent / "batch.py"),
                    str(EXAM_PATH), str(VIDEO_ROOT), "--only", pid
                ]
                if start_step is not None:
                    cmd += ["--step", start_step]
                
                subprocess.run(cmd, check=True)
            RENDER_STATUS[pid] = "done"
        except Exception as e:
            print(f"[render {pid}] 失敗:{e}")
            RENDER_STATUS[pid] = "error"

    threading.Thread(target=worker, daemon=True).start()
    return redirect(url_for("edit", pid=pid))


@app.route("/render_all", methods=["POST"])
def render_all():
    if EXAM_PATH is None: return redirect(url_for("exams_list"))
    data = load_exam()
    for p in data["problems"]:
        RENDER_STATUS[p["id"]] = "rendering"

    def worker():
        try:
            with RENDER_LOCK:
                subprocess.run(
                    [sys.executable, str(Path(__file__).parent / "batch.py"),
                     str(EXAM_PATH), str(VIDEO_ROOT)],
                    check=True,
                )
            for p in data["problems"]:
                RENDER_STATUS[p["id"]] = "done"
        except Exception as e:
            print(f"[render_all] 失敗:{e}")
            for p in data["problems"]:
                RENDER_STATUS[p["id"]] = "error"

    threading.Thread(target=worker, daemon=True).start()
    return redirect(url_for("index"))


@app.route("/video/<pid>")
def video(pid):
    return send_from_directory(current_exam_dir(), f"{pid}.mp4")


@app.route("/set_voice", methods=["POST"])
def set_voice():
    voice = request.form.get("voice", "")
    write_current_voice(voice)
    return redirect(request.referrer or url_for("index"))


@app.route("/voice_sample/<voice_id>")
def voice_sample(voice_id):
    """試聽:回傳該 voice 的預先錄好樣本 mp3"""
    entry = next((v for v in VOICES if v[0] == voice_id), None)
    if not entry:
        abort(404)
    fname = entry[2]
    if not (VOICE_SAMPLE_DIR / fname).exists():
        abort(404)
    return send_from_directory(VOICE_SAMPLE_DIR, fname)


@app.route("/slide_image/<stem>/<filename>")
def slide_image(stem, filename):
    """供編輯頁顯示 slide 縮圖。嚴格檢查路徑避免目錄穿越。"""
    if not _safe_stem(stem) or "/" in filename or "\\" in filename or ".." in filename:
        abort(400)
    folder = SLIDES_DIR / stem
    if not folder.is_dir():
        abort(404)
    target = folder / filename
    if not target.exists() or target.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        abort(404)
    return send_from_directory(folder, filename)


# ------------------ Exams 管理 ------------------

def _scan_exams() -> list[dict]:
    """列出 exams/ 裡所有 exam JSON"""
    EXAMS_DIR.mkdir(exist_ok=True)
    items = []
    for p in sorted(EXAMS_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        title = data.get("exam_title") or p.stem
        n_problems = len(data.get("problems", []))
        exam_video_dir = VIDEO_ROOT / p.stem
        n_videos = len(list(exam_video_dir.glob("*.mp4"))) if exam_video_dir.exists() else 0
        items.append({
            "stem": p.stem,
            "title": title,
            "problems": n_problems,
            "videos": n_videos,
            "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            "is_current": EXAM_PATH is not None and p.resolve() == EXAM_PATH.resolve(),
        })
    return items


EXAMS_HTML = BASE_CSS + """
<div class="container-wide">
  <div class="header-row">
    <div>
      <h1>📄 考卷列表</h1>
      <div class="muted" style="margin-top:4px">{{ items|length }} 份 · 位置:{{ exams_dir }}</div>
    </div>
    <div style="display:flex;gap:8px">
      <a href="/library" class="btn btn-gray">📚 Library</a>
      <a href="/upload" class="btn btn-success">⬆ 上傳新 PDF</a>
    </div>
  </div>

  {% if not items %}
  <div class="card"><span class="muted">還沒有考卷,按上方「上傳新 PDF」開始,或放一份 JSON 到 <code>exams/</code>。</span></div>
  {% endif %}

  {% for e in items %}
  <div class="card" style="display:flex;align-items:center;justify-content:space-between">
    <div style="flex:1;min-width:0">
      <div class="problem-title">
        <strong>{{ e.title }}</strong>
        <span class="tiny">{{ e.stem }}.json · {{ e.problems }} 題 · {{ e.videos }} 支影片 · {{ e.mtime }}</span>
        {% if e.is_current %}<span class="badge badge-done">編輯中</span>{% endif %}
      </div>
    </div>
    <div class="actions" style="display:flex;gap:8px;align-items:center">
      <a href="/switch/{{ e.stem }}" class="btn btn-primary">進入編輯</a>
      <form method="POST" action="/delete_exam_json/{{ e.stem }}" onsubmit="return confirm('確定要刪除此考卷 JSON 嗎？(注意：不會刪除影片資料夾)')">
        <button type="submit" class="tiny-btn" style="color:#a52a2a;padding:6px 10px">🗑</button>
      </form>
    </div>
  </div>
  {% endfor %}
</div>
"""


UPLOAD_HTML = BASE_CSS + """
<div class="container-wide">
  <div class="header-row">
    <div>
      <a href="/exams" class="btn-link">← 回考卷列表</a>
      <h1 style="margin-top:6px">⬆ 上傳 PDF</h1>
      <div class="muted" style="margin-top:4px">考卷會逐題解;簡報會逐張產旁白並切章節。</div>
    </div>
  </div>

  {% if error %}
  <div class="banner banner-warning">⚠ {{ error }}</div>
  {% endif %}

  <div class="card">
    <form method="POST" action="/upload" enctype="multipart/form-data">
      <div style="margin-bottom:14px">
        <label class="muted" style="display:block;margin-bottom:6px">PDF 類型</label>
        <label style="display:flex;align-items:flex-start;gap:8px;font-size:13px;margin-bottom:6px;cursor:pointer">
          <input type="radio" name="source_type" value="exam" checked style="margin-top:3px">
          <span><strong>考卷 / 試題</strong> — 走 solve.py,Gemini 逐題產解題步驟</span>
        </label>
        <label style="display:flex;align-items:flex-start;gap:8px;font-size:13px;cursor:pointer">
          <input type="radio" name="source_type" value="slide" style="margin-top:3px">
          <span><strong>簡報 / 講義</strong> — 走 slide_ingest.py,逐張投影片產旁白並自動切章節</span>
        </label>
      </div>
      <div style="margin-bottom:14px">
        <label class="muted" style="display:block;margin-bottom:4px">PDF 檔</label>
        <input type="file" name="pdf" accept="application/pdf" required
               style="padding:6px;border:1px solid #d3d1c7;border-radius:4px;width:100%">
      </div>
      <div style="margin-bottom:14px">
        <label class="muted" style="display:block;margin-bottom:4px">名稱 (存檔名,支援中文;空白=用 PDF 檔名)</label>
        <input type="text" name="exam_name" maxlength="80" placeholder="例:114-02 靜力學期中 / 第8章 字串處理"
               style="padding:6px 8px;border:1px solid #d3d1c7;border-radius:4px;width:100%;font-family:inherit">
      </div>
      <div style="margin-bottom:14px">
        <label style="display:flex;align-items:center;gap:6px;font-size:13px;color:#555">
          <input type="checkbox" name="mock" value="1">
          Mock 模式 — 不呼叫 Gemini,只產佔位 JSON(測試用,省 API 費用)
        </label>
      </div>
      <button type="submit" class="btn btn-success">上傳並解析</button>
    </form>
  </div>

  <div class="footer">
    提示:考卷 30~60 秒(視題目數);簡報每頁 ~3 秒(30 頁約 1.5~2 分鐘)。Mock 模式幾秒就好。
  </div>
</div>
"""


SOLVE_PROGRESS_HTML = BASE_CSS + """
<div class="container-wide">
  <h1>🧠 {{ source_label }} 解析中…</h1>
  <div class="card">
    <div style="font-size:14px">名稱:<strong>{{ stem }}</strong></div>
    <div id="state" class="muted" style="margin-top:6px">狀態:<span id="s">solving</span></div>
    <div id="msg" class="tiny" style="margin-top:4px;color:#633806"></div>
  </div>
  <div class="muted" style="margin-top:8px">{{ hint }}</div>
  <script>
    const stem = {{ stem|tojson }};
    async function poll() {
      try {
        const r = await fetch('/solve_status/' + encodeURIComponent(stem));
        const j = await r.json();
        document.getElementById('s').textContent = j.state;
        if (j.msg) document.getElementById('msg').textContent = j.msg;
        if (j.state === 'done') { window.location = '/switch/' + encodeURIComponent(stem); return; }
        if (j.state === 'error') return;
      } catch (e) {}
      setTimeout(poll, 2000);
    }
    poll();
  </script>
</div>
"""


@app.route("/exams")
def exams_list():
    return render_template_string(
        EXAMS_HTML, items=_scan_exams(), exams_dir=str(EXAMS_DIR)
    )


@app.route("/switch/<stem>")
def switch_exam(stem):
    global EXAM_PATH
    target = EXAMS_DIR / f"{stem}.json"
    if not target.exists():
        abort(404)
    EXAM_PATH = target.resolve()
    current_exam_dir().mkdir(parents=True, exist_ok=True)
    RENDER_STATUS.clear()
    return redirect(url_for("index"))


@app.route("/delete_exam_json/<stem>", methods=["POST"])
def delete_exam_json(stem):
    global EXAM_PATH
    if "/" in stem or ".." in stem:
        abort(400)
    target = EXAMS_DIR / f"{stem}.json"
    if target.exists():
        if EXAM_PATH and target.resolve() == EXAM_PATH.resolve():
            EXAM_PATH = None
        target.unlink()
    return redirect(url_for("exams_list"))


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "GET":
        return render_template_string(UPLOAD_HTML, error=None)

    # POST
    f = request.files.get("pdf")
    if not f or not f.filename:
        return render_template_string(UPLOAD_HTML, error="沒有選到 PDF 檔")
    if not f.filename.lower().endswith(".pdf"):
        return render_template_string(UPLOAD_HTML, error="只接受 .pdf")

    raw_name = (request.form.get("exam_name") or "").strip()
    if not raw_name:
        raw_name = Path(f.filename).stem
    stem = sanitize_exam_name(raw_name)
    if not stem:
        return render_template_string(UPLOAD_HTML, error="考卷名稱清理後空白,改一個")

    PDFS_DIR.mkdir(exist_ok=True)
    EXAMS_DIR.mkdir(exist_ok=True)

    pdf_path = PDFS_DIR / f"{stem}.pdf"
    json_path = EXAMS_DIR / f"{stem}.json"
    if json_path.exists():
        return render_template_string(
            UPLOAD_HTML,
            error=f"'{stem}.json' 已存在,請改名或先從考卷列表刪掉舊的",
        )

    f.save(str(pdf_path))
    use_mock = request.form.get("mock") == "1"
    source_type = request.form.get("source_type", "exam")
    if source_type not in {"exam", "slide"}:
        source_type = "exam"

    is_slide = source_type == "slide"
    script = SLIDE_INGEST_SCRIPT if is_slide else SOLVE_SCRIPT
    label = "簡報 ingest" if is_slide else "考卷解析"
    SOLVE_STATUS[stem] = {"state": "solving", "msg": f"啟動 {script.name}…",
                           "source_type": source_type}

    def worker():
        # solve.py 和 slide_ingest.py 都吃 (pdf, json) 的 positional 參數
        cmd = [sys.executable, str(script), str(pdf_path), str(json_path)]
        if use_mock:
            cmd.append("--mock")
        try:
            r = subprocess.run(cmd, capture_output=True, encoding="utf-8",
                               errors="replace", timeout=1800)
            if r.returncode == 0 and json_path.exists():
                SOLVE_STATUS[stem] = {"state": "done", "msg": "完成",
                                       "source_type": source_type}
            else:
                tail = (r.stderr or r.stdout or "")[-300:]
                SOLVE_STATUS[stem] = {"state": "error",
                                       "msg": tail.strip() or f"{script.name} 失敗",
                                       "source_type": source_type}
        except Exception as e:
            SOLVE_STATUS[stem] = {"state": "error", "msg": str(e),
                                   "source_type": source_type}

    threading.Thread(target=worker, daemon=True).start()
    hint = (
        "投影片每頁 ~3 秒, 30 頁約 1.5~2 分鐘, 完成會自動跳轉。"
        if is_slide
        else "約 30~60 秒(Mock 模式快很多), 完成會自動跳轉。"
    )
    return render_template_string(
        SOLVE_PROGRESS_HTML, stem=stem, source_label=label, hint=hint,
    )


@app.route("/solve_status/<stem>")
def solve_status(stem):
    return jsonify(SOLVE_STATUS.get(stem, {"state": "unknown", "msg": ""}))


# ------------------ Library (跨考卷影片瀏覽) ------------------

def _scan_library() -> list[dict]:
    """掃 VIDEO_ROOT 底下所有子資料夾,回傳每個考卷的影片清單(附帶 youtube 上傳狀態)。"""
    exams = []
    if not VIDEO_ROOT.exists():
        return exams
    for sub in sorted(VIDEO_ROOT.iterdir()):
        if not sub.is_dir():
            continue
        mp4s = sorted(sub.glob("*.mp4"))
        if not mp4s:
            continue
        # 讀對應的 exam JSON 取 youtube 狀態 (可能不存在; 例如手動丟進 videos/ 的影片)
        exam_data = load_exam_by_stem(sub.name)
        items = []
        total = 0
        for m in mp4s:
            size = m.stat().st_size
            total += size
            yt = get_problem_youtube(exam_data, m.stem) if exam_data else None
            publish_state = PUBLISH_STATUS.get(f"{sub.name}/{m.stem}")
            items.append({
                "name": m.name,
                "stem": m.stem,
                "size_mb": round(size / 1024 / 1024, 1),
                "mtime": datetime.fromtimestamp(m.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                "has_srt": (sub / f"{m.stem}.srt").exists(),
                "youtube": yt,
                "publish_state": (publish_state or {}).get("state"),
            })
        exams.append({
            "exam_stem": sub.name,
            "video_count": len(items),
            "total_mb": round(total / 1024 / 1024, 1),
            "is_current": EXAM_PATH is not None and sub.name == EXAM_PATH.stem,
            "has_exam_json": exam_data is not None,
            "items": items,
        })
    return exams


LIBRARY_HTML = BASE_CSS + """
<div class="container-wide">
  <div class="header-row">
    <div>
      <a href="/" class="btn-link">← 回考卷</a>
      <h1 style="margin-top:6px">📚 影片 Library</h1>
      <div class="muted" style="margin-top:4px">根目錄:{{ root }}</div>
    </div>
  </div>

  {% if not exams %}
  <div class="card"><span class="muted">還沒有任何已渲染的影片。先回去跑批次渲染。</span></div>
  {% endif %}

  {% for e in exams %}
  <div class="card">
    <div class="problem-title" style="margin-bottom:10px; display:flex; justify-content:space-between; align-items:center">
      <div>
        <strong>{{ e.exam_stem }}</strong>
        <span class="tiny">{{ e.video_count }} 支 · {{ e.total_mb }} MB</span>
        {% if e.is_current %}<span class="badge badge-done">目前編輯中</span>{% endif %}
      </div>
      <form method="POST" action="/library/delete_exam/{{ e.exam_stem }}" onsubmit="return confirm('確定要刪除「{{ e.exam_stem }}」資料夾下的所有影片嗎？')">
        <button type="submit" class="tiny-btn" style="color:#a52a2a">🗑 刪除全部</button>
      </form>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="background:#f1efe8;text-align:left">
          <th style="padding:6px 8px">檔名</th>
          <th style="padding:6px 8px;width:90px">大小</th>
          <th style="padding:6px 8px;width:140px">修改時間</th>
          <th style="padding:6px 8px;width:60px">SRT</th>
          <th style="padding:6px 8px;width:120px">YouTube</th>
          <th style="padding:6px 8px;width:200px">動作</th>
        </tr>
      </thead>
      <tbody>
        {% for it in e['items'] %}
        <tr style="border-top:1px solid #eeece3">
          <td class="mono" style="padding:6px 8px">{{ it.name }}</td>
          <td style="padding:6px 8px">{{ it.size_mb }} MB</td>
          <td style="padding:6px 8px">{{ it.mtime }}</td>
          <td style="padding:6px 8px">{% if it.has_srt %}✓{% else %}—{% endif %}</td>
          <td style="padding:6px 8px">
            {% if it.youtube and it.youtube.video_id %}
              <a href="{{ it.youtube.url }}" target="_blank" class="badge badge-done"
                 title="已上傳 ({{ it.youtube.privacy }})">📺 {{ it.youtube.privacy }}</a>
            {% elif it.publish_state == 'uploading' %}
              <span class="badge badge-rendering">⬆ 上傳中…</span>
            {% else %}
              <span class="tiny" style="color:#aaa">—</span>
            {% endif %}
          </td>
          <td style="padding:6px 8px">
            <a class="btn btn-gray" href="/library/file/{{ e.exam_stem }}/{{ it.name }}" target="_blank">▶</a>
            <a class="btn btn-link" href="/library/file/{{ e.exam_stem }}/{{ it.name }}" download title="下載">⬇</a>
            {% if e.has_exam_json %}
              {% if it.youtube and it.youtube.video_id %}
                <a class="btn btn-link" href="/upload_review/{{ e.exam_stem }}/{{ it.stem }}" title="重新上傳 / 改設定">↻</a>
              {% else %}
                <a class="btn btn-success" href="/upload_review/{{ e.exam_stem }}/{{ it.stem }}" title="上傳到 YouTube">📺</a>
              {% endif %}
            {% endif %}
            <form method="POST" action="/library/delete_file/{{ e.exam_stem }}/{{ it.name }}" style="display:inline" onsubmit="return confirm('刪除 {{ it.name }}?')">
              <button type="submit" class="tiny-btn" style="color:#a52a2a;border:none;background:none;padding:0;margin:0;margin-left:8px" title="刪除">🗑</button>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% endfor %}

  <div class="footer">
    想編輯非「目前」考卷?重啟 Flask:<code>python app.py &lt;那份.json&gt;</code>
  </div>
</div>
"""


@app.route("/library")
def library():
    return render_template_string(
        LIBRARY_HTML, exams=_scan_library(), root=str(VIDEO_ROOT)
    )


@app.route("/library/file/<exam_stem>/<filename>")
def library_file(exam_stem, filename):
    """供 library 頁面播放/下載影片跟字幕。嚴格檢查路徑避免目錄穿越"""
    # 禁止 path traversal
    if "/" in exam_stem or ".." in exam_stem or "/" in filename or ".." in filename:
        abort(400)
    folder = VIDEO_ROOT / exam_stem
    if not folder.is_dir():
        abort(404)
    target = folder / filename
    if not target.exists() or target.suffix.lower() not in {".mp4", ".srt"}:
        abort(404)
    return send_from_directory(folder, filename)


@app.route("/library/delete_exam/<exam_stem>", methods=["POST"])
def library_delete_exam(exam_stem):
    if "/" in exam_stem or ".." in exam_stem:
        abort(400)
    folder = VIDEO_ROOT / exam_stem
    if folder.is_dir():
        import shutil
        shutil.rmtree(folder)
    return redirect(url_for("library"))


@app.route("/library/delete_file/<exam_stem>/<filename>", methods=["POST"])
def library_delete_file(exam_stem, filename):
    if "/" in exam_stem or ".." in exam_stem or "/" in filename or ".." in filename:
        abort(400)
    folder = VIDEO_ROOT / exam_stem
    target = folder / filename
    if target.exists() and target.suffix.lower() == ".mp4":
        target.unlink()
        # 同時刪除配套的 srt
        srt = target.with_suffix(".srt")
        if srt.exists():
            srt.unlink()
    return redirect(url_for("library"))


# ------------------ YouTube 上傳 ------------------

UPLOAD_REVIEW_HTML = BASE_CSS + """
<div class="container-wide">
  <div class="header-row">
    <div>
      <a href="/library" class="btn-link">← 回 Library</a>
      <h1 style="margin-top:6px">📺 上傳審查 — {{ exam_stem }} / {{ pid }}</h1>
      <div class="muted" style="margin-top:4px">
        確認標題說明後送出, 上傳完成會自動回寫到 exam.json
      </div>
    </div>
  </div>

  {% if existing %}
  <div class="banner banner-warning">
    ⚠ 此影片已上傳過 (<a href="{{ existing.url }}" target="_blank">{{ existing.url }}</a>,
    {{ existing.privacy }})。再次送出會建立新的 YouTube 影片(舊的不會自動刪)。
  </div>
  {% endif %}

  <div style="display:flex;gap:20px;align-items:flex-start">
    <div style="flex:1;min-width:0">
      <video controls preload="metadata" style="width:100%;border-radius:6px;background:#000"
             src="/library/file/{{ exam_stem }}/{{ pid }}.mp4"></video>
      <div class="tiny" style="margin-top:6px;color:#888">
        檔案: {{ pid }}.mp4 · {{ size_mb }} MB · 字幕: {% if has_srt %}✓ 會一併上傳{% else %}—{% endif %}
      </div>
    </div>

    <div style="flex:1.2;min-width:0">
      <form method="POST" action="/upload_to_youtube/{{ exam_stem }}/{{ pid }}">
        <div style="margin-bottom:12px">
          <label class="muted" style="display:block;margin-bottom:4px">標題</label>
          <input type="text" name="title" required value="{{ default_title }}"
                 maxlength="100"
                 style="padding:6px 8px;border:1px solid #d3d1c7;border-radius:4px;width:100%;font-family:inherit">
        </div>
        <div style="margin-bottom:12px">
          <label class="muted" style="display:block;margin-bottom:4px">說明</label>
          <textarea name="description" rows="6"
                    style="padding:8px;border:1px solid #d3d1c7;border-radius:4px;width:100%;font-family:inherit;font-size:13px;resize:vertical">{{ default_description }}</textarea>
        </div>
        <div style="margin-bottom:12px">
          <label class="muted" style="display:block;margin-bottom:4px">標籤(逗號分隔)</label>
          <input type="text" name="tags" value="{{ default_tags }}"
                 style="padding:6px 8px;border:1px solid #d3d1c7;border-radius:4px;width:100%;font-family:inherit">
        </div>
        <div style="margin-bottom:14px">
          <label class="muted" style="display:block;margin-bottom:4px">隱私</label>
          <label style="display:inline-flex;align-items:center;gap:4px;margin-right:14px;font-size:13px">
            <input type="radio" name="privacy" value="unlisted" checked> 不公開
          </label>
          <label style="display:inline-flex;align-items:center;gap:4px;margin-right:14px;font-size:13px">
            <input type="radio" name="privacy" value="public"> 公開
          </label>
          <label style="display:inline-flex;align-items:center;gap:4px;font-size:13px">
            <input type="radio" name="privacy" value="private"> 私人
          </label>
        </div>
        <button type="submit" class="btn btn-success">📺 上傳到 YouTube</button>
        <a href="/library" class="btn btn-gray" style="margin-left:8px">取消</a>
      </form>
    </div>
  </div>

  <div class="footer">
    YouTube quota: 一次上傳 ~1,600 units, 每日上限 10,000(約 6 支)。
    若是首次跳出 OAuth 同意頁, 請在伺服器端的瀏覽器完成授權。
  </div>
</div>
"""

UPLOAD_PROGRESS_HTML = BASE_CSS + """
<div class="container-wide">
  <h1>📺 上傳中…</h1>
  <div class="card">
    <div style="font-size:14px">{{ exam_stem }} / {{ pid }}</div>
    <div class="muted" style="margin-top:6px">
      狀態:<span id="s">uploading</span>
    </div>
    <div id="msg" class="tiny" style="margin-top:6px;color:#444"></div>
    <div id="result" style="margin-top:10px"></div>
  </div>
  <div class="muted" style="margin-top:10px">
    上傳大小視 MP4 而定, 一般 10 MB 約幾秒~10 秒。完成會自動跳轉。
  </div>
  <script>
    const stem = {{ exam_stem|tojson }};
    const pid = {{ pid|tojson }};
    async function poll() {
      try {
        const r = await fetch('/youtube_status/' + encodeURIComponent(stem) + '/' + encodeURIComponent(pid));
        const j = await r.json();
        document.getElementById('s').textContent = j.state || '?';
        if (j.msg) document.getElementById('msg').textContent = j.msg;
        if (j.state === 'done' && j.result && j.result.url) {
          document.getElementById('result').innerHTML =
            '<a class="btn btn-success" href="' + j.result.url + '" target="_blank">✓ 觀看 YouTube 影片 ↗</a>' +
            ' <a class="btn btn-gray" href="/library">回 Library</a>';
          return;
        }
        if (j.state === 'error') {
          document.getElementById('result').innerHTML =
            '<a class="btn btn-gray" href="/library">回 Library</a>';
          return;
        }
      } catch (e) {}
      setTimeout(poll, 2000);
    }
    poll();
  </script>
</div>
"""


def _build_default_review(exam_data: dict, pid: str) -> dict:
    """準備上傳審查頁的預設值。"""
    exam_title = exam_data.get("exam_title", "")
    prob = next((p for p in exam_data.get("problems", []) if p.get("id") == pid), None)
    if not prob:
        return {
            "default_title": pid,
            "default_description": "",
            "default_tags": "",
            "existing": None,
        }
    number = prob.get("number", "")
    problem_text = prob.get("problem", "")
    title = f"{exam_title} {number} 解析" if exam_title and number else (
        exam_title or number or pid
    )
    desc_lines = []
    if problem_text:
        desc_lines.append(problem_text)
    desc_lines.append("\n— DOF Lab · 自動生成解說影片")
    return {
        "default_title": title[:100],
        "default_description": "\n".join(desc_lines),
        "default_tags": "",
        "existing": prob.get("youtube"),
    }


@app.route("/upload_review/<exam_stem>/<pid>")
def upload_review(exam_stem, pid):
    if not _safe_stem(exam_stem) or not _safe_stem(pid):
        abort(400)
    folder = VIDEO_ROOT / exam_stem
    mp4 = folder / f"{pid}.mp4"
    if not mp4.exists():
        abort(404)
    exam_data = load_exam_by_stem(exam_stem)
    if exam_data is None:
        abort(404)
    defaults = _build_default_review(exam_data, pid)
    return render_template_string(
        UPLOAD_REVIEW_HTML,
        exam_stem=exam_stem, pid=pid,
        size_mb=round(mp4.stat().st_size / 1024 / 1024, 1),
        has_srt=(folder / f"{pid}.srt").exists(),
        **defaults,
    )


@app.route("/upload_to_youtube/<exam_stem>/<pid>", methods=["POST"])
def upload_to_youtube(exam_stem, pid):
    if not _safe_stem(exam_stem) or not _safe_stem(pid):
        abort(400)
    folder = VIDEO_ROOT / exam_stem
    mp4 = folder / f"{pid}.mp4"
    if not mp4.exists():
        abort(404)

    title = request.form.get("title", "").strip() or pid
    description = request.form.get("description", "").strip()
    tags = request.form.get("tags", "").strip()
    privacy = request.form.get("privacy", "unlisted")
    if privacy not in {"unlisted", "public", "private"}:
        privacy = "unlisted"

    key = f"{exam_stem}/{pid}"
    if PUBLISH_STATUS.get(key, {}).get("state") == "uploading":
        # 同一支正在上傳中, 直接導去進度頁不重啟
        return redirect(url_for("upload_review", exam_stem=exam_stem, pid=pid))

    out_json = folder / f"{pid}.youtube.json"
    if out_json.exists():
        out_json.unlink()  # 清舊結果
    PUBLISH_STATUS[key] = {"state": "uploading", "msg": "啟動 publish.py…", "result": None}

    def worker():
        cmd = [
            sys.executable, str(PUBLISH_SCRIPT),
            "--video", str(mp4),
            "--title", title,
            "--description", description,
            "--tags", tags,
            "--privacy", privacy,
            "--out-json", str(out_json),
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, encoding="utf-8",
                               errors="replace", timeout=1800)
            if out_json.exists():
                try:
                    result = json.loads(out_json.read_text(encoding="utf-8"))
                except Exception:
                    result = None
            else:
                result = None

            if r.returncode == 0 and result and result.get("video_id"):
                PUBLISH_STATUS[key] = {
                    "state": "done", "msg": "完成", "result": result,
                }
                # 寫回 exam.json
                set_problem_youtube(exam_stem, pid, result)
            else:
                tail = (r.stderr or r.stdout or "")[-400:]
                PUBLISH_STATUS[key] = {
                    "state": "error",
                    "msg": tail.strip() or "publish.py 失敗",
                    "result": result,
                }
        except Exception as e:
            PUBLISH_STATUS[key] = {"state": "error", "msg": str(e), "result": None}

    threading.Thread(target=worker, daemon=True).start()
    return render_template_string(
        UPLOAD_PROGRESS_HTML, exam_stem=exam_stem, pid=pid,
    )


@app.route("/youtube_status/<exam_stem>/<pid>")
def youtube_status(exam_stem, pid):
    if not _safe_stem(exam_stem) or not _safe_stem(pid):
        abort(400)
    return jsonify(PUBLISH_STATUS.get(f"{exam_stem}/{pid}",
                                       {"state": "unknown", "msg": ""}))


@app.route("/api/status")
def api_status():
    if EXAM_PATH is None:
        return jsonify({"error": "No exam selected"}), 400
    data = load_exam()
    return jsonify({p["id"]: problem_status(p["id"]) for p in data["problems"]})


# ------------------ Main ------------------

def main():
    from core.runtime import setup_utf8_stdout
    setup_utf8_stdout()
    global EXAM_PATH, VIDEO_ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("exam_json", nargs="?", default=None,
                    help="選填:指定啟動時預開的 exam.json;省略則停在考卷列表頁")
    ap.add_argument("--video-dir", default="./videos",
                    help="影片輸出根目錄 (實際輸出至 <video-dir>/<exam_stem>/)")
    ap.add_argument("--port", type=int, default=5000)
    args = ap.parse_args()

    VIDEO_ROOT = Path(args.video_dir).resolve()
    VIDEO_ROOT.mkdir(parents=True, exist_ok=True)
    EXAMS_DIR.mkdir(exist_ok=True)
    PDFS_DIR.mkdir(exist_ok=True)

    moved = migrate_root_exams()
    if moved:
        print(f"📦 遷移 {len(moved)} 份 exam JSON 到 exams/")

    # 解析啟動參數;若給的路徑不存在,嘗試當成 exams/<stem>.json
    if args.exam_json:
        cand = Path(args.exam_json)
        if not cand.exists():
            cand = EXAMS_DIR / cand.name
        if not cand.exists():
            sys.exit(f"❌ 找不到 {args.exam_json}(也不在 exams/ 裡)")
        EXAM_PATH = cand.resolve()
        current_exam_dir().mkdir(parents=True, exist_ok=True)
        print(f"📖 預開考卷: {EXAM_PATH}")
    else:
        print(f"📖 未指定考卷,將從考卷列表開始(/exams)")

    print(f"🎬 影片根目錄: {VIDEO_ROOT}")
    print(f"🌐 Web UI: http://localhost:{args.port}")

    # PR-3i: Track A 棄用準備 banner
    print()
    print("=" * 70)
    if KEEP_TRACK_A:
        print("⚠  Track A (Flask v1) — KEEP_TRACK_A=1, 維持原行為")
        print(f"   v3.1 後主介面已搬到 Track B: {TRACK_B_URL}")
        print(f"   本 UI 在 v3.2 預期完全退場, 請逐步遷移工作流程")
    else:
        print("⚠  Track A (Flask v1) 進入棄用準備期 (v3.1)")
        print(f"   根路徑 / 已 redirect 到 Track B: {TRACK_B_URL}")
        print(f"   要保留 Track A 完整行為請設環境變數 KEEP_TRACK_A=1")
        print(f"   仍可直接訪問 /upload / /exams / /library 等子路徑")
    print("=" * 70)
    print()

    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
