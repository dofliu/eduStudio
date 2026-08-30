"""影片翻譯與配音（從 translateGemma video_dubber.py 收編，eduStudio 合併 B-2）。

Pipeline: 下載(yt-dlp) → STT(faster-whisper) → 翻譯(core.translation) → 配音(edge-tts) → 合成(ffmpeg)。

移植調整（MERGE_PLAN §5.5）:
- 重依賴 yt_dlp / faster_whisper 改 **lazy import**（原檔頂層 import）；edge_tts 原本就 lazy。
- translator 改走 core.translation.service；get_edge_tts_voice 改走 core.langcode（容忍底線/連字號）。
- logger 改 stdlib logging。
- **lazy 單例**：原 module 級 `video_dubber = VideoDubber()` 的 ctor 會 mkdtemp（import 期 side-effect），
  改 get_video_dubber() lazy 化。
- 內部語言碼維持底線式（router 邊界轉換），與 translator 一致。
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import List, Tuple

from core.langcode import get_edge_tts_voice
from core.translation.service import translator

log = logging.getLogger(__name__)


@dataclass
class Segment:
    """字幕片段。"""

    start: float
    end: float
    text: str
    translated_text: str = ""
    audio_path: str = ""


class VideoDubber:
    """影片翻譯與配音服務。"""

    def __init__(self, output_dir: str | None = None):
        self.output_dir = output_dir or tempfile.mkdtemp(prefix="video_dub_")
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)
        self.whisper_model = None
        log.info("VideoDubber initialized with output_dir: %s", self.output_dir)

    def _get_whisper_model(self):
        """lazy-load whisper（共用 loader：large-v3 + GPU 優先；base 本機缺）。"""
        if self.whisper_model is None:
            from core.whisper_util import load_whisper_model
            self.whisper_model = load_whisper_model()
        return self.whisper_model

    def _create_job_dir(self, prefix="job"):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        job_dir = os.path.join(self.output_dir, f"{prefix}_{timestamp}")
        os.makedirs(job_dir, exist_ok=True)
        return job_dir

    def _run_cmd_checked(self, cmd: List[str], step: str) -> None:
        # 委派共用 runner(T3-3): 補上 timeout; 訊息格式維持「{step} failed:」
        from core.ffmpeg import run_media_cmd
        result = run_media_cmd(cmd, step=step, check=False)
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(f"{step} failed: {stderr or 'unknown error'}")

    def _assert_nonempty_file(self, file_path: str, step: str) -> None:
        if not file_path or not os.path.exists(file_path):
            raise RuntimeError(f"{step} failed: output not found ({file_path})")
        if os.path.getsize(file_path) <= 0:
            raise RuntimeError(f"{step} failed: output is empty ({file_path})")

    def download_youtube(self, url: str, output_dir: str, progress_callback=None) -> Tuple[str, str]:
        """下載 YouTube 影片，回 (video_path, audio_path)。"""
        import yt_dlp

        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(output_dir, "video.%(ext)s"),
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
        }
        if progress_callback:
            progress_callback("正在下載影片...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        video_path = os.path.join(output_dir, "video.mp4")
        audio_path = os.path.join(output_dir, "audio.wav")
        if progress_callback:
            progress_callback("正在提取音訊...")
        # 原本完全不檢查 returncode: 抽音失敗會靜默留下缺檔, 下游才莫名其妙炸
        self._run_cmd_checked([
            'ffmpeg', '-y', '-i', video_path,
            '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio_path,
        ], "extract audio")
        return video_path, audio_path

    def generate_subtitles(self, audio_path: str, source_lang: str = "auto",
                           progress_callback=None) -> List[Segment]:
        """用 Whisper 生成字幕片段。"""
        if progress_callback:
            progress_callback("正在辨識語音...")
        model = self._get_whisper_model()
        language = None if source_lang == "auto" else source_lang[:2]
        segments_result, info = model.transcribe(audio_path, language=language, word_timestamps=False)
        segments = []
        for seg in segments_result:
            segments.append(Segment(start=seg.start, end=seg.end, text=seg.text.strip()))
        if progress_callback:
            progress_callback(f"辨識完成，共 {len(segments)} 個片段")
        return segments

    # 不同語言平均語速（字/秒），引導翻譯長度避免配音重疊。
    SPEECH_RATE = {
        "zh_TW": 4.0, "zh_CN": 4.0, "ja": 5.0, "ko": 4.5, "en": 2.5,
        "de": 2.3, "fr": 2.5, "es": 2.8, "default": 3.0,
    }

    def translate_segments(self, segments: List[Segment], target_lang: str,
                           source_lang: str = "auto", progress_callback=None) -> List[Segment]:
        """翻譯所有字幕片段（走 core.translation 的 Gemini 後端）。"""
        total = len(segments)
        for i, seg in enumerate(segments):
            if progress_callback:
                progress_callback(f"翻譯中... ({i+1}/{total})")
            seg.translated_text = translator.translate(seg.text, source_lang, target_lang)
        return segments

    async def synthesize_segment_audio(self, segment: Segment, target_lang: str,
                                       output_dir: str, index: int) -> str:
        """為單一片段合成語音（edge-tts，lazy）。"""
        import edge_tts

        voice = get_edge_tts_voice(target_lang)
        output_path = os.path.join(output_dir, f"tts_{index:04d}.mp3")
        communicate = edge_tts.Communicate(segment.translated_text, voice)
        await communicate.save(output_path)
        segment.audio_path = output_path
        return output_path

    def synthesize_all_audio(self, segments: List[Segment], target_lang: str,
                             output_dir: str, progress_callback=None) -> List[Segment]:
        """為所有片段合成語音。"""
        total = len(segments)

        async def run_all():
            for i, seg in enumerate(segments):
                if progress_callback:
                    progress_callback(f"語音合成中... ({i+1}/{total})")
                await self.synthesize_segment_audio(seg, target_lang, output_dir, i)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_all())
        loop.close()
        return segments

    def get_audio_duration(self, audio_path: str) -> float:
        # ffprobe 不存在(FileNotFoundError/OSError)、壞路徑、輸出無法解析、或逾時 → 一律回 0
        # （優雅降級，不讓缺 ffprobe 的環境炸掉；CI 無 ffmpeg 時這條才不會 FileNotFoundError）。
        try:
            result = subprocess.run([
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', audio_path,
            ], capture_output=True, text=True, timeout=60)
            return float(result.stdout.strip())
        except (ValueError, TypeError, FileNotFoundError, OSError,
                subprocess.TimeoutExpired):
            return 0.0

    def adjust_audio_speed(self, audio_path: str, target_duration: float) -> str:
        """調整音訊速度以符合目標時長（夾在 0.85x~1.25x）。"""
        current_duration = self.get_audio_duration(audio_path)
        if current_duration <= 0:
            return audio_path
        speed_factor = current_duration / target_duration
        original_speed = speed_factor
        speed_factor = max(0.85, min(1.25, speed_factor))
        if abs(speed_factor - 1.0) < 0.05:
            return audio_path
        output_path = audio_path.replace('.mp3', '_adjusted.mp3')
        if original_speed < 0.85 or original_speed > 1.25:
            log.warning("Speech rate clamped: requested %.2fx, using %.2fx", original_speed, speed_factor)
        # 變速/截斷失敗走降級(回原檔照用), 不讓整段配音死在調速上;
        # 但走共用 runner 補 timeout, 且輸出缺檔時明確 fallback 而非把壞路徑往下傳
        from core.ffmpeg import run_media_cmd
        run_media_cmd([
            'ffmpeg', '-y', '-i', audio_path, '-filter:a', f'atempo={speed_factor}', output_path,
        ], step="atempo adjust", timeout=300, check=False)
        if not os.path.exists(output_path):
            log.warning("atempo adjust failed, using original audio: %s", audio_path)
            return audio_path
        adjusted_duration = self.get_audio_duration(output_path)
        if adjusted_duration > target_duration * 1.05:
            truncated_path = output_path.replace('.mp3', '_truncated.mp3')
            run_media_cmd([
                'ffmpeg', '-y', '-i', output_path, '-t', str(target_duration), truncated_path,
            ], step="audio truncate", timeout=300, check=False)
            if os.path.exists(truncated_path):
                return truncated_path
            log.warning("audio truncate failed, using adjusted audio: %s", output_path)
        return output_path

    def merge_dubbed_audio(self, segments: List[Segment], total_duration: float,
                           output_dir: str, progress_callback=None) -> str:
        """合併所有配音片段（adelay + amix + loudnorm）。"""
        if progress_callback:
            progress_callback("正在合併音軌...")
        output_path = os.path.join(output_dir, "dubbed_audio.wav")
        filter_parts = []
        inputs = []
        # ffmpeg 的輸入串流索引 = `-i` 的順序；缺音檔的 segment 會被跳過，
        # 所以 filtergraph 要用「保留段」的連續計數器 j，不能用 enumerate 的 i
        # （skip 會留洞 → [i:a] 指到不存在的輸入、amix 引用不到 [a{i}]，ffmpeg 直接崩）。
        j = 0
        for seg in segments:
            if not seg.audio_path or not os.path.exists(seg.audio_path):
                continue
            target_duration = seg.end - seg.start
            adjusted_path = self.adjust_audio_speed(seg.audio_path, target_duration)
            inputs.extend(['-i', adjusted_path])
            delay_ms = int(seg.start * 1000)
            filter_parts.append(f'[{j}:a]adelay={delay_ms}|{delay_ms}[a{j}]')
            j += 1
        if not filter_parts:
            return ""
        mix_inputs = ''.join([f'[a{i}]' for i in range(len(filter_parts))])
        filter_complex = ';'.join(filter_parts) + f';{mix_inputs}amix=inputs={len(filter_parts)}:duration=longest:dropout_transition=0,loudnorm=I=-14:TP=-1.0:LRA=11[out]'
        cmd = ['ffmpeg', '-y'] + inputs + [
            '-filter_complex', filter_complex, '-map', '[out]', '-t', str(total_duration), output_path,
        ]
        self._run_cmd_checked(cmd, "merge dubbed audio")
        self._assert_nonempty_file(output_path, "merge dubbed audio")
        return output_path

    def mux_video(self, video_path: str, dubbed_audio_path: str, output_dir: str,
                  subtitle_path: str = None, burn_subtitles: bool = False,
                  progress_callback=None) -> str:
        """合成最終影片（可選燒錄字幕）。"""
        if progress_callback:
            progress_callback("正在合成影片...")
        output_path = os.path.join(output_dir, "dubbed_video.mp4")
        if burn_subtitles and subtitle_path and os.path.exists(subtitle_path):
            subtitle_escaped = subtitle_path.replace('\\', '/').replace(':', '\\:')
            subtitle_style = (
                "FontSize=12,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,"
                "Outline=2,MarginV=15,WrapStyle=1,Alignment=2"
            )
            cmd = [
                'ffmpeg', '-y', '-i', video_path, '-i', dubbed_audio_path,
                '-vf', f"subtitles='{subtitle_escaped}':force_style='{subtitle_style}'",
                '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
                '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart',
                '-map', '0:v:0', '-map', '1:a:0', '-shortest', output_path,
            ]
        else:
            cmd = [
                'ffmpeg', '-y', '-i', video_path, '-i', dubbed_audio_path,
                '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart',
                '-map', '0:v:0', '-map', '1:a:0', '-shortest', output_path,
            ]
        self._run_cmd_checked(cmd, "mux video")
        self._assert_nonempty_file(output_path, "mux video")
        return output_path

    def generate_srt(self, segments: List[Segment], output_dir: str, use_translated: bool = False) -> str:
        """產生 SRT 字幕檔（純檔案 I/O）。"""
        filename = "translated.srt" if use_translated else "original.srt"
        output_path = os.path.join(output_dir, filename)

        def format_time(seconds: float) -> str:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            millis = int((seconds % 1) * 1000)
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

        with open(output_path, 'w', encoding='utf-8') as f:
            for i, seg in enumerate(segments, 1):
                text = seg.translated_text if use_translated else seg.text
                f.write(f"{i}\n")
                f.write(f"{format_time(seg.start)} --> {format_time(seg.end)}\n")
                f.write(f"{text}\n\n")
        return output_path

    def process_video(self, video_source: str, source_lang: str, target_lang: str,
                      burn_subtitles: bool = False, progress_callback=None,
                      job_dir: str = None) -> dict:
        """完整處理流程。"""
        job_dir = job_dir or self._create_job_dir()
        results = {}
        if video_source.startswith('http'):
            video_path, audio_path = self.download_youtube(video_source, job_dir, progress_callback)
        else:
            video_path = video_source
            audio_path = os.path.join(job_dir, "audio.wav")
            self._run_cmd_checked([
                'ffmpeg', '-y', '-i', video_path,
                '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio_path,
            ], "extract audio from local video")
            self._assert_nonempty_file(audio_path, "extract audio from local video")
        results['original_video'] = video_path
        segments = self.generate_subtitles(audio_path, source_lang, progress_callback)
        results['original_srt'] = self.generate_srt(segments, job_dir, use_translated=False)
        segments = self.translate_segments(segments, target_lang, source_lang, progress_callback)
        translated_srt = self.generate_srt(segments, job_dir, use_translated=True)
        results['translated_srt'] = translated_srt
        segments = self.synthesize_all_audio(segments, target_lang, job_dir, progress_callback)
        total_duration = self.get_audio_duration(audio_path)
        dubbed_audio = self.merge_dubbed_audio(segments, total_duration, job_dir, progress_callback)
        if dubbed_audio:
            results['dubbed_video'] = self.mux_video(
                video_path, dubbed_audio, output_dir=job_dir,
                subtitle_path=translated_srt, burn_subtitles=burn_subtitles,
                progress_callback=progress_callback,
            )
        if progress_callback:
            progress_callback("✅ 處理完成！")
        return results

    def process_video_batch(self, video_source: str, source_lang: str, target_langs: list,
                            burn_subtitles: bool = False, progress_callback=None) -> dict:
        """批次處理多語言翻譯（下載/STT 只做一次）。"""
        import copy

        job_dir = self._create_job_dir(prefix="batch_job")
        batch_results = {}
        total_langs = len(target_langs)
        if video_source.startswith('http'):
            video_path, audio_path = self.download_youtube(video_source, job_dir, progress_callback)
        else:
            video_path = video_source
            audio_path = os.path.join(job_dir, "audio.wav")
            self._run_cmd_checked([
                'ffmpeg', '-y', '-i', video_path,
                '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1', audio_path,
            ], "extract audio from local video")
            self._assert_nonempty_file(audio_path, "extract audio from local video")
        segments = self.generate_subtitles(audio_path, source_lang, progress_callback)
        original_srt = self.generate_srt(segments, job_dir, use_translated=False)
        batch_results['original_video'] = video_path
        batch_results['original_srt'] = original_srt
        batch_results['languages'] = {}
        for i, target_lang in enumerate(target_langs):
            if progress_callback:
                progress_callback(f"處理語言 {i+1}/{total_langs}: {target_lang}")
            lang_dir = os.path.join(job_dir, target_lang)
            os.makedirs(lang_dir, exist_ok=True)
            lang_result = {}
            lang_segments = copy.deepcopy(segments)
            lang_segments = self.translate_segments(lang_segments, target_lang, source_lang, progress_callback)
            translated_srt = self.generate_srt(lang_segments, lang_dir, use_translated=True)
            lang_result['translated_srt'] = translated_srt
            lang_segments = self.synthesize_all_audio(lang_segments, target_lang, lang_dir, progress_callback)
            total_duration = self.get_audio_duration(audio_path)
            dubbed_audio = self.merge_dubbed_audio(lang_segments, total_duration, lang_dir, progress_callback)
            if dubbed_audio:
                dubbed_video = self.mux_video(
                    video_path, dubbed_audio, output_dir=lang_dir,
                    subtitle_path=translated_srt, burn_subtitles=burn_subtitles,
                    progress_callback=progress_callback,
                )
                lang_result['dubbed_video'] = dubbed_video
            batch_results['languages'][target_lang] = lang_result
        if progress_callback:
            progress_callback(f"✅ 批次處理完成！共處理 {total_langs} 種語言")
        return batch_results


# ── lazy 單例（避免 import 期 mkdtemp side-effect）──
_default_dubber: VideoDubber | None = None


def get_video_dubber() -> VideoDubber:
    """共享 VideoDubber（lazy；第一次取用才建 output_dir）。"""
    global _default_dubber
    if _default_dubber is None:
        _default_dubber = VideoDubber()
    return _default_dubber
