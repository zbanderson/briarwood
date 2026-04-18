import type { NextConfig } from "next";

const apiBase = process.env.BRIARWOOD_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/artifacts/:path*", destination: `${apiBase}/artifacts/:path*` },
    ];
  },
};

export default nextConfig;
