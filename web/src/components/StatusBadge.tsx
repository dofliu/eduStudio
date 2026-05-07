import clsx from 'clsx';
import type { JobState } from '../types';

const STYLES: Record<JobState, string> = {
  pending: 'bg-stone-200 text-stone-700',
  ingesting: 'bg-yellow-100 text-yellow-800',
  awaiting_review: 'bg-chalk-yellow text-forest',
  rendering: 'bg-emerald-200 text-emerald-900',
  done: 'bg-forest text-chalk-yellow',
  failed: 'bg-red-700 text-white',
};

export function StatusBadge({ state }: { state: JobState }) {
  return <span className={clsx('badge', STYLES[state])}>{state}</span>;
}
