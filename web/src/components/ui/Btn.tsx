import type { ButtonHTMLAttributes, ReactNode } from 'react';

type Kind = 'primary' | 'secondary' | 'ghost' | 'quiet' | 'danger';
type Size = 'sm' | 'md' | 'lg';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  kind?: Kind;
  size?: Size;
  children: ReactNode;
}

const SIZES: Record<Size, string> = {
  sm: 'h-7 px-2.5 text-[12px]',
  md: 'h-9 px-3.5 text-[13px]',
  lg: 'h-11 px-5 text-[14px]',
};
const KINDS: Record<Kind, string> = {
  primary:   'bg-forest-600 text-chalk-yellow hover:bg-forest-700 border border-forest-700',
  secondary: 'bg-chalk-yellow text-forest-700 hover:bg-chalk-yellowDark border border-chalk-yellowDark/70',
  ghost:     'bg-transparent text-ink hover:bg-paper-warm border border-paper-edge',
  quiet:     'bg-transparent text-ink-muted hover:text-ink hover:bg-paper-warm border border-transparent',
  danger:    'bg-paper-warm text-accent-coral hover:bg-accent-coral hover:text-paper border border-accent-coral/40',
};

export function Btn({ kind = 'ghost', size = 'md', children, className = '', ...rest }: Props) {
  return (
    <button
      {...rest}
      className={
        'inline-flex items-center gap-1.5 rounded-sm font-medium transition-colors ' +
        'disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap ' +
        SIZES[size] + ' ' + KINDS[kind] + ' ' + className
      }
    >
      {children}
    </button>
  );
}
