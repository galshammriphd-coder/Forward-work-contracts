/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: { sans: ["'IBM Plex Sans Arabic'", "'IBM Plex Sans'", "system-ui", "sans-serif"] },
      colors: {
        brand: { 50: "#eef4ff", 100: "#dbe6fe", 200: "#bfd3fe", 300: "#93b4fd", 400: "#6090fa", 500: "#3b6cf5", 600: "#2552e0", 700: "#1d41b8", 800: "#1e3a8a", 900: "#1c2f6b" },
        ink: { 50: "#f8fafc", 100: "#f1f5f9", 200: "#e2e8f0", 300: "#cbd5e1", 400: "#94a3b8", 500: "#64748b", 600: "#475569", 700: "#334155", 800: "#1e293b", 900: "#0f172a", 950: "#0b1220" },
      },
    },
  },
  plugins: [],
};
