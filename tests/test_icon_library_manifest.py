"""E2-1 icon library manifest schema 驗證.

確保 assets/icon_library/manifest.json 結構正確, 避免後續 E2-2 ~ E2-7
新增 entry 時格式漂移 / position 寫錯 / size_ratio 超出範圍.

SVG 檔本身在 E2-2 才產 — 此 test 不檢查檔存在 (graceful fallback 設計).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


MANIFEST_PATH = Path(__file__).parent.parent / "assets" / "icon_library" / "manifest.json"
VALID_POSITIONS = {"top-left", "top-right", "bottom-left", "bottom-right", "center"}
VALID_DOMAINS = {"generic", "wind", "control", "mechanics"}
REQUIRED_ICON_FIELDS = {"keywords", "icon", "position", "size_ratio", "domain"}


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


class TestManifestStructure:
    def test_manifest_exists(self):
        assert MANIFEST_PATH.exists(), f"manifest 不存在: {MANIFEST_PATH}"

    def test_schema_version_is_int(self, manifest):
        assert isinstance(manifest.get("_schema_version"), int)

    def test_has_icons_dict(self, manifest):
        assert "icons" in manifest
        assert isinstance(manifest["icons"], dict)

    def test_icon_count_matches_rfc(self, manifest):
        """RFC 決議 25 個 (10 generic + 15 domain). 數字漂移就該更新 RFC."""
        assert len(manifest["icons"]) == 25


class TestEntrySchema:
    def test_every_entry_has_required_fields(self, manifest):
        for key, entry in manifest["icons"].items():
            missing = REQUIRED_ICON_FIELDS - set(entry.keys())
            assert not missing, f"entry {key} 缺欄位: {missing}"

    def test_keywords_non_empty(self, manifest):
        for key, entry in manifest["icons"].items():
            assert isinstance(entry["keywords"], list)
            assert len(entry["keywords"]) > 0, f"{key} keywords 不可空"
            for kw in entry["keywords"]:
                assert isinstance(kw, str) and kw.strip(), f"{key} 含空 keyword"

    def test_position_in_valid_set(self, manifest):
        for key, entry in manifest["icons"].items():
            assert entry["position"] in VALID_POSITIONS, (
                f"{key} position={entry['position']!r} 不在 {VALID_POSITIONS}"
            )

    def test_size_ratio_in_range(self, manifest):
        for key, entry in manifest["icons"].items():
            ratio = entry["size_ratio"]
            assert isinstance(ratio, (int, float))
            assert 0.05 <= ratio <= 0.25, f"{key} size_ratio={ratio} 超出 0.05~0.25"

    def test_domain_in_valid_set(self, manifest):
        for key, entry in manifest["icons"].items():
            assert entry["domain"] in VALID_DOMAINS, (
                f"{key} domain={entry['domain']!r} 不在 {VALID_DOMAINS}"
            )

    def test_icon_path_matches_domain(self, manifest):
        """icon 路徑首段該對應 domain (generic/question.svg domain=generic).
        wind/ 對 wind, control/ 對 control, mechanics/ 對 mechanics."""
        for key, entry in manifest["icons"].items():
            first_segment = entry["icon"].split("/")[0]
            assert first_segment == entry["domain"], (
                f"{key} icon={entry['icon']} 跟 domain={entry['domain']} 不一致"
            )

    def test_icon_path_ends_with_svg(self, manifest):
        for key, entry in manifest["icons"].items():
            assert entry["icon"].endswith(".svg"), f"{key} 非 .svg: {entry['icon']}"


class TestDomainCoverage:
    """RFC 規定 10 generic + 5 wind + 5 control + 5 mechanics."""

    def test_generic_has_10(self, manifest):
        count = sum(1 for e in manifest["icons"].values() if e["domain"] == "generic")
        assert count == 10

    def test_wind_has_5(self, manifest):
        count = sum(1 for e in manifest["icons"].values() if e["domain"] == "wind")
        assert count == 5

    def test_control_has_5(self, manifest):
        count = sum(1 for e in manifest["icons"].values() if e["domain"] == "control")
        assert count == 5

    def test_mechanics_has_5(self, manifest):
        count = sum(1 for e in manifest["icons"].values() if e["domain"] == "mechanics")
        assert count == 5


class TestNoDuplicateKeywords:
    """同一個 keyword 對到多 icon 會讓 keyword grep 結果不穩定. RFC 寧少勿多."""

    def test_no_duplicate_keyword_across_entries(self, manifest):
        seen: dict[str, str] = {}
        dupes: list[str] = []
        for key, entry in manifest["icons"].items():
            for kw in entry["keywords"]:
                if kw in seen:
                    dupes.append(f"{kw!r}: {seen[kw]} vs {key}")
                else:
                    seen[kw] = key
        assert not dupes, "重複 keyword: " + "; ".join(dupes)
