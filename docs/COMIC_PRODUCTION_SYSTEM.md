# eduStudio Comic Production System

狀態：Internal MVP implemented（2026-08-20）→ **正式化進行中**（2026-08-30 劉老師拍板投入）

## 正式化 Checklist（2026-08-30 起）

**已完成（offline 稽核，2026-08-30）**
- [x] 測試護網：`test_comics.py` / `test_comics_route.py` / `test_infocards_comic.py` 共 25 測全綠。
- [x] Reader XSS 防護：`build_reader_html` 對 title / summary / 對白 / alt text / speaker /
  asset id 全面 `html.escape`。
- [x] 存取控制：全部路由掛在 `/projects/{pid}/comics/*`，受全域 `EDUSTUDIO_API_TOKEN`
  middleware 保護（含 Internal Reader）。
- [x] Fail-closed 驗證：mock 圖 / 缺 evidence / 缺 scene / 缺 alt text / 缺 QA / 未人工核准
  → 不可發布；`CURRENT` immutable、改稿必 fork。
- [x] CI 依賴：`python-docx`（DOCX fallback export）與 PPTX 契約測試已入 CI。

**待做（依序）**
- [ ] 🔴 **GATE：一輪真實生成 QA**（開額度）— 用實際課程素材（例：齒輪箱講義）走完
  script → storyboard → Evidence Pack → 逐頁生圖 → 六道 QA gate → 發布，驗證角色
  visual lock 跨頁一致性與 negative space 排版實效。結果寫回本檔。
- [ ] 🟡 匯出實機檢查：DOCX（Windows Word 開啟、對白 bubble 可編輯）/ PDF / HTML /
  source ZIP 各一輪。
- [ ] 🟡 手冊補教學案例：USER_MANUAL §7 已有流程，真實案例（含截圖）待上一項完成後補。
- [ ] 🟢 對外開放決策：Internal Reader 是否對學生開放（需分享連結/權限機制，另議）。
- [ ] 🟢 成本記帳：漫畫生圖走 `core.infocards.gemini.generate_image_b64` 已入帳（visual 站）;
  正式化後評估是否獨立 station 標籤以便分帳。

本模組把漫畫納入 eduStudio 的「目標導向首頁」，但以獨立 Comic Core 管理連載、版本、evidence 與發布規則。影片、簡報、圖卡既有工作站不受影響。原型需求參考《離岸風電教學漫畫製作系統_跨Session開發交接手冊_v1.0》，附件與既有 episode package 均保持唯讀。

## 使用流程

1. 在 `/app/` 輸入需求，或選擇「漫畫」。
2. 選定 Project；建立或選擇 Series 與 Episode。
3. 在 Series Bible 維護世界觀、角色 visual lock、角色 voice 與 glossary。
4. 產生或編輯 script、storyboard、camera、learning point、對白與 alt text。
5. 建立 Evidence Pack；AI prompt 會攜帶角色與世界觀 lock，並禁止把 teaching story 寫成 field instruction。
6. 逐頁生成或上傳 scene asset。對白不烙在圖片內，保留 34–38% negative space 供版面配置。
7. 完成 anatomy、technical、text、safety、page_render、human_approval 六道 QA gate。
8. 只有 validation PASS 的版本可進入 `CURRENT`，只有 `CURRENT` 可發布到 Internal Reader。
9. 匯出 HTML、PDF、DOCX 或 source ZIP；發布後仍可撤回 release，修改內容則必須 fork 新版本。

## 架構決策

- 共用 eduStudio：Project、設定、AI provider、成本紀錄、統一入口與 artifact library。
- 獨立 Comic Core：Series Bible、Episode manifest、page/dialogue schema、evidence、asset provenance、QA、version 與 serialized reader。
- File-first：磁碟上的 `manifest.json` 是漫畫版本的單一真相；所有 source Markdown 與 history revision 都可直接檢查。
- Fail-closed：mock image、缺 evidence、缺 scene、缺 alt text、缺 QA 或未人工核准都不可發布。
- CURRENT immutable：已核准版本不能直接改稿；export/release 只追加 audit metadata。

```text
projects/{project_id}/comics/
├─ series/{series_id}/series.json
└─ episodes/{story_id}/{version}/
   ├─ manifest.json
   ├─ source/
   │  ├─ storyboard.md
   │  ├─ dialogue_script.md
   │  ├─ image_prompts.md
   │  ├─ technical_sources.md
   │  ├─ qa_report.md
   │  └─ revision_notes.md
   ├─ assets/
   ├─ exports/
   └─ history/manifest_rNNNN.json
```

## API

API prefix：`/projects/{project_id}/comics`

- Series：`GET/POST /series`、`GET/PUT /series/{series_id}`
- Episode：`GET/POST /episodes`、`GET/PATCH /episodes/{story_id}`、`POST /episodes/{story_id}/fork`
- AI：`POST /episodes/{story_id}/generate/script`、`generate/storyboard`、`generate/images`、`compose-prompts`
- Evidence / QA：`PUT /episodes/{story_id}/evidence/{source_id}`、`PUT /episodes/{story_id}/qa/{gate}`、`GET /validation`
- Assets：`POST /episodes/{story_id}/assets`、`GET /episodes/{story_id}/{version}/assets/{asset_id}`
- State / release：`POST /state`、`POST /publish`、`POST /{version}/releases/{release_id}/withdraw`
- Export：`POST /exports/{html|pdf|docx|source}` 與對應 download URL
- Reader：`GET /reader/{story_id}`、`GET /reader/series/{series_id}`
- Legacy package：`POST /discover` 僅掃描，`POST /import` 複製 normalized package；來源永不改寫。

## 輸出邊界

- DOCX 在 Windows + Microsoft Word + pywin32 環境優先輸出 native Shapes：背景圖、每個對白框、每個尾巴皆可獨立移動與編輯。
- 無 Word COM 時回退為 `editable_table_fallback`，API 會回傳實際 mode，不會冒充 native Shapes。
- PDF 是閱讀版；HTML Reader 提供 alt text 與 transcript；source ZIP 保留 manifest 與六份 Markdown。
- AI API 未設定時仍可完整人工編輯、匯入與匯出。離線 MOCK 只測流程，provenance 會讓正式發布失敗。

## 啟動與驗證

```powershell
# Backend
python -m server.main

# Frontend build
Set-Location frontend
npm test -- --run
npm run build

# Comic focused tests（回到 repository root）
python -m pytest tests/test_comics.py tests/test_comics_route.py -q
```

已驗證的代表案例：

- 真實 W11《齒間的線索》：20 pages、60 dialogues、8 evidence sources、11 scene assets；來源逐檔 SHA-256 比對 0 變更；匯入後停在 HOLD 等待新系統 human approval。
- Word native Shapes：2 pages、10 shapes、0 overflow，並由 Microsoft Word 實際轉存 PDF 後做 raster visual QA。
- Responsive UI：1440 px desktop 與 430 px mobile 無水平 overflow。

上述數字是本機 software/structure QA，不代表教學內容、技術正確性或 offshore field acceptance；正式 Episode 仍須各 gate reviewer 簽核。
