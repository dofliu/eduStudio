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
