/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",

  // 开发模式下允许从代理/VPN 等入口访问（如 tun网段 198.18.x），否则 HMR/字体等会被拦截
  allowedDevOrigins: ["198.18.0.1"],

  // 允许直接调用 FastAPI（CORS 由后端负责）
  async rewrites() {
    return [];
  },
};

export default nextConfig;
