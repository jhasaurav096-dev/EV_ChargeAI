/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        grid: {
          dark: '#0B0F19',
          card: '#111827',
          border: '#1F2937',
          accent: '#10B981',
          danger: '#EF4444',
          warning: '#F59E0B',
          cyan: '#06B6D4',
        }
      }
    },
  },
  plugins: [],
}

