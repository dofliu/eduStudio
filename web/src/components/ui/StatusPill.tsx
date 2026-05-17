import type { JobState } from '../../types';

const META: Record<JobState, { label: string; tone: string; dot: string }> = {
  pending:         { label: '排隊',      tone: 'text-ink-muted bg-paper-warm border-paper-edge',                  dot: 'bg-ink-faint' },
  ingesting:       { label: '分析中',    tone: 'text-accent-plum bg-paper-warm border-accent-plum/30',            dot: 'bg-accent-plum animate-pulse' },
  awaiting_review: { label: '待 REVIEW', tone: 'text-forest-700 bg-chalk-yellow/40 border-chalk-yellowDark',      dot: 'bg-chalk-yellowDark' },
  rendering:       { label: '渲染中',    tone: 'text-forest-700 bg-forest-100 border-forest-300',                 dot: 'bg-forest-500 animate-pulse' },
  done:            { label: '完成',      tone: 'text-forest-700 bg-forest-100 border-forest-300',                 dot: 'bg-forest-500' },
  failed:          { label: '失敗',      tone: 'text-accent-coral bg-paper-warm border-accent-coral/40',          dot: 'bg-accent-coral' },
};

interface Props { state: JobState; size?: 'sm' | 'md'; }

export function StatusPill({ state, size = 'md' }: Props) {
  const m = META[state] || META.pending;
  const sz = size === 'sm' ? 'text-[10px] px-1.5 py-0.5' : 'text-[11px] px-2 py-1';
  return (
    <span className={'inline-flex items-center gap-1.5 rounded-sm font-medium border uppercase tracking-[0.08em] whitespace-nowrap ' + m.tone + ' ' + sz}>
      <span className={'w-1.5 h-1.5 rounded-full ' + m.dot}></span>{m.label}
    </span>
  );
}
