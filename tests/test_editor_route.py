"""server/routes/editor.py — 輕量 deck editor route 測試覆蓋。

editor.py 從 PR-3d 上線後沒有對應 regression 測試. 這支 route 服務 server-side
HTML 直接 inline 在 string template, user-controlled 欄位 (deck_title /
section.title / slide.title / narration / bullets / source.path) 全走原 string
拼接 — 唯一防線是 `_html_escape`. 任何 refactor 不小心放行 `<script>` /
`</textarea>` / `"` 就是 XSS 上線.

測試覆蓋:
- `_html_escape` 純函式: HTML entity 全 5 種 (& < > " ') / None / 數字
- `_render_slide` / `_render_section` 整合: malicious payload 透過 user
  field 進來時, 不會逃出 HTML attribute / tag boundary
- HTTP `GET /editor`: 空 list / 含 job 列表
- HTTP `GET /editor/{job_id}`: 404 不存在 / v1 exam schema 走 fallback /
  deck schema 渲染含 escaped 內容
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server 內 upload route 需要")

from fastapi.testclient import TestClient

from server.jobs import JobStore, get_default_store
from server.main import create_app
from server.routes.editor import (
    _html_escape,
    _render_section,
    _render_slide,
)
from server.schemas import (
    JobOptions,
    JobRecord,
    JobSource,
    JobState,
    SourceType,
)


# ---------- _html_escape 純函式 (XSS safety lock) ----------

class TestHtmlEscape:
    """覆蓋 5 種 HTML entity + 邊界 (None / 空 / 非 str). 任何 entity 漏接 =
    XSS 出口."""

    def test_ampersand_escaped(self):
        assert _html_escape("a & b") == "a &amp; b"

    def test_less_than_escaped(self):
        assert _html_escape("<script>") == "&lt;script&gt;"

    def test_greater_than_escaped(self):
        assert _html_escape("a>b") == "a&gt;b"

    def test_double_quote_escaped(self):
        # value="<input>" 內含 " 會直接破 attribute, 必須轉 &quot;
        assert _html_escape('say "hi"') == "say &quot;hi&quot;"

    def test_single_quote_escaped(self):
        # 雖然 HTML attribute 用 double quote, " 已被 escape, 但 onclick="..."
        # 內若有 ' 仍要 escape 避免 JS string 注入
        assert _html_escape("don't") == "don&#39;t"

    def test_all_entities_together(self):
        """XSS 經典 payload — 5 entity 一次到位."""
        payload = """<img src="x" onerror='alert(1)'>"""
        out = _html_escape(payload)
        assert "<" not in out
        assert ">" not in out
        assert '"' not in out
        assert "'" not in out
        assert "&lt;img" in out
        assert "src=&quot;x&quot;" in out
        assert "onerror=&#39;alert(1)&#39;" in out

    def test_ampersand_processed_first(self):
        """& 要先轉, 否則後面的 &lt; 會被再轉一次成 &amp;lt;."""
        assert _html_escape("&lt;") == "&amp;lt;"

    def test_empty_string_returns_empty(self):
        assert _html_escape("") == ""

    def test_none_returns_empty(self):
        """None 不該炸 — 多處欄位 (file_path / code_snippet / cover_org) 可能 None."""
        assert _html_escape(None) == ""

    def test_zero_returns_empty(self):
        """falsy 但非 None — 0 / False 走 `if not s` 一律回空 (current behavior)."""
        # 注意: 目前實作 `if not s: return ""`, 數字 0 也回空.
        # 若未來需要支援 0 → "0", 該主動更新此 test.
        assert _html_escape(0) == ""

    def test_int_passthrough_when_truthy(self):
        """非 0 整數會走 str(s) 路徑."""
        assert _html_escape(42) == "42"

    def test_chinese_passthrough(self):
        """繁中字非 HTML entity, 該原樣留 (避免 over-escape)."""
        assert _html_escape("劉老師 < 學生") == "劉老師 &lt; 學生"


# ---------- _render_slide / _render_section XSS lock (整合層) ----------

class TestRenderSlideEscape:
    """malicious user input 透過 deck field 進入 _render_slide 時, 該被 escape."""

    def test_xss_in_title_escaped(self):
        sl = {
            "id": "s1", "title": "<script>alert(1)</script>",
            "bullets": [], "narration": "", "code_snippet": None, "file_path": None,
        }
        html = _render_slide("sec1", 0, sl)
        assert "<script>" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html

    def test_xss_in_narration_escaped(self):
        sl = {
            "id": "s1", "title": "ok",
            "bullets": [], "narration": "</textarea><script>x</script>",
            "code_snippet": None, "file_path": None,
        }
        html = _render_slide("sec1", 0, sl)
        # 不能讓 </textarea> 提早結束 narration textarea
        assert "</textarea><script>" not in html
        assert "&lt;/textarea&gt;&lt;script&gt;" in html

    def test_xss_in_bullets_escaped(self):
        sl = {
            "id": "s1", "title": "ok",
            "bullets": ["normal", "<img src=x onerror=alert(1)>"],
            "narration": "", "code_snippet": None, "file_path": None,
        }
        html = _render_slide("sec1", 0, sl)
        assert "<img src=x" not in html
        assert "&lt;img src=x onerror=alert(1)&gt;" in html

    def test_double_quote_in_value_attr_escaped(self):
        """title value="..." 內含 " 會直接破 input, escape 必要."""
        sl = {
            "id": "s1", "title": 'click " then injection',
            "bullets": [], "narration": "", "code_snippet": None, "file_path": None,
        }
        html = _render_slide("sec1", 0, sl)
        # 不該有未 escape 的 " 在 value 屬性內
        assert 'value="click " then' not in html
        assert 'value="click &quot; then injection"' in html

    def test_section_id_in_data_attr_escaped(self):
        """section_id 雖內部產生, 走 data-slide-id="..." 仍 escape (防 deck 被
        人工編輯後注入)."""
        sl = {
            "id": "s1", "title": "ok", "bullets": [],
            "narration": "", "code_snippet": None, "file_path": None,
        }
        html = _render_slide('sec"injection', 0, sl)
        assert 'data-slide-id="sec"injection__0"' not in html
        assert 'data-slide-id="sec&quot;injection__0"' in html

    def test_default_slide_id_when_missing(self):
        """slide 缺 id 走 fallback `section_id_idx+1`."""
        sl = {
            "title": "ok", "bullets": [], "narration": "",
            "code_snippet": None, "file_path": None,
        }
        html = _render_slide("sec1", 2, sl)
        # 缺 id 該 fallback (section_id + "_" + idx+1)
        assert "sec1_3" in html

    def test_code_snippet_html_escaped(self):
        """code 內含 <html-like-tag> 該 escape, 不該被當 HTML tag."""
        sl = {
            "id": "s1", "title": "ok", "bullets": [],
            "narration": "", "code_snippet": "<div onclick=evil()>",
            "file_path": "core/foo.py",
        }
        html = _render_slide("sec1", 0, sl)
        assert "<div onclick=evil()>" not in html
        assert "&lt;div onclick=evil()&gt;" in html


class TestRenderSectionEscape:
    def test_section_title_escaped(self):
        sec = {"id": "sec1", "title": "<b>bold</b>", "slides": []}
        html = _render_section(0, sec)
        assert "<b>bold</b>" not in html
        assert "&lt;b&gt;bold&lt;/b&gt;" in html

    def test_section_id_in_data_attr_escaped(self):
        sec = {"id": 'sec"injection', "title": "ok", "slides": []}
        html = _render_section(0, sec)
        assert 'data-section-id="sec"injection"' not in html
        assert 'data-section-id="sec&quot;injection"' in html

    def test_section_with_slides_renders_each(self):
        sec = {
            "id": "sec1", "title": "intro",
            "slides": [
                {"id": "s1", "title": "slide 1", "bullets": [], "narration": "",
                 "code_snippet": None, "file_path": None},
                {"id": "s2", "title": "slide 2", "bullets": [], "narration": "",
                 "code_snippet": None, "file_path": None},
            ],
        }
        html = _render_section(0, sec)
        assert "slide 1" in html
        assert "slide 2" in html

    def test_default_section_id_when_missing(self):
        sec = {"title": "untitled", "slides": []}
        html = _render_section(2, sec)
        # 缺 id 走 fallback `sec{idx+1}` = sec3
        assert "sec3" in html


# ---------- HTTP endpoint 整合 ----------

@pytest.fixture
def client(tmp_path):
    app = create_app()
    store = JobStore(root=tmp_path / "jobs")
    app.dependency_overrides[get_default_store] = lambda: store
    with TestClient(app) as c:
        yield c, store


def _make_job(store: JobStore, *, source_type=SourceType.DOCUMENT,
              state=JobState.AWAITING_REVIEW, source_path="/tmp/x.pdf",
              deck_content: dict | None = None) -> JobRecord:
    """直接塞 JobRecord 進 store + 寫 deck.json. 跳過 create_job 的 ingest
    flow."""
    now = datetime.now(timezone.utc)
    rec = JobRecord(
        id="testjob01",
        source_type=source_type,
        source=JobSource(path=source_path),
        options=JobOptions(),
        state=state,
        created_at=now,
        updated_at=now,
    )
    store._cache[rec.id] = rec
    job_dir = store.root / rec.id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "artifacts").mkdir(exist_ok=True)
    if deck_content is not None:
        store.deck_path(rec.id).write_text(
            json.dumps(deck_content, ensure_ascii=False), encoding="utf-8",
        )
    return rec


class TestEditorIndex:
    def test_empty_list_renders(self, client):
        c, _ = client
        r = c.get("/editor")
        assert r.status_code == 200
        assert "尚無 job" in r.text
        assert "<!DOCTYPE html>" in r.text

    def test_lists_existing_job(self, client):
        c, store = client
        _make_job(store)
        r = c.get("/editor")
        assert r.status_code == 200
        assert "testjob01" in r.text
        # awaiting_review 該有 badge
        assert "badge-awaiting_review" in r.text

    def test_source_path_escaped_in_card(self, client):
        c, store = client
        _make_job(store, source_path='/tmp/<evil>"x.pdf')
        r = c.get("/editor")
        assert r.status_code == 200
        # source path 走 _html_escape, < / " 不該裸露
        assert '/tmp/<evil>"x.pdf' not in r.text
        assert "/tmp/&lt;evil&gt;&quot;x.pdf" in r.text

    def test_job_error_escaped_in_card(self, client):
        # j.error 可能含來源檔名/外部工具輸出, 進卡片前必須 escape (T2-3)
        c, store = client
        rec = _make_job(store, state=JobState.FAILED)
        rec.error = "<img src=x onerror=alert(1)>boom"
        r = c.get("/editor")
        assert r.status_code == 200
        assert "<img src=x onerror=" not in r.text
        assert "&lt;img src=x onerror=alert(1)&gt;boom" in r.text


class TestEditorPage:
    def test_nonexistent_job_404(self, client):
        c, _ = client
        r = c.get("/editor/nonexistent_id")
        assert r.status_code == 404

    def test_v1_exam_schema_shows_fallback_message(self, client):
        """exam_pdf (problems / steps) 該顯示「Flask app.py 介面」訊息, 不該
        試圖渲染 sections."""
        c, store = client
        _make_job(store, source_type=SourceType.EXAM_PDF,
                  deck_content={
                      "exam_title": "材料力學",
                      "problems": [{"id": "q1", "number": "第1題", "score": 20,
                                    "problem": "", "steps": []}],
                  })
        r = c.get("/editor/testjob01")
        assert r.status_code == 200
        assert "v1 exam schema" in r.text
        assert "Flask app.py" in r.text

    def test_missing_deck_shows_message(self, client):
        """job 還沒 ingest 完 (沒 deck.json) — 該顯示「deck.json 不存在」."""
        c, store = client
        _make_job(store, state=JobState.INGESTING, deck_content=None)
        r = c.get("/editor/testjob01")
        assert r.status_code == 200
        assert "deck.json 不存在" in r.text

    def test_deck_schema_renders_sections(self, client):
        c, store = client
        _make_job(store, deck_content={
            "deck_title": "Python 入門",
            "source_meta": {"title": "tutorial"},
            "sections": [
                {"id": "intro", "title": "簡介", "slides": [
                    {"id": "intro_1", "title": "什麼是 Python",
                     "bullets": ["直譯式", "動態型別"],
                     "narration": "Python 是...", "code_snippet": None,
                     "file_path": None},
                ]},
            ],
        })
        r = c.get("/editor/testjob01")
        assert r.status_code == 200
        assert "Python 入門" in r.text
        assert "簡介" in r.text
        assert "什麼是 Python" in r.text
        assert "直譯式" in r.text

    def test_deck_xss_in_html_render_path_escaped(self, client):
        """惡意 deck 內容 (假設有人改了 deck.json) 走 HTML 渲染路徑 (toolbar
        deck_title / section title 走 _html_escape) 該被 escape.

        注意: deck 還會 *額外* 透過 `json.dumps` 注進 `<script>const DECK = ...`
        block — 該路徑不走 _html_escape, 若 deck_title 含 `</script>` 會打破
        JS 邊界 (見 docs/ROUTINE_FINDINGS.md). 那是另一條攻擊面, 修法需主程式
        改 (用 `json.dumps(deck).replace("</", "<\\/")` 或在 dumps 後額外 escape),
        屬於 routine 不該自行決策的行為改動, 該測試不在這支驗.
        """
        c, store = client
        _make_job(store, deck_content={
            "deck_title": "evil<title>&attack",
            "sections": [
                {"id": "sec1", "title": "</h3><img src=x onerror=evil()>",
                 "slides": [
                     {"id": "s1", "title": "ok",
                      "bullets": ['"><b>bullet payload</b>'],
                      "narration": "", "code_snippet": None, "file_path": None},
                 ]},
            ],
        })
        r = c.get("/editor/testjob01")
        assert r.status_code == 200
        # toolbar 的 <strong>{deck_title}</strong> — deck_title 走 _html_escape
        assert "<strong>evil&lt;title&gt;&amp;attack</strong>" in r.text
        # section <h3>...<input value="{title}"> — title 走 _html_escape
        assert 'value="&lt;/h3&gt;&lt;img src=x onerror=evil()&gt;"' in r.text
        # bullet <input value="{bullet}"> — 走 _html_escape (escaped 版本一定在)
        assert "&quot;&gt;&lt;b&gt;bullet payload&lt;/b&gt;" in r.text
        # JS-context 路徑 (<script>const DECK = ...) 的 </ escape 由
        # TestEditorScriptContextEscape 專門驗.


class TestEditorScriptContextEscape:
    """<script>const DECK = {json}</script> 的 JS-context XSS 防線.

    deck 任一字串欄位含 `</script>` 會讓 HTML parser 提早結束 script tag
    → 後面內容當成新 tag 解析 (XSS). 修法: json.dumps 後把 `</` 換成 `<\\/`
    (JSON 標準, 不改 JS 語意). 原本只有 _html_escape 護 DOM 路徑, 這條漏掉
    (見 docs/ROUTINE_FINDINGS.md 2026-05-24 finding, 已修)."""

    def test_script_close_in_deck_title_is_neutralized(self, client):
        c, store = client
        # deck_title 帶 </script> break-out 嘗試
        payload = "</script><img src=x onerror=alert(1)>"
        _make_job(store, deck_content={
            "deck_title": payload,
            "sections": [
                {"id": "sec1", "title": "ok", "slides": [
                    {"id": "s1", "title": "ok", "bullets": [],
                     "narration": "", "code_snippet": None, "file_path": None},
                ]},
            ],
        })
        r = c.get("/editor/testjob01")
        assert r.status_code == 200
        # 裸露的 </script><img...> 不該出現 (那代表 break out 成功)
        assert payload not in r.text
        # 該以 escape 形式出現在 const DECK JSON 內: </ → <\/
        assert "<\\/script><img src=x onerror=alert(1)>" in r.text

    def test_script_close_in_narration_is_neutralized(self, client):
        c, store = client
        evil = "正常旁白</script><script>steal()</script>"
        _make_job(store, deck_content={
            "deck_title": "ok",
            "sections": [
                {"id": "sec1", "title": "ok", "slides": [
                    {"id": "s1", "title": "ok", "bullets": [],
                     "narration": evil, "code_snippet": None, "file_path": None},
                ]},
            ],
        })
        r = c.get("/editor/testjob01")
        assert r.status_code == 200
        # narration 的 </script> 在 const DECK JSON 內全被 escape, 不裸露
        assert "</script><script>steal()" not in r.text
        assert "<\\/script><script>steal()<\\/script>" in r.text
