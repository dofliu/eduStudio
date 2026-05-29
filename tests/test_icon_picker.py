"""E2-3 icon_picker keyword grep 行為驗證.

對應 core/icon_picker.py — narration → IconMatch list.
重點: graceful fallback (SVG 不存在不噴 error), 命中行為 (dedup / 上限 /
case-insensitive), 邊界 (None / 空字串).

SVG 檔在 E2-2 才產, 用 tmp_path 寫假 manifest + 假 svg 隔離測試, 不依賴
真 assets/icon_library/ 內容.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.icon_picker import (
    IconMatch,
    MANIFEST_PATH,
    load_manifest,
    pick_icons,
    suggest_for_deck,
)


def _write_manifest(dir_: Path, icons: dict) -> Path:
    """寫一個小 manifest 進 tmp dir, 回傳 path."""
    path = dir_ / "manifest.json"
    path.write_text(
        json.dumps({"_schema_version": 1, "icons": icons}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _touch_svg(library_root: Path, rel_path: str) -> Path:
    """library_root 下建子目錄並 touch 一個假 svg, 回傳絕對 path."""
    full = library_root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text("<svg/>", encoding="utf-8")
    return full


@pytest.fixture()
def fake_library(tmp_path: Path) -> tuple[Path, Path]:
    """建一個 fake icon library — manifest + 兩個 svg 檔."""
    library_root = tmp_path / "lib"
    library_root.mkdir()
    _touch_svg(library_root, "generic/question.svg")
    _touch_svg(library_root, "wind/wind_turbine.svg")
    manifest_path = _write_manifest(
        library_root,
        {
            "question": {
                "keywords": ["?", "為什麼", "提問"],
                "icon": "generic/question.svg",
                "position": "top-right",
                "size_ratio": 0.10,
                "domain": "generic",
            },
            "wind_turbine": {
                "keywords": ["風力機", "風機", "wind turbine"],
                "icon": "wind/wind_turbine.svg",
                "position": "bottom-right",
                "size_ratio": 0.16,
                "domain": "wind",
            },
        },
    )
    return manifest_path, library_root


class TestEmptyOrInvalidNarration:
    def test_empty_string_returns_empty(self, fake_library):
        manifest_path, library_root = fake_library
        assert pick_icons("", manifest_path=manifest_path, library_root=library_root) == []

    def test_whitespace_only_returns_empty(self, fake_library):
        manifest_path, library_root = fake_library
        assert pick_icons("   \n\t  ", manifest_path=manifest_path, library_root=library_root) == []

    def test_none_returns_empty(self, fake_library):
        manifest_path, library_root = fake_library
        # 故意傳非 str, 函式該防呆
        assert pick_icons(None, manifest_path=manifest_path, library_root=library_root) == []  # type: ignore[arg-type]


class TestBasicMatching:
    def test_single_keyword_match_returns_one(self, fake_library):
        manifest_path, library_root = fake_library
        result = pick_icons(
            "為什麼風力發電機要這樣設計?",
            manifest_path=manifest_path,
            library_root=library_root,
        )
        # "為什麼" 命中 question; "?" 也命中 (但 dedup 同 entry); "風力機" 不命中 ("風力發電機" 不含 "風力機" 子字串其實有...)
        # 實際: "風力發電機" 含 "風力" 不含 "風力機"; 不過 "風機" 也不在. 但 "?" 命中 question.
        # 結論: 只命中 question (dedup)
        assert len(result) == 1
        assert result[0].key == "question"

    def test_no_match_returns_empty(self, fake_library):
        manifest_path, library_root = fake_library
        result = pick_icons(
            "今天天氣很好",
            manifest_path=manifest_path,
            library_root=library_root,
        )
        assert result == []

    def test_dedup_same_entry_multiple_keywords(self, fake_library):
        manifest_path, library_root = fake_library
        # narration 同時含 "為什麼" + "?" + "提問" — 都對 question entry, 只回 1 筆
        result = pick_icons(
            "為什麼會這樣? 我有個提問",
            manifest_path=manifest_path,
            library_root=library_root,
        )
        assert len(result) == 1
        assert result[0].key == "question"

    def test_multiple_entries_match(self, fake_library):
        manifest_path, library_root = fake_library
        result = pick_icons(
            "為什麼風力機會這樣轉?",
            manifest_path=manifest_path,
            library_root=library_root,
        )
        keys = {m.key for m in result}
        assert keys == {"question", "wind_turbine"}


class TestMaxIconsCap:
    def test_max_icons_default_3(self, tmp_path):
        library_root = tmp_path / "lib"
        library_root.mkdir()
        icons = {}
        for i in range(5):
            rel = f"generic/icon{i}.svg"
            _touch_svg(library_root, rel)
            icons[f"icon{i}"] = {
                "keywords": [f"kw{i}"],
                "icon": rel,
                "position": "top-right",
                "size_ratio": 0.10,
                "domain": "generic",
            }
        manifest_path = _write_manifest(library_root, icons)
        result = pick_icons(
            "kw0 kw1 kw2 kw3 kw4",
            manifest_path=manifest_path,
            library_root=library_root,
        )
        assert len(result) == 3  # 預設上限

    def test_max_icons_override(self, tmp_path):
        library_root = tmp_path / "lib"
        library_root.mkdir()
        icons = {}
        for i in range(5):
            rel = f"generic/icon{i}.svg"
            _touch_svg(library_root, rel)
            icons[f"icon{i}"] = {
                "keywords": [f"kw{i}"],
                "icon": rel,
                "position": "top-right",
                "size_ratio": 0.10,
                "domain": "generic",
            }
        manifest_path = _write_manifest(library_root, icons)
        result = pick_icons(
            "kw0 kw1 kw2 kw3 kw4",
            manifest_path=manifest_path,
            library_root=library_root,
            max_icons=10,
        )
        assert len(result) == 5  # 全回


class TestGracefulFallback:
    def test_missing_svg_filtered_by_default(self, tmp_path):
        """SVG 檔不存在 (E2-2 未完成) → require_file_exists=True 該過濾掉."""
        library_root = tmp_path / "lib"
        library_root.mkdir()
        # 不 touch svg, 只寫 manifest
        manifest_path = _write_manifest(
            library_root,
            {
                "question": {
                    "keywords": ["?"],
                    "icon": "generic/question.svg",
                    "position": "top-right",
                    "size_ratio": 0.10,
                    "domain": "generic",
                },
            },
        )
        result = pick_icons(
            "為什麼?",
            manifest_path=manifest_path,
            library_root=library_root,
        )
        assert result == []

    def test_missing_svg_returned_when_not_required(self, tmp_path):
        """require_file_exists=False — review UI 階段該看到所有建議, 渲染前再過濾."""
        library_root = tmp_path / "lib"
        library_root.mkdir()
        manifest_path = _write_manifest(
            library_root,
            {
                "question": {
                    "keywords": ["?"],
                    "icon": "generic/question.svg",
                    "position": "top-right",
                    "size_ratio": 0.10,
                    "domain": "generic",
                },
            },
        )
        result = pick_icons(
            "為什麼?",
            manifest_path=manifest_path,
            library_root=library_root,
            require_file_exists=False,
        )
        assert len(result) == 1
        assert result[0].key == "question"
        assert result[0].file_exists is False


class TestIconMatchFields:
    def test_all_fields_populated(self, fake_library):
        manifest_path, library_root = fake_library
        result = pick_icons(
            "風力機",
            manifest_path=manifest_path,
            library_root=library_root,
        )
        assert len(result) == 1
        m = result[0]
        assert m.key == "wind_turbine"
        assert m.icon_path == library_root / "wind/wind_turbine.svg"
        assert m.icon_path.is_absolute()
        assert m.matched_keyword == "風力機"
        assert m.position == "bottom-right"
        assert m.size_ratio == 0.16
        assert m.domain == "wind"
        assert m.file_exists is True


class TestCaseInsensitive:
    def test_english_keyword_case_insensitive(self, tmp_path):
        """'PID' manifest keyword, narration 寫 'pid' 該命中."""
        library_root = tmp_path / "lib"
        library_root.mkdir()
        _touch_svg(library_root, "control/pid.svg")
        manifest_path = _write_manifest(
            library_root,
            {
                "pid_loop": {
                    "keywords": ["PID"],
                    "icon": "control/pid.svg",
                    "position": "bottom-right",
                    "size_ratio": 0.16,
                    "domain": "control",
                },
            },
        )
        result = pick_icons(
            "this pid loop controls the motor",
            manifest_path=manifest_path,
            library_root=library_root,
        )
        assert len(result) == 1
        assert result[0].key == "pid_loop"


class TestRealManifest:
    """跑真的 assets/icon_library/manifest.json — 確保 schema 沒漂移到 picker 讀不下."""

    def test_load_real_manifest_has_icons(self):
        manifest = load_manifest()
        assert "icons" in manifest
        assert len(manifest["icons"]) > 0

    def test_real_manifest_path_constant_correct(self):
        assert MANIFEST_PATH.name == "manifest.json"
        assert MANIFEST_PATH.parent.name == "icon_library"

    def test_real_narration_no_svg_yet_graceful(self):
        """E2-2 SVG 還沒產, require_file_exists=True 該回空 list (不噴 error)."""
        # 用會命中多 entry 的 narration, 但 SVG 還沒進 repo
        result = pick_icons("這是 PID 控制風力機的方塊圖")
        # SVG 不存在, default require_file_exists=True 該過濾光
        assert result == []

    def test_real_narration_with_relaxed_flag_returns_matches(self):
        """require_file_exists=False — 該看到建議, file_exists=False 標記."""
        result = pick_icons(
            "這是 PID 控制風力機的方塊圖",
            require_file_exists=False,
        )
        assert len(result) > 0
        assert all(m.file_exists is False for m in result)
        # 該包含 pid_loop / wind_turbine / block_diagram 之一
        keys = {m.key for m in result}
        assert keys & {"pid_loop", "wind_turbine", "block_diagram"}


class TestManifestOrderPriority:
    """manifest 出現順序 = priority — pick_icons docstring 明定『Order: 按 manifest
    中 entry 出現順序』, 且 max_icons 截斷依此序保留前 N 個. 既有 test 用 set 驗命中
    集合, 沒鎖『順序』與『截斷依 manifest 序非 narration 序』兩個契約."""

    def _ordered_library(self, tmp_path):
        """alpha/beta/gamma 三 entry, manifest 順序 alpha→beta→gamma."""
        library_root = tmp_path / "lib"
        library_root.mkdir()
        icons = {}
        # dict 插入序即 JSON 序 (Py3.7+ + json.loads 保留序), 鎖死 alpha<beta<gamma
        for name, kw in [("alpha", "aaa"), ("beta", "bbb"), ("gamma", "ccc")]:
            rel = f"generic/{name}.svg"
            _touch_svg(library_root, rel)
            icons[name] = {
                "keywords": [kw],
                "icon": rel,
                "position": "top-right",
                "size_ratio": 0.10,
                "domain": "generic",
            }
        manifest_path = _write_manifest(library_root, icons)
        return manifest_path, library_root

    def test_result_order_follows_manifest_not_narration(self, tmp_path):
        """narration 以 gamma→alpha→beta 順序提及 keyword, 結果仍該照 manifest 序回."""
        manifest_path, library_root = self._ordered_library(tmp_path)
        result = pick_icons(
            "ccc 出現在前 aaa 居中 bbb 最後",
            manifest_path=manifest_path,
            library_root=library_root,
        )
        assert [m.key for m in result] == ["alpha", "beta", "gamma"]

    def test_max_icons_truncates_by_manifest_order(self, tmp_path):
        """三個都命中但 max_icons=2 → 保留 manifest 前兩個 (alpha/beta),
        而非 narration 先提到的 gamma. 鎖『截斷依 manifest 序非提及序』."""
        manifest_path, library_root = self._ordered_library(tmp_path)
        result = pick_icons(
            "ccc 先講 然後 aaa 再來 bbb",
            manifest_path=manifest_path,
            library_root=library_root,
            max_icons=2,
        )
        assert [m.key for m in result] == ["alpha", "beta"]
        assert "gamma" not in {m.key for m in result}


class TestManifestMissingIconsKey:
    def test_manifest_without_icons_key_returns_empty(self, tmp_path):
        """manifest 缺 'icons' key (極端 defensive) → manifest.get('icons', {})
        該回 [] 不噴 KeyError."""
        library_root = tmp_path / "lib"
        library_root.mkdir()
        path = library_root / "manifest.json"
        path.write_text(json.dumps({"_schema_version": 1}), encoding="utf-8")
        result = pick_icons("為什麼風力機?", manifest_path=path, library_root=library_root)
        assert result == []


class TestSuggestForDeck:
    """E2-6 backend slice: 對整個 deck 批次跑 pick_icons 給 review UI 用."""

    def test_empty_deck_returns_empty_dict(self, fake_library):
        manifest_path, library_root = fake_library
        result = suggest_for_deck(
            {"sections": []},
            manifest_path=manifest_path,
            library_root=library_root,
        )
        assert result == {}

    def test_missing_sections_returns_empty_dict(self, fake_library):
        """deck 連 sections key 都沒 (極端 defensive) → 空 dict, 不噴 KeyError."""
        manifest_path, library_root = fake_library
        result = suggest_for_deck(
            {},
            manifest_path=manifest_path,
            library_root=library_root,
        )
        assert result == {}

    def test_single_slide_with_match(self, fake_library):
        manifest_path, library_root = fake_library
        deck = {
            "sections": [
                {
                    "id": "s1",
                    "slides": [
                        {"id": "s1_1", "narration": "我們聊聊風機的運轉原理"},
                    ],
                }
            ]
        }
        result = suggest_for_deck(
            deck,
            manifest_path=manifest_path,
            library_root=library_root,
        )
        assert set(result.keys()) == {"s1_1"}
        assert len(result["s1_1"]) == 1
        assert result["s1_1"][0].key == "wind_turbine"

    def test_multi_section_multi_slide_preserves_all_ids(self, fake_library):
        """跨章節多 slide — 每個 slide_id 都該在 result 裡, 沒命中也保留空 list."""
        manifest_path, library_root = fake_library
        deck = {
            "sections": [
                {
                    "id": "intro",
                    "slides": [
                        {"id": "intro_1", "narration": "風機是甚麼"},
                        {"id": "intro_2", "narration": "沒有命中的詞"},
                    ],
                },
                {
                    "id": "deep",
                    "slides": [
                        {"id": "deep_1", "narration": "為什麼要這樣設計?"},
                    ],
                },
            ]
        }
        result = suggest_for_deck(
            deck,
            manifest_path=manifest_path,
            library_root=library_root,
        )
        assert set(result.keys()) == {"intro_1", "intro_2", "deep_1"}
        assert result["intro_1"][0].key == "wind_turbine"
        assert result["intro_2"] == []  # 沒命中, key 仍保留 (跟「沒掃到」做區別)
        assert result["deep_1"][0].key == "question"

    def test_slide_missing_id_is_skipped(self, fake_library):
        """缺 id 的 slide 跳過 — normalize_deck 後不該發生, 但 defensive."""
        manifest_path, library_root = fake_library
        deck = {
            "sections": [
                {
                    "id": "s1",
                    "slides": [
                        {"id": "ok", "narration": "風機"},
                        {"narration": "風機"},  # 缺 id
                        {"id": "", "narration": "風機"},  # 空 id
                    ],
                }
            ]
        }
        result = suggest_for_deck(
            deck,
            manifest_path=manifest_path,
            library_root=library_root,
        )
        assert set(result.keys()) == {"ok"}

    def test_empty_narration_slide_returns_empty_list(self, fake_library):
        """slide.narration 空 → result[slide_id]=[], key 仍保留."""
        manifest_path, library_root = fake_library
        deck = {
            "sections": [
                {
                    "id": "s1",
                    "slides": [
                        {"id": "a", "narration": ""},
                        {"id": "b"},  # 沒 narration key
                    ],
                }
            ]
        }
        result = suggest_for_deck(
            deck,
            manifest_path=manifest_path,
            library_root=library_root,
        )
        assert result == {"a": [], "b": []}

    def test_kwargs_passthrough_to_pick_icons(self, fake_library):
        """max_icons / require_file_exists 該透傳給每個 slide 的 pick_icons."""
        manifest_path, library_root = fake_library
        deck = {
            "sections": [
                {
                    "id": "s1",
                    "slides": [
                        # 故意撞兩個 entry (風機 + 提問), 預期 max_icons=1 截到 1 個
                        {"id": "both", "narration": "為什麼風機要這樣?"},
                    ],
                }
            ]
        }
        result = suggest_for_deck(
            deck,
            manifest_path=manifest_path,
            library_root=library_root,
            max_icons=1,
        )
        assert len(result["both"]) == 1

    def test_section_with_no_slides_yields_no_entries(self, fake_library):
        """空 section (slides=[] / 缺 key) — 不該爆, 直接無 entry."""
        manifest_path, library_root = fake_library
        deck = {
            "sections": [
                {"id": "empty", "slides": []},
                {"id": "noslideskey"},  # 缺 slides key
            ]
        }
        result = suggest_for_deck(
            deck,
            manifest_path=manifest_path,
            library_root=library_root,
        )
        assert result == {}
