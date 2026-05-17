import { NavLink } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { VoicePicker } from '../VoicePicker';

const NAV = [
  { to: '/',          end: true,  label: 'Jobs',      sub: '作業中心',     glyph: '▤' },
  { to: '/proposals', end: false, label: 'Proposals', sub: '自動企劃',     glyph: '✦' },
  { to: '/library',   end: false, label: 'Library',   sub: '影片庫',       glyph: '▶' },
];

interface Counts {
  jobs?: number;
  proposals?: number;
  library?: number;
}

const STORAGE_KEY = 'ui.sidebar.collapsed';

export function Sidebar({ counts }: { counts?: Counts }) {
  // persistent collapse state
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.localStorage.getItem(STORAGE_KEY) === '1';
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
  }, [collapsed]);

  const width = collapsed ? 'w-[56px]' : 'w-[220px]';

  return (
    <aside className={'shrink-0 border-r border-paper-line bg-paper flex flex-col h-screen sticky top-0 transition-[width] duration-200 ease-out ' + width}>
      {/* Brand + collapse toggle */}
      <div className={'border-b border-paper-line ' + (collapsed ? 'px-2 py-3.5 flex flex-col items-center gap-2' : 'px-4 pt-4 pb-3 flex items-center gap-2')}>
        {!collapsed ? (
          <>
            <span className="inline-block w-7 h-7 rounded-sm chalk-surface text-chalk-yellow text-center leading-7 font-display text-lg shrink-0">a</span>
            <div className="leading-tight flex-1 min-w-0">
              <div className="font-display text-[19px] text-forest-700 -mt-0.5 truncate">autoSolver</div>
              <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-ink-muted -mt-0.5">video studio</div>
            </div>
            <button
              onClick={() => setCollapsed(true)}
              className="text-ink-faint hover:text-forest-600 text-[14px] w-6 h-6 rounded-sm hover:bg-paper-warm"
              title="收合側欄"
            >‹</button>
          </>
        ) : (
          <>
            <span className="inline-block w-7 h-7 rounded-sm chalk-surface text-chalk-yellow text-center leading-7 font-display text-lg shrink-0">a</span>
            <button
              onClick={() => setCollapsed(false)}
              className="text-ink-faint hover:text-forest-600 text-[14px] w-6 h-6 rounded-sm hover:bg-paper-warm"
              title="展開側欄"
            >›</button>
          </>
        )}
      </div>

      <nav className={'py-3 space-y-0.5 ' + (collapsed ? 'px-2' : 'px-2.5')}>
        {NAV.map((n) => {
          const cnt = (counts && (
            n.to === '/' ? counts.jobs :
            n.to === '/proposals' ? counts.proposals :
            n.to === '/library' ? counts.library : undefined
          ));
          return (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              title={collapsed ? `${n.label} · ${n.sub}` : undefined}
              className={({ isActive }) =>
                'w-full text-left flex items-center rounded-sm transition-colors group ' +
                (collapsed ? 'justify-center py-2.5 ' : 'gap-2.5 px-2.5 py-2 ') +
                (isActive ? 'bg-forest-600 text-chalk-white' : 'text-ink hover:bg-paper-warm')
              }
            >
              {({ isActive }) => (
                <>
                  <span className={'font-mono text-[14px] w-5 text-center shrink-0 ' + (isActive ? 'text-chalk-yellow' : 'text-ink-subtle group-hover:text-forest-600')}>{n.glyph}</span>
                  {!collapsed && (
                    <>
                      <span className="flex-1 min-w-0">
                        <span className="block text-[13px] font-medium leading-tight truncate">{n.label}</span>
                        <span className={'block text-[10.5px] leading-tight truncate ' + (isActive ? 'text-chalk-white/70' : 'text-ink-muted')}>{n.sub}</span>
                      </span>
                      {cnt != null && (
                        <span className={'num text-[10.5px] font-mono px-1.5 py-0.5 rounded shrink-0 ' + (isActive ? 'bg-forest-700 text-chalk-yellow' : 'bg-paper-warm text-ink-muted')}>
                          {cnt}
                        </span>
                      )}
                    </>
                  )}
                </>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Voice picker (展開時顯示, 摺疊時隱藏避免擠) */}
      {!collapsed && (
        <div className="mt-auto border-t border-paper-line">
          <div className="px-4 pt-3 pb-1.5 text-[9.5px] font-mono uppercase tracking-[0.18em] text-ink-muted">Voice</div>
          <div className="px-2.5 pb-3">
            <div className="bg-forest-700 rounded-sm p-2">
              <VoicePicker />
            </div>
          </div>
          <div className="px-4 pb-3 text-[9.5px] font-mono text-ink-faint">
            api · localhost:8000 <span className="inline-block w-1.5 h-1.5 rounded-full bg-forest-500 ml-1 align-middle"></span>
          </div>
        </div>
      )}

      {collapsed && (
        <div className="mt-auto pb-3 flex justify-center">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-forest-500" title="api · localhost:8000"></span>
        </div>
      )}
    </aside>
  );
}
