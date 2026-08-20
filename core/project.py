"""Project 薄層 + 磁碟持久化（eduStudio 合併 PR-M1，原 PR-U3a/U3b，MERGE_PLAN §3 Phase A）。

為什麼存在：編排層要在既有 autoSolver JobStore 之上「加一層 Project」管 project_id
生命週期、來源（sources）與產出（artifacts）。但**不重造 JobStore** —— jobs[] 只存
autoSolver JobRecord.id 字串，真正的 job 狀態仍由 server/jobs.py 的 JobStore 持有。

設計取向（仿 autoSolver JobStore 風格）:
- 每個 Project 一個資料夾 {root}/{pid}/，狀態檔 project.json（單一真相、人可讀）。
- threading.RLock 保護所有讀寫 —— FastAPI 多 worker / 背景任務可能併發改同一 store；
  用可重入鎖讓 add_source→save 這種「鎖內再呼叫鎖方法」不自我死鎖。
- project_id 做 safe_id 過濾防 path traversal（仿 autoSolver 對 sec_id 的處理）：
  外部傳進來的 id 會直接拼進檔案系統路徑，不過濾則 "../../etc" 之類可逃出 root。

canonical 語言碼 = 'zh-TW'（BCP-47 連字號）；底線式只在 translateGemma 邊界出現。
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from core import config
from core.glossary import Glossary, glossary_path_for, load_glossary, save_glossary

# ---------- 受控字彙（對齊 MERGE_PLAN §7 / DESIGN_SPEC §5）----------
# 為什麼用 Literal 而非自由字串：schema 的列舉欄位若放任意字串，打字錯（如 "vidoe"）
# 會靜默寫進 json，下游分流 produced_by/kind 時才爆；Literal 讓 pydantic 在「寫入當下」
# 就擋掉，錯誤早暴露。
SourceType = Literal["exam_pdf", "slides_pdf", "repo", "document", "url", "youtube"]
ArtifactKind = Literal["infographic", "deck", "video", "srt", "image", "comic", "pdf", "docx", "html"]
ProducedBy = Literal["infoCard", "autoSolver", "translateGemma", "eduStudio"]
# artifacts[].state 沿 autoSolver JobState 語意（exam_pdf 仍強制 review）。
ArtifactState = Literal["draft", "awaiting_review", "approved", "published"]

_DEFAULT_ARTIFACT_STATE: ArtifactState = "draft"


# ---------- safe_id：防 path traversal ----------
# 只留字母/數字/底線/連字號；其餘（含 '/', '\\', '.', 空白）一律轉底線。
# 為什麼這樣切：project_id 會成為資料夾名，"../x" 或 "a/b" 會逃出 root 或建出非預期層級。
_UNSAFE_ID_CHARS = re.compile(r"[^A-Za-z0-9_-]+")


def safe_id(raw: str) -> str:
    """把任意字串清成可當資料夾名的安全 id（防 path traversal）。

    為什麼回傳值還要再驗空/全點：過濾後若變空字串（例如全是 '../'），或變成
    '.'/'..' 這類特殊目錄名，仍可能害到檔案系統，故 fallback 成隨機 id。
    """
    cleaned = _UNSAFE_ID_CHARS.sub("_", (raw or "").strip())
    cleaned = cleaned.strip("_")
    # 全被過濾掉、或變成檔案系統特殊名 → 給個隨機 id 兜底，絕不回危險值。
    if not cleaned or cleaned in {".", ".."}:
        return f"project_{uuid.uuid4().hex[:8]}"
    return cleaned


# ---------- 資料模型（pydantic，欄位對齊 §7 schema）----------
class Source(BaseModel):
    """一筆素材來源（exam/slides/repo/...）。indexed 是 Phase 2 RAG 才會翻 true。"""

    source_id: str
    type: SourceType
    path_or_url: str
    lang: str = config.CANONICAL_LANG
    indexed: bool = False


class Artifact(BaseModel):
    """一個產出物（圖卡/簡報/影片/字幕/圖）。state 沿 JobState 語意。

    為什麼 links 用固定鍵 dict 而非自由欄位：§7 只定義 youtube/file 兩個落點，
    用 default 容納 null（R4：缺值合法，不可當必填查崩）。citations 是 Phase 2 才填。
    """

    artifact_id: str
    kind: ArtifactKind
    produced_by: ProducedBy
    state: ArtifactState = _DEFAULT_ARTIFACT_STATE
    lang: str = config.CANONICAL_LANG
    citations: list[str] = Field(default_factory=list)
    links: dict[str, str | None] = Field(
        default_factory=lambda: {"youtube": None, "file": None}
    )


class Project(BaseModel):
    """Project 聚合根：sources + jobs(只存 id 字串) + artifacts。

    jobs[] 只存 autoSolver JobRecord.id 字串 —— 不重造 JobStore，真正 job 狀態在
    server/jobs.py 的 JobStore（DESIGN_SPEC §5）。
    """

    project_id: str
    title: str
    target_languages: list[str] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    jobs: list[str] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)


class ProjectNotFoundError(KeyError):
    """查無此 project_id（get 不存在的 pid）。"""


# ---------- 持久化 store ----------
_PROJECT_FILE = "project.json"


class ProjectStore:
    """Project 的磁碟持久化 store（仿 autoSolver JobStore：每物件一資料夾 + RLock）。

    狀態檔落 {root}/{safe_pid}/project.json。所有公開方法在 RLock 內完成「讀檔→改→寫檔」，
    讓併發呼叫不互相覆蓋；RLock 可重入，故 add_source 內部再呼 _save 不死鎖。
    """

    def __init__(self, root: Path | str = config.PROJECTS_DIR) -> None:
        # root 參數化：預設用 config.PROJECTS_DIR，測試可傳 tmp_path 隔離（不污染真實 projects/）。
        self.root = Path(root)
        self._lock = threading.RLock()

    # ----- 路徑 helper -----
    def _dir(self, pid: str) -> Path:
        # pid 已是 safe_id 後的值；組路徑前不再信任外部輸入。
        return self.root / pid

    def _file(self, pid: str) -> Path:
        return self._dir(pid) / _PROJECT_FILE

    # ----- 磁碟讀寫（私有，呼叫端須已持鎖）-----
    def _save(self, project: Project) -> None:
        """把 Project 寫成 project.json。為什麼 ensure_ascii=False：中文標題直接落字面,
        檔案人可讀；indent 讓 diff/手改友善。"""
        d = self._dir(project.project_id)
        d.mkdir(parents=True, exist_ok=True)
        self._file(project.project_id).write_text(
            json.dumps(project.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self, pid: str) -> Project | None:
        f = self._file(pid)
        if not f.is_file():
            return None
        # model_validate 會順帶驗 Literal/型別，磁碟上被手改壞的檔在 reload 時即爆。
        return Project.model_validate(json.loads(f.read_text(encoding="utf-8")))

    # ----- 公開 API -----
    def create(
        self,
        project_id: str,
        title: str,
        target_languages: list[str] | None = None,
    ) -> Project:
        """建立並落盤一個 Project。project_id 先過 safe_id 防 traversal。

        已存在同 pid 則丟 FileExistsError（不靜默覆蓋既有資料）。
        """
        pid = safe_id(project_id)
        with self._lock:
            if self._file(pid).is_file():
                raise FileExistsError(f"project 已存在: {pid}")
            project = Project(
                project_id=pid,
                title=title,
                target_languages=list(target_languages or []),
            )
            self._save(project)
            return project

    def get(self, project_id: str) -> Project:
        """讀單一 Project；不存在丟 ProjectNotFoundError。"""
        pid = safe_id(project_id)
        with self._lock:
            project = self._load(pid)
            if project is None:
                raise ProjectNotFoundError(pid)
            return project

    def list(self) -> list[Project]:
        """列出 root 下所有 Project（依 project_id 排序，輸出穩定）。

        為什麼略過讀不出來的子資料夾：root 下可能混入非 project 目錄或壞檔，
        list 不該因單一壞檔整批崩 —— 安靜跳過，由 get 單筆時才嚴格報錯。
        """
        with self._lock:
            if not self.root.is_dir():
                return []
            out: list[Project] = []
            for child in sorted(self.root.iterdir()):
                if not child.is_dir():
                    continue
                try:
                    project = self._load(child.name)
                except (json.JSONDecodeError, ValueError):
                    continue
                if project is not None:
                    out.append(project)
            return out

    def add_source(
        self,
        project_id: str,
        *,
        type: SourceType,
        path_or_url: str,
        lang: str = config.CANONICAL_LANG,
        source_id: str | None = None,
        indexed: bool = False,
    ) -> Source:
        """追加一筆 source 並落盤；回傳新建的 Source。source_id 未給則自動配。"""
        with self._lock:
            project = self.get(project_id)
            sid = source_id or f"src_{uuid.uuid4().hex[:8]}"
            source = Source(
                source_id=sid,
                type=type,
                path_or_url=path_or_url,
                lang=lang,
                indexed=indexed,
            )
            project.sources.append(source)
            self._save(project)
            return source

    def remove_source(self, project_id: str, source_id: str) -> bool:
        """移除一筆 source 並落盤；移除成功回 True，找不到該 source_id 回 False。"""
        with self._lock:
            project = self.get(project_id)
            before = len(project.sources)
            project.sources = [s for s in project.sources if s.source_id != source_id]
            if len(project.sources) == before:
                return False
            self._save(project)
            return True

    def add_artifact(
        self,
        project_id: str,
        *,
        kind: ArtifactKind,
        produced_by: ProducedBy,
        state: ArtifactState = _DEFAULT_ARTIFACT_STATE,
        lang: str = config.CANONICAL_LANG,
        artifact_id: str | None = None,
        citations: list[str] | None = None,
        links: dict[str, str | None] | None = None,
    ) -> Artifact:
        """追加一筆 artifact 並落盤；回傳新建的 Artifact。artifact_id 未給則自動配。"""
        with self._lock:
            project = self.get(project_id)
            aid = artifact_id or f"art_{uuid.uuid4().hex[:8]}"
            artifact = Artifact(
                artifact_id=aid,
                kind=kind,
                produced_by=produced_by,
                state=state,
                lang=lang,
                citations=list(citations or []),
                # links 未給才用 model 預設（youtube/file 皆 null）；給了就尊重呼叫端。
                **({"links": links} if links is not None else {}),
            )
            project.artifacts.append(artifact)
            self._save(project)
            return artifact

    def add_job(self, project_id: str, job_id: str) -> Project:
        """把 autoSolver JobRecord.id 字串掛進 jobs[]（不重造 JobStore）。

        idempotent：同 job_id 重複 add 不重複塞（避免清單膨脹）。
        """
        with self._lock:
            project = self.get(project_id)
            if job_id not in project.jobs:
                project.jobs.append(job_id)
                self._save(project)
            return project

    # ----- 課程術語表 glossary（F9-2：一課一 glossary，落 {pid}/glossary.json）-----
    # 為什麼跟 project.json 分檔而非塞進 Project schema：glossary 是獨立、可人手編的大塊
    # 資料（術語可上百條），跟 project 生命週期不同步——常單獨重編；分檔讓兩者各自 diff、
    # 避免每次改一條術語就重寫整個 project.json。路徑慣例由 core.glossary 統一持有。
    def get_glossary(self, project_id: str) -> Glossary | None:
        """讀該課的 glossary；無 glossary.json 回 None（沿 load_glossary 寬容語意）。

        先 get() 驗 project 存在（不存在丟 ProjectNotFoundError）——glossary 必依附於
        某個 project，對不存在的 pid 讀 glossary 是呼叫端的錯，不靜默回 None 掩蓋。
        """
        with self._lock:
            self.get(project_id)  # 驗存在；pid 在內部會再過 safe_id
            return load_glossary(glossary_path_for(self._dir(safe_id(project_id))))

    def save_glossary(self, project_id: str, glossary: Glossary) -> Glossary:
        """把該課 glossary 寫進 {pid}/glossary.json 並回傳；project 須已存在。"""
        with self._lock:
            self.get(project_id)  # 驗存在，避免在無主資料夾留孤兒 glossary
            path = glossary_path_for(self._dir(safe_id(project_id)))
            save_glossary(glossary, path)
            return glossary
