# Code Review + 後續改善規劃 — 2026-07-09

> 範圍:全庫靜態審查(~65k 行 Python + React 前端)。方法:5 條並行子系統審查
> (server/API · pipeline/render · AI/內容生成 · 安全/設定 · 品質/架構/測試)+ 主審對
> 每條的最嚴重發現逐一 Read 驗證。file:line 皆對應本次 commit 時的原始碼。
>
> 這份接續 [docs/CODE_REVIEW.md](CODE_REVIEW.md)(v3.1+v3.2,2026-05)。**先報喜:上一份
> 列的 4 個 P0 已全部修掉**(logging lock、SystemExit catch 移除、上傳 200MB 上限、
> utc_now)——追蹤修復的紀律良好,這份沿用同樣的「只列真實問題」原則。

---

## 摘要

整體體質**明顯高於一般自架開源專案**:安全四大常見致命傷(命令注入 / path traversal /
secrets 落庫 / CORS)都有系統性防護且實際落地;`diagram_gen` 對 AI 生成的 matplotlib 程式
還走 AST allowlist + 受限 subprocess sandbox;規劃文件體系(ROADMAP / TODO /
PRODUCT_READINESS / STATUS)齊全。**沒有發現可被遠端未授權利用的嚴重漏洞。**

技術債集中、可控,但有兩條主軸值得優先處理:

1. **產品核心正確性**——系統的賣點是「絕不發布未驗證的 AI 數字」,但目前有 4 個缺口
   直接打在「考題答案 / 公式」這條最敏感的資料流上(其中 `clean_json_escapes` 會**靜默**
   把 `\theta`/`\times`/`\frac` 解析成控制字元)。這類 bug 不會 crash、review 也難察覺,
   風險最高。

2. **一次沒做完的架構遷移**——`core/` 被宣告為乾淨邊界,實際是頂層 CLI 腳本(solve.py /
   pipeline.py / slide_ingest.py)的**空殼再匯出層**,依賴方向反了。最重的業務邏輯滯留在
   print-only、弱測試、型別稀薄的根腳本裡,並外溢成 Gemini client(13+ 處)與 ffmpeg 指令
   (14+ 處)到處手刻的重複。

下面依「修了對產品最有感」的順序分 4 個 Tier;文末給分 Sprint 的執行建議。

---

## ✅ 已經做得好的部分(校準用,別動)

- **無命令注入面**:全庫 0 個 `shell=True` / `os.system` / `eval` / `pickle` /
  `yaml.load`;23 個 subprocess 呼叫全部 list-form argv。
- **Path traversal 一致落地**:`server/path_safety.py` 三道防護(字元檢查 → resolve →
  `relative_to`),且**每個**檔案下載端點都用了。
- **Secrets 衛生佳**:無密鑰進 repo,`.gitignore` 覆蓋完整,`/health` 只回布林,grep 無
  log 出金鑰。
- **Review gate 主閘門正確**:`server/runner.py:1393` render 前 assert `reviewed`、
  re-ingest 清 flag、draft 編輯重跑 flag——擋得住已審查流程被繞過。
- **CORS 預設安全**:預設只放行 localhost、`allow_credentials=False`。
- **prod compose 正確**:`docker-compose.prod.yml` 綁 `127.0.0.1` 且有明確警告。

---

## Tier 0 — 產品核心正確性(最優先,直擊「絕不發布錯誤數字」)

### T0-1 🔴 `clean_json_escapes` 靜默把最高頻 LaTeX 解析成控制字元 ✓已驗證
- **位置**:`core/text_utils.py:95`(影響 solve / scriptor / outliner / ideate 全部 JSON parse)
- **問題**:修復規則用黑名單 `(?<!\\)\\(?!["\\/bfnrtu])`,排除了 `b f n r t u` 開頭。但
  Gemini 最愛用的 `\theta`/`\tau`/`\times`(t)、`\nu`/`\nabla`(n)、`\beta`(b)、
  `\frac`/`\phi`(f)、`\rho`(r) 首字母正好都是合法 JSON escape 字元 → 不加倍 →
  `json.loads` 把 `\t`→Tab、`\n`→換行、`\b`→退格、`\f`→換頁塞進 display/narration。
  結果 `\theta = 30` 靜默變成 `<Tab>heta = 30`,`5 \times 3` 變 `5<Tab>imes 3`。
  `\alpha`/`\sigma` 反而正確,行為不一致。**這正是系統最在意的公式被無聲破壞**。
- **修法**:改白名單(只承認真正合法的 escape 情境),或對數學內容一律把單反斜線加倍,
  而非黑名單排除 `bfnrtu`。附回歸測試涵蓋 `\theta \times \frac \nu \beta \rho`。

### T0-2 🔴 考題 review gate 可被呼叫端一個參數關掉 ✓已驗證
- **位置**:`server/jobs.py:68-70`(`_resolve_default_review`:`if opt_value is not None: return opt_value`);
  既有繞過:`server/routes/uploads_pptx.py:93`、`scripts/submit_job.py --no-review`
- **問題**:gate 本身正確,但 `exam_pdf` 只是「預設」True。任何 `POST /jobs` 帶
  `options.require_review=false` 即可讓 AI 考題答案零審查 render/發布。若「絕不」是硬底線,
  `exam_pdf` 不該接受 caller 覆寫成 False。
- **修法**:`_resolve_default_review` 對 `EXAM_PDF`(與 `SONG`)強制回 True、忽略 `opt_value`
  (或至少記 WARN log)。

### T0-3 🟡 `review_assist` 對三角 / 開根號步驟靜默零檢查
- **位置**:`core/review_assist.py:163-172`(遇函式回 None)、`:234`(`len(evaluable)<2` 直接 return)
- **問題**:材力 / 動力學答案幾乎每步都有 `sin/cos/tan/√`,這些步驟一律不產 flag。reviewer
  看到「無 flag」會誤以為已驗證,但最容易按錯計算機的步驟恰好完全沒被檢查(高精度低召回的
  代價未對 reviewer 揭露)。
- **修法**:在 review UI 顯示「N 步無法自動驗證」的覆蓋率提示,別讓「無 flag」被解讀成
  「已驗證」。

### T0-4 🟡 解題路徑寫死舊模型、繞過設定頁金鑰 ✓已驗證
- **位置**:`solve.py:30`(`MODEL="gemini-2.5-flash"` 寫死)、`solve.py:168` / `core/ideate.py:315,408`
  (直接讀 `os.environ`,而非 `core/config.py:167 get_gemini_api_key()`);model id 三處分歧
  (`solve.py:30` / `core/config.py:189` / `core/models.py:67` 自稱「單一真實來源」)
- **問題**:① 只在設定頁填金鑰的部署,解題與自動企劃會 `RuntimeError`,而簡報/翻譯正常 →
  使用者困惑「為何只有解題壞掉」。② 使用者在設定頁選更強模型想提高解題正確性時,**考題解析
  (最該升級的路徑)完全無效**。③ model id 若與 live API 不符會 404 且無 fallback。
- **修法**:solve / scriptor / outliner 統一走 `core.models.resolve_id(...)` + `config.get_gemini_api_key()`,
  並在啟動期驗證 model id 存在性。

---

## Tier 1 — 穩定性 / robustness(會壞掉 / 會卡死)

### T1-1 🔴 `merge_dubbed_audio` filtergraph 索引錯位:任一段缺音檔就整個配音 job 崩潰 ✓已驗證
- **位置**:`core/video/dubber.py:207-218`
- **問題**:第 214 行 `[{i}:a]` 的 `i` 是 enumerate 全部 segments 的索引,但 `inputs` 只對
  「有音檔」的 segment 加 `-i`(208 行 `continue` 跳過)。只要有一段被跳過(空字幕 / 某段
  TTS 失敗),`[i:a]` 就指向不存在的輸入 → ffmpeg `Invalid file index`;第 217 行
  `range(len(filter_parts))` 產出的 `[a1]` label 也對不上實際的 `[a2]`,雙重錯位。**skip-guard
  的容錯意圖被索引算法完全反噬。**
- **修法**:對「保留的」segment 用獨立連續計數器 `j` 編號(`-i` 與 `[a{j}]` 一致遞增)。

### T1-2 🔴 外部呼叫全線無 timeout:一個卡住的進程就讓循序 worker 永久掛死 ✓已驗證
- **位置(系統性)**:23 個 subprocess 呼叫只有 2 個帶 `timeout`;所有 `generate_content`
  也都沒 timeout。ffmpeg/ffprobe/edge-tts/yt-dlp 遍布 `pipeline.py`、`tts_backend.py`、
  `core/video/dubber.py`、`core/video_concat.py`、`server/runner.py:901`;Gemini 呼叫遍布
  `solve.py`、`core/scriptor.py:448`、`core/outliner.py:181`、`core/ideate.py`、`core/infocards/gemini.py`
- **問題**:Track B 是循序 job worker,任一外部進程 / API hang 住就無限期占住整個 worker,
  後續 job 全塞住,retry 也不觸發(沒逾時就不算失敗),只能靠重啟的 `resume_interrupted` 收拾。
- **修法**:所有 subprocess 帶 `timeout=`(ffmpeg 依影片長度,如 600s);Gemini client 設
  request timeout。逾時捕捉 `TimeoutExpired` 標 job FAILED、計入 retry。

### T1-3 🟡 背景 job 無並行上限 + fire-and-forget task 可能被 GC 回收
- **位置**:`server/runner.py:1447-1468`(無 Semaphore);`runner.py:1452/1457/1468`、
  `routes/uploads_html.py:218`、`routes/uploads_pptx.py:117`、`routes/youtube.py:204`、
  `ideate_runner.py:224`(`create_task` 回傳值全被丟棄)
- **問題**:① 連送 N 個 job → N 個 `to_thread(ffmpeg/solve_pdf)` 搶預設 ThreadPoolExecutor,
  CPU / 記憶體爆掉還會餓死其他 handler 的檔案 I/O。② asyncio 只持 task 的 weak ref,無強
  參照理論上可被中途 GC → 背景工作靜默中斷。
- **修法**:module 級 `asyncio.Semaphore` 限並行;module 級 `set()` 存 task +
  `add_done_callback` 移除。

### T1-4 🟡 `state.json` 非原子寫入:寫一半 crash → job 整個消失(連 retry 都做不到)
- **位置**:`server/jobs.py:321-328`(`_persist` 直接 `write_text`);`jobs.py:104-109`
  對壞檔只 print 略過
- **問題**:程序在 `write_text` 期間被 kill → state.json 截斷 → 下次啟動解析失敗被跳過 →
  該 job 從唯一真實來源徹底消失。
- **修法**:寫 `.tmp` 後 `os.replace()` 原子換檔。

### T1-5 🟡 `VideoDubber` 暫存目錄從不清理 → 長駐 server 最終塞爆磁碟
- **位置**:`core/video/dubber.py:45`(`mkdtemp`)、`58-62`(每 job 子目錄累積)
- **問題**:每支影片的下載檔 / wav / 逐段 mp3 / 輸出 mp4 全留在 `/tmp`,無上限成長。
- **修法**:`process_video` 結束 `shutil.rmtree(job_dir, ignore_errors=True)`,或改用
  `TemporaryDirectory` context。

### T1-6 🟡 `pipeline.py` 硬寫 Windows 字型路徑、無 Linux fallback
- **位置**:`pipeline.py:37-38`(`FONT_PATH` 預設 `C:/Windows/Fonts/msjh.ttc`)
- **問題**:本部署是 Linux。`_get_font()` 遇不存在路徑直接 `OSError` → 整批渲染掛掉,只靠
  `CLAUDE_FONT_PATH` 環境變數兜。對比 `core/render/pptx_style.py:173` 有系統字型探測 +
  graceful degrade,pipeline.py 完全沒有。
- **修法**:比照 pptx_style 做候選字型探測 fallback。

### T1-7 🟢 dubber 三處 ffmpeg 不檢查 returncode → 靜默產出缺檔
- **位置**:`core/video/dubber.py:96-99`(抽音訊)、`187-189`(變速)、`193-195`(截斷)
- **修法**:一律走同檔已有的 `_run_cmd_checked` + `_assert_nonempty_file`。

---

## Tier 2 — 安全強化(縱深防禦,風險受「單一使用者自架」定位緩解)

### T2-1 🟡 SSRF:`url` 來源只驗 scheme,未擋內網 / metadata IP ✓已驗證(可用性)
- **位置**:`core/adapters/url.py:56-63` → `server/routes/jobs.py:75-81` → `server/runner.py:521 scan_url()`
- **攻擊**:`POST /jobs {"source_type":"url","source":{"url":"http://169.254.169.254/..."}}`,
  server 端代抓,內容還會被渲染進 deck,再 `GET /jobs/{id}/draft` 讀回。**未設 token(預設)時
  遠端未授權可觸發。**
- **修法**:解析後拒 RFC1918 / loopback / link-local / ULA,關 redirect 或每跳重驗,限 port 80/443。

### T2-2 🟡 不安全預設:base compose 對 `0.0.0.0` 開 port + 預設無 token ✓已驗證
- **位置**:`docker-compose.yml:29`(`"8000:8000"`,對照 prod 用 `127.0.0.1:8000:8000`)
- **攻擊**:快速上手文件叫使用者跑 base compose,而 `EDUSTUDIO_API_TOKEN` 預設未設 → 同網段
  任何人都能連上這台**無驗證** server(讀 job / 燒 Gemini 額度 / 觸發上面的 SSRF)。
- **修法**:base compose 也綁 `127.0.0.1:8000:8000`,要對外再由 override / 反代放行。

### T2-3 🟢 `editor.py` 的 `j.error` 未跳脫直接插 HTML(stored-XSS 缺口) ✓已驗證
- **位置**:`server/routes/editor.py:234`(`{j.error}` 生插;正上方 `:258 src_text` 卻有 `_html_escape`)
- **問題**:`j.error` 來自 `f"ingest 失敗: {e}"`,例外訊息常內嵌使用者提供的檔名 / URL → 儲存型 XSS。
- **修法**:`_html_escape(j.error)`。

### T2-4 🟢 schema 零輸入界限
- **位置**:`server/schemas.py`(50 個 `Field()` 但 0 個 `ge/le/max_length/max_items`)
- **問題**:`subtitle_font_size` / `max_files` / `photo_max_select` 可為負或極大值,字串 / list
  無長度上限,直達 ffmpeg 參數 / 迴圈。
- **修法**:數值加 `ge=/le=`,字串 / list 加 `max_length/max_items`。

### T2-5 🟢 其餘縱深強化(低優先)
- Auth cookie 存 raw 共享 token(非簽章 session)→ 無法單獨撤銷、外洩即永久全權(`auth.py:184`)。
- Dockerfile 以 root 執行 → 建非 root user + `USER app`。
- rate limit 只掛部分端點;`localization` 上傳無大小上限(`routes/localization.py:37`)。
- 上傳 `await file.read()` 仍整檔入記憶體(惡意省略 Content-Length 可 OOM)→ 改串流分塊。
- 寫金鑰檔時主動 `os.chmod(0o600)`。

---

## Tier 3 — 架構 / 可維護性(償技術債,最高槓桿在前兩項)

### T3-1 🔴 `core/` 是空殼再匯出層,依賴方向反了(根本技術債)✓已驗證
- **位置**:`core/__init__.py:72-119`(`__getattr__` lazy `from pipeline import main`、
  `from solve import solve_with_gemini`、`from slide_ingest import ingest`、`from batch import ...`)
- **問題**:docstring 自己寫「應該只 import core」,但遷移沒做完。最重的業務邏輯壓在
  solve.py / pipeline.py / slide_ingest.py 裡,這正是後面 Gemini / ffmpeg 分散、print-only、
  沒測試、型別稀薄的**根因**。(註:lazy import 本身為冷啟動有正當理由,問題在依賴**方向**。)
- **修法(漸進)**:把實作搬進 `core/` 模組,根腳本變薄 argloop CLI 呼叫 core;保留 lazy
  loading 但反轉依賴。這是最高槓桿的一步,其餘重複 / 拆檔問題多會隨之化解。

### T3-2 🟡 統一 Gemini client(13+ 檔各自 new,繞過 `core/providers` 與 `core/config`)
- **位置**:`ideate.py:320,418`、`scriptor.py:148,231`、`outliner.py:160`、`mermaid_render.py:246`、
  `diagram_gen.py:176`、`slide_ingest.py:186,472`、`solve.py:174` … 全 inline
  `genai.Client(api_key=os.environ.get(...))`
- **問題**:retry / timeout / model fallback / logging / mock 沒有單一落點,每個測試得逐點
  monkeypatch(也拖累測試品質)。與 T1-2(timeout)、T0-4(model)是同一根源。
- **修法**:所有文字 / 圖片生成走 `core.providers`,刪 inline client。**修這條會順帶解掉
  T0-4 / T1-2 的一半。**

### T3-3 🟡 統一 ffmpeg runner(~14 檔各自手組指令)
- **位置**:`core/srt.py`、`video_concat.py`、`image_frames.py`、`song_render.py`、
  `render/pptx_style.py`、`video/dubber.py`、`server/runner.py:905`、`pipeline.py`、`tts_backend.py` …
- **修法**:建 `core/ffmpeg.py` 的 `run_ffmpeg(args, timeout=...)`,集中 binary 解析 +
  timeout + stderr / 錯誤處理。**修這條會順帶解掉 T1-2 的另一半 + T1-7。**

### T3-4 🟡 移除 Track A(`app.py`)+ 收斂三個並存 UI ✓已驗證
- **現況**:三個 UI 並存——Track A(Flask `app.py` 1355 行)、legacy `web/`(React 18,`/ui`+`/studio`)、
  官方 `frontend/edustudio`(React 19,`/app`)。
- **`app.py` 可安全移除**:0 個模組 import 它、0 個測試測它、根路徑已 redirect 到 Track B;
  **但它 subprocess 呼叫的 solve.py/slide_ingest.py/publish.py/batch.py 不是 Track A 專屬
  (Track B 經 facade 也用),必須留下。** 確認 Track B 已覆蓋上傳/render/發布工作流後,刪
  app.py + 移除 Flask 依賴是低風險的一刀。legacy `web/` 依 PRODUCT_READINESS U-3 退場。

### T3-5 🟡 拆分 god 檔案
- `core/render/pptx_style.py`(2536 行)→ `pptx_theme` / `pptx_components` / `pptx_decorations` /
  `pptx_slides`;~20 個同簽名 `_draw_*` 裝飾改 registry dict 取代 if/elif 分派。
- `server/runner.py`(1468 行)→ `runner_ingest` / `runner_render` / `deck_intro_outro`,
  `runner.py` 只留編排;`_prepare_intro/outro_for_problems`(~90% 重複)合成帶參 helper。
- `frontend/edustudio/app.jsx`(**3508 行單檔 / 208KB**)→ 依工作站(影片 / 視覺 / 在地化 /
  發布)拆元件。
- `solve.py:163 solve_with_gemini()`(203 行,全庫最大函式)→ 拆 identify / solve / format 三 pass。

### T3-6 🟡 測試結構與覆蓋缺口
- 148 個測試檔全平鋪在 `tests/`(唯一子目錄 `fixtures/`)→ 鏡射原始碼樹(`tests/core/`、`tests/server/routes/`)。
- 零測 / 弱測的關鍵模組:`batch.py`(0)、`publish.py`(0,含真實 YouTube OAuth 上傳)、
  `slide_ingest.py`(558 行僅 1 檔)、`app.py` Flask 路由(0)、`routes/uploads_pptx.py`(0)。
- 至少補 `batch.problem_to_v0_json`、`slide_ingest.ingest` 單元測試。

### T3-7 🟢 一致性收斂
- **Logging**:`core/logging_setup.py` 有正規基建但只 3 個非測試模組 import;根腳本全 print
  (`solve.py` 16、`pipeline.py` 14、`publish.py` 18)→ 最重、跑最久的 pipeline 輸出是無結構
  stdout,無法被 Track B job log 捕獲。根腳本改用 logging_setup。
- **CI 依賴漂移**:`.github/workflows/test.yml:74` 手維護一長串 `pip install fastapi ...` 而非
  `requirements.txt` → 改 `pip install -r requirements.txt`(或 requirements-ci.txt)。
- **成本記帳失真**(非阻擋,但別當真實帳單):圖片「輸入」token 未計(`solve.py` 每頁 base64
  圖 0 計)、費率不分 model、未知 model 記 $0(`core/usage.py:28-33`)、char→token 用英文
  4:1 假設對繁中低估。依 model id 分別定價、未知 model fallback 到預設價而非 0。
- **`scan_artifacts` 用 module 級 `JOBS_DIR` 而非 `self.root`**(`server/jobs.py:240`,與同函式
  `:229` 不一致)→ root≠JOBS_DIR 時 `ValueError`,改 `self.root`。

---

## 建議執行順序(分 Sprint)

> 原則:先修「對產品最有感 + 低風險」的,再處理架構。Tier 3 的 T3-2 / T3-3 建議在動
> Tier 1 的 timeout 前先做,因為它們是同一根源——修抽象順帶解掉散落的 timeout / model 問題。

**Sprint 1(本週,產品核心 + 快速止血)**
- T0-1 `clean_json_escapes` 公式修復(+ 回歸測試)← 影響最大、最該先做
- T0-2 exam review gate 強制 True
- T1-1 dubber filtergraph 索引修復
- T2-2 base compose 綁 loopback、T2-3 `j.error` 跳脫(兩個一行修)

**Sprint 2(穩定性根源)**
- T3-2 統一 Gemini client → 落地 T0-4(model)+ 一半的 T1-2(timeout)
- T3-3 建 `core/ffmpeg.py` → 落地另一半 T1-2 + T1-7
- T1-3 並行上限、T1-4 state.json 原子寫、T1-5 dubber 暫存清理

**Sprint 3(安全縱深 + 輸入界限)**
- T2-1 SSRF 位址過濾、T2-4 schema 界限、T2-5 選項(cookie session 化 / 容器降權 / 限流)
- T0-3 review_assist 覆蓋率提示、T3-7 成本記帳分 model

**Sprint 4+(架構償債,長期)**
- T3-1 反轉 core 依賴(把邏輯搬進 core、根腳本變薄 CLI)← 最高槓桿但最大工程
- T3-4 刪 app.py + 收斂 UI、T3-5 拆 god 檔、T3-6 測試結構、T3-7 logging / CI 收斂

---

## 附:方法與驗證

- 5 條並行子系統審查,主審對每條最嚴重發現逐一 Read 原始碼驗證。
- 標 **✓已驗證** 者為主審親自複核程式碼確認屬實:T0-1、T0-2、T0-4、T1-1、T1-2、T2-1、
  T2-2、T2-3、T3-1、T3-4。
- 環境未裝 fastapi/pytest,未實跑測試套件;所有發現為靜態分析 + 交叉 grep 量化。
- 嚴重度以「單一使用者自架」定位校準(非多租戶 SaaS),故多數安全項落 🟡/🟢。
