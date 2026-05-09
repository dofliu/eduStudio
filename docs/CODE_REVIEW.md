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
