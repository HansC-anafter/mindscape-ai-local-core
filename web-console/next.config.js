const path = require('path');

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: false, // Disabled to prevent double-render abort issues
  output: 'standalone',
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  },
  async rewrites() {
    // rewrites() runs on the Next.js server (inside Docker container)
    // Use BACKEND_URL (Docker internal hostname) for server-side proxying
    // NEXT_PUBLIC_BACKEND_URL is for client-side code (browser), not for server-side rewrites
    const backendUrl = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8200';
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
  webpack: (config) => {
    // Add path alias resolution for @/* to ./src/*
    // CRITICAL: This allows webpack to resolve @/ aliases in dynamic imports at build time
    // Webpack needs to statically analyze dynamic import paths to create proper chunks
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      '@': path.resolve(__dirname, 'src'),
    };
    config.resolve.symlinks = false;

    // Ensure webpack can handle dynamic imports with aliases
    // This tells webpack to include all files matching the pattern in the build
    config.module = config.module || {};
    config.module.rules = config.module.rules || [];

    return config;
  },
  // Disable RSC prefetching for client components to avoid 404 errors
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb',
    },
  },
}

module.exports = nextConfig
