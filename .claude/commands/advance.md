---
description: 推進 autoSolverVideo — 從 TODO.md 挑下個小任務 → 做 → 測 → commit → push
---

# /advance — 推進 autoSolverVideo 一個迭代

你正在持續推進這個專案。**這是 user 明確授權的自動迭代模式**,跟「不要自動 commit」的硬規則
在這個情境下是「自動 commit OK,但仍然遵守其他硬規則 + STOP 條件」。

每次呼叫 `/advance` 跑完下面 7 步,然後決定要不要再來一輪。

---

## 1. 健康檢查 (≤ 1 分鐘)

```bash
git status            # working tree 必須乾淨, 髒就先盤點
git pull              # 拉最新, 雲端可能有別處 commit
pytest tests/ -q      # baseline 必須全綠
```

- baseline 紅 → **優先修綠**,這輪不做其他事
- working tree 有 untracked / dirty → 看是不是 `tts_config.json` 之類的測試副作用,確認後 `git checkout HEAD -- <file>` 清掉

## 2. 挑下個任務 (按優先序)

**從上往下挑,挑到第一個 ready-to-do 的就執行,不貪多。**

1. 🔴 **CI 紅** — 立刻修 (見 `gh run list --limit 5`)
2. 🟡 **TODO.md `🌟 下階段規劃` 階段 1 內的子項** — 主要產出, C → A 順序
3. 🟢 **TODO.md `🟡 中優先` / `🟢 低優先` 內可獨立完成** (~30 分以內):
   - 內容品質 / F5 後續 / UI/UX / 技術債 / 文件
   - Round 2 殘留小事
4. ✨ **掃 code review 機會** — 用 `Grep` 找 `TODO`、`FIXME`、`XXX` 或重複 pattern
5. 📈 **加測試覆蓋** — 從 `docs/CODE_REVIEW.md` 「已知測試覆蓋盲點」表挑一條

**任務大小**:單次迭代不超過 ~30 分鐘的程式量。大任務拆細,只做第一步。

## 3. 執行

修改前先在 chat 說明:**改什麼、為什麼、有哪些副作用**。然後動手。

遵守 `claude.md` / `CLAUDE.md` 硬規則(這些 /loop 模式下也不准繞):

- ❌ **不繞 `require_review=True`** (學術誠信底線)
- ❌ **不把 AI 估算值偽裝成實驗數據**
- ✅ **修 schema 前考慮 migration** (Pydantic v2 對舊資料的相容)
- ✅ **async 路徑的 sync I/O 用 `await asyncio.to_thread(...)`**
- ✅ **layout 常數從 `core.visuals` import**,不要散 magic number
- ✅ **schema dispatch 用 type guard** (`isExamDraft` / `isDeckDraft` / `_deck_has_section_id`)
- ✅ **字型路徑走環境變數** (`CLAUDE_FONT_PATH` 等)
- ✅ **新功能進 Track B 不進 Track A**
- ✅ **設定 / 路徑常數集中 `core/config.py`**

## 4. 驗證

```bash
pytest tests/ -q                       # 必須全綠
cd web && npm run build && cd ..       # 動到前端才跑
```

動到 server runner / 路由,有時間的話 `python -m server.main` 確認 startup 訊息正常。
(此步耗時 + 需手動 Ctrl+C,/loop 內可以跳過,或在最後一輪做)

## 5. Commit + push (auto mode 授權)

- **訊息格式**:`feat/fix/refactor/docs/chore/test(scope): 中文一句話`
- **body** 寫「改了什麼、為什麼、副作用」,跟既有風格一致
- 加 `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`
- **永遠新 commit 不 amend**(pre-commit hook 失敗後 amend 會炸)
- **一個邏輯單位一個 commit**,不要塞多件無關事
- `git push` 自動推

特例:**`tts_config.json` 跑過 server / smoke test 後可能變髒**,commit 前
`git status` 看一下,有的話 `git checkout HEAD -- tts_config.json` 還原。

## 6. 更新追蹤檔

按變更幅度更新:

- **必更**:`TODO.md` 完成的項目打勾,加 commit hash + 日期
- **大段落完成**:`STATUS.yaml` `progress` + `last_updated` + `next_milestone` 推
- **里程碑**:`ROADMAP.md` 對應段落打勾或標 ✅
- **新 lesson learned**:`docs/CODE_REVIEW.md` 加 round / 三通則

## 7. 決定下次

判斷要不要再一輪:

✅ **繼續** 條件:
- TODO 上還有 ready-to-do 任務
- 剛剛 commit 沒卡 review point
- 連續做的 commit 沒發散(沒在同一個檔 / 同個 module 反覆動)

⛔ **停下來等用戶** 觸發:
- **架構決策** — v4 階段 3 D (持久化 worker)、選 RQ/Celery、schema migration framework 設計
- **破壞性變更** — 移除 Track A、刪除舊欄位、改 public API
- **動 schema** — Pydantic 欄位類型改、JSON shape 改
- **動 YouTube OAuth / API key / publish 流程**
- **動 .env / settings.json / 預設 config**
- **pytest 紅且非顯而易見** — 報告原因,別硬修
- **連續 3 個 commit 都同檔案 / 同 module** — 已發散,停
- **單一任務超 30 分** — 大任務應拆,中途停下對齊

✅ **stopping 時的報告格式**:

```
〔/advance 迭代 N 結束〕
- 做了: <task>
- Commit: <hash>
- 為什麼停: <reason — 上述觸發條件之一>
- 建議下一步: <如何接 — 需用戶決策的選項列出來>
```

✅ **繼續時的迭代摘要**(每輪都要寫):

```
〔iter N〕<時間>
- 挑了: <task>
- 改了: <files> +X -Y
- 驗證: 155 tests passed / build ok
- Commit: <hash> <message>
- 下次預定: <next task>
```

---

## 觸發方式

```
/loop /advance          # 自我配速 (建議, 看任務複雜度自己決定間隔)
/loop 30m /advance      # 每 30 分跑一次 (定時 polling)
/loop 1h /advance       # 每小時 (適合 user 處理別的事時跑)
```

Ctrl+C / Esc 隨時中斷。

---

## 規範鏈接

- 全域風格: `~/.claude/CLAUDE.md`
- 專案硬規則: `claude.md`
- 短期任務: `TODO.md` (主要選任務的地方)
- 版本路線: `ROADMAP.md`
- Lessons learned: `docs/CODE_REVIEW.md`
- 上次 session 接手筆記: `docs/SESSION_HANDOFF.md`
