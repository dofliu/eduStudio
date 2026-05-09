"""TTS 後端抽象層
====================

支援兩種 backend:
- `edge`  — Microsoft Edge TTS(雲端免費,預設)
- `f5`    — F5-TTS(本機聲音複製,需 CUDA + `pip install f5-tts`)

切換靠 `tts_config.json` 的 `backend` 欄位。F5 呼叫失敗(缺套件、缺 ref、CUDA 不可用)
會自動 fallback 到 edge,不會讓整條 pipeline 卡死。

使用方式:
    backend = load_tts_backend()
    await backend.synthesize(text, Path("out.mp3"))
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path


CONFIG_PATH = Path(__file__).parent / "tts_config.json"
PRONUNCIATION_MAP_PATH = Path(__file__).parent / "pronunciation.json"


# ---------- 文字正規化 (套 pronunciation.json + 分數/下標展開) ----------
# 為什麼放在 backend 層: 任何 backend 都該套發音對照, 不是只有走 pipeline.py 的路徑。
# tts_compare、未來其他 caller 都自動受惠, 不會像舊版只有 pipeline 套到。
_PRONUNCIATION_MAP_CACHE: list[tuple[str, str]] | None = None


def _load_pronunciation_map() -> list[tuple[str, str]]:
    global _PRONUNCIATION_MAP_CACHE
    if _PRONUNCIATION_MAP_CACHE is None:
        if PRONUNCIATION_MAP_PATH.exists():
            raw = json.loads(PRONUNCIATION_MAP_PATH.read_text(encoding="utf-8"))
            # longest-first 比對, 避免 ω_n 被 ω 提前吃掉
            _PRONUNCIATION_MAP_CACHE = sorted(
                [(k, v) for k, v in raw.items() if not k.startswith("_")],
                key=lambda x: -len(x[0]),
            )
        else:
            _PRONUNCIATION_MAP_CACHE = []
    return _PRONUNCIATION_MAP_CACHE


def split_for_f5(text: str, max_chars: int = 30) -> list[str]:
    """PR-5b: F5-TTS 預切句, 解決 F5 內部 batch 不顧中文詞邊界的問題。

    F5 把長 gen_text 切成內部 batch 時會在「字元數」邊界硬切, 對中文常常
    切到詞中間 (例: 「處理與應用」→「處」+「理與應用」, 第二段聽起來像新句子)。
    我們先用標點預切成 ≤ max_chars 的短段, 逐段呼叫 F5 後 concat, 等於我們
    自己掌握 batch 切點。

    切分策略:
    - 主要切點 (。！？.!?) 一律 flush
    - 次要切點 (，、；：;,:) 累積 >=60% max_chars 才 flush (避免太短)
    - 累積到 max_chars 仍沒看到切點 → 找最近一個次要切點 / 空白
    - 真的沒切點 (英文無標點 / 連續中文無標點) → 硬切 max_chars

    max_chars=30 是實測值: F5 內部似乎 30~40 字會自切, 比它短一點就能搶在
    它之前, 不會出現中-中切錯。不解中-英切換口音漂移 (那是 base model 訓練資料)。
    """
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    PRIMARY = set("。！？.!?")
    SECONDARY = set("，、；：;,:")
    SOFT_SEC = SECONDARY | set(" \t")  # 找退路時也接受空白

    segments: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in PRIMARY:
            segments.append(buf)
            buf = ""
        elif ch in SECONDARY and len(buf) >= max_chars * 0.6:
            segments.append(buf)
            buf = ""
        elif len(buf) >= max_chars:
            # 太長還沒切, 找最後一個 soft 切點
            last_sec = max((buf.rfind(c) for c in SOFT_SEC), default=-1)
            if last_sec > max_chars * 0.5:
                segments.append(buf[:last_sec + 1])
                buf = buf[last_sec + 1:]
            else:
                # 找不到合理切點: 硬切 (英文單詞 / 純中文無標點)
                segments.append(buf)
                buf = ""
    if buf:
        segments.append(buf)
    return [s for s in segments if s.strip()]


def normalize_text(text: str) -> str:
    """進 TTS 前的標準前處理: 分數展開、變數下標、發音對照、空白清理。

    所有 backend 的 synthesize 都會自動先過這個函式, 確保 pronunciation.json
    在每個入口都生效。
    """
    if not text:
        return ""
    # 分數: (a)/(b) → b 分之 a
    text = re.sub(
        r"([\w\d]+|\([^()]+\))\s*/\s*\(([^()]+)\)",
        lambda m: f"{m.group(2)} 分之 {m.group(1).strip('()')}",
        text,
    )
    text = re.sub(
        r"\(([^()]+)\)\s*/\s*([A-Za-z_]\w*|\d+)",
        lambda m: f"{m.group(2)} 分之 {m.group(1)}",
        text,
    )
    # 變數下標: F1, P12 → F 一, P 一二 (避免 TTS 念錯)
    digit_map = {"0": "零", "1": "一", "2": "二", "3": "三", "4": "四",
                 "5": "五", "6": "六", "7": "七", "8": "八", "9": "九"}
    text = re.sub(
        r"([FPxyzuvQT])(\d+)",
        lambda m: f"{m.group(1)} {''.join(digit_map.get(c, c) for c in m.group(2))}",
        text,
    )
    # 發音對照: longest-match 替換, 前後補空白避免黏字
    for src, dst in _load_pronunciation_map():
        text = text.replace(src, f" {dst} ")
    return re.sub(r"\s+", " ", text).strip()


# ---------- 抽象介面 ----------
class TTSBackend(ABC):
    name: str = "base"

    @abstractmethod
    async def synthesize(self, text: str, out_path: Path) -> bool:
        """產生 mp3 到 out_path,成功回 True,失敗回 False(不 raise)。
        實作層應在最開頭呼叫 `text = normalize_text(text)` 套發音對照。"""


# ---------- Edge TTS (雲端) ----------
class EdgeTTS(TTSBackend):
    name = "edge"

    def __init__(self, voice: str = "zh-TW-HsiaoChenNeural", rate: str = "-5%"):
        self.voice = voice
        self.rate = rate

    async def synthesize(self, text: str, out_path: Path) -> bool:
        text = normalize_text(text)
        try:
            import edge_tts  # lazy import
            await edge_tts.Communicate(text, self.voice, rate=self.rate).save(str(out_path))
            return True
        except Exception as e:
            print(f"[edge-tts] failed: {e}")
            return False


# ---------- F5-TTS (本機聲音複製) ----------
class F5TTS(TTSBackend):
    name = "f5"

    def __init__(
        self,
        ref_audio: str,
        ref_text: str,
        model: str = "F5TTS_v1_Base",
        remove_silence: bool = True,
        speed: float = 1.0,
        lead_trim_sec: float = 0.3,
        cfg_strength: float = 2.0,
        cross_fade_duration: float = 0.15,
        nfe_step: int = 32,
    ):
        """F5 hyper-params 對應的可調效應:
        - speed:        1.0 原速 (<1 慢, >1 快)
        - lead_trim_sec: 每段輸出最前面砍掉的秒數 (F5 偶爾洩漏 ref 前緣)
        - cfg_strength:  Classifier-free guidance 強度 (預設 2)。提高可拉近 ref 口音,
                         過高會出現 over-fit artifact
        - cross_fade_duration: 內部 batch 邊界 cross-fade 秒數 (預設 0.15)。
                         提高可平滑斷句, 但 batch 切點本身的位置不變
        - nfe_step:      Number of function evaluations (預設 32, 越高品質越好但更慢)
        """
        self.ref_audio = ref_audio
        self.ref_text = ref_text
        self.model = model
        self.remove_silence = remove_silence
        self.speed = speed
        self.lead_trim_sec = lead_trim_sec
        self.cfg_strength = cfg_strength
        self.cross_fade_duration = cross_fade_duration
        self.nfe_step = nfe_step
        self._api = None

    def _lazy_init(self):
        """首次使用才載入 F5-TTS 跟模型(載入約 10~20 秒,之後快取)"""
        if self._api is not None:
            return
        ref_path = Path(self.ref_audio)
        if not ref_path.exists():
            raise FileNotFoundError(f"F5 ref_audio 不存在: {self.ref_audio}")
        if not self.ref_text.strip():
            raise ValueError("F5 ref_text 不可為空,請在 tts_config.json 填逐字稿")
        # 延遲載入,避免沒安裝 f5-tts 時整個 module 掛掉
        from f5_tts.api import F5TTS as F5API
        self._api = F5API(model=self.model)

    async def synthesize(self, text: str, out_path: Path) -> bool:
        text = normalize_text(text)
        try:
            self._lazy_init()
            # PR-5b: 先預切句, 每段 ≤ 30 字, 避免 F5 內部 batch 切到中文詞中間。
            # 短文 (≤ 30 字) 仍是單段, 行為跟舊版一致。
            segments = split_for_f5(text, max_chars=30)
            if not segments:
                return False

            # 為每段呼叫一次 F5 → wav, 然後 ffmpeg concat 成一支
            tmp_dir = out_path.parent
            seg_wavs: list[Path] = []
            for i, seg_text in enumerate(segments):
                seg_wav = tmp_dir / f".{out_path.stem}.f5seg{i:03d}.wav"
                await asyncio.to_thread(
                    self._api.infer,
                    ref_file=self.ref_audio,
                    ref_text=self.ref_text,
                    gen_text=seg_text,
                    file_wave=str(seg_wav),
                    remove_silence=self.remove_silence,
                    speed=self.speed,
                    cfg_strength=self.cfg_strength,
                    cross_fade_duration=self.cross_fade_duration,
                    nfe_step=self.nfe_step,
                )
                seg_wavs.append(seg_wav)

            # 單段直接走舊路徑 (省一次 concat ffmpeg)
            if len(seg_wavs) == 1:
                wav_path = seg_wavs[0]
            else:
                # 寫 ffmpeg concat manifest, 同 dir 用相對檔名避免路徑空白問題
                manifest = tmp_dir / f".{out_path.stem}.f5concat.txt"
                manifest.write_text(
                    "\n".join(f"file '{w.name}'" for w in seg_wavs),
                    encoding="utf-8",
                )
                wav_path = tmp_dir / f".{out_path.stem}.f5merged.wav"
                subprocess.run(
                    ["ffmpeg", "-y", "-loglevel", "error",
                     "-f", "concat", "-safe", "0",
                     "-i", str(manifest), "-c", "copy", str(wav_path)],
                    check=True,
                )
                manifest.unlink(missing_ok=True)

            # 下游 pipeline 吃 mp3;順便砍掉前 lead_trim_sec 秒的 ref 洩漏
            # (預切後 lead_trim 仍套在最終 concat 結果首段, 跟舊版邏輯一致)
            ff = ["ffmpeg", "-y", "-loglevel", "error"]
            if self.lead_trim_sec > 0:
                ff += ["-ss", f"{self.lead_trim_sec:.3f}"]
            ff += ["-i", str(wav_path), "-b:a", "128k", str(out_path)]
            subprocess.run(ff, check=True)

            # 清掉所有暫存
            for w in seg_wavs:
                w.unlink(missing_ok=True)
            if len(seg_wavs) > 1:
                wav_path.unlink(missing_ok=True)
            return True
        except Exception as e:
            print(f"[F5-TTS] failed: {e}")
            return False


# ---------- Fallback wrapper ----------
class FallbackTTS(TTSBackend):
    """主 backend 失敗時,自動改用 fallback(通常是 edge)"""

    def __init__(self, primary: TTSBackend, fallback: TTSBackend):
        self.primary = primary
        self.fallback = fallback
        self.name = f"{primary.name}+fallback({fallback.name})"
        self._primary_disabled = False

    async def synthesize(self, text: str, out_path: Path) -> bool:
        # 一旦 primary 失敗過,後續都直接走 fallback,避免每步都重試
        if not self._primary_disabled:
            if await self.primary.synthesize(text, out_path):
                return True
            print(f"[tts] primary '{self.primary.name}' 失敗,後續改用 '{self.fallback.name}'")
            self._primary_disabled = True
        return await self.fallback.synthesize(text, out_path)


# ---------- 載入器 ----------
def load_tts_backend(config_path: Path | None = None) -> TTSBackend:
    """讀 tts_config.json,回傳已裝好 fallback 的 backend。
    沒有設定檔時走 edge 預設值。
    """
    path = config_path or CONFIG_PATH
    if path.exists():
        cfg = json.loads(path.read_text(encoding="utf-8"))
    else:
        cfg = {}

    edge_cfg = cfg.get("edge", {}) or {}
    edge = EdgeTTS(
        voice=edge_cfg.get("voice", "zh-TW-HsiaoChenNeural"),
        rate=edge_cfg.get("rate", "-5%"),
    )

    backend_name = cfg.get("backend", "edge")
    if backend_name == "f5":
        f5cfg = cfg.get("f5", {}) or {}
        primary = F5TTS(
            ref_audio=f5cfg.get("ref_audio", "./voices/teacher_ref.wav"),
            ref_text=f5cfg.get("ref_text", ""),
            model=f5cfg.get("model", "F5TTS_v1_Base"),
            remove_silence=f5cfg.get("remove_silence", True),
            speed=float(f5cfg.get("speed", 1.0)),
            lead_trim_sec=float(f5cfg.get("lead_trim_sec", 0.3)),
            cfg_strength=float(f5cfg.get("cfg_strength", 2.0)),
            cross_fade_duration=float(f5cfg.get("cross_fade_duration", 0.15)),
            nfe_step=int(f5cfg.get("nfe_step", 32)),
        )
        return FallbackTTS(primary, edge)
    return edge
