# Code Review — v3.1 + v3.2 (2026-05-09)

審查範圍:PR-3f ~ PR-5c 引入的新 code(13 個 commit)。獨立 reviewer(Claude Explore agent) + 自審。下面只列**真實問題**,跳過偽陽性。

---

## 🔴 P0 真該修(個人專案也建議補)

### 1. `core/logging_setup.py` `_job_handlers` 無 lock

```python
_job_handlers: dict[str, logging.Handler] = {}
```

同時兩個 `schedule_section_render` 觸發背景 task 跑 attach/detach,可能彼此覆蓋 handler reference,結果 log 寫到錯的檔。

**修法**:加 `threading.Lock()` 包 `attach_job_log` / `detach_job_log`。

**影響**:目前 runner 是 sequential(單一 process 同時只跑一個 task),不會踩到。但若未來改 worker pool 就會撞。

### 2. `server/runner.py` 的 `SystemExit` catch 太寬

```python
except (Exception, SystemExit) as e:
    _end_stage_fail(...)
```

當初為了 `solve.py` 缺 `GEMINI_API_KEY` 時會 `sys.exit()`(legacy 行為),所以接住。但這條也會接到 user Ctrl+C 觸發的 KeyboardInterrupt 嗎?(SystemExit 不算 BaseException 子類別,KeyboardInterrupt 才是,所以這條 OK)。

**真正的問題**:`solve.py` 應該改成 raise 而非 sys.exit,讓上層自己決定。`SystemExit` catch 是 workaround,不是設計。

**修法**:重構 `solve.py` 把 sys.exit 改 raise,這條 catch 改回單純 `Exception`。

### 3. 檔案上傳無 size limit

`server/routes/uploads.py` 的 `POST /upload` 接受任意大檔,理論上 100GB PDF 也吃進來。

**修法**:加 `Content-Length` 預檢查 + 串流寫檔(現在是 `await file.read()` 全載入記憶體)。

```python
MAX_UPLOAD_SIZE = 200 * 1024 * 1024  # 200 MB
content_length = request.headers.get("content-length")
if content_length and int(content_length) > MAX_UPLOAD_SIZE:
    raise HTTPException(413, "檔案過大")
```

### 4. `utc_now()` 缺 timezone

```python
def utc_now() -> datetime:
    return datetime.utcnow()  # naive, no tz info
```

寫進 state.json 的 ISO 字串沒 `Z` 字尾,前端 `new Date(s)` 在不同瀏覽器可能解讀成本地時間,顯示就跑 8 小時。

**修法**:用 `datetime.now(timezone.utc)`,Pydantic 序列化會帶 `+00:00`。

---

## 🟡 P1 應補(實戰會踩)

### 5. Idempotent publish(double-click)

`POST /jobs/{id}/artifacts/{name}/publish` 第一次按沒擋 button(只 server 端 409 second call),但前端按下後 setSubmitting 沒立刻 lock,使用者快速雙擊會看到一秒後跳「上傳已開始」+「409」交錯。

**修法**:`onSubmit` 一進入就 `setSubmitting(true)`,且 button `disabled={submitting || isUploading}`。

### 6. PptxStyleRenderer 對損毀 deck 沒 IndexError 防護

```python
step = data["steps"][step_idx - 1]   # 若 deck.json 損, step_idx 越界 → 500
```

**修法**:render 前檢查 `len(data.get("steps", []))`,缺就 raise 帶清楚訊息。

### 7. `read_job_log` 對長 log 整檔讀進記憶體

```python
lines = log_path.read_text(encoding="utf-8").splitlines()
return ... lines[-tail:]
```

實測 50 頁簡報 render 跑 30 分鐘 log ~ 5MB,200 行 tail 不到 60KB,**目前不是問題**。但若用戶把 mock=False + 詳盡 prompt 連跑幾天,單檔可能上百 MB。

**修法**(等真的踩到再做):seek 到末尾反向讀。或自動 rotate(每 10MB 切新檔)。

### 8. F5 預切失敗時暫存 WAV 不清

`tts_backend.py` `F5TTS.synthesize` 的 finally block 只在 try 成功時跑 cleanup,失敗(except 路徑)會留下 `.f5segNNN.wav` 在 OUTPUT_DIR 累積。

**修法**:把 cleanup 移到 `finally`,用 `seg_wavs` list 收集後統一 unlink。

---

## 🟢 P2 知道但暫不修(評估後可接受)

### 9. `tts_config.json` runtime 被改寫,容易誤 commit

`POST /voices` 跟 smoke test 都會改它。已踩到兩次(merge 前忘記 restore)。

**減緩**:加 pre-commit hook 偵測 `tts_config.json` 在 staged area 時警告。或直接把它加 `.gitignore`(配個 `tts_config.example.json` 當範本)。

不修原因:風險知道了,手動小心就行。

### 10. LogPanel auto-scroll 會打斷使用者往上看

每次 poll 拿到新 log 都 `scrollTop = scrollHeight`,user 想看歷史 log 滾上去就被打回最底。

**修法**:detect `scrollTop + clientHeight >= scrollHeight - 5`,只在「在底端」時才 auto-scroll。

不修原因:長 log 反正每秒重畫,user 通常只看最新。低頻痛點。

### 11. `_overlay_teacher_photo` import 失敗吞例外

```python
try:
    from pipeline import _overlay_teacher_photo
    _overlay_teacher_photo(img)
except Exception:
    pass
```

PR-2b-ii 寫的 fallback,擔心 pipeline.py 沒 load。但現在 pipeline 一定有,bare except 反而藏掉真實 bug。

**修法**:改 `except ImportError`(只接住 import 失敗,其他例外往外丟)。

不修原因:小範圍影響,pipeline 內部出 bug 黑板/簡報模式也會炸,優先抓那邊。

### 12. SRT 浮點時間漂移

50 頁影片約 15 分鐘,floating point sub_s 累積偏差 < 100ms,人耳幾乎聽不出。理論上應該用 integer ms。

不修原因:沒實測到問題。

---

## 已知測試覆蓋盲點

| 路徑 | 為什麼沒測 | 若要補 |
|---|---|---|
| `runner.py schedule_section_render` 並行情境 | 需 asyncio TestClient 場景 | `tests/test_runner_concurrent.py` |
| `library.py` srt 檢查邏輯 | 依賴 artifact dir setup | 加 fixture 寫假 mp4+srt |
| `pptx_style.py` 渲染邊界 | 需要字型 + Pillow + Windows path,跨 OS 難寫 | 留 visual integration test |
| F5 真實 inference | 需 GPU + 1GB model 下載 | 留 manual test |
| `burn_subtitles` 跨平台 | 需 ffmpeg + 真 subtitle 檔 | smoke test 用 mock subprocess |

---

## 我的優先序

如果你問「這些要做嗎」,我建議:

**v3.3 動工時順手做**(0.5 天):
- P0 #1 logging lock(5 行 code)
- P0 #4 utc_now timezone(2 行)
- P1 #5 publish double-click 防呆(前端 disabled)
- P1 #6 PptxStyleRenderer 防越界(3 行)
- P1 #8 F5 seg cleanup 移 finally(5 行)

**等踩到再做**:
- P0 #3 上傳 size limit(實際你只在 localhost 跑,沒外網)
- P0 #2 SystemExit refactor(等 Track A 退場後 solve.py 可以放心改)
- P1 #7 read_job_log 大檔(年用量內不會踩)

**就接受不修**:P2 全部。

---

## 補充:沒問題的部份

不是只挑毛病,以下是我審完覺得 OK 的:

- **140 tests 覆蓋 8 個 module**,純函式 + JobStore 的 read/write/CRUD 都有
- **Pydantic schema 嚴格** + TypeScript types 對齊
- **contextvar 隔離 job log**,跨 task 不會混
- **Static files path traversal 防護到位**(/slide_images / /artifacts 都有 `.relative_to()` 二次驗證)
- **schema dispatch (exam vs deck)** clean,type guard 在 client + server 各一份
- **Lazy import 在 core/__init__.py** 避免拉重型依賴

整體 OK,這是個維護得不錯的個人專案。

---

# Round 2 — 2026-05-10 (P0/P1 fix + Phase 4 + 三條實戰補洞)

審查範圍:7 個 commit (`7db9aab` ~ `07c4a45`),涵蓋 Round 1 的 P0/P1 follow-up + Phase 4 split-left + 三條實戰才踩出來的 hotfix。下面是這輪的觀察。

## 修正了什麼

### P0 全清 (commit 7db9aab)
- ✅ `core/logging_setup.py` `_job_handlers` 加 `threading.Lock`
- ✅ `utc_now()` → `datetime.now(timezone.utc)` (但開了新坑, 見 Lessons learned #1)
- ✅ `/upload` `MAX_UPLOAD_SIZE = 200 MB` + content-length 預檢
- ✅ `solve.py` / `scriptor.py` / `outliner.py` / `slide_ingest.py` `sys.exit` → `raise RuntimeError`, runner 兩處 `except (Exception, SystemExit)` 收回為純 `except Exception`

### P1 三條 (commit e093720)
- ✅ `PptxStyleRenderer.render` 加 step_idx 越界 `ValueError` (而非 `IndexError` 500)
- ✅ `F5TTS.synthesize` `tmp_files` list 收所有暫存, `finally` 統一 unlink (P1 #8)
- ✅ `PublishReview` `submittingRef` 同步擋雙擊 closure stale + button `isUploading` 條件 disabled

### Phase 4 split-left (commit 7b1eba2)
- ✅ `SlideRenderer.render()` dispatch `_render_full` / `_render_split_left`
- ✅ `core.deck.deck_to_exam_schema_slides` 透傳 `title + bullets` (`list(...)` 拷貝避免污染)
- ✅ `SlideEditor` 加 layout `<select>`, split-left 才顯示 bullets 編輯器
- ✅ 7 tests (5 dispatch + 2 deck passthrough)

### 實戰才補的三條 hotfix
- ✅ `f3fca88` AwareDatetime AfterValidator: 既存 naive state.json 與新 aware datetime 共存時 `sorted()` 不再 TypeError
- ✅ `318f5e8` F5 `_lazy_init` 改 `await asyncio.to_thread(...)`: 1.35GB safetensors 下載不再阻 event loop
- ✅ `e372b7f` `update_draft` 允許 `DONE` state: 接通 PR-4a 既有的 DONE section re-render 路徑
- ✅ `07c4a45` `_render_full` letterbox 進 `visible_h = HEIGHT - 180`: slide 底部 16.7% 不再被字幕帶蓋

## 這輪審完還剩的小問題

### 🟡 P1 殘留

**1. `_render_split_left` bullets 截斷檢查時機**

```python
for b in bullets:
    ...
    y = draw_text_wrapped(...)
    y += 14
    if y > content_y_max:
        break
```

`y > content_y_max` 在 bullet 已經畫完才檢查, 該條 bullet 可能本身就跨進字幕帶。實戰罕見 (bullets 通常 ≤ 4 條, 不會超), 沒踩前不修。

**2. `test_jobs_store.py` 仍有 `datetime.utcnow()`**

line 165 / 174 / 176 三處測試手寫 stage 用 `datetime.utcnow()` (naive)。經 `AwareDatetime AfterValidator` 自動 normalize, 不會炸, 但測試碼風格不一致。值得順手換掉。

**3. `_render_full` 縮小 16.7% 的迴歸風險**

舊 b40d51a96a07 (Chap05) 的 4 支 mp4 是 fix 前產的, 視覺比 fix 後大 17%。要不要重 render 看用戶決定; 不重 render 也能用, 只是底部 16.7% 缺失。文件沒提這個 visual regression, **README / ROADMAP 應該要記一筆** 讓未來看 commit 的人知道為什麼某些 mp4 看起來小。

### 🟢 P2 (接受)

**4. `AwareDatetime` 對所有 datetime 欄位都套用嗎?**

只套了 `JobRecord.created_at / updated_at`、`StageInfo.started_at / ended_at`、`YoutubeUpload.started_at / uploaded_at`。`Artifact` 沒有 datetime 欄位, OK。但若未來 schema 加新 datetime 欄位忘了用 `AwareDatetime` 而用 `datetime`, 同樣的 bug 會復發。**沒辦法 statically 強制**, 靠 review 抓。

**5. Phase 4 split-left bullets 上限沒明文**

UI 上沒寫「最多 4 條」, 用戶填 10 條會被靜默截斷。低頻痛點, 加個 hint 5 分鐘但目前先擱置。

## 沒問題的部份

- **AwareDatetime Annotated + AfterValidator** 設計乾淨, 對 Optional 自動跳過 None
- **F5 `_lazy_init` to_thread + `_render_full` 可視區** 兩個 hotfix 都有清楚 docstring 說明 root cause
- **DONE editable** 配 stale artifact warning + 隱藏 Approve button, UX 一致
- **PR-4a section render** 經 e372b7f 後完整接通 (本來只通一半: 准重 render 但不准改 deck)
- **148 tests + GitHub Actions matrix** 全綠

整體 OK。

---

# Lessons learned — Round 1 review 沒抓到、實戰才踩

這三條是 Round 1 (2026-05-09) 跟 P0 #4 fix 都漏掉的, **存進來給下次大改 schema / 加新 backend / 動 renderer 時的 checklist**。

## 1. 改 schema type 要做 data migration

**Round 1 P0 #4** 把 `utc_now()` 從 `datetime.utcnow()` (naive) 換成 `datetime.now(timezone.utc)` (aware), 沒考慮**既存 state.json 還是 naive ISO 字串**。Pydantic v2 把舊 ISO 字串 parse 成 naive datetime, 跟新建 job 的 aware 混存時 `sorted()` TypeError, GET /jobs 全部 500。

**修法** (commit f3fca88): `Annotated[datetime, AfterValidator(_ensure_aware_utc)]` 讀檔時 normalize naive → aware UTC, 全程記憶體裡都是 aware。

**下次改 schema type 前**:
- [ ] 既存資料 (state.json / deck.json / 其他持久化檔) 是不是用舊格式寫的?
- [ ] 新 type 接舊資料時 Pydantic 會怎麼 parse? (tz-naive / tz-aware / Optional / Enum 變動都會踩)
- [ ] 要不要寫個 normalize validator 兼容舊格式? 還是寫一次性 migration script?
- [ ] 加 regression test 模擬「混存舊新格式」的情境 (見 `tests/test_jobs_store.py::TestList::test_list_mixes_naive_and_aware_state_jsons`)

## 2. 單一 FastAPI process 的任何 sync I/O 都要 `to_thread`

**P1 #8** 修 F5 cleanup 移到 `finally`, 但沒注意 `_lazy_init()` 本身是 sync 且會觸發 huggingface 下載 1.35GB safetensors。在 `async def synthesize` 裡直接 `self._lazy_init()` → 阻塞 event loop → GET /jobs / Library / 所有端點 hang 5+ 分鐘。

Track A 沒踩是因為 Flask 多 process: web UI 跟 CLI render 是兩個 process, CLI 卡住不影響 web。Track B 改成單一 FastAPI process, **server 跟 background task 共用 event loop**, 任何 sync blocking call 都會炸。

**修法** (commit 318f5e8): `await asyncio.to_thread(self._lazy_init)`。`infer` 早就有 `to_thread`, init 漏掉。

**下次加新 TTS backend / model loader / 任何外部 I/O**:
- [ ] 是不是 sync (requests.get / subprocess.run / file I/O 大檔)?
- [ ] 在 async function 裡呼叫嗎?
- [ ] 要不要 `await asyncio.to_thread(...)` 包起來?
- [ ] 第一次跑會不會觸發隱性 download / cache build?
- [ ] 加個壓力測試或人工 timing 確認不阻 event loop

可以考慮在 `tts_backend.py` 加 module-level docstring 強調「所有 sync method 不能在 async 路徑裡直接呼叫」, 給未來開發者 (包括 Kiwi / Christian) 看。

## 3. Letterbox-fit 必須扣 overlay 區域才算可視區

**`_render_full` 一直存在的 bug** (從 PR-3h 引入 SlideRenderer 就有, Phase 4 才注意到): letterbox 的 `ratio` 跟居中算的是整個 1920×1080, 然後再 `draw.rectangle([0, 900, 1920, 1080])` 蓋字幕帶。結果 slide 底部 16.7% (footer 文字 / x 軸標籤) 完全被黑帶覆蓋, 觀眾看不到。

`BlackboardRenderer` 沒這問題 (本來就用 grid 計算, 主動避開字幕帶)。`PptxStyleRenderer` 也沒這問題 (`CONTENT_BOTTOM = VIDEO_HEIGHT - SUBTITLE_STRIP_HEIGHT` 明文)。只有 `SlideRenderer._render_full` 圖個方便 letterbox 整個 frame。

**修法** (commit 07c4a45): `visible_h = HEIGHT - 180`, ratio + 居中都用這個。

**下次寫新 renderer / 改 frame layout**:
- [ ] 字幕帶位置寫成模組常數 (e.g., `SUBTITLE_BAND_HEIGHT = 180`), 不要用 magic number
- [ ] 任何 「letterbox-fit 進 frame」邏輯, 可視區是 `HEIGHT - SUBTITLE_BAND`, 不是 `HEIGHT`
- [ ] 老師頭像位置 (`_overlay_teacher_photo`) 也要算進去 — 目前在右下角 220px, 跟字幕帶重疊 OK, 但若 layout 變了要重算
- [ ] 加 visual integration test 比較難 (需要字型 + Pillow + Windows path), 但起碼跑一次實機 mp4 看底部完整

## 通則:架構觀察

這三條的共通點是**抽象層的隱性假設**:

- **#1**: schema validation 假設「序列化 → 反序列化 round-trip 是 idempotent」, 實際 type 改了之後 round-trip 不對齊
- **#2**: async/await 假設「await 點之間 yield 給 event loop」, 實際 sync 呼叫不 yield
- **#3**: render layer 假設「frame = 整個 1920×1080」, 實際還有 overlay 區域 (字幕帶 / 老師頭像 / 動態 avatar)

這些假設在當下都看起來合理, 但**跨多個 commit / 多個層級才會浮現衝突**。靜態 review (Round 1) 抓不到, 要實戰跑或寫 integration test 才會炸。值得在 v4 規劃時想想能不能把這幾個假設明文化 (e.g., `core/visuals.py` 集中所有 layout 常數, `core/async_safe.py` 包所有 sync I/O 強制 `to_thread`)。

