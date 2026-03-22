/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        sage: {
          50: "#f4faf6",
          100: "#e8f2ec",
          200: "#d1e4d9",
          300: "#a8cdb8",
          400: "#7aad8f",
          500: "#55906f",
          600: "#417459",
          700: "#365d49",
          800: "#2d4b3d",
          900: "#263e34",
        },
        blush: {
          50: "#fdf6f7",
          100: "#fce8ec",
          200: "#f9d0d9",
          300: "#f4a8b8",
          400: "#ec7a94",
          500: "#e04d72",
        },
        ink: "#1a2e28",
        taupe: "#6b756f",
      },
      fontFamily: {
        sans: ['"DM Sans"', "system-ui", "sans-serif"],
        display: ['"Fraunces"', "Georgia", "serif"],
      },
      boxShadow: {
        soft: "0 4px 24px -4px rgba(26, 46, 40, 0.08), 0 12px 48px -12px rgba(26, 46, 40, 0.12)",
        glass: "0 8px 32px rgba(26, 46, 40, 0.06), inset 0 1px 0 rgba(255,255,255,0.65)",
        glow: "0 0 60px -12px rgba(244, 168, 184, 0.45)",
      },
      backgroundImage: {
        "hero-mesh":
          "radial-gradient(ellipse 100% 80% at 50% -30%, rgba(244, 168, 184, 0.18), transparent), radial-gradient(ellipse 70% 50% at 100% 0%, rgba(168, 205, 184, 0.35), transparent), radial-gradient(ellipse 60% 40% at 0% 100%, rgba(209, 228, 217, 0.6), transparent)",
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-10px)" },
        },
        "soft-pulse": {
          "0%, 100%": { opacity: "0.5" },
          "50%": { opacity: "0.85" },
        },
      },
      animation: {
        float: "float 5s ease-in-out infinite",
        "float-delayed": "float 5s ease-in-out 0.8s infinite",
        "soft-pulse": "soft-pulse 4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
