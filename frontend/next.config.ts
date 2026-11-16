import type { NextConfig } from "next";

const isDevServer = process.env.NODE_ENV === "development" || process.argv.includes("dev");

const nextConfig: NextConfig = {
  // Give the dev server a clean, separate cache from production builds.
  distDir: isDevServer ? ".next-calendar-dev" : ".next",
};

export default nextConfig;
