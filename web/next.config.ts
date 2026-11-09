import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  agentRules: false, // Project guidance lives in the root AGENTS.md and CLAUDE.md.
  poweredByHeader: false,
  turbopack: { root: path.resolve(__dirname) },   // a stray lockfile in the home folder confused root detection
};

export default nextConfig;
