/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        echo: {
          void: '#05070A',
          surface: '#0B0E14',
          card: '#121721',
          border: '#1C2331',
          cyan: '#00F0FF',
          'cyan-dim': '#008B99',
          blue: '#0070F3',
          purple: '#7928CA',
          success: '#00E676',
          warning: '#FFB300',
          danger: '#FF1744',
          text: '#F0F6FC',
          muted: '#8B949E',
        }
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Consolas', 'Courier New', 'monospace'],
        sans: ['Inter', 'system-ui', 'Segoe UI', 'sans-serif'],
      },
      boxShadow: {
        'cyan-glow': '0 0 20px rgba(0, 240, 255, 0.25)',
        'blue-glow': '0 0 20px rgba(0, 112, 243, 0.25)',
        'danger-glow': '0 0 20px rgba(255, 23, 68, 0.25)',
      }
    },
  },
  plugins: [],
}

