interface Props {
  title: string;
  theme?: string | null;
  duration?: string | null;
  big?: boolean;
}

const THEME_BG: Record<string, string> = {
  forest:  'linear-gradient(135deg, #1e3a2e 0%, #2a5040 100%)',
  navy:    'linear-gradient(135deg, #1a2a4a 0%, #2e3f6b 100%)',
  journal: 'linear-gradient(135deg, #e7e0c8 0%, #cdc5a4 100%)',
  naruto:  'linear-gradient(135deg, #b8541c 0%, #d97f3a 100%)',
  frieren: 'linear-gradient(135deg, #2d3656 0%, #4a557d 100%)',
};

export function VideoThumb({ title, theme, duration, big }: Props) {
  const bg = (theme && THEME_BG[theme]) || THEME_BG.forest;
  const fg = theme === 'journal' ? '#5b4a2a' : '#ffd96b';
  return (
    <div className="relative w-full overflow-hidden rounded-sm" style={{ aspectRatio: '16/9', background: bg }}>
      <div className="absolute inset-0 stripes-placeholder opacity-25"></div>
      <div className="absolute inset-0 flex flex-col p-3 justify-between">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em]" style={{ color: fg, opacity: 0.7 }}>
          autoSolver · {theme || 'forest'}
        </div>
        <div>
          <div
            className="font-display leading-[1.05] line-clamp-2"
            style={{ color: fg, fontSize: big ? 22 : 15 }}
          >
            {title}
          </div>
          {duration && (
            <div className="font-mono text-[10px] mt-1" style={{ color: fg, opacity: 0.75 }}>{duration}</div>
          )}
        </div>
      </div>
      <div className="absolute right-2 top-2 w-7 h-7 rounded-full bg-black/30 flex items-center justify-center backdrop-blur-sm">
        <span className="text-white text-[11px] ml-0.5">▶</span>
      </div>
    </div>
  );
}
