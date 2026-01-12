const path = require('path');

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: false,
  output: 'standalone',
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  },
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8200';
    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
  webpack: (config) => {
    const corePackagePath = path.resolve(__dirname, '../packages/core/src');
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      '@': path.resolve(__dirname, 'src'),
      '@mindscape-ai/core': path.resolve(__dirname, '../packages/core/src/index.ts'),
      '@mindscape-ai/core/api': path.resolve(corePackagePath, 'api/index.ts'),
      '@mindscape-ai/core/contexts': path.resolve(corePackagePath, 'contexts/index.ts'),
    };
    config.resolve.symlinks = false;
    config.resolve.extensions = [
      ...(config.resolve.extensions || []),
      '.ts',
      '.tsx',
    ];
    config.resolve.modules = [
      ...(config.resolve.modules || []),
      path.resolve(__dirname, 'packages'),
      path.resolve(__dirname, 'src'),
      'node_modules',
    ];

    config.module = config.module || {};
    config.module.rules = config.module.rules || [];
    config.plugins = config.plugins || [];

    return config;
  },
  experimental: {
    serverActions: {
      bodySizeLimit: '2mb',
    },
  },
}

module.exports = nextConfig
