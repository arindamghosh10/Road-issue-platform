import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output = a small self-contained server for the Docker image.
  output: "standalone",
  reactStrictMode: true,
};

export default nextConfig;
