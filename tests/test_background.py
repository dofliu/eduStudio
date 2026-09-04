"""T1-3 背景任務管理測試 — `server/background.py`。

覆蓋兩個原本的缺口:
- 並行上限(連送 N 個 job 不再同時搶 ThreadPoolExecutor)
- task 強參照(`create_task` 回傳值被丟掉 → 理論上可被 GC 中途回收)
"""
from __future__ import annotations

import asyncio

import pytest

from server import background
from server.background import (
    MAX_CONCURRENT_ENV,
    max_concurrent_jobs,
    pending_count,
    spawn,
)


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """每個 test 用乾淨的 task set 與未設定的並行環境變數。"""
    monkeypatch.setattr(background, "_TASKS", set())
    monkeypatch.delenv(MAX_CONCURRENT_ENV, raising=False)
    yield


class TestMaxConcurrentJobs:
    def test_default_when_unset(self):
        assert max_concurrent_jobs() == background.DEFAULT_MAX_CONCURRENT_JOBS

    def test_reads_env(self, monkeypatch):
        monkeypatch.setenv(MAX_CONCURRENT_ENV, "5")
        assert max_concurrent_jobs() == 5

    @pytest.mark.parametrize("value", ["0", "-1"])
    def test_zero_or_negative_means_unlimited(self, monkeypatch, value):
        monkeypatch.setenv(MAX_CONCURRENT_ENV, value)
        assert max_concurrent_jobs() <= 0

    def test_garbage_falls_back_to_default(self, monkeypatch):
        """打錯字不該默默把保護關掉。"""
        monkeypatch.setenv(MAX_CONCURRENT_ENV, "abc")
        assert max_concurrent_jobs() == background.DEFAULT_MAX_CONCURRENT_JOBS

    def test_blank_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv(MAX_CONCURRENT_ENV, "   ")
        assert max_concurrent_jobs() == background.DEFAULT_MAX_CONCURRENT_JOBS


@pytest.mark.asyncio
class TestConcurrencyLimit:
    async def test_never_exceeds_limit(self, monkeypatch):
        monkeypatch.setenv(MAX_CONCURRENT_ENV, "2")
        running = 0
        peak = 0
        release = asyncio.Event()

        async def work():
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await release.wait()
            running -= 1

        tasks = [spawn(work(), name=f"w{i}") for i in range(6)]
        await asyncio.sleep(0)      # 讓 task 起跑
        await asyncio.sleep(0)
        assert peak <= 2, f"同時跑了 {peak} 個, 超過上限 2"

        release.set()
        await asyncio.gather(*tasks)
        assert peak == 2, "上限內應該真的有並行, 不是被序列化"

    async def test_all_tasks_eventually_run(self, monkeypatch):
        """排隊不是丟棄 —— 每一個都要跑到。"""
        monkeypatch.setenv(MAX_CONCURRENT_ENV, "1")
        done: list[int] = []

        async def work(i):
            await asyncio.sleep(0)
            done.append(i)

        await asyncio.gather(*[spawn(work(i), name=f"w{i}") for i in range(5)])
        assert sorted(done) == [0, 1, 2, 3, 4]

    async def test_unlimited_when_disabled(self, monkeypatch):
        monkeypatch.setenv(MAX_CONCURRENT_ENV, "0")
        running = 0
        peak = 0
        release = asyncio.Event()

        async def work():
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await release.wait()
            running -= 1

        tasks = [spawn(work(), name=f"w{i}") for i in range(4)]
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(*tasks)
        assert peak == 4

    async def test_limit_false_bypasses_semaphore(self, monkeypatch):
        """YouTube 上傳這種純網路等待不該佔掉 render 名額。"""
        monkeypatch.setenv(MAX_CONCURRENT_ENV, "1")
        running = 0
        peak = 0
        release = asyncio.Event()

        async def work():
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await release.wait()
            running -= 1

        tasks = [spawn(work(), name=f"u{i}", limit=False) for i in range(3)]
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(*tasks)
        assert peak == 3


@pytest.mark.asyncio
class TestStrongReference:
    async def test_task_is_held_while_running(self):
        release = asyncio.Event()

        async def work():
            await release.wait()

        task = spawn(work(), name="held")
        await asyncio.sleep(0)
        assert pending_count() == 1
        assert task in background._TASKS, "跑到一半必須有強參照(否則可能被 GC)"

        release.set()
        await task
        await asyncio.sleep(0)
        assert pending_count() == 0, "完成後要移除, 不能無限累積"

    async def test_reference_dropped_after_failure(self, caplog):
        async def boom():
            raise RuntimeError("背景炸了")

        task = spawn(boom(), name="boomer")
        with pytest.raises(RuntimeError):
            await task
        await asyncio.sleep(0)
        assert pending_count() == 0

    async def test_failure_is_logged(self, caplog):
        """背景 task 沒人 await, 例外不記下來就等於消失。"""
        async def boom():
            raise RuntimeError("背景炸了")

        with caplog.at_level("ERROR", logger="server.background"):
            task = spawn(boom(), name="boomer")
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.sleep(0)
        assert any("背景工作失敗" in r.message for r in caplog.records)

    async def test_cancelled_task_is_not_logged_as_failure(self, caplog):
        async def forever():
            await asyncio.Event().wait()

        with caplog.at_level("ERROR", logger="server.background"):
            task = spawn(forever(), name="cancelme")
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.sleep(0)
        assert not any("背景工作失敗" in r.message for r in caplog.records)
        assert pending_count() == 0

    async def test_task_gets_a_name(self):
        async def work():
            return None

        task = spawn(work(), name="job:abc123")
        assert task.get_name() == "job:abc123"
        await task
