import type { NextConfig } from "next";
import path from "path";

// The orchestrator the panel proxies its API calls to. On the docker-compose
// deploy nginx is the single entry point and routes /api/* to the
// orchestrator, so no proxy is needed there. On GCP (Cloud Run) the panel is a
// separate service with no nginx in front, so the panel's own Next server
// proxies /api/* to the orchestrator's public URL via the rewrites below
// (cookie-based cloud auth flows through the proxy, no CORS needed).
// ROBOFLEET_API_URL is the orchestrator's public Cloud Run URL, set in the
// panel service manifest. Falls back to the compose internal name + localhost.
const BACKEND_URL =
  process.env.ROBOFLEET_API_URL ||
  process.env.INTERNAL_API_URL ||
  "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",

  // Pin the file-tracing root to this directory so `output: "standalone"` is
  // deterministic regardless of stray lockfiles higher up the tree (e.g. a
  // ~/package-lock.json). Without it Next can infer the wrong workspace root
  // from a sibling lockfile and nest the standalone output, so `server.js`
  // never lands at `.next/standalone/server.js` and `node server.js` fails.
  outputFileTracingRoot: path.join(__dirname),

  // Proxy API calls to the orchestrator to avoid CORS issues. The Next server
  // (output: standalone, `node server.js`) forwards /api/* to BACKEND_URL,
  // carrying the browser's cloud-auth session cookie through to the
  // orchestrator. Next's production router proxies WebSocket upgrades through these
  // build-time rewrites too (middleware never runs for upgrades), so /ws
  // needs the real orchestrator URL at BUILD time (panel.Dockerfile build
  // arg). /health is the panel's connection-status probe; it lives at the
  // orchestrator root, not under /api.
  async rewrites() {
    const base = BACKEND_URL.replace(/\/$/, "");
    return [
      {
        source: "/api/:path*",
        destination: `${base}/api/:path*`,
      },
      {
        source: "/ws/:path*",
        destination: `${base}/ws/:path*`,
      },
      {
        source: "/health",
        destination: `${base}/health`,
      },
    ];
  },
};

export default nextConfig;
