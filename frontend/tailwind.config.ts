import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#fdf6f0",
          100: "#fae8d4",
          200: "#f5cfa2",
          300: "#efae6a",
          400: "#e8883a",
          500: "#e06b1a",
          600: "#c45310",
          700: "#a33d10",
          800: "#843214",
          900: "#6c2a14",
        },
        gold: "#c9a84c",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
