"""Repo adapter — 把 folder/repo 掃成統一的 raw_content。

設計目標:
- 只挑值得餵 LLM 的檔案: README / STATUS / 入口檔 / 主要 source 檔
- 跳過 binary、build artifact、deps 目錄、隱藏檔
- 限制總檔數 (預設 50) 與單檔 size (預設 80KB), 避免 token 爆炸
- file tree 跟 key file content 各自輸出, outliner / scriptor 各自取需要的

raw_content schema:
{
  "source_kind": "repo",
  "root_name": "autoSolverVideo",
  "tree": "文字版檔樹 (限頂層 2~3 層)",
  "lang_stats": {"python": 5132, "markdown": 800},
  "primary_language": "python",
  "key_files": [
    {"path": "README.md", "content": "...", "bytes": 1200, "kind": "doc"},
    {"path": "core/__init__.py", "content": "...", "bytes": 800, "kind": "code"},
    ...
  ],
  "skipped_files": [
    {"path": "videos/big.mp4", "reason": "binary"},
  ]
}
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


# ---------- 常數 ----------

# 資料夾忽略清單 (以名稱完全比對, 任一層級命中就跳過)
SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".venv", "venv", "env",
    "dist", "build", "out", "target", ".next", ".nuxt", ".cache",
    ".idea", ".vscode",
    "videos", "videos_test", "output", "work", "slides",  # autoSolverVideo 自身產物
    "jobs",  # server runtime
    "exams",  # 考卷檔案夾, 不算 repo 內容
    "pdfs", "photos", "voices",  # 人類資源檔
})

# 副檔名分類 — 只把 code/doc/config 餵給 LLM, 其他 (binary 為主) 一律 skip
EXT_KIND = {
    # docs
    ".md": "doc", ".rst": "doc", ".txt": "doc",
    # config
    ".yaml": "config", ".yml": "config", ".json": "config", ".toml": "config",
    ".ini": "config", ".cfg": "config", ".env.example": "config",
    # code (覆蓋常見語言)
    ".py": "code", ".pyi": "code",
    ".js": "code", ".jsx": "code", ".ts": "code", ".tsx": "code", ".mjs": "code",
    ".go": "code", ".rs": "code", ".java": "code", ".kt": "code",
    ".c": "code", ".h": "code", ".cpp": "code", ".hpp": "code", ".cc": "code",
    ".cs": "code", ".rb": "code", ".php": "code", ".swift": "code",
    ".sh": "code", ".bash": "code", ".ps1": "code",
    ".st": "code",  # IEC 61131-3 Structured Text (劉老師教學用)
    ".sql": "code",
    ".html": "code", ".css": "code", ".scss": "code", ".vue": "code", ".svelte": "code",
}

# 不論副檔名,看到這些檔名直接吸 (高訊息密度)
ALWAYS_INCLUDE_NAMES = frozenset({
    "README", "README.md", "README.rst", "README.txt",
    "CLAUDE.md", "STATUS.yaml", "ROADMAP.md", "TODO.md", "CHANGELOG.md",
    "package.json", "pyproject.toml", "requirements.txt", "Pipfile",
    "Cargo.toml", "go.mod", "pom.xml", "build.gradle",
    "Dockerfile", "docker-compose.yml", "Makefile",
    ".gitignore",
})

# 單檔最大讀取 size (bytes) — 超過就 truncate 並標記
DEFAULT_MAX_FILE_BYTES = 80 * 1024
# 總檔數上限 (PR-2b-i 限制)
DEFAULT_MAX_FILES = 50
# 檔樹輸出深度
DEFAULT_TREE_DEPTH = 3
# tree 字串最大長度 (太長 LLM 會塞不下)
DEFAULT_TREE_MAX_CHARS = 4000


# ---------- 資料結構 ----------

@dataclass
class KeyFile:
    path: str       # 相對 repo root, posix 風格
    content: str
    bytes: int
    kind: str       # "doc" | "code" | "config"
    truncated: bool = False


@dataclass
class SkippedFile:
    path: str
    reason: str


# ---------- 內部工具 ----------

def _is_probably_binary(p: Path, peek: int = 4096) -> bool:
    """讀檔頭判斷 binary。比 file extension 更可靠 (有些 .txt 是 GBK 二進位)。

    啟發式: 樣本內 NUL byte 即視為 binary。對純文字幾乎不會誤判。
    """
    try:
        with p.open("rb") as f:
            chunk = f.read(peek)
        return b"\x00" in chunk
    except OSError:
        return True  # 讀不到就當 binary, 安全


def _classify(p: Path) -> str | None:
    """回傳檔案 kind, None 表示不要這個檔。"""
    if p.name in ALWAYS_INCLUDE_NAMES:
        if p.suffix in (".md", ".rst", ".txt"):
            return "doc"
        if p.suffix in (".yaml", ".yml", ".json", ".toml"):
            return "config"
        return "doc"  # README/STATUS/ROADMAP/TODO/CHANGELOG 沒副檔名也算 doc
    return EXT_KIND.get(p.suffix.lower())


def _priority(p: Path, kind: str) -> int:
    """排序優先序 (大者先選)。讓 README / 入口檔在 50 檔 budget 用完前一定被收。"""
    name = p.name
    if name in ("README.md", "README", "README.rst"):
        return 1000
    if name in ("STATUS.yaml", "CLAUDE.md"):
        return 950
    if name in ("ROADMAP.md", "TODO.md", "CHANGELOG.md"):
        return 900
    if name in ("package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod"):
        return 850
    if name in ("__init__.py", "main.py", "index.js", "index.ts", "app.py", "server.py"):
        return 800
    if kind == "doc":
        return 600
    if kind == "config":
        return 500
    if kind == "code":
        # 越淺層級越高 (root 直接的 .py 通常是入口)
        depth = len(p.parts)
        return max(200, 400 - depth * 20)
    return 100


def _read_text(p: Path, max_bytes: int) -> tuple[str, bool]:
    """讀檔, 超過 max_bytes truncate 並標記。回 (content, truncated)。"""
    raw = p.read_bytes()
    truncated = False
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
        truncated = True
    # 統一 utf-8, decode 失敗就 surrogateescape (極少發生在已 binary-filter 過的檔)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    return text, truncated


def _build_tree(root: Path, max_depth: int, max_chars: int) -> str:
    """產生文字版 tree, 限制深度跟總長度避免炸 token。

    格式採 ascii (不用 unicode 框線), LLM 容易讀且不依賴字型。
    """
    lines: list[str] = [f"{root.name}/"]

    def walk(d: Path, prefix: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        except OSError:
            return
        # 過濾掉 SKIP_DIRS / 隱藏檔
        entries = [e for e in entries if not e.name.startswith(".") or e.name in ALWAYS_INCLUDE_NAMES]
        entries = [e for e in entries if e.name not in SKIP_DIRS]
        for i, e in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "`-- " if is_last else "|-- "
            suffix = "/" if e.is_dir() else ""
            lines.append(f"{prefix}{connector}{e.name}{suffix}")
            # 早期終止: 字數超過上限就停止繼續展開
            if sum(len(l) + 1 for l in lines) > max_chars:
                lines.append(f"{prefix}    ... (tree truncated at {max_chars} chars)")
                return
            if e.is_dir():
                next_prefix = prefix + ("    " if is_last else "|   ")
                walk(e, next_prefix, depth + 1)

    walk(root, "", 1)
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (truncated)"
    return text


# ---------- Public API ----------

def scan_repo(
    repo_path: Path,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    tree_depth: int = DEFAULT_TREE_DEPTH,
) -> dict:
    """掃 repo, 回傳 raw_content dict。

    - 用 priority 排序選 max_files 個檔, 預算用完後其他檔列入 skipped_files
    - tree 限 tree_depth 層, 避免 monorepo 一炸就幾千行
    - 自動跳過 binary 檔 (read 4KB 看 NUL)
    """
    repo_path = repo_path.resolve()
    if not repo_path.is_dir():
        raise NotADirectoryError(f"不是資料夾: {repo_path}")

    candidates: list[tuple[int, Path, str]] = []  # (priority, path, kind)
    skipped: list[SkippedFile] = []
    lang_counter: Counter[str] = Counter()

    for p in repo_path.rglob("*"):
        # 早期過濾: 任一父層在 SKIP_DIRS 就跳
        if any(part in SKIP_DIRS for part in p.relative_to(repo_path).parts):
            continue
        # 隱藏檔/dir (除了 ALWAYS_INCLUDE)
        if any(part.startswith(".") and part not in ALWAYS_INCLUDE_NAMES
               for part in p.relative_to(repo_path).parts):
            continue
        if not p.is_file():
            continue

        rel = p.relative_to(repo_path).as_posix()
        kind = _classify(p)
        if kind is None:
            skipped.append(SkippedFile(rel, "unsupported_ext"))
            continue
        if _is_probably_binary(p):
            skipped.append(SkippedFile(rel, "binary"))
            continue

        # 統計語言分佈 (用副檔名近似)
        ext = p.suffix.lower() or p.name
        lang_counter[ext] += p.stat().st_size

        candidates.append((_priority(p, kind), p, kind))

    # 按 priority desc 取前 max_files
    candidates.sort(key=lambda x: -x[0])
    chosen = candidates[:max_files]
    overflow = candidates[max_files:]
    for _, p, _ in overflow:
        skipped.append(SkippedFile(p.relative_to(repo_path).as_posix(), "over_max_files"))

    key_files: list[KeyFile] = []
    for _, p, kind in chosen:
        try:
            content, truncated = _read_text(p, max_file_bytes)
        except OSError as e:
            skipped.append(SkippedFile(p.relative_to(repo_path).as_posix(), f"read_error:{e}"))
            continue
        key_files.append(KeyFile(
            path=p.relative_to(repo_path).as_posix(),
            content=content,
            bytes=p.stat().st_size,
            kind=kind,
            truncated=truncated,
        ))

    # primary_language 從 lang_counter 取 byte 最多的非 doc/config 副檔名
    code_exts = [ext for ext, _ in lang_counter.most_common()
                 if EXT_KIND.get(ext) == "code"]
    primary_lang = _ext_to_lang_name(code_exts[0]) if code_exts else None

    tree_str = _build_tree(repo_path, tree_depth, DEFAULT_TREE_MAX_CHARS)

    return {
        "source_kind": "repo",
        "root_name": repo_path.name,
        "tree": tree_str,
        "lang_stats": {ext: bytes_ for ext, bytes_ in lang_counter.most_common(8)},
        "primary_language": primary_lang,
        "key_files": [_keyfile_to_dict(k) for k in key_files],
        "skipped_files": [{"path": s.path, "reason": s.reason} for s in skipped[:30]],
        "stats": {
            "total_candidates": len(candidates),
            "selected": len(key_files),
            "skipped": len(skipped),
        },
    }


def _ext_to_lang_name(ext: str) -> str:
    return {
        ".py": "python", ".pyi": "python",
        ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
        ".ts": "typescript", ".tsx": "typescript",
        ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
        ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp",
        ".cs": "csharp", ".rb": "ruby", ".php": "php", ".swift": "swift",
        ".sh": "bash", ".bash": "bash", ".ps1": "powershell",
        ".st": "iec61131",
        ".sql": "sql",
        ".html": "html", ".css": "css", ".vue": "vue", ".svelte": "svelte",
    }.get(ext, ext.lstrip("."))


def _keyfile_to_dict(k: KeyFile) -> dict:
    return {
        "path": k.path,
        "content": k.content,
        "bytes": k.bytes,
        "kind": k.kind,
        "truncated": k.truncated,
    }


# ---------- CLI 自我測試 ----------

if __name__ == "__main__":
    import argparse
    import sys

    from core.runtime import setup_utf8_stdout
    setup_utf8_stdout()

    ap = argparse.ArgumentParser(description="Repo adapter 自我測試")
    ap.add_argument("path", help="要掃的資料夾")
    ap.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    ap.add_argument("--out", default=None, help="把 raw_content 寫到 JSON")
    args = ap.parse_args()

    result = scan_repo(Path(args.path), max_files=args.max_files)
    print(f"root: {result['root_name']}")
    print(f"primary_language: {result['primary_language']}")
    print(f"stats: {result['stats']}")
    print(f"selected files:")
    for kf in result["key_files"][:10]:
        print(f"  - {kf['path']:40s}  ({kf['kind']}, {kf['bytes']} bytes"
              + (", truncated)" if kf["truncated"] else ")"))
    if len(result["key_files"]) > 10:
        print(f"  ... +{len(result['key_files']) - 10} more")

    if args.out:
        Path(args.out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n✅ 寫到 {args.out}")
