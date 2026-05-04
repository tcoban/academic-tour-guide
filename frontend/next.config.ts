import type { NextConfig } from "next";

const lifecycle = process.env.npm_lifecycle_event;
const distDir = process.env.NEXT_DIST_DIR ?? (lifecycle === "build" || lifecycle === "start" ? ".next-build" : ".next");

const nextConfig: NextConfig = {
  distDir,
  typedRoutes: true,
  experimental: {
    cpus: 1,
    workerThreads: false,
  },
};

export default nextConfig;
