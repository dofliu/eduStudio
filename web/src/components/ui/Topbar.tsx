import type { ReactNode } from 'react';

interface Props {
  eyebrow?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
}

export function Topbar({ eyebrow, title, subtitle, right }: Props) {
  return (
    <header className="flex items-center justify-between gap-5 px-7 py-4 border-b border-paper-line bg-paper">
      <div className="min-w-0">
        <div className="flex items-baseline gap-3 flex-wrap">
          {eyebrow && <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-ink-muted shrink-0">{eyebrow}</div>}
          <h1 className="font-display text-[26px] leading-[1.1] text-forest-700 truncate">{title}</h1>
        </div>
        {subtitle && <p className="text-[12px] text-ink-muted mt-1 max-w-3xl line-clamp-1">{subtitle}</p>}
      </div>
      {right && <div className="flex items-center gap-2 shrink-0">{right}</div>}
    </header>
  );
}
