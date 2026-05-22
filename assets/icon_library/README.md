# icon_library — E2 內容感知 icon overlay 素材庫

對應 RFC: [docs/dynamic-visual-assets-design.md](../../docs/dynamic-visual-assets-design.md) E2 軸.
路線: 候選 A (keyword grep + manifest.json, 0 LLM call).

## 目錄

```
assets/icon_library/
├── manifest.json       # 對照表 (25 entries, 此檔)
├── README.md           # 本檔
├── generic/            # 跨主題 10 個 (question/exclamation/lightbulb/...)
├── wind/               # 風能 5 個
├── control/            # 自動控制 5 個
└── mechanics/          # 材料力學 5 個
```

> SVG 檔本身**尚未產出** — 等 E2-2 (Gemini 一次性產 25 個扁平 SVG) commit.
> 在 SVG 進來之前, `core/icon_picker.py` 命中 keyword 但檔不存在會 graceful 跳過 (不擋 pipeline).

## manifest 欄位

| 欄位 | 型別 | 說明 |
|---|---|---|
| `keywords` | `list[str]` | narration 內出現任一即視為命中. 加詞前看實機反饋 (避免誤命中) |
| `icon` | `str` | 相對本資料夾的路徑 (`generic/question.svg`) |
| `position` | `str` | `top-left` / `top-right` / `bottom-left` / `bottom-right` / `center` |
| `size_ratio` | `float` | icon 寬佔影片寬比例 (0.08~0.20 推薦, generic 用 0.10, domain 用 0.16) |
| `domain` | `str` | `generic` / `wind` / `control` / `mechanics`, 給 UI 分組顯示 |

## 加新 icon

1. 補 SVG 到對應子資料夾 (viewBox 256×256, stroke #1e3a2e, fill #ffd96b, 純線條 + 純色填充)
2. `manifest.json` 加一條 entry, key 用簡短 snake_case
3. tests/test_icon_library_manifest.py 自動驗證 schema (不必另寫 test)
4. 命中策略保守: keywords 寧少勿多, 避免 narration 含通用詞誤觸發

## 為何 keyword grep 不是 LLM classify

- 0 cost / 0 latency / 純文字 grep
- 結果可解釋 — review UI 顯示「自動建議 icon 因為 narration 含 'X'」
- 對齊硬規則 `require_review=True` — AI 不直接決定畫面, 走 proposals 人工勾選

升級到 LLM (候選 B) 或 embedding (候選 C) 等收 1-2 月實機反饋後再評估.
