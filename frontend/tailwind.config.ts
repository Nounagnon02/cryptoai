import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        crypto: {
          green: "#00C853",
          red: "#FF1744",
          blue: "#2979FF",
          yellow: "#FFD600",
        },
        surface: {
          DEFAULT: "#0f1017",
          card: "#1a1b2e",
          hover: "#24253a",
          border: "#2a2b3e",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      animation: {
        "pulse-slow": "pulse 3s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
