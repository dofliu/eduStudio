"""core.project ProjectStore 持久化測試（eduStudio 合併 PR-M1，原 PR-U3a/U3b）。

驗收點：
- create→get round-trip、list。
- add_source / add_artifact 落盤後「重建 store reload」不掉資料（真磁碟持久化）。
- 兩個 project 互相隔離（各自資料夾，不串資料）。
- 非法 project_id（path traversal）被 safe_id 過濾，不逃出 root。

用 tmp_path 當 root：每個測試獨立資料夾，不污染真實 projects/。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core import config
from core.project import (
    ProjectNotFoundError,
    ProjectStore,
    safe_id,
)


def _store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(root=tmp_path)


def test_create_get_round_trip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = store.create(
        "course_statics_2026", "靜力學 2026", ["zh-TW", "en-US"]
    )
    assert created.project_id == "course_statics_2026"
    assert created.title == "靜力學 2026"
    assert created.target_languages == ["zh-TW", "en-US"]
    # round-trip：get 回的內容與 create 一致。
    got = store.get("course_statics_2026")
    assert got == created
    # 新建 project 各 list 皆空（default_factory，不互相共用同一 list 實例）。
    assert got.sources == []
    assert got.jobs == []
    assert got.artifacts == []


def test_create_persists_file_to_disk(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create("p1", "T1")
    # 狀態檔確實落在 {root}/{pid}/project.json。
    assert (tmp_path / "p1" / "project.json").is_file()


def test_get_missing_raises(tmp_path: Path) -> None:
    store = _store(tmp_path)
    with pytest.raises(ProjectNotFoundError):
        store.get("nope")


def test_create_duplicate_raises(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create("dup", "T")
    # 不靜默覆蓋既有 project 資料。
    with pytest.raises(FileExistsError):
        store.create("dup", "T2")


def test_list_sorted_and_isolated(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create("b_proj", "B")
    store.create("a_proj", "A")
    listed = store.list()
    # 依 project_id 排序，輸出穩定。
    assert [p.project_id for p in listed] == ["a_proj", "b_proj"]


def test_list_empty_when_root_missing(tmp_path: Path) -> None:
    # root 還沒任何 project（甚至不存在）時 list 回空，不崩。
    store = ProjectStore(root=tmp_path / "not_created_yet")
    assert store.list() == []


def test_add_source_persists_across_reload(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create("p", "T")
    src = store.add_source(
        "p",
        type="exam_pdf",
        path_or_url="/data/ch3.pdf",
        lang="zh-TW",
        source_id="src_ch3",
    )
    assert src.source_id == "src_ch3"
    assert src.indexed is False  # Phase 2 才翻 true
    # 關鍵：用「新的 store 實例」reload，證明資料是落磁碟而非僅存記憶體。
    reloaded = ProjectStore(root=tmp_path).get("p")
    assert len(reloaded.sources) == 1
    assert reloaded.sources[0].path_or_url == "/data/ch3.pdf"
    assert reloaded.sources[0].type == "exam_pdf"


def test_add_artifact_persists_across_reload(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create("p", "T")
    art = store.add_artifact(
        "p",
        kind="video",
        produced_by="autoSolver",
        artifact_id="art_v1",
    )
    # 預設 state 沿 JobState 語意起點 draft；links 兩鍵皆 null（R4 缺值合法）。
    assert art.state == "draft"
    assert art.links == {"youtube": None, "file": None}
    assert art.citations == []
    reloaded = ProjectStore(root=tmp_path).get("p")
    assert len(reloaded.artifacts) == 1
    assert reloaded.artifacts[0].artifact_id == "art_v1"
    assert reloaded.artifacts[0].kind == "video"
    assert reloaded.artifacts[0].produced_by == "autoSolver"


def test_add_artifact_custom_links_and_state(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create("p", "T")
    store.add_artifact(
        "p",
        kind="deck",
        produced_by="infoCard",
        state="awaiting_review",
        links={"youtube": "yt123", "file": "/out/d.pptx"},
        citations=["src_ch3#p12"],
    )
    reloaded = ProjectStore(root=tmp_path).get("p")
    a = reloaded.artifacts[0]
    assert a.state == "awaiting_review"
    assert a.links == {"youtube": "yt123", "file": "/out/d.pptx"}
    assert a.citations == ["src_ch3#p12"]


def test_jobs_store_only_id_strings_idempotent(tmp_path: Path) -> None:
    # jobs[] 只存 autoSolver job id 字串（不重造 JobStore）；重複 add 不膨脹。
    store = _store(tmp_path)
    store.create("p", "T")
    store.add_job("p", "job_abc")
    store.add_job("p", "job_abc")  # idempotent
    store.add_job("p", "job_def")
    reloaded = ProjectStore(root=tmp_path).get("p")
    assert reloaded.jobs == ["job_abc", "job_def"]
    assert all(isinstance(j, str) for j in reloaded.jobs)


def test_two_projects_isolated(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create("p1", "T1")
    store.create("p2", "T2")
    store.add_source("p1", type="url", path_or_url="http://a")
    store.add_artifact("p2", kind="image", produced_by="infoCard")
    p1 = store.get("p1")
    p2 = store.get("p2")
    # p1 有 source 無 artifact；p2 反之 —— 互不串資料。
    assert len(p1.sources) == 1 and len(p1.artifacts) == 0
    assert len(p2.sources) == 0 and len(p2.artifacts) == 1


def test_default_root_is_config_projects_dir() -> None:
    # 不傳 root 時預設用 config.PROJECTS_DIR（集中設定，硬規則 #5）。
    assert ProjectStore().root == config.PROJECTS_DIR


# ---------- safe_id：path traversal 防護 ----------
@pytest.mark.parametrize(
    "raw",
    ["../evil", "../../etc/passwd", "a/b/c", "a\\b", "  ", "...", "."],
)
def test_safe_id_blocks_traversal(raw: str) -> None:
    sid = safe_id(raw)
    # 過濾後不得含路徑分隔字元，也不得是 '.'/'..' 特殊目錄名。
    assert "/" not in sid
    assert "\\" not in sid
    assert sid not in {".", ".."}
    assert sid != ""


def test_illegal_project_id_filtered_stays_in_root(tmp_path: Path) -> None:
    store = _store(tmp_path)
    project = store.create("../../escape", "惡意")
    # safe_id 後的 pid 不含路徑分隔，資料夾仍落在 root 之內（沒逃出去）。
    pid = project.project_id
    assert "/" not in pid and "\\" not in pid
    project_dir = tmp_path / pid
    assert project_dir.is_file() is False  # 是目錄不是檔
    assert (project_dir / "project.json").is_file()
    # 解析後的真實路徑確實在 tmp_path 底下（沒 traversal 逃出 root）。
    assert tmp_path.resolve() in (project_dir.resolve()).parents

    # 同一個非法 id 再 get 得回同一 project（safe_id 對同輸入穩定）。
    assert store.get("../../escape").title == "惡意"


def test_invalid_source_type_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create("p", "T")
    # Literal 守住列舉欄位：打字錯的 type 在寫入當下即被 pydantic 擋下。
    with pytest.raises(Exception):
        store.add_source("p", type="bogus_type", path_or_url="x")  # type: ignore[arg-type]


# ---------- 課程術語表 glossary（F9-2：一課一 glossary）----------
def test_get_glossary_none_when_no_file(tmp_path: Path) -> None:
    # project 存在但還沒建 glossary.json → 回 None（寬容語意，不崩）。
    store = _store(tmp_path)
    store.create("p", "材料力學")
    assert store.get_glossary("p") is None


def test_save_glossary_persists_across_reload(tmp_path: Path) -> None:
    from core.glossary import Glossary, GlossaryEntry

    store = _store(tmp_path)
    store.create("p", "材料力學")
    g = Glossary(
        course="材料力學",
        entries=[
            GlossaryEntry(
                term="ω_n",
                reading="自然頻率",
                translations={"en": "natural frequency"},
                aliases=["wn", "ωn"],
            ),
            GlossaryEntry(term="PID", expansion="比例-積分-微分"),
        ],
    )
    store.save_glossary("p", g)
    # 落在 {pid}/glossary.json，跟 project.json 同資料夾、分檔。
    assert (tmp_path / "p" / "glossary.json").is_file()
    # 用新 store 實例 reload，證明是落磁碟而非僅記憶體。
    reloaded = ProjectStore(root=tmp_path).get_glossary("p")
    assert reloaded is not None
    assert reloaded.course == "材料力學"
    assert reloaded.entries[0].term == "ω_n"
    assert reloaded.entries[0].translations == {"en": "natural frequency"}
    assert reloaded.entries[1].expansion == "比例-積分-微分"


def test_glossary_isolated_per_project(tmp_path: Path) -> None:
    from core.glossary import Glossary, GlossaryEntry

    store = _store(tmp_path)
    store.create("p1", "材力")
    store.create("p2", "自控")
    store.save_glossary("p1", Glossary(course="材力", entries=[GlossaryEntry(term="應力")]))
    # p1 有 glossary、p2 沒有 —— 互不串。
    assert store.get_glossary("p1") is not None
    assert store.get_glossary("p2") is None


def test_glossary_requires_existing_project(tmp_path: Path) -> None:
    from core.glossary import Glossary

    store = _store(tmp_path)
    # 對不存在的 pid 讀/寫 glossary 都丟 ProjectNotFoundError（glossary 必依附 project）。
    with pytest.raises(ProjectNotFoundError):
        store.get_glossary("ghost")
    with pytest.raises(ProjectNotFoundError):
        store.save_glossary("ghost", Glossary(course="無"))
