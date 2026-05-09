# claude.md — 教學影片自動生成平台

## 專案目的

一條 pipeline,三種輸入,終點 YouTube:

1. **考題 PDF** → 黑板風格逐題解答影片(配老師旁白 + SRT)
2. **教學簡報 PDF** → 投影片講解影片(逐頁旁白)
3. **Blog / 文件 / 程式碼 repo (txt/md/pdf/url)** → AI 產簡報內容 → 講解影片

設計原則:同一條渲染核心、同一套 TTS / 字幕 / YouTube 上傳通道、同一個 Web UI。

## 關於我

- **劉瑞弘 (Dof)** — 國立勤益科技大學 智慧自動化工程系 副教授
- 教學科目:材料力學、自動控制、風力發電系統、C/Python 程式設計
- DOF Lab: doflab.cc
- 開發環境:Windows 11 + RTX 4080, 必要時 WSL

## 三條 Track(過渡期共存,目標合一)

```
                         ┌─── Track A (port 5000): app.py Flask
                         │      考卷 / 簡報 review-and-render UI (成熟,業務在跑)
                         │      v1 exam schema, 逐題逐段編輯 + YouTube 上傳審查
[ pipeline.py ]          │
   渲染核心       ◄──────┤ ─── Track B (port 8000): server/ FastAPI + JobStore
( BlackboardRenderer     │      5 種 source: exam_pdf / slides_pdf / repo / document / url
  SlideRenderer          │      非同步 job + 磁碟持久化 + 排程友善
  PptxStyleRenderer )    │      ⚠ 缺 YouTube 整合 + 考卷編輯 UI (v3.1 補)
                         │
                         └─── Track C (web/): React 18 SPA
                                掛 :8000/ui/, deck schema 編輯
```

**v3.1 主任務**:把 Track A 功能搬進 Track B,只留一個入口。詳見 [ROADMAP.md](ROADMAP.md)。

## 技術棧

- **Python 3.10+** 後端主語言
- **FastAPI + uvicorn + Pydantic v2** Track B server
- **Flask 3** Track A (legacy, 過渡期保留)
- **React 18 + TypeScript + Vite + Tailwind CSS** Track C
- **FFmpeg** 影片合成
- **Gemini 2.5 Flash** (Vision + Text) PDF 讀題 / 大綱 / 簡報內容
- **PyMuPDF** PDF → PNG
- **BeautifulSoup4** URL adapter
- **edge-tts / F5-TTS** TTS 兩條線
- **Pillow** 黑板 / Forest pptx 純畫
- **Google YouTube Data API v3** 上傳 (publish.py)

## 硬規則(不可妥協)

1. **AI 產出的數值不能未經人工 review 就當最終答案。**
   - 適用每個 step、公式、數字。Web UI 存在就是為了逐段檢查。
   - 對 `exam_pdf` 強制 `require_review=True`,job 停在 `awaiting_review`。
   - 學術誠信底線,不接受任何折衷。
2. **不要自動 `git commit`。** 變更等我明確確認後再 commit。
3. **修 bug 前先跟我討論**,除非顯而易見 typo。
4. **新功能進 Track B 不進 Track A**(2026-05 起)。Track A 只維護現有業務,等 v3.1 完成 redirect。
5. **字型路徑不寫死。** 用 `CLAUDE_FONT_PATH` / `CLAUDE_FALLBACK_FONT_PATH` / `CLAUDE_MONO_FONT_PATH`,Win/Mac/Linux 都跑得動。
6. **設定檔 / 路徑常數集中 `core/config.py`**,不在各模組各定義 BASE_DIR。

## 目前進度速查

| 階段 | 狀態 | 對應 ROADMAP |
|---|---|---|
| v0 POC(沙箱黑板渲染) | ✅ | v0 |
| v1 本機完整考卷產品 | ✅ | v1.0~v1.6 |
| v1.7 簡報講解擴充 (Phase 1/2/3/5) | ✅ | v1.7.0~v1.7.4 |
| v1.7 Phase 4 split-left layout | ⏳ 推到 v3.3 | v1.7.5 |
| v2.0 YouTube 上傳通道 (Track A) | ✅ | v2.0 |
| v3.0 平台基礎 (PR-1 ~ PR-3e) | ✅ | v3.0a~g |
| **v3.1 平台合一 (PR-3f ~ PR-3i)** | 🔴 進行中 | v3.1 |
| v3.2 基礎建設 (測試 / log / 重渲染) | 🟡 並行 | v3.2 |
| v3.3 體驗加分 (Navy / F5 / split-left) | 📋 排隊 | v3.3 |
| v4 平台收斂 (worker / Docker / ideate) | 📋 規劃 | v4 |

## JSON Schema

### v1 exam schema(`solve.py` / Track A)

```json
{
  "exam_title": "材料力學 — 期中考",
  "problems": [
    {
      "id": "q1",
      "number": "第 1 題",
      "score": 20,
      "problem": "題目原文",
      "steps": [
        {
          "_section": "題目解讀 | 觀念切入 | 公式導入 | 代入計算 | 易錯提醒",
          "display": "黑板顯示 (≤40 字)",
          "narration": "口語 (60~180 字)"
        }
      ]
    }
  ]
}
```

### deck schema(repo / document / url,Track B 新)

```json
{
  "deck_title": "...",
  "source_type": "repo | document | url",
  "source_meta": { "path": "...", "primary_language": "python" },
  "sections": [
    {
      "id": "intro",
      "title": "...",
      "slides": [
        {
          "id": "intro_1",
          "title": "...",
          "bullets": ["..."],
          "code_snippet": null,
          "code_lang": null,
          "file_path": null,
          "narration": "(100~200 字)"
        }
      ]
    }
  ]
}
```

渲染前用 `core.deck.deck_to_exam_schema_pptx` 壓平成 v1 schema 餵 pipeline。

## 開發偏好 / 溝通風格

- **直接、精簡。** 不要客套開場/結尾、不要過度解釋。
- **技術討論用繁體中文**,程式碼註解也以繁中為主。
- **架構層面決策先列選項 + trade-off**,別直接動手做一版丟給我。
- **Bullet point 可以用,實用為主**,不要為湊格式寫廢話。
- 每次交付前,先簡述「改了什麼、為什麼、有哪些副作用」。
- 「快版」= 只給結果不解釋
- 「審查」= 只找問題不重寫

## 我熟的 / 不熟的

**熟:** Python、Windows/Linux、MCP、RAG、SCADA、風力發電、工業通訊協定 (Modbus TCP/OPC UA)、IEC 61400、學術論文寫作

**不太熟但願意學:** 前端細節、複雜 CSS 動畫、React 生態(逐漸熟)、雲端部署 (AWS/GCP)

## 相關背景 Context

- 實驗室有兩位研究生會接觸到這個 repo:Kiwi (RAG domain)、Christian (RAG 架構)
- 工具未來可能整合進 IAE 系課程網站 / 我的 YouTube 頻道
- 影片輸出考慮檔案大小,單題目標 < 3 MB(1 分鐘左右)
- 簡報講解類影片每章 ~15 分鐘,長片要注意 TTS 累積誤差

## Git 同步規則

- 開始工作前先執行 `/sync`
- 結束工作前 commit + push
- 切換環境(本地 ↔ 雲端)前確認 `git status` 乾淨
- 主目錄開 branch,不用 worktree(主目錄 = 工作區,避免測試摩擦)
