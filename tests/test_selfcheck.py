"""D-5 啟動自檢測試 — 鎖 collect_checks / format_report 行為。

全程 monkeypatch（shutil.which / config getter / 環境），不打真 API、不碰真實
ffmpeg/字型，純函式驗證綠/紅判定與報告排版。
"""
from __future__ import annotations

import core.selfcheck as selfcheck
from core.selfcheck import Check, collect_checks, format_report


def _checks_by_name(checks: list[Check]) -> dict[str, Check]:
    return {c.name: c for c in checks}


def _all_present(monkeypatch, tmp_path, *, key="AIzaTest"):
    """讓所有自檢項都通過：ffmpeg/ffprobe 在 PATH、字型存在、key 已設。"""
    font = tmp_path / "font.ttf"
    font.write_bytes(b"\x00")
    monkeypatch.setattr(selfcheck.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(selfcheck, "get_font_path", lambda: str(font))
    monkeypatch.setattr(selfcheck, "get_fallback_font_path", lambda: str(font))
    monkeypatch.setattr(selfcheck, "get_mono_font_path", lambda: str(font))
    monkeypatch.setattr(selfcheck, "get_gemini_api_key", lambda: key)


class TestCollectChecks:
    def test_all_green(self, monkeypatch, tmp_path):
        _all_present(monkeypatch, tmp_path)
        checks = collect_checks()
        assert all(c.ok for c in checks)
        # 鎖住自檢項集合，未來拿掉某項該 fail 提醒
        assert {c.name for c in checks} == {
            "ffmpeg", "ffprobe", "font_main", "font_fallback", "font_mono", "gemini_api_key",
        }

    def test_ffmpeg_missing_is_critical(self, monkeypatch, tmp_path):
        _all_present(monkeypatch, tmp_path)
        monkeypatch.setattr(
            selfcheck.shutil, "which",
            lambda name: None if name == "ffmpeg" else f"/usr/bin/{name}",
        )
        by_name = _checks_by_name(collect_checks())
        assert by_name["ffmpeg"].ok is False
        assert by_name["ffmpeg"].critical is True
        assert by_name["ffprobe"].ok is True

    def test_missing_font_is_critical(self, monkeypatch, tmp_path):
        _all_present(monkeypatch, tmp_path)
        monkeypatch.setattr(selfcheck, "get_font_path", lambda: "/no/such/font.ttf")
        by_name = _checks_by_name(collect_checks())
        assert by_name["font_main"].ok is False
        assert by_name["font_main"].critical is True

    def test_missing_key_is_warning_not_critical(self, monkeypatch, tmp_path):
        _all_present(monkeypatch, tmp_path, key=None)
        by_name = _checks_by_name(collect_checks())
        assert by_name["gemini_api_key"].ok is False
        # 缺 key 是黃字警告（非 critical）—— 仍可瀏覽/設定
        assert by_name["gemini_api_key"].critical is False

    def test_empty_key_treated_as_missing(self, monkeypatch, tmp_path):
        _all_present(monkeypatch, tmp_path, key="")
        by_name = _checks_by_name(collect_checks())
        assert by_name["gemini_api_key"].ok is False


class TestFormatReport:
    def test_green_marks_when_all_ok(self, monkeypatch, tmp_path):
        _all_present(monkeypatch, tmp_path)
        report = format_report(collect_checks())
        assert "✅" in report
        assert "❌" not in report
        assert "⛔" not in report  # 無 critical 缺項 → 不印醒目總結

    def test_critical_missing_shows_red_and_summary(self):
        checks = [
            Check(name="ffmpeg", ok=False, detail="找不到", critical=True),
            Check(name="gemini_api_key", ok=False, detail="未設定", critical=False),
        ]
        report = format_report(checks)
        assert "❌ ffmpeg" in report
        assert "⚠  gemini_api_key" in report  # 非 critical 用 ⚠ 不用 ❌
        assert "⛔ 缺少核心相依：ffmpeg" in report
        assert "gemini_api_key" not in report.split("⛔")[1]  # 總結只列 critical


def test_print_startup_selfcheck_prints_and_returns(monkeypatch, tmp_path, capsys):
    _all_present(monkeypatch, tmp_path)
    result = selfcheck.print_startup_selfcheck()
    out = capsys.readouterr().out
    assert "啟動自檢" in out
    assert len(result) == 6
