/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Forest 主題色票, 跟 PptxStyleRenderer 對齊
        forest: {
          DEFAULT: '#1e3a2e',
          light: '#2a5040',
          dark: '#152822',
          bg: '#fafaf6',
          card: '#ffffff',
        },
        chalk: {
          white: '#e8e6d8',
          yellow: '#ffd96b',
          yellowDark: '#ffc94a',
          cyan: '#b4dcc8',
          orange: '#ffc88c',
        },
        ink: {
          DEFAULT: '#1f2d28',
          muted: '#6b6e6a',
          subtle: '#a09e95',
        },
        border: '#d8d4c2',
      },
      fontFamily: {
        sans: ['"Microsoft JhengHei"', '"PingFang TC"', 'system-ui', 'sans-serif'],
        mono: ['Consolas', 'Monaco', 'monospace'],
      },
    },
  },
  plugins: [],
};
