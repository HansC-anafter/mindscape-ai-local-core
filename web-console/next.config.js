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
    const mediaProxyUrl = process.env.MEDIA_PROXY_URL || 'http://127.0.0.1:8202';
    return [
      {
        source: '/api/v1/media/:path*',
        destination: `${mediaProxyUrl}/api/v1/media/:path*`,
      },
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
  webpack: (config, { isServer }) => {
    const corePackagePath = path.resolve(__dirname, '../packages/core/src');
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      '@': path.resolve(__dirname, 'src'),
      '@mindscape-ai/core': path.resolve(__dirname, '../packages/core/src/index.ts'),
      '@mindscape-ai/core/api': path.resolve(corePackagePath, 'api/index.ts'),
      '@mindscape-ai/core/contexts': path.resolve(corePackagePath, 'contexts/index.ts'),
    };
    // config.resolve.symlinks = false; // Disabled to support pnpm symlinks
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

    if (isServer) {
      config.externals = config.externals || [];
      if (typeof config.externals === 'function') {
        const originalExternals = config.externals;
        config.externals = [
          originalExternals,
          ({ request }, callback) => {
            if (request === 'react-player' || request.startsWith('react-player/')) {
              return callback(null, 'commonjs ' + request);
            }
            callback();
          },
        ];
      } else if (Array.isArray(config.externals)) {
        config.externals.push(({ request }, callback) => {
          if (request === 'react-player' || request.startsWith('react-player/')) {
            return callback(null, 'commonjs ' + request);
          }
          callback();
        });
      }
    }

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
