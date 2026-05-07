import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';
import clsx from 'clsx';

interface ToastState {
  message: string;
  kind: 'info' | 'error';
}

interface ToastCtx {
  show: (message: string, kind?: 'info' | 'error') => void;
  current: ToastState | null;
}

const ToastContext = createContext<ToastCtx | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [current, setCurrent] = useState<ToastState | null>(null);
  const show = useCallback<ToastCtx['show']>((message, kind = 'info') => {
    setCurrent({ message, kind });
    setTimeout(() => setCurrent(null), 3000);
  }, []);
  return (
    <ToastContext.Provider value={{ show, current }}>
      {children}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be inside ToastProvider');
  return ctx;
}

export function Toast() {
  const ctx = useContext(ToastContext);
  if (!ctx?.current) return null;
  return (
    <div
      className={clsx(
        'fixed bottom-6 right-6 z-50 rounded px-4 py-3 shadow-lg',
        ctx.current.kind === 'error'
          ? 'bg-red-700 text-white'
          : 'bg-forest text-chalk-yellow',
      )}
    >
      {ctx.current.message}
    </div>
  );
}
