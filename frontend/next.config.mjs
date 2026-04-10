/** @type {import('next').NextConfig} */
const nextConfig = {
  // 允许直接调用 FastAPI（CORS 由后端负责）
  async rewrites() {
    return [];
  },
};

export default nextConfig;
