/** @type {import('tailwindcss').Config} */
// PayDesk look: calm and plain. One font (Apple SF Pro, Inter on Windows), neutral greys, ONE blue for actions.
// "indigo" is used for buttons/links across the app, so it is mapped to the action blue here;
// "violet" (old AI accents) is mapped to quiet greys.
const blue = {
  50: "#f0f6ff", 100: "#dcebff", 200: "#b9d6ff", 300: "#8bbcfb", 400: "#4c97f0",
  500: "#1a7ae6", 600: "#0071e3", 700: "#0060c2", 800: "#004c9a", 900: "#003a76",
};
const grey = {
  50: "#f5f5f7", 100: "#ececef", 200: "#e1e1e6", 300: "#d2d2d7", 400: "#a1a1a6",
  500: "#86868b", 600: "#6e6e73", 700: "#48484c", 800: "#1d1d1f", 900: "#111113",
};
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        // Apple's own font (SF Pro) on iPhone/Mac; Inter (closest free look-alike) everywhere else
        sans: ["-apple-system", "BlinkMacSystemFont", "SF Pro Display", "SF Pro Text", "Inter", "Segoe UI", "Helvetica Neue", "Arial", "sans-serif"],
      },
      colors: { indigo: blue, violet: grey, slate: grey },
      boxShadow: {
        sm: "0 1px 2px rgba(0,0,0,0.04)",
        DEFAULT: "0 1px 3px rgba(0,0,0,0.06)",
        md: "0 4px 16px rgba(0,0,0,0.06)",
        lg: "0 12px 32px rgba(0,0,0,0.08)",
      },
    },
  },
  plugins: [],
}
