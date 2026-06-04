"""V2 (E2-2) 驗收測試 — icon_library 25 SVG 補齊完整性鎖.

對應 docs/dynamic-visual-v2-v3-proposal.md「怎麼驗收」段: 劉老師 2026-06-04 用
Gemini 產完 25 個扁平 SVG 補進 assets/icon_library/ 後, routine 自主做的 offline
驗收 — 純檔案系統 + manifest 對照, 0 LLM call / 0 cost / CI 可重現.

鎖三件事:
1. manifest 每個 entry 的 `icon` 路徑檔案存在 + 是合法 SVG (開頭 <svg + viewBox).
2. manifest 每個 entry 欄位齊全且值在 _field_spec 合法集 (position / domain / size_ratio).
3. 雙向完整性 — manifest 25 個都有檔 (正向) + assets 內每個 .svg 都登記在 manifest
   (反向, 防「補了檔但忘了登記」或「登記了但檔在別處」).

補檔後 pick_icons(require_file_exists=True) 自然能命中 (V1d 已驗 False 路徑;
這裡補 True 路徑 — 渲染端預設值真的疊得出 icon).
"""
from __future__ import annotations

import pytest

from core.icon_picker import ICON_LIBRARY_ROOT, load_manifest, pick_icons

# _field_spec 合法集 (跟 manifest._field_spec 文字對齊, 任一改動該同步)
_VALID_POSITIONS = {"top-left", "top-right", "bottom-left", "bottom-right", "center"}
_VALID_DOMAINS = {"generic", "wind", "control", "mechanics"}

_MANIFEST = load_manifest()
_ICONS = _MANIFEST["icons"]
_ICON_ITEMS = sorted(_ICONS.items())  # 穩定順序給 parametrize


def test_manifest_defines_25_icons():
    """manifest 定義數鎖在 25 (G/E 軸決議: 風能/控制/材力各 5 + generic 10).

    防誤刪 entry — 數量變了該是有意決策, 不該悄悄掉.
    """
    assert len(_ICONS) == 25


@pytest.mark.parametrize("key, entry", _ICON_ITEMS)
def test_icon_file_exists(key, entry):
    """每個 manifest entry 的 icon 路徑在磁碟上真的有檔 (V2 核心驗收)."""
    icon_path = ICON_LIBRARY_ROOT / entry["icon"]
    assert icon_path.exists(), f"{key}: 缺 SVG 檔 {entry['icon']}"


@pytest.mark.parametrize("key, entry", _ICON_ITEMS)
def test_icon_is_valid_svg(key, entry):
    """檔案是合法 SVG — 開頭含 <svg 標籤 + viewBox 屬性 (proposal 驗收條件)."""
    text = (ICON_LIBRARY_ROOT / entry["icon"]).read_text(encoding="utf-8")
    assert "<svg" in text, f"{key}: 不是 SVG (無 <svg)"
    assert "viewBox" in text, f"{key}: SVG 缺 viewBox (定位/縮放靠它)"


@pytest.mark.parametrize("key, entry", _ICON_ITEMS)
def test_icon_viewbox_256(key, entry):
    """風格鎖 — 全 viewBox 0 0 256 256 (統一風格規範, compose_icons 等比縮放假設)."""
    text = (ICON_LIBRARY_ROOT / entry["icon"]).read_text(encoding="utf-8")
    assert 'viewBox="0 0 256 256"' in text, f"{key}: viewBox 非 256 (風格不一致)"


@pytest.mark.parametrize("key, entry", _ICON_ITEMS)
def test_entry_fields_complete_and_valid(key, entry):
    """每 entry 欄位齊全且值在合法集 — keywords / position / size_ratio / domain."""
    kws = entry.get("keywords")
    assert isinstance(kws, list) and kws, f"{key}: keywords 該是非空 list"
    assert all(isinstance(k, str) and k.strip() for k in kws), f"{key}: keyword 有空字串"

    assert entry.get("position") in _VALID_POSITIONS, f"{key}: position 非法 {entry.get('position')}"
    assert entry.get("domain") in _VALID_DOMAINS, f"{key}: domain 非法 {entry.get('domain')}"

    sr = entry.get("size_ratio")
    assert isinstance(sr, (int, float)), f"{key}: size_ratio 非數值"
    # 0 < ratio <= 0.5 (compose_icons 上界 clamp 0.50, 超過無意義)
    assert 0 < sr <= 0.5, f"{key}: size_ratio {sr} 超出 (0, 0.5]"


def test_no_duplicate_keyword_across_entries():
    """keyword 跨 entry 不重複 — icon_picker 靠『第一個命中即唯一』假設.

    (icon_picker.pick_icons docstring 明寫依賴此, 補檔後一併鎖死.)
    """
    seen: dict[str, str] = {}
    dup: list[str] = []
    for key, entry in _ICONS.items():
        for kw in entry["keywords"]:
            lc = kw.lower()
            if lc in seen:
                dup.append(f"{kw!r} 同時在 {seen[lc]} 與 {key}")
            seen[lc] = key
    assert not dup, "keyword 跨 entry 重複: " + "; ".join(dup)


def test_no_orphan_svg_files():
    """反向完整性 — assets/icon_library 下每個 .svg 都登記在 manifest.

    防『產了檔但忘了加進 manifest』(picker grep 不到 = 等於沒產) 或
    『登記路徑與實際檔名不符』留下孤兒檔.
    """
    registered = {entry["icon"].replace("\\", "/") for entry in _ICONS.values()}
    on_disk = {
        p.relative_to(ICON_LIBRARY_ROOT).as_posix()
        for p in ICON_LIBRARY_ROOT.rglob("*.svg")
    }
    orphans = on_disk - registered
    assert not orphans, f"未登記在 manifest 的孤兒 SVG: {sorted(orphans)}"


@pytest.mark.parametrize("key, entry", _ICON_ITEMS)
def test_pick_icons_resolves_each_with_file_exists(key, entry):
    """補檔後 — 每個 icon 用自己第一個 keyword 餵 pick_icons (預設 require_file_exists
    =True) 都能命中且 file_exists=True (渲染端預設值真的疊得出 icon).

    V1d 已驗 require_file_exists 過濾掉缺檔的 False 路徑; 補檔後這是對稱的 True 路徑.
    """
    first_kw = entry["keywords"][0]
    matches = pick_icons(first_kw, max_icons=25, require_file_exists=True)
    hit = [m for m in matches if m.key == key]
    assert hit, f"{key}: keyword {first_kw!r} 補檔後仍命中不到"
    assert hit[0].file_exists is True, f"{key}: file_exists 該為 True"
