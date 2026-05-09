"""GET / POST / sample endpoints for TTS voice 切換 (PR-3l)。

把 Track A app.py 的 voice picker 邏輯搬到 Track B。tts_config.json 是全域,
所有 job 共用 (per-job override 走 options.tts_provider, 但這是 backend 層級
edge/f5, 不是 voice id)。

設計:
- GET /voices         列所有可選 voice + 當前 active
- POST /voices        切換 active voice (寫 tts_config.json)
- GET /voices/{id}/sample   stream 試聽 mp3
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from core.config import PROJECT_ROOT, TTS_CONFIG_PATH


router = APIRouter(prefix="/voices", tags=["voices"])


VOICE_SAMPLE_DIR = PROJECT_ROOT / "voices" / "samples"


# (id, label, sample 檔名) — 跟 Track A app.py VOICES list 對齊, 統一 source of truth。
# f5: 開頭代表 F5-TTS 聲音複製 (本機推論, 用 voices/teacher_ref.wav),
# 切換時 backend 改 f5; 其他 id 都是 edge backend 的 voice 名稱。
VOICES: list[dict] = [
    {"id": "zh-TW-HsiaoChenNeural", "label": "小陳 (台女, 新聞風)",     "sample": "voice_tw_hsiaochen_F.mp3"},
    {"id": "zh-TW-HsiaoYuNeural",   "label": "小雨 (台女, 較甜)",       "sample": "voice_tw_hsiaoyu_F.mp3"},
    {"id": "zh-CN-YunxiNeural",     "label": "雲希 (陸男, 年輕)",       "sample": "voice_cn_yunxi_M.mp3"},
    {"id": "zh-CN-YunyangNeural",   "label": "雲揚 (陸男, 主播穩)",     "sample": "voice_cn_yunyang_M.mp3"},
    {"id": "zh-CN-XiaoxiaoNeural",  "label": "曉曉 (陸女, 大陸通用)",   "sample": "voice_cn_xiaoxiao_F.mp3"},
    {"id": "f5:teacher",            "label": "劉老師 (F5 聲音複製)",   "sample": "voice_f5_teacher_M.mp3"},
]
VOICE_IDS = {v["id"] for v in VOICES}


# ---------- Helpers (跟 Track A app.py 同邏輯, 不 import 避免 Track A 啟動依賴) ----------

def _read_current_voice() -> str:
    """從 tts_config.json 推算當前 voice id。"""
    if not TTS_CONFIG_PATH.exists():
        return VOICES[0]["id"]
    try:
        cfg = json.loads(TTS_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return VOICES[0]["id"]
    if cfg.get("backend") == "f5":
        return "f5:teacher"
    return cfg.get("edge", {}).get("voice") or VOICES[0]["id"]


def _write_current_voice(voice_id: str) -> bool:
    """切聲音 = 同時切 backend 跟對應 edge.voice。f5 區塊 (ref_audio 等) 維持不動。"""
    if voice_id not in VOICE_IDS:
        return False
    cfg: dict = {}
    if TTS_CONFIG_PATH.exists():
        try:
            cfg = json.loads(TTS_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}

    if voice_id.startswith("f5:"):
        cfg["backend"] = "f5"
    else:
        cfg["backend"] = "edge"
        cfg.setdefault("edge", {})["voice"] = voice_id

    TTS_CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return True


# ---------- Schemas ----------

class VoiceInfo(BaseModel):
    id: str
    label: str
    sample_url: str


class VoiceListResponse(BaseModel):
    voices: list[VoiceInfo]
    current: str


class SetVoiceRequest(BaseModel):
    voice_id: str = Field(..., description="VOICE_IDS 之一")

    model_config = ConfigDict(extra="allow")


# ---------- Routes ----------

@router.get("", response_model=VoiceListResponse)
async def list_voices() -> VoiceListResponse:
    return VoiceListResponse(
        voices=[
            VoiceInfo(
                id=v["id"],
                label=v["label"],
                sample_url=f"/voices/{v['id']}/sample",
            )
            for v in VOICES
        ],
        current=_read_current_voice(),
    )


@router.post("", response_model=VoiceListResponse)
async def set_voice(req: SetVoiceRequest) -> VoiceListResponse:
    if not _write_current_voice(req.voice_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"未知 voice_id: {req.voice_id} (合法值: {list(VOICE_IDS)})",
        )
    return await list_voices()


@router.get("/{voice_id:path}/sample")
async def voice_sample(voice_id: str) -> FileResponse:
    """Stream voice sample mp3。

    為什麼 voice_id 用 path 而不是普通 str: id 含冒號 "f5:teacher", 普通 str
    converter 把 ":" 視為違法。 用 :path converter 讓整段不解析直接 match。
    """
    info = next((v for v in VOICES if v["id"] == voice_id), None)
    if info is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"未知 voice: {voice_id}")
    target = VOICE_SAMPLE_DIR / info["sample"]
    if not target.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"sample 檔不存在: {info['sample']} (請放 voices/samples/)",
        )
    return FileResponse(target, media_type="audio/mpeg")
