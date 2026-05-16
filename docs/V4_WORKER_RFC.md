# V4 Worker RFC — 持久化 job 執行 (2026-05-16 草案)

> **狀態**: 🟡 **暫緩 (2026-05-16 劉老師決策)**
> **作者**: Claude (iter 73)
> **Reviewer**: 劉瑞弘
> **不動 code**, 只列選項 + trade-offs, 等你選了再實作.

---

## 2026-05-16 決策紀錄

**決策**: 暫緩 v4 worker, 個人使用情境不痛.

**Reasoning**:
- 目前單一用戶 (劉老師自己), 不對外開放
- Server 重啟頻率低, 沒踩到「跑一半的 job 死掉」場景
- 沒並發跑 ≥2 個 job 的需求
- 暫不部署 Cloud Run

**下次觸發條件** (任一中再啟動):
- 開始給學生 / 實驗室成員用, server 不能死
- 同時要 render 多個影片
- 部署到 Cloud Run / Heroku (free tier sleep 頻繁重啟)
- 加新 schema 欄位踩 migration bug

**現在優先做**: 影片內容品質 (主題 / 格式 / narration 等), 不動底層架構.

---

## 問題陳述

iter 22 code review 抓到 4 個 P0 結構性弱點 (STATUS.yaml 已列), 全是「沒
持久化 job 執行框架」造成的:

1. **無 job 持久化** — `asyncio.create_task()` 即起即忘, server 重啟丟所有 job
2. **單一 process sync I/O 仍是炸雷** — F5-TTS lazy_init 已踩過 (iter 22 Round 2), 沒 enforcement
3. **schema migration 無框架** — `state.json` 改型別還會踩 (Round 2 P0 #4 已踩)
4. **無 review gate 強制機制** — `require_review` flag 可繞

這 4 條都是同一個根因: **「我們用 asyncio.create_task 當 job runner 是
prototype 工具, 不是 production framework」**.

實際痛點 (我自己跑時遇到):
- server 重啟 → 跑到一半的 ingest job 全死. 用戶手動回去從 proposal 重發.
- F5-TTS 第一次 inference 載 1.35 GB safetensors 阻 event loop, GET /jobs 全 hang.
- 改 JobOptions schema (加 `cover_speaker` 等) 需要小心舊 state.json — 沒
  migration 機制, 只靠 Pydantic `extra="allow"` + Optional default 撐.

---

## 設計目標

按優先序:

1. **job 重啟存活** — server 死掉重啟, pending / running job 自動 resume
   (或 minimum: state 不掉, 可手動 retry)
2. **sync I/O 隔離** — TTS / ffmpeg / Gemini API 等 blocking call 不能阻
   server event loop
3. **job 觀測性** — 已有 per-job logging (PR-4c), 要保留 + 加 retry count /
   error history
4. **跨 process** — 至少分「web server」+「worker process」兩個, 不在同
   一個 process 跑 job
5. **Windows / Linux 雙跑** — 我主力 Win 11, 可能未來上 Cloud Run (Linux)

非目標:
- 不需要多 node 分布式 (我一台機就夠, 未來頂多 cloud 上 1-2 instance)
- 不需要 priority queue (job 量小, FIFO 夠)
- 不需要排程 cron (job 都是 user-triggered, 沒有 daily / weekly task)
- 不需要 dead letter queue 之類複雜 ops (個人 / 實驗室專案, 死了人工救)

---

## 選項

### 選項 A: BullMQ-style (Redis + 自寫 worker.py)

```
┌─ FastAPI (web)         ┌─ Worker process (python worker.py)
│  POST /jobs            │  while True:
│  → push to Redis queue │      job = redis.brpop("jobs", timeout=5)
│                        │      run_ingest_or_render(job)
│  GET /jobs             │      update Redis hset job:<id>
│  ← read Redis hset     │
└─                       └─
        ↑                          ↑
        └────── Redis (jobs queue + job:<id> hset) ──────┘
```

**依賴**: `redis-py`, 一個 Redis instance (Win: 用 WSL / Docker / Memurai)

**Pros**:
- Redis 是業界標準, 學習曲線大家都熟
- 重啟存活: 隊列在 Redis, job 不消失. server / worker 重啟自動 resume
- 跨 process / 跨機器 (未來上 Cloud 沒包袱)
- 已有 cloud Redis service (Upstash 等)

**Cons**:
- 多一個 Redis 依賴 — Win 11 上跑要 WSL/Docker 或 Memurai (商用免費版)
- Web ↔ Worker 兩個 process 要分別 deploy / docker-compose
- 自寫 worker.py + job dispatcher = ~200-300 行新 code

**估時**: 1.5-2 週 (含測試 + Docker compose 整合)

---

### 選項 B: Celery (Redis / RabbitMQ broker)

**依賴**: `celery`, Redis 或 RabbitMQ

**Pros**:
- 業界最成熟 Python task queue
- 內建 retry / chord / chain / canvas pattern
- Flower 提供 web UI 監控

**Cons**:
- Celery 對 asyncio 整合差 — 我們 server 是 FastAPI (async), Celery worker
  是同步, 兩邊 sync/async 邊界要小心
- 複雜度過高 — 我們的需求是「Job FIFO + 重啟存活」, Celery 是「任意拓樸
  task graph」. 多餘的能力反而是 maintainence 負擔
- Win 11 上 Celery 已知 bug 多 (concurrency 4+ 有時 hang), 解過 issue
  Linux 才是 first-class platform

**估時**: 1-1.5 週, 但 maintainence 長尾不可控

---

### 選項 C: RQ (Redis Queue, 比 Celery 輕)

**依賴**: `rq`, Redis

**Pros**:
- 比 Celery 簡單一個量級 — 3 個概念 (Queue / Job / Worker), API ~50 行學
- 一樣 Redis 後端, 一樣重啟存活
- Win / Linux 都跑

**Cons**:
- 對 asyncio 同樣不友善 (RQ worker 是同步)
- 還是要 Redis
- RQ 對長時 job (>10 分鐘) 心跳機制有點脆弱, 需要 tuning

**估時**: 1 週 (簡潔很多)

---

### 選項 D: 自寫 minimal queue (SQLite + 自寫 worker.py)

```
┌─ FastAPI (web)              ┌─ Worker (python worker.py)
│  POST /jobs                 │  while True:
│  → INSERT job row           │      job = sqlite.SELECT ... WHERE state='QUEUED'
│                             │           ORDER BY id LIMIT 1
│  GET /jobs                  │      UPDATE state='RUNNING', heartbeat=now
│  ← SELECT *                 │      run_ingest_or_render(job)
│                             │      UPDATE state='DONE' / 'FAILED'
└─                            └─
              ↑                              ↑
              └─── sqlite jobs.db (file lock + WAL) ───┘
```

**依賴**: 標準庫 `sqlite3` (已內建)

**Pros**:
- 零新依賴 — 只用 stdlib
- SQLite 已是事實上的 portable DB, file-based 沒 Redis instance 維運
- Win / Linux / Docker 全跑
- 重啟存活: job state 在 SQLite file, 不消失
- crash recovery 簡單: heartbeat 超時的 RUNNING job 視為 stale, retry 或 fail
- 跟現有 `state.json` 概念對接平順 (其實 state.json 本來就是 minimal "DB")

**Cons**:
- 沒有 Redis 那種真正的 atomic queue 操作 — 要靠 `BEGIN IMMEDIATE` +
  row-level state machine 自己保證, 若有 bug 會踩
- 跨 worker 競爭 row 需要 transaction + retry on busy (但我們頂多 2 worker)
- 沒 BullMQ / Celery 的 ecosystem (no Flower, 自己寫 minimal /workers UI)

**估時**: 1 週 (~400 行 code, 大部分是 worker.py + sqlite schema migration)

---

## 推薦: **D (SQLite + 自寫)**

**理由**:

1. **依賴最少** — 個人 / 實驗室專案, 多一個 Redis 維運成本實質高於價值.
   我目前在 Win 11 開發 + 可能 Cloud Run 部署, SQLite file 兩邊都跑.
2. **複雜度合需求** — 我們的場景是「user-triggered job FIFO + 重啟存活」,
   不是任意 task graph. Celery / BullMQ 的能力多數用不到.
3. **跟現有設計接平順** — `server/jobs.py` 的 `state.json` 本來就是
   minimal append-only "DB". 換成 sqlite 是 incremental upgrade, 不是
   重寫.
4. **schema migration 順帶解掉** — sqlite 加 schema_version column +
   `migrations/<n>.sql`, 解 P0 #3.

**捨棄 A/B/C 的理由**:
- A (BullMQ): Redis 多餘. 我們不需要 distributed atomic queue.
- B (Celery): 太重, asyncio 邊界爛, Win bug. 殺雞用牛刀.
- C (RQ): 比 B 好但仍需要 Redis. 若沒 Redis 痛點不夠強, 不該引入.

---

## 實作 outline (等決策再動)

如果你 OK 走 D, 預估拆 4 個 PR 漸進:

### PR D-1: SQLite jobs.db (schema only, 不動現有 runner)
- `server/jobs_db.py` (新): `JobsDB` class wrap sqlite3
- Schema: `jobs(id PK, state, source_type, options_json, created_at,
  updated_at, schema_version, error_json)` + index on state
- 跟 `state.json` 雙寫 (dual-write) — 兩邊保持同步, 但 read 仍走 state.json
- Tests: CRUD + 並發寫

### PR D-2: Worker process (worker.py)
- `worker.py` (新): poll sqlite, claim job (`UPDATE state='RUNNING' WHERE
  state='QUEUED' AND id=...` with retry on busy), run, update done/failed
- Heartbeat: `RUNNING` job 每 30s update `last_heartbeat_at`. Web 讀
  時若 `now - last_heartbeat_at > 90s` 視為 stale.
- 不串原本 `_run_ingest` / `_run_render` — 從 sqlite 撈 source_type +
  options, dispatch 到對應 phase.
- Tests: TestClient 起 worker thread + mock pipeline.

### PR D-3: Web 路由切到 sqlite
- POST /jobs → INSERT row + return 200 (不再 `asyncio.create_task`)
- GET /jobs → SELECT * (替代 state.json)
- 移除 dual-write (確認 sqlite 路徑穩了之後)
- Tests: 對齊現有 jobs_store tests, 改成走 sqlite

### PR D-4: docker-compose + migration framework
- `docker-compose.yml`: web + worker 兩個 service, share volume for sqlite
- `migrations/001_initial.sql`, `migrations/002_*.sql` 等
- `JobsDB.migrate()` 跑 pending migrations
- Tests: migration round-trip, downgrade safety

---

## 風險 / unknowns

| 風險 | 影響 | 緩解 |
|---|---|---|
| SQLite 並發寫衝突 | worker / web 同時 INSERT 可能 `database is locked` | WAL mode + `BEGIN IMMEDIATE` + retry. 已知模式. |
| Worker crash → RUNNING job 卡住 | 失去進度, 用戶看到 RUNNING 但實際死的 | heartbeat 超時偵測, ≥90s 視為 stale, 標 FAILED, allow retry |
| 大 deck (10 章) render 超過 30 分鐘 | heartbeat 機制需要在 render 內部跑而非 worker level | render_video 內每 N 秒 heartbeat (現有 logger 已有, 接它) |
| FastAPI / SPA UX 沒被改 | 應該沒問題, API contract 不變 | 對齊現有 JobRecord schema, 只換 storage layer |

---

## 替代方案: 拖到不做

如果上述 4 條 P0 你還沒實際痛到 (i.e., server 不常重啟, F5 已不用 / 改 edge,
你不 demo 給別人試), 可以**繼續用 asyncio.create_task** 不上 worker. 等
真痛了再啟動 D-1.

實際痛點檢查清單 (任一條中就該動):
- [ ] server 重啟超過 2 次 / 月, 每次都有 job 死掉重來
- [ ] 同時跑 2 個以上 job (現在單 process, sequential 跑)
- [ ] 要上 Cloud Run / Heroku (free tier 經常 sleep, 重啟頻繁)
- [ ] 對外 demo / 學生用, server 不能死

---

## 決策請求

請從以下三選一:

1. **走 D (SQLite + 自寫 worker)** — 我開始拆 D-1, 約 1 週
2. **走 A/B/C** — 哪個? 為什麼覺得 D 不行?
3. **暫不做 v4 worker** — 繼續用 asyncio.create_task, 哪天痛了再啟動

也歡迎完全不同方向 (例: 直接走 cloud function event-driven 之類). 上面只
是把我能想到的選項列出來.
