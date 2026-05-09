"""PR-5c: 燒字幕 ffmpeg 指令組合 unit test (不跑 ffmpeg)."""
from __future__ import annotations

from pathlib import Path

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
