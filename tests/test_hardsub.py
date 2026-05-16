"""PR-5c: 燒字幕 ffmpeg 指令組合 unit test (不跑 ffmpeg)."""
from __future__ import annotations

import subprocess
from pathlib import Path, PureWindowsPath
from unittest.mock import patch

import pytest


# pipeline.py 在頂部 import PIL / mutagen 等, 在 CI 環境 (有裝 Pillow) 可以跑
# 但 mutagen 可能沒裝, 所以包 try / 跳過避免擋整個 CI。
pipeline = pytest.importorskip(
    "pipeline",
    reason="pipeline.py 需要 PIL / mutagen, CI 沒裝就跳過",
)


class TestBuildHardsubCmd:
    def test_basic_structure(self):
        cmd = pipeline._build_hardsub_cmd("q1", Path("/fake/output"))
        assert cmd[0] == "ffmpeg"
        assert "-y" in cmd
        assert "-loglevel" in cmd
        assert "-vf" in cmd
        # 輸入是相對檔名 (避開 Windows path escape)
        assert "q1.mp4" in cmd
        # 輸出
        assert "q1.hardsub.mp4" in cmd

    def test_uses_relative_srt_path(self):
        # 為什麼用相對檔名: subtitles filter 在 Windows 上含冒號的絕對路徑
        # (D:\...) 要 escape, 用 cwd + 相對檔名最穩
        cmd = pipeline._build_hardsub_cmd("ch1", Path("/whatever"))
        vf_idx = cmd.index("-vf")
        vf_value = cmd[vf_idx + 1]
        assert vf_value.startswith("subtitles=ch1.srt")
        assert "ch1.srt" in vf_value
        # 不該有絕對路徑碎片
        assert "/whatever" not in vf_value
        assert "D:" not in vf_value

    def test_force_style_includes_chinese_font(self):
        cmd = pipeline._build_hardsub_cmd("foo", Path("/x"))
        vf = cmd[cmd.index("-vf") + 1]
        # FontName 應該是中文字型 (Windows 預設 Microsoft JhengHei)
        assert "Microsoft JhengHei" in vf

    def test_force_style_has_readable_settings(self):
        cmd = pipeline._build_hardsub_cmd("foo", Path("/x"))
        vf = cmd[cmd.index("-vf") + 1]
        # 應有底色 box (BorderStyle=3) 跟邊距 (MarginV)
        assert "BorderStyle=3" in vf
        assert "MarginV=" in vf
        # 字 white outline black 高對比
        assert "PrimaryColour" in vf
        assert "OutlineColour" in vf

    def test_audio_copy_not_reencoded(self):
        # 音訊重編浪費 CPU 又掉品質, 應該 -c:a copy
        cmd = pipeline._build_hardsub_cmd("foo", Path("/x"))
        assert "-c:a" in cmd
        assert cmd[cmd.index("-c:a") + 1] == "copy"

    def test_output_name_includes_hardsub_suffix(self):
        # 輸出檔名加 .hardsub 字尾, 給 burn_subtitles 後續 rename 用
        # (避免 ffmpeg input/output 同名讀寫衝突)
        cmd = pipeline._build_hardsub_cmd("q1", Path("/x"))
        assert "q1.hardsub.mp4" in cmd
        # 確實是最後一個參數 (output)
        assert cmd[-1] == "q1.hardsub.mp4"


class TestIter80SubtitleStyleOverride:
    """iter 80 (D2): 字幕字級 / 字色 / 描邊色可調."""

    def test_hex_to_ass_bgr_simple(self):
        from pipeline import _hex_to_ass_bgr
        # 白色 #FFFFFF → BGR = FFFFFF
        assert _hex_to_ass_bgr("#FFFFFF") == "&H00FFFFFF&"
        # 黑色
        assert _hex_to_ass_bgr("000000") == "&H00000000&"
        # 紅色 #FF0000 (R=255 G=0 B=0) → ASS = &H000000FF& (B=0 G=0 R=255)
        assert _hex_to_ass_bgr("#ff0000") == "&H000000FF&"
        # 藍色 #0000FF (R=0 G=0 B=255) → ASS = &H00FF0000&
        assert _hex_to_ass_bgr("#0000FF") == "&H00FF0000&"

    def test_hex_to_ass_bgr_invalid(self):
        from pipeline import _hex_to_ass_bgr
        assert _hex_to_ass_bgr(None) is None
        assert _hex_to_ass_bgr("") is None
        assert _hex_to_ass_bgr("nope") is None
        assert _hex_to_ass_bgr("#zzz") is None

    def test_default_font_size_22(self):
        cmd = pipeline._build_hardsub_cmd("q1", Path("/x"))
        vf = cmd[cmd.index("-vf") + 1]
        assert "FontSize=22" in vf

    def test_custom_font_size(self):
        cmd = pipeline._build_hardsub_cmd("q1", Path("/x"), font_size=32)
        vf = cmd[cmd.index("-vf") + 1]
        assert "FontSize=32" in vf

    def test_default_primary_white(self):
        cmd = pipeline._build_hardsub_cmd("q1", Path("/x"))
        vf = cmd[cmd.index("-vf") + 1]
        assert "PrimaryColour=&H00FFFFFF&" in vf

    def test_default_outline_black(self):
        cmd = pipeline._build_hardsub_cmd("q1", Path("/x"))
        vf = cmd[cmd.index("-vf") + 1]
        assert "OutlineColour=&H00000000&" in vf

    def test_custom_primary_yellow(self):
        cmd = pipeline._build_hardsub_cmd(
            "q1", Path("/x"), primary_color="#FFD700",
        )
        vf = cmd[cmd.index("-vf") + 1]
        # 黃 #FFD700 R=FF G=D7 B=00 → BGR = 00D7FF
        assert "PrimaryColour=&H0000D7FF&" in vf

    def test_custom_outline_navy(self):
        cmd = pipeline._build_hardsub_cmd(
            "q1", Path("/x"), outline_color="#001f3f",
        )
        vf = cmd[cmd.index("-vf") + 1]
        # 深藍 #001F3F → BGR = 3F1F00
        assert "OutlineColour=&H003F1F00&" in vf

    def test_invalid_hex_falls_back_to_default(self):
        """invalid hex 該 fallback 到白/黑 (不該炸)."""
        cmd = pipeline._build_hardsub_cmd(
            "q1", Path("/x"),
            primary_color="garbage", outline_color="zzz",
        )
        vf = cmd[cmd.index("-vf") + 1]
        assert "PrimaryColour=&H00FFFFFF&" in vf
        assert "OutlineColour=&H00000000&" in vf


class TestWindowsPathSafety:
    """CR 已知測試覆蓋盲點之一 (test_burn_subtitles_windows_path).

    Windows OUTPUT_DIR 含冒號 (例 'D:\\Project\\...\\output') 是 subtitles
    filter 跨平台 escape 規則差異的常見地雷. 邏輯靠 cwd=OUTPUT_DIR + 相對
    檔名繞過, 這層測試確保未來重構不會「優化」回絕對路徑。
    """

    def test_cmd_no_windows_drive_letter_even_with_windows_workdir(self):
        # 模擬 Windows: 用 PureWindowsPath 傳入, 確認回傳的 cmd 仍是相對檔名
        win_dir = PureWindowsPath("D:/Project_CodingSimulation/output")
        cmd = pipeline._build_hardsub_cmd("foo", win_dir)
        vf = cmd[cmd.index("-vf") + 1]
        # 任何形態的絕對路徑碎片都不該出現
        assert "D:" not in vf
        assert "\\" not in vf
        assert "D:/" not in vf
        # 仍然是相對檔名
        assert "subtitles=foo.srt" in vf


class TestBurnSubtitles:
    """burn_subtitles wrapper 行為測試 (CR 已知盲點).

    這個 wrapper 是 _build_hardsub_cmd 之外的另一層保險:
    - 必須 cwd=OUTPUT_DIR (subtitles filter 解析相對檔名靠這個)
    - 失敗時保留原 mp4 + 清掉殘留 hardsub.mp4
    """

    def test_subprocess_called_with_cwd_output_dir(self, monkeypatch, tmp_path):
        """關鍵防禦: subprocess.run 一定要帶 cwd=OUTPUT_DIR.

        沒這個的話 ffmpeg subtitles filter 解析的工作目錄是別處,
        相對檔名 foo.srt 找不到 → ffmpeg 報錯 → 字幕燒不進去。
        """
        # 假裝 OUTPUT_DIR 換成 tmp_path, 模擬 Windows 含冒號路徑
        mp4 = tmp_path / "foo.mp4"
        hard = tmp_path / "foo.hardsub.mp4"
        mp4.write_bytes(b"fake mp4")
        hard.write_bytes(b"fake hardsub")  # 模擬 ffmpeg 成功產出

        monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)

        captured = {}
        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["cwd"] = kwargs.get("cwd")
            return subprocess.CompletedProcess(cmd, 0)
        monkeypatch.setattr(subprocess, "run", fake_run)

        pipeline.burn_subtitles("foo")

        # 關鍵: cwd 一定是 OUTPUT_DIR, 不是 None / 隨機
        assert captured["cwd"] == tmp_path
        assert captured["cmd"][0] == "ffmpeg"

    def test_failure_cleanup_preserves_original_mp4(self, monkeypatch, tmp_path):
        """ffmpeg 失敗時應該保留原 mp4 + 清掉殘留 .hardsub.mp4.

        失敗常見原因: 字型缺 / SRT 編碼壞 / 影片軌損毀. 不能因此把原 mp4 也丟。
        """
        mp4 = tmp_path / "foo.mp4"
        hard = tmp_path / "foo.hardsub.mp4"
        mp4.write_bytes(b"original")
        hard.write_bytes(b"partial")  # ffmpeg 半成品

        monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
        # 模擬 ffmpeg 失敗
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: (_ for _ in ()).throw(
                subprocess.CalledProcessError(1, a[0])
            ),
        )

        pipeline.burn_subtitles("foo")  # 不應該 raise

        # 原 mp4 必須還在 (內容不變)
        assert mp4.exists()
        assert mp4.read_bytes() == b"original"
        # 殘留 hardsub 已清掉
        assert not hard.exists()

    def test_success_replaces_original_with_hardsub(self, monkeypatch, tmp_path):
        """ffmpeg 成功時 foo.mp4 應該被 foo.hardsub.mp4 取代."""
        mp4 = tmp_path / "foo.mp4"
        hard = tmp_path / "foo.hardsub.mp4"
        mp4.write_bytes(b"original")
        # 假裝 ffmpeg 已經寫好 hardsub
        monkeypatch.setattr(pipeline, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **kw: (
                hard.write_bytes(b"with subs"),
                subprocess.CompletedProcess(a[0], 0),
            )[1],
        )

        pipeline.burn_subtitles("foo")

        # 原 mp4 位置現在是 hardsub 版本內容
        assert mp4.exists()
        assert mp4.read_bytes() == b"with subs"
        # .hardsub.mp4 已經 rename 走, 不該還在
        assert not hard.exists()
