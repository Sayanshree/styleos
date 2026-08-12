import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The engine URL and the BFF shared token are server-only on purpose: they are
  // deliberately NOT exposed through `env` here, which would inline them into the
  // client bundle. They are read only inside lib/engine.ts, which is server-only.
};

export default nextConfig;
