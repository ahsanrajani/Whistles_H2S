import type { NextConfig } from "next";

const backend = process.env.GURU_API_ORIGIN ?? "http://127.0.0.1:5000";

const nextConfig: NextConfig = {
  agentRules: false,
  allowedDevOrigins: ["127.0.0.1", "localhost", "192.168.18.159"],
  async rewrites() {
    return [
      {source: "/api/:path*", destination: `${backend}/api/:path*`},
      {source: "/favicon.ico", destination: `${backend}/favicon.ico`},
      {source: "/brand/:path*", destination: `${backend}/static/brand/:path*`},
      {source: "/uploads/:path*", destination: `${backend}/static/uploads/:path*`},
    ];
  },
  async redirects() {
    // Legacy path parity: /evidence?… → /mentions?… (querystring passes through).
    return [{source: "/evidence", destination: "/mentions", permanent: true}];
  },
};

export default nextConfig;
