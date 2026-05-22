/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Forest 主題色票 — UI redesign 後完整色階
        forest: {
          DEFAULT: '#1e3a2e',
          50:  '#f1f4f1',
          100: '#dde6df',
          200: '#b8cabd',
          300: '#7d9d87',
          400: '#4a7559',
          500: '#2a5040',
          600: '#1e3a2e',
          700: '#152822',
          800: '#0e1c18',
          900: '#08110e',
          // legacy aliases — 原 code 還用得到
          light: '#2a5040',
          dark: '#152822',
          bg: '#f7f4ea',
          card: '#fbf9f0',
        },
        chalk: {
          DEFAULT: '#ffd96b',
          white: '#f4f1e3',
          yellow: '#ffd96b',
          yellowDark: '#e8be4d',
          // legacy
          yellowDark_legacy: '#ffc94a',
          cyan: '#b4dcc8',
          orange: '#ffc88c',
        },
        paper: {
          DEFAULT: '#f7f4ea',
          warm: '#efeada',
          card: '#fbf9f0',
          line: '#d8d2bd',
          edge: '#c4bda3',
        },
        ink: {
          DEFAULT: '#15201b',
          muted: '#5b5e58',
          subtle: '#8a8a7c',
          faint: '#b3b09f',
        },
        accent: {
          coral: '#c8553d',
          plum: '#7a3c52',
          moss: '#5f7a4a',
        },
        // legacy border 別名
        border: '#d8d2bd',
      },
      fontFamily: {
        display: ['"Instrument Serif"', 'Georgia', 'serif'],
        sans: ['"IBM Plex Sans"', '"Microsoft JhengHei"', '"PingFang TC"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'Consolas', 'Monaco', 'monospace'],
      },
      boxShadow: {
        card:  '0 1px 0 rgba(20,28,24,0.04), 0 0 0 1px rgba(20,28,24,0.06)',
        lift:  '0 10px 32px -12px rgba(20,28,24,0.18), 0 0 0 1px rgba(20,28,24,0.06)',
        inset: 'inset 0 0 0 1px rgba(20,28,24,0.06)',
      },
    },
  },
  plugins: [],
};
