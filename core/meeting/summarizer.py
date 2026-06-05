"""會議摘要服務（從 translateGemma meeting_summarizer.py 收編，eduStudio 合併 B-2）。

Pipeline: 影片 →(ffmpeg)→ 音訊 →(faster-whisper)→ 轉錄 →(Gemini)→ 摘要。

移植調整（MERGE_PLAN §5.5）:
- **預設後端改 gemini**（原預設 ollama）；gemini 分支改用核心共用 `_gemini_complete`
  （新版 google.genai SDK + core.config 金鑰/模型），取代原本的舊版 `google.generativeai`
  SDK。ollama 分支保留作 fallback（lazy import）。
- whisper / ffmpeg 維持 lazy / subprocess，未裝套件不炸 collect（測試 importorskip）。
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Generator


@dataclass
class TranscriptSegment:
    """一段轉錄（含起訖時間）。"""

    start: float
    end: float
    text: str


@dataclass
class MeetingSummaryResult:
    transcript: str
    transcript_with_time: str
    summary: dict
    duration: float
    language: str


SUMMARY_TYPES = {
    "key_points": {
        "name": "Key Points",
        "prompt": "List the key points from this meeting using concise bullet points.",
    },
    "action_items": {
        "name": "Action Items",
        "prompt": "List action items with owner, due date (if available), and concrete next steps.",
    },
    "decisions": {
        "name": "Decisions",
        "prompt": "List decisions that were explicitly made in the meeting.",
    },
    "full_summary": {
        "name": "Full Summary",
        "prompt": "Provide a complete meeting summary including context, discussion, decisions, and follow-ups.",
    },
}

# whisper 語言碼對照（底線式，與 translateGemma 內部一致）。
_WHISPER_LANG_MAP = {
    "zh_TW": "zh", "zh_CN": "zh", "en_US": "en", "ja_JP": "ja", "ko_KR": "ko",
    "de_DE": "de", "fr_FR": "fr", "es_ES": "es", "it_IT": "it", "ru_RU": "ru",
    "pt_BR": "pt", "vi_VN": "vi", "th_TH": "th", "ar_SA": "ar",
}


def _summary_prompt(transcript: str, task: str) -> str:
    return (
        "You are a professional meeting summarizer.\n\n"
        f"Transcript:\n---\n{transcript}\n---\n\n"
        f"Task: {task}\n\n"
        "Return only the summary content without additional commentary."
    )


class MeetingSummarizer:
    """會議摘要服務。"""

    def __init__(
        self,
        ai_backend: str = "gemini",
        ollama_model: str = "qwen3:4b",
        gemini_api_key: str = "",
    ):
        self.ai_backend = ai_backend
        self.ollama_model = ollama_model
        self.gemini_api_key = gemini_api_key  # 保留相容；gemini 分支實際走 core.config 金鑰
        self._whisper_model = None

    def _get_whisper_model(self):
        """lazy-load whisper。"""
        if self._whisper_model is None:
            from faster_whisper import WhisperModel
            self._whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
        return self._whisper_model

    def extract_audio(self, video_path: str, output_dir: str | None = None) -> str:
        """用 ffmpeg 抽 16kHz mono WAV。"""
        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix="meeting_audio_")
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        audio_path = os.path.join(output_dir, f"{base_name}_audio.wav")
        cmd = [
            "ffmpeg", "-y", "-i", video_path, "-vn",
            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_path,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            return audio_path
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"Audio extraction failed: {exc.stderr.decode(errors='ignore')}")

    def transcribe(self, audio_path: str, language: str = "auto",
                   progress_callback=None) -> tuple[list[TranscriptSegment], str]:
        """轉錄成 segments + 偵測語言。"""
        model = self._get_whisper_model()
        lang_code = None if language == "auto" else _WHISPER_LANG_MAP.get(language)
        if progress_callback:
            progress_callback("Transcribing audio...")
        segments_iter, info = model.transcribe(audio_path, language=lang_code, word_timestamps=False)
        segments: list[TranscriptSegment] = []
        for seg in segments_iter:
            segments.append(TranscriptSegment(start=seg.start, end=seg.end, text=seg.text.strip()))
        return segments, info.language

    def format_transcript(self, segments: list[TranscriptSegment], with_timestamps: bool = True) -> str:
        lines = []
        for seg in segments:
            if with_timestamps:
                lines.append(f"[{self._format_time(seg.start)}] {seg.text}")
            else:
                lines.append(seg.text)
        return "\n".join(lines)

    def _format_time(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def generate_summary(self, transcript: str, summary_types: list[str], progress_callback=None) -> dict:
        """產生選定的摘要區塊（依 ai_backend 分流）。"""
        if self.ai_backend == "ollama":
            return self._generate_summary_ollama(transcript, summary_types, progress_callback)
        return self._generate_summary_gemini(transcript, summary_types, progress_callback)

    def _generate_summary_gemini(self, transcript: str, summary_types: list[str], progress_callback=None) -> dict:
        """用核心共用 Gemini helper 產摘要（新 SDK + core.config 金鑰）。"""
        from core.translation.service import _gemini_complete

        results = {}
        for i, summary_type in enumerate(summary_types):
            if summary_type not in SUMMARY_TYPES:
                continue
            type_info = SUMMARY_TYPES[summary_type]
            if progress_callback:
                progress_callback(f"Generating {type_info['name']} ({i + 1}/{len(summary_types)})...")
            try:
                results[summary_type] = _gemini_complete(_summary_prompt(transcript, type_info["prompt"]))
            except Exception as exc:
                results[summary_type] = f"Summary generation failed: {exc}"
        return results

    def _generate_summary_ollama(self, transcript: str, summary_types: list[str], progress_callback=None) -> dict:
        """ollama fallback（lazy import；預設不走此路）。"""
        import ollama

        results = {}
        for i, summary_type in enumerate(summary_types):
            if summary_type not in SUMMARY_TYPES:
                continue
            type_info = SUMMARY_TYPES[summary_type]
            if progress_callback:
                progress_callback(f"Generating {type_info['name']} ({i + 1}/{len(summary_types)})...")
            try:
                response = ollama.chat(
                    model=self.ollama_model,
                    messages=[{"role": "user", "content": _summary_prompt(transcript, type_info["prompt"])}],
                    options={"num_predict": 2048},
                )
                results[summary_type] = response["message"]["content"]
            except Exception as exc:
                results[summary_type] = f"Summary generation failed: {exc}"
        return results

    def process_video(self, video_path: str, language: str = "auto",
                      summary_types: list[str] | None = None,
                      progress_callback=None) -> MeetingSummaryResult:
        """完整 pipeline：extract → transcribe → summarize。"""
        if summary_types is None:
            summary_types = ["full_summary"]
        if progress_callback:
            progress_callback("Extracting audio from video...")
        audio_path = self.extract_audio(video_path)
        if progress_callback:
            progress_callback("Transcribing audio...")
        segments, detected_lang = self.transcribe(audio_path, language, progress_callback)
        transcript = self.format_transcript(segments, with_timestamps=False)
        transcript_with_time = self.format_transcript(segments, with_timestamps=True)
        duration = segments[-1].end if segments else 0.0
        if progress_callback:
            progress_callback("Generating meeting summary...")
        summary = self.generate_summary(transcript, summary_types, progress_callback)
        try:
            os.remove(audio_path)
            os.rmdir(os.path.dirname(audio_path))
        except OSError:
            pass
        return MeetingSummaryResult(
            transcript=transcript,
            transcript_with_time=transcript_with_time,
            summary=summary,
            duration=duration,
            language=detected_lang,
        )

    def process_video_stream(self, video_path: str, language: str = "auto",
                             summary_types: list[str] | None = None,
                             progress_callback=None) -> Generator[dict, None, None]:
        """長任務的串流狀態更新。"""
        if summary_types is None:
            summary_types = ["full_summary"]
        yield {"stage": "extract_audio", "progress": 0.1, "message": "Extracting audio from video..."}
        audio_path = self.extract_audio(video_path)
        yield {"stage": "extract_audio", "progress": 0.2, "message": "Audio extraction completed."}
        yield {"stage": "transcribe", "progress": 0.3, "message": "Transcribing audio..."}
        segments, detected_lang = self.transcribe(audio_path, language)
        transcript = self.format_transcript(segments, with_timestamps=False)
        transcript_with_time = self.format_transcript(segments, with_timestamps=True)
        duration = segments[-1].end if segments else 0.0
        yield {
            "stage": "transcribe", "progress": 0.5,
            "message": f"Transcription completed ({self._format_time(duration)}).",
            "transcript": transcript, "transcript_with_time": transcript_with_time,
            "language": detected_lang, "duration": duration,
        }
        yield {"stage": "summarize", "progress": 0.6, "message": "Generating summary..."}
        summary = {}
        for i, summary_type in enumerate(summary_types):
            progress = 0.6 + (0.35 * (i + 1) / len(summary_types))
            type_name = SUMMARY_TYPES.get(summary_type, {}).get("name", summary_type)
            yield {"stage": "summarize", "progress": progress, "message": f"Generating {type_name}..."}
            partial_summary = self.generate_summary(transcript, [summary_type])
            summary.update(partial_summary)
            yield {
                "stage": "summarize", "progress": progress,
                "message": f"{type_name} completed.",
                "partial_summary": {summary_type: partial_summary.get(summary_type, "")},
            }
        try:
            os.remove(audio_path)
            os.rmdir(os.path.dirname(audio_path))
        except OSError:
            pass
        yield {"stage": "done", "progress": 1.0, "message": "Done.", "summary": summary}


# 模組級單例（ctor side-effect-free，whisper lazy）。
meeting_summarizer = MeetingSummarizer()
