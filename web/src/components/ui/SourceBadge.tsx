import type { SourceType } from '../../types';

export const SOURCE_META: Record<SourceType, { label: string; short: string; icon: string; tone: string }> = {
  exam_pdf:   { label: '考卷',  short: 'EXAM', icon: '✎', tone: 'bg-paper-warm text-accent-coral border-accent-coral/30' },
  slides_pdf: { label: '簡報',  short: 'DECK', icon: '▦', tone: 'bg-paper-warm text-forest-600 border-forest-600/30' },
  repo:       { label: 'Repo',  short: 'REPO', icon: '⌥', tone: 'bg-paper-warm text-accent-plum border-accent-plum/30' },
  document:   { label: '文件',  short: 'DOC',  icon: '¶', tone: 'bg-paper-warm text-accent-moss border-accent-moss/30' },
  url:        { label: '網頁',  short: 'URL',  icon: '↗', tone: 'bg-paper-warm text-ink border-ink/20' },
  song:       { label: '歌曲',  short: 'SONG', icon: '♪', tone: 'bg-paper-warm text-chalk-orange border-chalk-orange/40' },
};

interface Props { type: SourceType; size?: 'sm' | 'md'; }

export function SourceBadge({ type, size = 'md' }: Props) {
  const m = SOURCE_META[type] || SOURCE_META.document;
  const sz = size === 'sm' ? 'text-[10px] px-1.5 py-0.5' : 'text-[11px] px-2 py-0.5';
  return (
    <span className={'inline-flex items-center gap-1 rounded-sm font-mono uppercase tracking-[0.08em] border whitespace-nowrap ' + m.tone + ' ' + sz}>
      <span className="opacity-70">{m.icon}</span>{m.short}
    </span>
  );
}
