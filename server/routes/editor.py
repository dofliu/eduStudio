"""輕量 deck editor — server-side HTML 直接服務 (PR-3d)。

設計目標:
- 不另外起前端 build, HTML 內聯在這裡, vanilla JS + fetch 走既有 /jobs API
- 列表頁: 看所有 job 的狀態, 進入 editor
- 編輯頁: 展開新 deck schema (sections / slides) 逐欄編輯, save / approve 一鍵
- 既有 Flask app.py 不動 (還在服務 v1 exam schema 的考卷檢討流程)

路由:
    GET /                        -> 重導 /editor
    GET /editor                  -> 全部 job 列表
    GET /editor/{job_id}         -> 單一 job 的 deck 編輯頁

存取後端用既有 API:
    PUT  /jobs/{id}/draft        -> 儲存 deck
    POST /jobs/{id}/approve      -> 通過 review, 觸發 render
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse

from ..jobs import JobStore, get_default_store
from ..schemas import JobRecord, JobState


router = APIRouter(tags=["editor"])


def _store() -> JobStore:
    return get_default_store()


# ---------- 共用 CSS ----------
# 內聯 CSS 避免 static 檔案管理. Forest 配色呼應渲染主題, 但介面色階壓低
# 不要太搶眼 (UI 是工具, 不是內容)。

_CSS = """
* { box-sizing: border-box; }
body {
  font-family: 'Microsoft JhengHei', 'PingFang TC', system-ui, sans-serif;
  background: #fafaf6; color: #1f2d28;
  margin: 0; padding: 0; line-height: 1.5;
}
header {
  background: #1e3a2e; color: #f0ede0;
  padding: 14px 28px; border-bottom: 4px solid #ffd96b;
  display: flex; justify-content: space-between; align-items: center;
}
header h1 { font-size: 1.1rem; font-weight: 500; margin: 0; }
header a { color: #ffd96b; text-decoration: none; font-size: 0.9rem; }
header a:hover { text-decoration: underline; }

main { max-width: 1100px; margin: 0 auto; padding: 24px 28px; }
h2 { font-size: 1.4rem; margin: 24px 0 12px; color: #1e3a2e; }

.job-card {
  background: white; border: 1px solid #d8d4c2; border-radius: 6px;
  padding: 14px 18px; margin-bottom: 12px;
  display: flex; gap: 16px; align-items: flex-start;
}
.job-card .meta { flex: 1; min-width: 0; }
.job-card .actions { display: flex; gap: 8px; flex-wrap: wrap; }
.job-id { font-family: Consolas, Monaco, monospace; color: #555; font-size: 0.85rem; }
.job-source { color: #1e3a2e; font-weight: 600; word-break: break-all; }
.job-stats { color: #666; font-size: 0.9rem; margin-top: 4px; }
.job-error { color: #b04a3e; font-size: 0.9rem; margin-top: 4px; }

.badge {
  display: inline-block; padding: 3px 10px; border-radius: 12px;
  font-size: 0.78rem; font-weight: 600; letter-spacing: 0.5px;
  text-transform: uppercase; vertical-align: middle;
}
.badge-pending      { background: #ddd; color: #444; }
.badge-ingesting    { background: #fde7a7; color: #7a5b00; }
.badge-awaiting_review { background: #ffd96b; color: #5a3e00; }
.badge-rendering    { background: #b0e0c8; color: #1a4d2f; }
.badge-done         { background: #1e3a2e; color: #ffd96b; }
.badge-failed       { background: #b04a3e; color: white; }

button, .btn {
  background: #1e3a2e; color: #ffd96b; border: 0;
  padding: 6px 14px; border-radius: 4px; cursor: pointer;
  font-size: 0.85rem; text-decoration: none; display: inline-block;
}
button:hover, .btn:hover { background: #2a5040; }
button.btn-primary { background: #ffd96b; color: #1e3a2e; font-weight: 600; }
button.btn-primary:hover { background: #ffc94a; }
button.btn-ghost { background: transparent; color: #1e3a2e; border: 1px solid #c0bcaa; }
button.btn-ghost:hover { background: #ece8d6; }
button.btn-danger { background: #b04a3e; color: white; }
button:disabled { opacity: 0.5; cursor: not-allowed; }

.toolbar {
  position: sticky; top: 0; background: rgba(250, 250, 246, 0.95);
  padding: 12px 0; border-bottom: 1px solid #d8d4c2; margin-bottom: 16px;
  display: flex; gap: 10px; align-items: center; z-index: 5;
}
.toolbar .grow { flex: 1; }

section.deck-section {
  background: white; border: 1px solid #d8d4c2; border-radius: 6px;
  padding: 16px 20px; margin-bottom: 16px;
}
section.deck-section h3 {
  font-size: 1.05rem; color: #1e3a2e; margin: 0 0 12px 0;
  padding-bottom: 8px; border-bottom: 2px solid #ffd96b;
}

.slide-card {
  background: #fafaf6; border: 1px solid #e3dfca; border-radius: 4px;
  padding: 12px 14px; margin-bottom: 12px;
}
.slide-card .slide-id {
  font-family: Consolas, monospace; color: #888; font-size: 0.8rem;
  margin-bottom: 6px;
}
.field { margin: 8px 0; }
.field label {
  display: block; font-size: 0.8rem; color: #555; margin-bottom: 3px;
  text-transform: uppercase; letter-spacing: 0.4px;
}
.field input[type=text], .field textarea {
  width: 100%; padding: 6px 8px; border: 1px solid #c0bcaa; border-radius: 3px;
  font-family: inherit; font-size: 0.95rem; background: white;
}
.field textarea { resize: vertical; min-height: 60px; font-family: inherit; }
.field textarea.code { font-family: Consolas, monospace; font-size: 0.85rem; min-height: 100px; }
.bullets-list { list-style: none; padding: 0; margin: 0; }
.bullets-list li { display: flex; gap: 6px; margin-bottom: 4px; }
.bullets-list input { flex: 1; }
.bullets-list button { padding: 4px 10px; }

.toast {
  position: fixed; bottom: 20px; right: 20px;
  background: #1e3a2e; color: #ffd96b;
  padding: 12px 18px; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.2);
  display: none; z-index: 100;
}
.toast.show { display: block; }
.toast.error { background: #b04a3e; color: white; }

.empty {
  text-align: center; padding: 40px 20px; color: #888;
}
"""


# ---------- HTML 共用 layout ----------

def _layout(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — autoSolverVideo</title>
<style>{_CSS}</style>
</head>
<body>
<header>
  <h1>🎬 autoSolverVideo — Deck Editor</h1>
  <a href="/editor">← Jobs</a>
</header>
<main>
{body}
</main>
<div id="toast" class="toast"></div>
<script>
function showToast(msg, isError) {{
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show' + (isError ? ' error' : '');
  setTimeout(() => {{ t.className = 'toast'; }}, 3000);
}}

// index 卡片上的「Approve」按鈕呼叫: 直接觸發 render, 不打開 editor
async function approveJob(jobId) {{
  if (!confirm('Approve 後會立刻開始渲染, 確定?')) return;
  try {{
    const r = await fetch(`/jobs/${{jobId}}/approve`, {{ method: 'POST' }});
    if (!r.ok) {{
      const err = await r.text();
      showToast(`Approve 失敗: ${{r.status}} ${{err}}`, true);
      return;
    }}
    showToast('已 Approve, 渲染中...');
    setTimeout(() => location.reload(), 1500);
  }} catch (e) {{ showToast(`Approve 失敗: ${{e}}`, true); }}
}}
</script>
</body>
</html>"""


# ---------- Index page ----------

def _render_index(jobs: list[JobRecord]) -> str:
    if not jobs:
        body = '<div class="empty">尚無 job。用 <code>POST /jobs</code> 或 <code>scripts/submit_job.py</code> 建立。</div>'
    else:
        cards = []
        for j in jobs:
            cards.append(_render_job_card(j))
        body = "<h2>Jobs</h2>" + "\n".join(cards)
    return _layout("Jobs", body)


def _render_job_card(j: JobRecord) -> str:
    state = j.state.value
    badge = f'<span class="badge badge-{state}">{state}</span>'

    # 來源描述
    if j.source_type.value == "url":
        src_text = f'url: {j.source.url}' if j.source.url else "url: ?"
    else:
        src_text = f'{j.source_type.value}: {j.source.path or "?"}'

    # 統計 — 從 deck.json 讀 (若存在), 否則顯示 stage 進度
    deck_path = JobStore.deck_path(j.id)
    stats = ""
    if deck_path.exists():
        try:
            d = json.loads(deck_path.read_text(encoding="utf-8"))
            if "sections" in d:
                slides = sum(len(s.get("slides", [])) for s in d["sections"])
                stats = f"{len(d['sections'])} sections / {slides} slides"
            elif "problems" in d:
                steps = sum(len(p.get("steps", [])) for p in d["problems"])
                stats = f"{len(d['problems'])} problems / {steps} steps"
        except Exception:
            pass

    error_html = f'<div class="job-error">⚠ {j.error}</div>' if j.error else ""

    # actions 依狀態變: review 中可 edit + approve, done 可下載
    actions = []
    if j.state in (JobState.AWAITING_REVIEW, JobState.DONE, JobState.FAILED):
        actions.append(f'<a class="btn btn-ghost" href="/editor/{j.id}">✏ Edit</a>')
    if j.state == JobState.AWAITING_REVIEW:
        actions.append(f'<button class="btn-primary" onclick="approveJob(\'{j.id}\')">✓ Approve</button>')
    if j.state == JobState.DONE and j.artifacts:
        # 取第一個 mp4 當代表
        mp4s = [a for a in j.artifacts if a.kind == "mp4"]
        if mp4s:
            actions.append(
                f'<a class="btn" href="/jobs/{j.id}/artifacts/{mp4s[0].name}">▶ {mp4s[0].name}</a>'
            )
        if len(mp4s) > 1:
            actions.append(f'<span class="job-stats">+{len(mp4s)-1} more</span>')

    actions_html = '<div class="actions">' + "".join(actions) + '</div>'

    return f"""
<div class="job-card">
  <div class="meta">
    <span class="job-id">{j.id}</span> {badge}
    <div class="job-source">{_html_escape(src_text)}</div>
    <div class="job-stats">{stats}</div>
    {error_html}
  </div>
  {actions_html}
</div>"""


# ---------- Editor page ----------

def _render_editor(j: JobRecord) -> str:
    deck_path = JobStore.deck_path(j.id)
    if not deck_path.exists():
        return _layout("Editor",
            f'<div class="empty">deck.json 不存在 (job 還在 ingest 中?)<br>'
            f'狀態: {j.state.value}</div>')

    deck = json.loads(deck_path.read_text(encoding="utf-8"))

    # 只支援新 deck schema (sections / slides). v1 exam schema 的 jobs 仍由 Flask app.py 編
    if "sections" not in deck:
        return _layout("Editor",
            f'<div class="empty">這是 v1 exam schema (problems / steps), '
            f'目前 deck editor 只支援新 schema (repo / document / url)。<br>'
            f'考卷編輯請用 Flask app.py 介面 (port 5000)。</div>')

    can_save = j.state == JobState.AWAITING_REVIEW
    can_approve = j.state == JobState.AWAITING_REVIEW

    save_btn = (
        '<button class="btn-primary" onclick="saveDeck()">💾 Save</button>'
        if can_save else
        '<button disabled title="僅 awaiting_review 可儲存">💾 Save</button>'
    )
    approve_btn = (
        '<button class="btn-primary" onclick="approve()">✓ Approve & Render</button>'
        if can_approve else
        f'<button disabled title="目前 {j.state.value} 不能 approve">✓ Approve</button>'
    )

    sections_html = "\n".join(
        _render_section(i, sec) for i, sec in enumerate(deck.get("sections", []))
    )

    deck_title = _html_escape(deck.get("deck_title", ""))
    summary = _html_escape(deck.get("source_meta", {}).get("title")
                           or deck.get("source_meta", {}).get("root_name", ""))
    state_badge = f'<span class="badge badge-{j.state.value}">{j.state.value}</span>'

    body = f"""
<div class="toolbar">
  <strong>{deck_title}</strong>
  {state_badge}
  <span class="job-stats">{summary}</span>
  <span class="grow"></span>
  {save_btn}
  {approve_btn}
</div>

<form id="deck-form" onsubmit="event.preventDefault(); saveDeck();">
{sections_html}
</form>

<script>
const JOB_ID = {json.dumps(j.id)};
const DECK = {json.dumps(deck, ensure_ascii=False)};

function collectDeck() {{
  // 從 DOM 收集編輯後的 deck — 結構照原 deck schema, 只更新允許編輯的欄位
  const sections = DECK.sections.map((sec, si) => {{
    const slides = sec.slides.map((sl, sli) => {{
      const root = document.querySelector(`[data-slide-id="${{sec.id}}__${{sli}}"]`);
      const bullets = Array.from(root.querySelectorAll('.bullet-input'))
        .map(el => el.value.trim()).filter(Boolean);
      return {{
        ...sl,
        title: root.querySelector('.slide-title').value,
        bullets: bullets,
        code_snippet: root.querySelector('.slide-code').value || null,
        file_path: root.querySelector('.slide-filepath').value || null,
        narration: root.querySelector('.slide-narration').value,
      }};
    }});
    const secRoot = document.querySelector(`[data-section-id="${{sec.id}}"]`);
    return {{
      ...sec,
      title: secRoot.querySelector('.section-title').value,
      slides: slides,
    }};
  }});
  return {{ ...DECK, sections }};
}}

async function saveDeck() {{
  const updated = collectDeck();
  try {{
    const r = await fetch(`/jobs/${{JOB_ID}}/draft`, {{
      method: 'PUT', headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{ deck: updated }}),
    }});
    if (!r.ok) {{
      const err = await r.text();
      showToast(`儲存失敗: ${{r.status}} ${{err}}`, true);
      return;
    }}
    showToast('已儲存');
  }} catch (e) {{ showToast(`儲存失敗: ${{e}}`, true); }}
}}

async function approve() {{
  if (!confirm('Approve 後會立刻開始渲染, 確定?')) return;
  await saveDeck();
  try {{
    const r = await fetch(`/jobs/${{JOB_ID}}/approve`, {{ method: 'POST' }});
    if (!r.ok) {{
      const err = await r.text();
      showToast(`Approve 失敗: ${{r.status}} ${{err}}`, true);
      return;
    }}
    showToast('已 Approve, 渲染中...');
    setTimeout(() => location.href = '/editor', 1500);
  }} catch (e) {{ showToast(`Approve 失敗: ${{e}}`, true); }}
}}

function addBullet(btn) {{
  const list = btn.parentElement.querySelector('.bullets-list');
  const li = document.createElement('li');
  li.innerHTML = '<input type="text" class="bullet-input" placeholder="新 bullet"><button type="button" onclick="this.parentElement.remove()">×</button>';
  list.appendChild(li);
}}
</script>
"""
    return _layout("Edit deck", body)


def _render_section(idx: int, sec: dict) -> str:
    sid = sec.get("id", f"sec{idx+1}")
    title = _html_escape(sec.get("title", ""))
    slides_html = "\n".join(
        _render_slide(sid, i, sl) for i, sl in enumerate(sec.get("slides", []))
    )
    return f"""
<section class="deck-section" data-section-id="{_html_escape(sid)}">
  <h3>章 {idx+1}: <input type="text" class="section-title field" value="{title}"
      style="display:inline-block; width:auto; min-width: 300px; font-size: 1rem;"></h3>
  {slides_html}
</section>"""


def _render_slide(section_id: str, slide_idx: int, sl: dict) -> str:
    sl_id = sl.get("id", f"{section_id}_{slide_idx+1}")
    title = _html_escape(sl.get("title", ""))
    narration = _html_escape(sl.get("narration", ""))
    code = _html_escape(sl.get("code_snippet") or "")
    file_path = _html_escape(sl.get("file_path") or "")

    bullets = sl.get("bullets") or []
    bullets_html = "\n".join(
        f'<li><input type="text" class="bullet-input" value="{_html_escape(b)}">'
        f'<button type="button" onclick="this.parentElement.remove()">×</button></li>'
        for b in bullets
    )

    return f"""
<div class="slide-card" data-slide-id="{_html_escape(section_id)}__{slide_idx}">
  <div class="slide-id">{_html_escape(sl_id)}</div>
  <div class="field">
    <label>title</label>
    <input type="text" class="slide-title" value="{title}">
  </div>
  <div class="field">
    <label>bullets</label>
    <ul class="bullets-list">{bullets_html}</ul>
    <button type="button" class="btn-ghost" onclick="addBullet(this)">+ add bullet</button>
  </div>
  <div class="field">
    <label>code_snippet (留空 = 不放程式碼)</label>
    <textarea class="slide-code code">{code}</textarea>
  </div>
  <div class="field">
    <label>file_path (code 來源, 例 core/foo.py)</label>
    <input type="text" class="slide-filepath" value="{file_path}">
  </div>
  <div class="field">
    <label>narration (旁白, 100~200 字)</label>
    <textarea class="slide-narration">{narration}</textarea>
  </div>
</div>"""


def _html_escape(s: str | None) -> str:
    if not s:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


# ---------- Routes ----------

# GET / 由 main.py 處理 (依 React UI 是否 build 過決定導 /ui/ 或 /editor)


@router.get("/editor", response_class=HTMLResponse)
async def editor_index(store: JobStore = Depends(_store)) -> HTMLResponse:
    return HTMLResponse(_render_index(store.list()))


@router.get("/editor/{job_id}", response_class=HTMLResponse)
async def editor_page(job_id: str, store: JobStore = Depends(_store)) -> HTMLResponse:
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    return HTMLResponse(_render_editor(rec))


# 給 index page 上的 approve 按鈕呼叫的小 wrapper script (避免 inline JS 重複)
# 直接 inline 在 index 卡片裡, 但定義在 layout 共用 — 補一個 endpoint 不必要
