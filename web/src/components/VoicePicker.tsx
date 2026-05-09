// PR-3l: 全域聲音切換 picker — 放 App header
//
// 行為跟 Track A 的 VOICE_PICKER_HTML 對齊:
//   - 下拉選 6 種聲音 (台女 / 陸男 / 陸女 / F5 聲音複製)
//   - 旁邊 audio 元素試聽 sample
//   - 切換寫 tts_config.json (POST /voices), 影響後續所有 render
//   - 不影響進行中的 render (那已經寫進 deck.json 了)

import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from './Toast';
import type { VoiceInfo } from '../types';

export function VoicePicker() {
  const { show } = useToast();
  const [voices, setVoices] = useState<VoiceInfo[]>([]);
  const [current, setCurrent] = useState<string>('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .getVoices()
      .then((r) => {
        if (cancelled) return;
        setVoices(r.voices);
        setCurrent(r.current);
      })
      .catch((e) => show(`載入聲音清單失敗: ${e}`, 'error'))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [show]);

  const onChange = async (voiceId: string) => {
    const prev = current;
    setCurrent(voiceId); // 樂觀更新
    try {
      await api.setVoice(voiceId);
      show('聲音已切換 (下次 render 生效)');
    } catch (e) {
      setCurrent(prev);
      show(`切換失敗: ${e}`, 'error');
    }
  };

  if (loading) {
    return <span className="text-xs text-chalk-yellow/70">載入聲音中…</span>;
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs hidden sm:inline">🗣</span>
      <select
        className="text-xs bg-forest/30 text-chalk-white border border-chalk-yellow/30 rounded px-2 py-1
                   focus:outline-none focus:border-chalk-yellow"
        value={current}
        onChange={(e) => onChange(e.target.value)}
        title="切換 TTS 聲音 (寫進 tts_config.json, 影響後續 render)"
      >
        {voices.map((v) => (
          <option key={v.id} value={v.id} className="text-ink">
            {v.label}
          </option>
        ))}
      </select>
      {/* 試聽 — key 強制 audio 在切換 voice 時 reload src */}
      <audio
        key={current}
        controls
        src={current ? api.voiceSampleUrl(current) : undefined}
        preload="none"
        className="h-7 max-w-[180px]"
      />
    </div>
  );
}
