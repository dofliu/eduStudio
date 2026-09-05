"""ComicStore file-first、版本與 evidence gate 測試。"""
from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from core.comics import (
    Character,
    ComicConflictError,
    ComicGateError,
    ComicPage,
    ComicStore,
    Dialogue,
    EpisodeManifest,
    EvidenceSource,
    GlossaryTerm,
    QARecord,
    REQUIRED_QA_GATES,
    Series,
)


def _png(color: str = "#173042") -> bytes:
    image = Image.new("RGB", (320, 450), color)
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def _store(tmp_path) -> ComicStore:
    return ComicStore(tmp_path / "projects")


def _series(store: ComicStore) -> Series:
    return store.create_series(
        Series(
            project_id="course",
            series_id="wind_lab",
            title="海風值班日誌",
            characters=[
                Character(
                    character_id="dofu",
                    name="杜夫",
                    role="O&M Lead",
                    visual_lock="adult East Asian male, short black hair, navy coverall",
                )
            ],
            glossary=[GlossaryTerm(term="Evidence gate", definition="先驗證證據，再形成結論。")],
        )
    )


def _episode(store: ComicStore, pages: int = 2) -> EpisodeManifest:
    _series(store)
    return store.create_episode(
        EpisodeManifest(
            project_id="course",
            series_id="wind_lab",
            story_id="W01_C01_test",
            version="v0.1",
            title="測試故事",
            page_count=pages,
            story_brief="以 evidence 判斷異常",
            learning_objectives=["區分 alarm 與 root cause"],
            characters=["dofu"],
        )
    )


def _ready_episode(store: ComicStore) -> EpisodeManifest:
    episode = _episode(store)
    evidence = EvidenceSource(
        source_id="src_1",
        title="課程教材",
        supported_claims=["alarm 需要交叉驗證"],
        limits=["不是現場操作授權"],
    )
    episode = store.add_evidence("course", episode.story_id, episode.version, evidence)
    pages = [
        ComicPage(
            page_no=index,
            beat="Evidence gate" if index == 1 else "Debrief",
            scene_id=f"scene_{index:02d}",
            scene_description="控制室檢視 historian trend",
            camera="medium shot",
            learning_point="不能用單一 alarm 直接判定 root cause",
            evidence_ids=["src_1"],
            dialogues=[Dialogue(dialogue_id=f"p{index}_d1", speaker_id="dofu", text="先保留證據，再下結論。")],
            image_prompt="No text. Adult engineer reviews evidence in a control room.",
            alt_text="杜夫在控制室檢視趨勢資料。",
        )
        for index in (1, 2)
    ]
    episode = store.update_episode("course", episode.story_id, episode.version, {"pages": pages, "state": "STORYBOARD"})
    for page in pages:
        episode = store.attach_asset(
            "course",
            episode.story_id,
            episode.version,
            filename=f"scene_{page.page_no}.png",
            data=_png(),
            kind="scene",
            provenance="gemini:test-image-model",
            asset_id=f"scene_{page.page_no}",
            status="FINAL",
        )
        episode = store.set_page_asset("course", episode.story_id, episode.version, page.page_no, f"scene_{page.page_no}")
    for gate in REQUIRED_QA_GATES:
        episode = store.add_qa_record(
            "course",
            episode.story_id,
            episode.version,
            QARecord(gate=gate, result="PASS", evidence=f"人工檢查 {gate}", reviewer="teacher"),
        )
    return episode


def test_file_first_package_and_revision_history(tmp_path) -> None:
    store = _store(tmp_path)
    episode = _episode(store)
    root = store.episode_dir("course", episode.story_id, episode.version)
    assert (root / "manifest.json").is_file()
    assert (root / "source" / "storyboard.md").is_file()

    updated = store.update_episode("course", episode.story_id, episode.version, {"story_summary": "新摘要"})
    assert updated.revision == 2
    assert (root / "history" / "manifest_r0001.json").is_file()


def test_prompt_composer_includes_character_and_no_text_rule(tmp_path) -> None:
    store = _store(tmp_path)
    episode = _episode(store, pages=1)
    page = ComicPage(
        page_no=1,
        scene_description="杜夫在機艙檢視 sensor trend",
        learning_point="先確認 asset identity",
        dialogues=[Dialogue(dialogue_id="d1", speaker_id="dofu", text="先對資產編號。")],
        alt_text="杜夫檢查資產編號。",
    )
    store.update_episode("course", episode.story_id, episode.version, {"pages": [page]})
    composed = store.compose_prompts("course", episode.story_id, episode.version)
    prompt = composed.pages[0].image_prompt
    assert "adult East Asian male" in prompt
    assert "No generated captions" in prompt
    assert "34–38%" in prompt


def test_mock_asset_is_fail_closed(tmp_path) -> None:
    store = _store(tmp_path)
    episode = _episode(store, pages=1)
    page = ComicPage(
        page_no=1,
        scene_description="mock",
        dialogues=[Dialogue(dialogue_id="d", text="mock")],
        image_prompt="mock",
        alt_text="mock",
    )
    store.update_episode("course", episode.story_id, episode.version, {"pages": [page]})
    store.attach_asset(
        "course", episode.story_id, episode.version,
        filename="mock.png", data=_png(), kind="scene", provenance="mock_placeholder", asset_id="mock_scene",
    )
    episode = store.set_page_asset("course", episode.story_id, episode.version, 1, "mock_scene")
    report = store.validate_episode(episode)
    item = next(item for item in report.items if item.check == "asset_provenance")
    assert item.result == "FAIL"
    assert not report.publish_ready


def test_ready_episode_exports_and_publishes(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path)
    episode = _ready_episode(store)
    report = store.validate_episode(episode)
    assert report.result == "PASS" and report.publish_ready

    episode, html_path = store.export_html("course", episode.story_id, episode.version)
    episode, pdf_path = store.export_pdf("course", episode.story_id, episode.version)
    monkeypatch.setattr(store, "_export_docx_word_shapes", lambda *_: (_ for _ in ()).throw(ImportError("no COM")))
    episode, docx_path, mode = store.export_docx("course", episode.story_id, episode.version)
    assert html_path.stat().st_size > 0
    assert "杜夫" in html_path.read_text(encoding="utf-8")
    assert pdf_path.stat().st_size > 0
    assert docx_path.stat().st_size > 0
    assert mode == "editable_table_fallback"

    episode = store.transition("course", episode.story_id, episode.version, "CURRENT")
    with pytest.raises(ComicConflictError):
        store.update_episode("course", episode.story_id, episode.version, {"title": "不可直接改"})
    episode = store.publish("course", episode.story_id, episode.version, published_by="teacher")
    assert episode.releases and episode.releases[-1].public_version == "v0.1"
    archive = store.build_series_archive_html(store.get_series("course", "wind_lab"), [episode])
    assert "測試故事" in archive and "Evidence gate" in archive
    release_id = episode.releases[-1].release_id
    episode = store.withdraw_release("course", episode.story_id, episode.version, release_id)
    assert episode.releases[-1].withdrawn_at is not None


def test_dialogue_layout_is_image_aware_and_manual_coordinates_are_preserved(tmp_path) -> None:
    store = _store(tmp_path)
    episode = _ready_episode(store)
    page = episode.pages[0].model_copy(update={
        "dialogues": [
            Dialogue(dialogue_id="d1", speaker_id="dofu", text="先看左側的低細節留白。"),
            Dialogue(dialogue_id="d2", speaker_id="dofu", text="第二顆泡泡不可與第一顆重疊。"),
        ]
    })
    laid_out = store.resolve_dialogue_layout(episode, page)
    assert len(laid_out) == 2
    assert (laid_out[0].x, laid_out[0].y) != (laid_out[1].x, laid_out[1].y)
    assert all(item.bubble_style == "rounded_callout" for item in laid_out)
    assert all(item.tail_x is not None and item.tail_y is not None for item in laid_out)
    assert store._rect_overlap(
        (laid_out[0].x, laid_out[0].y, laid_out[0].w, laid_out[0].h),
        (laid_out[1].x, laid_out[1].y, laid_out[1].w, laid_out[1].h),
    ) == 0

    manual = Dialogue(
        dialogue_id="manual",
        text="人工定位",
        layout_mode="MANUAL",
        x=0.41,
        y=0.32,
        w=0.27,
        h=0.11,
        tail_x=0.55,
        tail_y=0.70,
    )
    manual_page = page.model_copy(update={"dialogues": [manual]})
    resolved_manual = store.resolve_dialogue_layout(episode, manual_page)[0]
    assert (resolved_manual.x, resolved_manual.y, resolved_manual.w, resolved_manual.h) == (0.41, 0.32, 0.27, 0.11)
    assert (resolved_manual.tail_x, resolved_manual.tail_y) == (0.55, 0.70)

    overflow_page = page.model_copy(update={
        "dialogues": [
            Dialogue(dialogue_id=f"d{i}", speaker_id="dofu", text=f"對白 {i}")
            for i in range(1, 5)
        ]
    })
    resolved_overflow = store.resolve_dialogue_layout(episode, overflow_page)
    assert [item.dialogue_id for item in resolved_overflow] == ["d1", "d2", "d3", "d4"]


def test_speaker_positions_keep_bubbles_off_faces_and_point_tail_at_head(tmp_path) -> None:
    store = _store(tmp_path)
    episode = _ready_episode(store)
    # 杜夫站在左上區 (頭在 x=0.22, y=0.30); 沒有定位時舊演算法偏好左上候選點會壓到臉
    head = (0.22, 0.30)
    page = episode.pages[0].model_copy(update={
        "speaker_positions": {"dofu": list(head)},
        "dialogues": [Dialogue(dialogue_id="d1", speaker_id="dofu", text="泡泡不可以蓋到我的臉。")],
    })
    bubble = store.resolve_dialogue_layout(episode, page)[0]
    face = (head[0] - 0.085, head[1] - 0.10, 0.17, 0.24)
    assert store._rect_overlap((bubble.x, bubble.y, bubble.w, bubble.h), face) == 0
    assert (bubble.tail_x, bubble.tail_y) == head          # 尾巴直指頭部
    assert abs((bubble.x + bubble.w / 2) - head[0]) < 0.35  # 泡泡靠近說話者

    # 兩個角色都有定位: 各自的泡泡都不能蓋到任何一張臉
    two = episode.pages[0].model_copy(update={
        "speaker_positions": {"dofu": [0.30, 0.55], "mei": [0.70, 0.50]},
        "dialogues": [
            Dialogue(dialogue_id="a", speaker_id="dofu", text="先保留證據。"),
            Dialogue(dialogue_id="b", speaker_id="mei", text="油溫也在爬。"),
        ],
    })
    laid = store.resolve_dialogue_layout(episode, two)
    faces = [(0.30 - 0.085, 0.55 - 0.10, 0.17, 0.24), (0.70 - 0.085, 0.50 - 0.10, 0.17, 0.24)]
    for item in laid:
        for zone in faces:
            assert store._rect_overlap((item.x, item.y, item.w, item.h), zone) == 0
    assert store._rect_overlap((laid[0].x, laid[0].y, laid[0].w, laid[0].h), (laid[1].x, laid[1].y, laid[1].w, laid[1].h)) == 0


def test_speaker_positions_schema_validation() -> None:
    ComicPage(page_no=1, speaker_positions={"dofu": [0.2, 0.3]})
    import pytest as _pytest
    with _pytest.raises(ValueError):
        ComicPage(page_no=1, speaker_positions={"dofu": [1.2, 0.3]})
    with _pytest.raises(ValueError):
        ComicPage(page_no=1, speaker_positions={"dofu": [0.2]})


def test_hold_needs_reason_and_current_gate_cannot_be_skipped(tmp_path) -> None:
    store = _store(tmp_path)
    episode = _episode(store)
    with pytest.raises(ComicGateError):
        store.transition("course", episode.story_id, episode.version, "HOLD")
    with pytest.raises(ComicGateError):
        store.transition("course", episode.story_id, episode.version, "CURRENT")
    held = store.transition("course", episode.story_id, episode.version, "HOLD", "等待 technical source")
    assert held.state == "HOLD"


def test_fork_preserves_old_version(tmp_path) -> None:
    store = _store(tmp_path)
    episode = _ready_episode(store)
    forked = store.fork_version("course", episode.story_id, "v0.1", "v0.2")
    assert forked.version == "v0.2"
    assert forked.exports == {}
    assert all(store.resolve_asset(forked, asset.asset_id).is_file() for asset in forked.assets)
    assert store.get_episode("course", episode.story_id, "v0.1").version == "v0.1"


def test_discover_and_import_existing_package_without_touching_origin(tmp_path) -> None:
    origin = tmp_path / "W11_C01_demo_v0.1"
    source = origin / "source"
    assets = origin / "assets"
    source.mkdir(parents=True)
    assets.mkdir()
    (source / "storyboard.md").write_text(
        "# 《既有故事》2 頁 storyboard\n\nLearning objective：辨識證據。\n\n"
        "| 頁 | 標題／場景 | 技術記憶點 | 視覺與泡泡留白 |\n|---|---|---|---|\n"
        "| 01 | Hook／控制室 | 先看 timestamp | 右上留白 |\n"
        "| 02 | Debrief／會議室 | 不用單一 alarm 結案 | 左上留白 |\n",
        encoding="utf-8",
    )
    (source / "dialogue_script.md").write_text(
        "# 《既有故事》對白\n\n## P01｜Hook\n- 杜夫：先保存證據。\n- 小櫻：再比對趨勢。\n\n"
        "## P02｜Debrief\n- 杜夫：單一 alarm 不是 root cause。\n",
        encoding="utf-8",
    )
    (source / "image_prompts.md").write_text(
        "# prompts\n\n## CONTINUITY LOCK\nNo text.\n\n"
        "## Scene 01｜Control room (P01)\nAdult engineers in control room.\n\n"
        "## Scene 02｜Debrief (P02)\nAdult engineers debrief.\n",
        encoding="utf-8",
    )
    (source / "technical_sources.md").write_text(
        "# sources\n\n## SOURCE\n\n1. Example Course Manual. Evidence workflow.  \n   https://example.edu/manual\n\n"
        "## INFERENCE FOR TEACHING\n- teaching only\n",
        encoding="utf-8",
    )
    (source / "revision_notes.md").write_text("# revisions\n", encoding="utf-8")
    (source / "qa_report.md").write_text("# QA\n\n狀態：PASS\n", encoding="utf-8")
    (assets / "scene_01_a.png").write_bytes(_png("#111111"))
    (assets / "scene_02_b.png").write_bytes(_png("#222222"))

    store = _store(tmp_path / "target")
    _series(store)
    before = {path.relative_to(origin).as_posix(): path.read_bytes() for path in origin.rglob("*") if path.is_file()}
    report = store.discover_package(origin)
    assert (report.page_count, report.scene_count, report.dialogue_count) == (2, 2, 3)
    assert report.historical_qa_claim == "PASS"

    episode = store.import_package("course", "wind_lab", origin)
    assert episode.state == "HOLD"
    assert len(episode.pages) == 2 and all(page.image_asset_id for page in episode.pages)
    assert len(episode.pages[0].dialogues) == 2
    assert episode.external_origin == str(origin.resolve())
    after = {path.relative_to(origin).as_posix(): path.read_bytes() for path in origin.rglob("*") if path.is_file()}
    assert before == after
