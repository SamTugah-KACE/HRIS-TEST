/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#e6f0fa',
          100: '#b3d1f0',
          200: '#80b3e6',
          300: '#4d94db',
          400: '#2680c2',
          500: '#003366',
          600: '#002d5c',
          700: '#002452',
          800: '#001b3d',
          900: '#001229',
        },
      },
    },
  },
  plugins: [],
}
