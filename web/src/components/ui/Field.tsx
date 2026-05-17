import type { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes, ReactNode } from 'react';

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-muted">{label}</span>
        {hint && <span className="text-[10px] text-ink-subtle">{hint}</span>}
      </div>
      {children}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={
        'w-full h-9 px-3 rounded-sm border border-paper-edge bg-paper-card text-[13px] ' +
        'focus:outline-none focus:ring-2 focus:ring-chalk-yellow focus:border-transparent ' +
        (props.className || '')
      }
    />
  );
}

export function Select({ children, ...rest }: SelectHTMLAttributes<HTMLSelectElement> & { children: ReactNode }) {
  return (
    <select
      {...rest}
      className={
        'w-full h-9 px-2.5 rounded-sm border border-paper-edge bg-paper-card text-[13px] ' +
        'focus:outline-none focus:ring-2 focus:ring-chalk-yellow focus:border-transparent ' +
        (rest.className || '')
      }
    >
      {children}
    </select>
  );
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={
        'w-full px-3 py-2 rounded-sm border border-paper-edge bg-paper-card text-[13px] leading-relaxed ' +
        'focus:outline-none focus:ring-2 focus:ring-chalk-yellow focus:border-transparent ' +
        (props.className || '')
      }
    />
  );
}
