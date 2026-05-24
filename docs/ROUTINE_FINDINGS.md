# Routine Findings

> Routine 推進過程中遇到的「需用戶決策才能修」的事項. 不是 BLOCKED (routine 仍能繼續做別的),
> 是「該由用戶在下個 review 視窗決定怎麼處理」的累積清單.

格式: 日期 + iter + 來源 + 描述 + 建議行動.

---

## 2026-05-24 (iter 113) — editor.py route 有 JS-context XSS 風險

**來源**: 補 `server/routes/editor.py` 測試覆蓋時發現 (test_editor_route.py
test_deck_xss_in_html_render_path_escaped 原本想驗 deck_title 含 `<script>`
也該安全, 結果 fail 揭出真實風險).

**問題**:
`server/routes/editor.py::_render_editor` 渲染編輯頁時, 把整個 deck 直接透過
`json.dumps(deck, ensure_ascii=False)` 注入 `<script>const DECK = {...}` block:

```python
# server/routes/editor.py:323
const DECK = {json.dumps(deck, ensure_ascii=False)};
```

若 `deck.json` 內任一字串欄位 (deck_title / section.title / slide.* / bullets /
narration / code_snippet) 含 `</script>`, JS string literal 會被 HTML parser
提早截斷, 進入新 tag 解析模式 → XSS.

`_html_escape` 已護住所有 HTML 渲染路徑 (toolbar / section / slide DOM 都過
escape, 28 個測試都綠), 唯獨 `<script>const DECK = ...` 這條 JS-context 路徑沒護.

**攻擊面**: 低. editor.py 只在 localhost server (port 8000) 對自己人開, 而且
deck.json 內容理論上都是 Gemini 產或用戶手寫 — 但 routine / 第三方 (Kiwi /
Christian) 可能跑別人的 deck, 仍有風險.

**建議修法** (兩個方向, 任選一即可):

1. 用 `</` → `<\/` replace (JSON 標準作法, 跟 facebook / json2.js 風格一致):
   ```python
   json_str = json.dumps(deck, ensure_ascii=False).replace("</", "<\\/")
   ```
2. 把 deck 改放到 `<script type="application/json" id="deck-data">...</script>`
   block, JS 用 `JSON.parse(document.getElementById('deck-data').textContent)`
   讀. 該 type 下 browser 不解析 JS, 但仍會被 `</script>` 結束 — 仍需 replace.

兩種都不影響現有測試, 改 1 行即可.

**STOP 原因**: 動行為的 bug fix, 硬規則 #3「修 bug 前先跟用戶討論」. routine
不該自行 patch, 留筆等用戶決定. test_editor_route 28 個 HTML-escape 測試已
鎖住 _html_escape 部分, JS-context 那條留給用戶定案.

---

## 2026-05-24 (iter 121) — library.py `_read_deck_title` 對非 str 型別 title 會炸

**來源**: 補 `server/routes/library.py::_read_deck_title` 邊角測試 (test_library_route.py
TestReadDeckTitleEdgeCases) 時, 邊看 code 邊推. 已寫的 5 個 test 都是 graceful
退 job_id 路徑 (binary / 0-byte / null / whitespace / BOM), 但發現另兩條沒護住.

**問題**:

```python
# server/routes/library.py:53-58
try:
    import json
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
except Exception:
    return job_id
return (deck.get("exam_title") or deck.get("deck_title") or job_id).strip()
```

`try/except` 只包到 `json.loads`. 後面 `.get(...).strip()` 沒護住, 兩條 raise 路徑:

1. **deck 不是 dict** (例 deck.json 頂層是 list `[]` 或 string `"hi"`): `deck.get` AttributeError
2. **title 是 non-str truthy 值** (例 `{"exam_title": 42}` 或 `{"exam_title": ["a"]}`):
   `or` 鏈回 truthy 42 / list, 然後 `.strip()` AttributeError

兩條都會 500 而非 graceful 退 job_id, 跟既有設計 (deck.json 壞掉就退 job_id) 不一致.

**攻擊面**: 低. deck.json 都是 Gemini 產 (schema 化, 不該吐 int) 或用戶手寫.
但 Gemini 偶爾偏差 / 用戶手改錯, 仍可能踩 — 而且 500 對 Library 頁是整頁掛
不只一筆 job 影響, 不像 editor.py XSS 那麼集中.

**建議修法** (1 行, 任選):

1. 把 `try/except` 範圍擴大包到最後 return:
   ```python
   try:
       deck = json.loads(deck_path.read_text(encoding="utf-8"))
       return (deck.get("exam_title") or deck.get("deck_title") or job_id).strip()
   except Exception:
       return job_id
   ```
2. 型別守: `title = deck.get("exam_title") if isinstance(deck, dict) else None;
   title = title if isinstance(title, str) and title.strip() else ...`

第 1 種 1 行縮排, 跟既有 graceful-degrade pattern 一致, 最省事. 第 2 種更
顯式但 4 行起跳.

**STOP 原因**: 硬規則 #3「修 bug 前先跟用戶討論」. 現有 5 個新 test 已鎖住
graceful-degrade 三條路徑 (binary / 0-byte / null), 等用戶定案再補非 str /
非 dict 的修法跟對應 test.
