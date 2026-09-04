/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // Expose backend URL to the browser bundle at build time
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080",
  },
};

module.exports = nextConfig;
