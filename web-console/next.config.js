const path = require('path');

const staticCapabilityHostCodes = [
  'blender_bridge',
  'brand_identity',
  'character_training',
  'chat_capture',
  'comfyui_runtime',
  'content_scheduler',
  'demo_aol_pack',
  'expert_network',
  'ig',
  'layer_asset_forge',
  'mindscape_cloud_integration',
  'multi_media_studio',
  'newsletter',
  'practice_companion',
  'public_persona_studio',
  'video_chapter_studio',
  'video_renderer',
  'web_generation',
  'world_asset_forge',
  'yogacoach',
];

function capabilityRouteSources(capabilityCode) {
  const variants = new Set([
    capabilityCode,
    capabilityCode.replace(/_/g, '-'),
  ]);
  return Array.from(variants).flatMap((variant) => [
    `/workspaces/:workspaceId/capabilities/${variant}`,
    `/workspaces/:workspaceId/capabilities/${variant}/ui`,
    `/workspaces/:workspaceId/capabilities/${variant}/ui/loaded`,
  ]);
}

function staticCapabilityRedirects() {
  return staticCapabilityHostCodes.flatMap((capabilityCode) =>
    capabilityRouteSources(capabilityCode).map((source) => ({
      source,
      destination: `/workspaces/:workspaceId/capability-ui-hosts/${capabilityCode}`,
      permanent: false,
    })),
  );
}

function performanceDirectionRedirects() {
  return ['performance_direction', 'performance-direction'].flatMap((capabilityCode) =>
    [
      `/workspaces/:workspaceId/capabilities/${capabilityCode}`,
      `/workspaces/:workspaceId/capabilities/${capabilityCode}/ui`,
      `/workspaces/:workspaceId/capabilities/${capabilityCode}/ui/loaded`,
    ].map((source) => ({
      source,
      destination: '/workspaces/:workspaceId/capabilities/performance_direction/start',
      permanent: false,
      missing: [
        { type: 'query', key: 'sessionId' },
        { type: 'query', key: 'session_id' },
      ],
    })),
  );
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: false,
  output: 'standalone',
  // Preserve backend route shape when using same-origin rewrites.
  // Some FastAPI endpoints are slash-sensitive and must not be normalized by Next.
  skipTrailingSlashRedirect: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  },
  async redirects() {
    return [
      ...performanceDirectionRedirects(),
      ...staticCapabilityRedirects(),
    ];
  },
  async rewrites() {
    // /api/* and /health are handled by App Route proxy code so retry,
    // no-store, and upstream selection are explicit and testable.
    return [];
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
