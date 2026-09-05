"""core.comic_video — 漫畫 episode → 動態漫畫影片。

涵蓋:
- 時間軸: 片頭 → 每頁 [進場 → 逐句 → 收尾] → 片尾, 音長缺時用估算補
- SRT: 每句一條 cue, 角色句帶名字前綴, 旁白不帶
- HTML 播放器: 圖片內嵌、泡泡 / 旁白 caption 分流、文字 escape、水印
- 混音指令: 有音檔 → adelay+amix; 無音檔 → anullsrc 靜音軌
- 渲染 gate: 有頁缺 scene asset 直接擋
- mock 端到端 (需 ffmpeg): 出 mp4 + srt + html, 且 manifest.exports 有登記
- 路由: POST /episodes/{story_id}/video 建 job (mock) 走到 DONE; 缺圖 422
"""
from __future__ import annotations

import asyncio
import base64
import shutil
from pathlib import Path

import pytest

from core.comics import (
    Character,
    ComicGateError,
    ComicPage,
    ComicStore,
    Dialogue,
    EpisodeManifest,
    Series,
)
from core import comic_video as cv

_needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="需要 ffmpeg")

# 1x1 PNG
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _store(tmp_path: Path) -> ComicStore:
    return ComicStore(project_root=tmp_path / "projects")


def _episode(store: ComicStore, *, with_assets: bool = True, mock_asset: bool = False) -> EpisodeManifest:
    store.create_series(Series(
        project_id="course", series_id="wind", title="海風值班日誌",
        characters=[
            Character(character_id="dofu", name="杜夫", role="O&M Lead"),
            Character(character_id="mei", name="小美", role="Trainee"),
        ],
    ))
    ep = store.create_episode(EpisodeManifest(
        project_id="course", series_id="wind", story_id="W01", title="齒間的線索",
        page_count=2, learning_objectives=["先保留證據，再下結論", "alarm 不等於 root cause"],
        characters=["dofu", "mei"],
    ))
    pages = [
        ComicPage(
            page_no=1, camera="wide shot", alt_text="控制室", image_prompt="p",
            dialogues=[
                Dialogue(dialogue_id="d1", speaker_id="narrator", text="凌晨三點，控制室跳出振動警報。"),
                Dialogue(dialogue_id="d2", speaker_id="dofu", text="先別急著停機，把 <trend> 拉出來。"),
            ],
        ),
        ComicPage(
            page_no=2, camera="close-up", alt_text="齒輪箱", image_prompt="p",
            dialogues=[Dialogue(dialogue_id="d3", speaker_id="mei", text="油溫也在爬。")],
        ),
    ]
    ep = store.update_episode("course", "W01", "v0.1", {"pages": pages, "state": "STORYBOARD"})
    if with_assets:
        for n in (1, 2):
            ep = store.attach_asset(
                "course", "W01", "v0.1", filename=f"s{n}.png", data=_PNG, kind="scene",
                provenance="mock_placeholder" if mock_asset else "gemini:test", asset_id=f"scene_{n}",
            )
            ep = store.set_page_asset("course", "W01", "v0.1", n, f"scene_{n}")
    return ep


# ---------------- 時間軸 ----------------
class TestTimeline:
    def test_estimate_prefers_cjk_rate_and_floor(self):
        assert cv.estimate_speech_seconds("好") == cv.MIN_SPEECH_S
        long = cv.estimate_speech_seconds("這是一句大約二十個字的中文旁白測試句子喔")
        assert 5.0 < long < 7.5

    def test_pages_are_sequential_and_use_measured_durations(self, tmp_path):
        store = _store(tmp_path)
        ep = _episode(store)
        series = store.get_series("course", "wind")
        imgs = {p.page_no: store.resolve_asset(ep, p.image_asset_id) for p in ep.pages}
        tl = cv.build_timeline(ep, series, image_paths=imgs, durations={"d1": 3.0, "d2": 2.0, "d3": 1.5})

        assert tl.intro_end == cv.INTRO_S
        p1, p2 = tl.pages
        assert p1.start == cv.INTRO_S
        assert p1.cues[0].start == pytest.approx(cv.INTRO_S + cv.PAGE_LEAD_S)
        assert p1.cues[0].end - p1.cues[0].start == pytest.approx(3.0)
        assert p1.cues[1].start == pytest.approx(p1.cues[0].end + cv.BUBBLE_GAP_S)
        assert p1.end == pytest.approx(p1.cues[1].end + cv.BUBBLE_GAP_S + cv.PAGE_TAIL_S)
        assert p2.start == p1.end
        assert tl.outro_start == p2.end
        assert tl.total == pytest.approx(p2.end + cv.OUTRO_S)
        # 角色名由 series 解析; narrator 無名
        assert p1.cues[0].is_narrator and p1.cues[0].speaker_name == ""
        assert p1.cues[1].speaker_name == "杜夫"

    def test_missing_duration_falls_back_to_estimate(self, tmp_path):
        store = _store(tmp_path)
        ep = _episode(store)
        imgs = {p.page_no: store.resolve_asset(ep, p.image_asset_id) for p in ep.pages}
        tl = cv.build_timeline(ep, None, image_paths=imgs, durations={})
        c = tl.pages[1].cues[0]
        assert c.end - c.start == pytest.approx(cv.estimate_speech_seconds("油溫也在爬。"))

    def test_missing_image_is_gate_error(self, tmp_path):
        store = _store(tmp_path)
        ep = _episode(store)
        with pytest.raises(ComicGateError):
            cv.build_timeline(ep, None, image_paths={1: Path("x.png")}, durations={})


# ---------------- SRT / HTML ----------------
def _timeline(tmp_path):
    store = _store(tmp_path)
    ep = _episode(store)
    series = store.get_series("course", "wind")
    imgs = {p.page_no: store.resolve_asset(ep, p.image_asset_id) for p in ep.pages}
    return cv.build_timeline(ep, series, image_paths=imgs, durations={"d1": 2, "d2": 2, "d3": 2},
                             preview_label="草稿預覽")


def test_srt_has_one_cue_per_dialogue_with_speaker_prefix(tmp_path):
    srt = cv.build_comic_srt(_timeline(tmp_path))
    blocks = [b for b in srt.strip().split("\n\n") if b]
    assert len(blocks) == 3
    assert blocks[0].splitlines()[2] == "凌晨三點，控制室跳出振動警報。"   # 旁白不加前綴
    assert blocks[1].splitlines()[2].startswith("杜夫：")
    assert " --> " in blocks[0].splitlines()[1]


def test_html_player_embeds_images_escapes_text_and_marks_preview(tmp_path):
    tl = _timeline(tmp_path)
    doc = cv.build_motion_comic_html(tl, width=640, height=360)
    assert doc.count("data:image/png;base64,") >= 4          # 每頁 bg + img
    assert "&lt;trend&gt;" in doc and "<trend>" not in doc     # 對白 escape
    assert 'class="bubble" data-id="d2"' in doc                # 角色句 → 泡泡
    assert 'data-id="d1"' not in doc                           # 旁白 → caption, 不做泡泡
    assert "草稿預覽" in doc and 'class="watermark"' in doc
    assert "__COMIC_TIMELINE__" in doc and '"total":' in doc
    assert "杜夫" in doc


def test_preview_label_rules(tmp_path):
    store = _store(tmp_path)
    ep = _episode(store, mock_asset=True)
    assert "MOCK" in cv.preview_label_for(ep)
    ep2 = ep.model_copy(update={"assets": [a.model_copy(update={"provenance": "gemini:x"}) for a in ep.assets]})
    assert "草稿預覽" in cv.preview_label_for(ep2)
    assert cv.preview_label_for(ep2.model_copy(update={"state": "CURRENT"})) == ""


# ---------------- 混音 ----------------
def test_mux_cmd_uses_adelay_for_clips_and_silence_without(tmp_path, monkeypatch):
    seen: list[list[str]] = []
    monkeypatch.setattr(cv, "run_media_cmd", lambda cmd, **kw: seen.append(cmd))
    tl = _timeline(tmp_path)
    cv.mux_audio(Path("v.mp4"), tl, Path("o.mp4"))
    assert any("anullsrc" in a for a in seen[0])
    tl.pages[0].cues[1].audio_path = "d2.mp3"
    cv.mux_audio(Path("v.mp4"), tl, Path("o.mp4"))
    fc = seen[1][seen[1].index("-filter_complex") + 1]
    start_ms = int(round(tl.pages[0].cues[1].start * 1000))
    assert f"adelay={start_ms}|{start_ms}" in fc and "amix=inputs=1" in fc


# ---------------- 端到端 (mock) ----------------
@_needs_ffmpeg
def test_render_comic_video_mock_end_to_end(tmp_path):
    store = _store(tmp_path)
    ep = _episode(store)
    out = tmp_path / "out"
    progress: list[int] = []
    res = cv.render_comic_video(
        store, "course", "W01", "v0.1", out_dir=out, fps=5, width=320, height=180,
        mock=True, on_progress=progress.append,
    )
    assert res.mp4.exists() and res.mp4.stat().st_size > 0
    assert b"ftyp" in res.mp4.read_bytes()[:64]
    assert res.srt.exists() and res.html.exists()
    assert progress[-1] == 100 and progress == sorted(progress)
    assert res.timeline.preview_label.startswith("草稿預覽")
    assert res.timeline.total > cv.INTRO_S + cv.OUTRO_S


def test_render_refuses_when_page_has_no_asset(tmp_path):
    store = _store(tmp_path)
    _episode(store, with_assets=False)
    with pytest.raises(ComicGateError):
        cv.render_comic_video(store, "course", "W01", "v0.1", out_dir=tmp_path / "o", mock=True)


def test_synthesize_dialogues_raises_on_tts_failure(tmp_path):
    store = _store(tmp_path)
    ep = _episode(store)

    async def bad_tts(text, path):
        return False

    with pytest.raises(RuntimeError):
        asyncio.run(cv.synthesize_dialogues(ep, tmp_path / "tts", bad_tts))


# ---------------- 播放器 JS (需瀏覽器; 沒裝 playwright / Chromium 就跳過) ----------------
def _chromium_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    import os
    return bool(os.environ.get("EDUSTUDIO_CHROMIUM_PATH")) or shutil.which("chromium") is not None


@pytest.mark.skipif(not _chromium_available(), reason="需要 playwright + Chromium")
def test_player_js_shows_caption_for_narrator_and_bubble_for_character(tmp_path):
    """旁白走底部 caption、角色句走泡泡, 兩者都要在對應時間點真的顯示 (曾有 return 順序 bug 讓旁白全消失)。"""
    import os
    from playwright.sync_api import sync_playwright
    from core.html_video import _VIRTUAL_CLOCK_JS

    tl = _timeline(tmp_path)
    html_path = tmp_path / "p.html"
    html_path.write_text(cv.build_motion_comic_html(tl, width=640, height=360), encoding="utf-8")
    narr = tl.pages[0].cues[0]
    bubble = tl.pages[0].cues[1]
    kwargs = {"args": ["--no-sandbox", "--disable-gpu"]}
    if os.environ.get("EDUSTUDIO_CHROMIUM_PATH"):
        kwargs["executable_path"] = os.environ["EDUSTUDIO_CHROMIUM_PATH"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**kwargs)
        try:
            page = browser.new_page(viewport={"width": 640, "height": 360})
            page.add_init_script(_VIRTUAL_CLOCK_JS)
            page.goto(html_path.resolve().as_uri(), wait_until="load")
            page.evaluate("(d) => window.__advanceFrame(d)", (narr.start + 0.8) * 1000)
            cap = page.evaluate("() => { const c = document.getElementById('caption'); return [parseFloat(c.style.opacity), c.textContent]; }")
            assert cap[0] > 0.9 and cap[1] == narr.text
            assert page.evaluate(f"() => parseFloat(document.querySelector('[data-id=\"{bubble.dialogue_id}\"]').style.opacity)") == 0
            page.evaluate("(d) => window.__advanceFrame(d)", (bubble.start - narr.start - 0.8 + 0.5) * 1000)
            assert page.evaluate(f"() => parseFloat(document.querySelector('[data-id=\"{bubble.dialogue_id}\"]').style.opacity)") > 0.9
            assert page.evaluate("() => parseFloat(document.getElementById('caption').style.opacity)") == 0
        finally:
            browser.close()


# ---------------- 路由 ----------------
pytest.importorskip("fastapi.testclient", reason="需要 fastapi")
pytest.importorskip("multipart", reason="server.main upload routes 需要")

from fastapi.testclient import TestClient  # noqa: E402

from core.project import ProjectStore  # noqa: E402
from server.main import create_app  # noqa: E402
import server.jobs as jobs_mod  # noqa: E402
import server.routes.comics as comics_routes  # noqa: E402
import server.routes.projects as projects_routes  # noqa: E402
from server.jobs import JobStore, get_default_store  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    project_store = ProjectStore(root=tmp_path / "projects")
    comic_store = ComicStore(project_root=tmp_path / "projects")
    jobs_root = tmp_path / "jobs"
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", jobs_root)
    job_store = JobStore(root=jobs_root)
    monkeypatch.setattr(projects_routes, "_default_project_store", project_store)
    monkeypatch.setattr(comics_routes, "_default_comic_store", comic_store)
    app = create_app()
    app.dependency_overrides[projects_routes.get_default_project_store] = lambda: project_store
    app.dependency_overrides[comics_routes.get_default_comic_store] = lambda: comic_store
    app.dependency_overrides[get_default_store] = lambda: job_store
    with TestClient(app) as c:
        yield c, comic_store, job_store


def _bootstrap(c: TestClient, comic_store: ComicStore, *, with_assets: bool = True) -> None:
    assert c.post("/projects", json={"project_id": "course", "title": "課程"}).status_code == 201
    _episode(comic_store, with_assets=with_assets)


@_needs_ffmpeg
def test_video_route_creates_job_and_reaches_done(client):
    c, comic_store, job_store = client
    _bootstrap(c, comic_store)
    r = c.post("/projects/course/comics/episodes/W01/video",
               json={"version": "v0.1", "mock": True, "fps": 5, "width": 320, "height": 180})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["preview_label"].startswith("草稿預覽")
    job_id = body["job_id"]

    # TestClient 的背景 task 在同一 loop; 輪詢到 DONE / FAILED
    for _ in range(200):
        rec = c.get(f"/jobs/{job_id}").json()
        if rec["state"] in ("done", "failed"):
            break
        import time
        time.sleep(0.05)
    assert rec["state"] == "done", rec.get("error")
    names = {a["name"] for a in rec["artifacts"]}
    assert "W01_v0.1_motion_comic.mp4" in names and "W01_v0.1_motion_comic.srt" in names
    ep = comic_store.get_episode("course", "W01", "v0.1")
    assert ep.exports["video"].endswith("motion_comic.mp4")
    assert (comic_store.episode_dir("course", "W01", "v0.1") / ep.exports["video_html"]).exists()
    # 影片可從 episode exports 下載
    assert c.get(body["download_url"]).status_code == 200


def test_video_route_rejects_missing_assets(client):
    c, comic_store, _ = client
    _bootstrap(c, comic_store, with_assets=False)
    r = c.post("/projects/course/comics/episodes/W01/video", json={"mock": True})
    assert r.status_code == 422
    assert c.post("/projects/course/comics/episodes/NOPE/video", json={"mock": True}).status_code == 404
