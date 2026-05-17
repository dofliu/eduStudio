interface Props {
  value?: number;       // 0..1
  tone?: 'forest' | 'yellow' | 'coral';
}

export function Meter({ value = 0, tone = 'forest' }: Props) {
  const tones = {
    forest: 'bg-forest-500',
    yellow: 'bg-chalk-yellowDark',
    coral:  'bg-accent-coral',
  } as const;
  return (
    <div className="h-1 rounded-full bg-paper-line overflow-hidden">
      <div className={'h-full ' + tones[tone]} style={{ width: `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%` }}></div>
    </div>
  );
}
