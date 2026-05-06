# TODO

短期可以立刻做、小而具體的事項。
大方向規劃看 [ROADMAP.md](ROADMAP.md),這邊放 actionable items。

規則:
- 完成的打勾,每隔一陣子把勾完的搬去 CHANGELOG 或刪掉
- 新增項目加日期當引用(方便之後追)
- 優先度標示:🔴 高 / 🟡 中 / 🟢 低

---

## 🔴 高優先

### 實戰驗證
- [ ] **跑一份真正剛考完的期中考 PDF 完整流程**
  - 上傳 → 解析 → 逐題 review → 渲染 → 聽 3 支輸出
  - 紀錄:哪些 step Gemini 寫錯、哪些發音不準、哪些版面卡到
- [ ] **完整跑一支 13~19 分鐘簡報影片驗證**
  - exams/第8章_教學簡報_火影風_擴充版.json 已 ingest 好,挑 ch1 渲染聽
  - 觀察:長影片有沒有累積誤差(SRT 偏移、TTS 變調)、F5 還是 edge 比較適合長片

### Phase 4 split-left layout (2026-05-07)
- [ ] **`SlideRenderer` 加 layout="split-left"**
  - 投影片縮到左半,右半當黑板區疊累積式 step
  - 用途:解題型投影片,讓 step-by-step 解答跟原投影片並陳
  - 詳見 plan_slidevideo.md Phase 4

### F5 品質
- [ ] **F5 mid-word 切點問題**(2026-05-06)
  - 「處理與應用」被切成「處」+「理與應用」, F5 內部 batch 不顧中文詞邊界
  - 治本: 預切句邏輯 — 在 F5TTS class 裡用標點先切短段, 逐段 infer 後 concat
  - 預期能根除大部分中-中切錯;不解中文-英文切換的口音漂移
- [ ] **F5 中國腔仍明顯**(F5 base model 訓練資料偏向)
  - 短期可調 cfg_strength 拉更高試, 過高會 over-fit
  - 中期: 試 GPT-SoVITS 等其他台灣腔友善的 model
  - 長期: 自己 fine-tune 一份台灣腔 checkpoint

---

## 🟡 中優先

### Gemini / narration
- [ ] **截斷率仍 22%**(2026-05-07)
  - 三段式 retry + truncate 之後仍然有 22% 頁面 narration 不完整
  - 候選: 換 Gemini 2.5 Pro (更穩但慢且貴) 跑詳盡模式;或加第 4 次 retry
- [ ] **Pronunciation map 缺漏收集**
  - 跑幾份考卷後列出 F5 / Edge 念錯的字,補進 `pronunciation.json`
  - 候選未加但可能需要:`-` → `減`(注意 `-1` 是負一不是減一)、`×10⁶` 念法

### 聲音品質
- [ ] **錄音腳本工具**:`tools/record_ref_script.py`
  - 產生一份適合當 F5 ref 的朗讀腳本(10~12 秒、抑揚頓挫)
  - 你錄完直接放 voices/

### UI / UX
- [ ] **考卷列表上傳 PDF 後的預覽**
  - Gemini 解完直接進編輯頁有點突兀
  - 或許中間插一個「這是辨識結果,check 一下」的概覽頁?
- [ ] **上傳審查頁的描述自動帶時間軸**(plan_youtube_agent.md 提到)
  - 依 step durations 算累積時間, 自動產 YouTube 時間軸 chapter
- [ ] **上傳審查頁加 SRT 重新生成預覽**(若用戶手動編了 narration 後)

### 渲染細節
- [ ] **`display` 超長會 overflow?**
  - 步驟文字現在有換行但字型大, 2 行還 OK, 3 行以上可能溢出

---

## 🟢 低優先

### 新功能
- [ ] **字幕燒進影片選項**(ROADMAP v1.5)
- [ ] **Email 通知**:批次渲染完成寄信給自己
- [ ] **包成 Claude Code skill**(2026-05-06,留 v2.2)
  - `pdf-to-video` skill: PDF → JSON → 暫停 review → render
  - `video-to-youtube` skill: 已 review JSON → publish.py
  - 設計考量:強制 review 點(配合硬規則「AI 數值要人工 review」)
- [ ] **v2.1 ideate.py**(plan_youtube_agent.md)
  - 掃 watched_folders → Gemini 分析 → proposals.json → app.py 列企劃

### 技術債
- [ ] **`pipeline.py` 拆檔**(800+ 行)
  - 候選切法:render / tts / srt / photo overlay 各一檔
  - 優先度低,能跑就好
- [ ] **app.py 的 HTML template 拆出 `templates/` 資料夾**
  - 頁面再多就值得拆,目前 4 個頁還能忍
- [ ] **單元測試**
  - 至少 `normalize_for_tts`、`sanitize_exam_name`、`wrap_text_for_font` 這些純函式該有 pytest

### 文件
- [ ] **寫一份「操作手冊」給研究室助理**
  - Kiwi、Christian 之後接手時有 reference
  - 包含:設 API key、上傳流程、錯誤排除
- [ ] **做一個 demo 影片**
  - 自己的 YouTube 頻道開專區介紹這個系統

---

## 已知問題(未決,先記著)

- **F5-TTS 幻覺**:ref 12 秒 cutoff + ref_text 對齊是主因,用 YouTube 抽音軌的 ref 品質不穩。v2 處理。
- **Gemini 偶爾寫錯單位**:硬規則是人工 review,不是系統 bug。
- **edge-tts 停用了 `zh-TW-YunJheNeural`**:台灣男聲目前無選項,只能用大陸男聲。沒辦法。
- **Windows 終端 cp950 吃不下 emoji**: 已用 `sys.stdout.reconfigure` 解決。

---

## 已完成(偶爾清一清)

搬到 ROADMAP 的 v1.x 去。這裡只保留最近 1~2 週的。

- [x] 2026-05-07 narration 長度收斂(prompt 三輪迭代 + 3 段式 retry + truncate 兜底)
- [x] 2026-05-07 F5 暴露 cfg_strength / cross_fade_duration / nfe_step
- [x] 2026-05-07 ζ / ω_n 改念概念名(避中-英切換 + 中國腔)
- [x] 2026-05-07 pronunciation map 套用層下移到 tts_backend(原本只在 pipeline 套, tts_compare 跳過)
- [x] 2026-05-06 v2.0 publish.py CLI + UI 整合(YouTube 上傳通道)
- [x] 2026-05-06 v1.7 Phase 1+2+3+5(簡報講解影片擴充)
- [x] 2026-04-22 批次 / 網頁管理介面(`/exams` / `/upload` / `/switch` / `/library`)
- [x] 2026-04-22 影片 per-exam subfolder
- [x] 2026-04-22 Web UI 聲音選單 + 試聽
- [x] 2026-04-22 F5-TTS backend + fallback
- [x] 2026-04-22 老師頭像 overlay
- [x] 2026-04-22 SRT 按句切
- [x] 2026-04-22 題目 / 步驟自動換行 + 底部字幕預留 + 滾動
- [x] 2026-04-21 字型 fallback(`≤` `≥` 不再 tofu)
- [x] 2026-04-21 Pronunciation map
