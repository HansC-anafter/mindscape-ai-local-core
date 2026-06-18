import fs from 'node:fs';

import {
  CAPABILITY_HOST_CSS_OUTPUT,
  findReadableRuntimeAssetPath,
  prepareCapabilityHostRuntimeAssets,
  resolveCapabilityHostStylesheetPath,
} from './build-runtime-assets.mjs';

export const RUNTIME_ASSET_PREFIX = '/__mindscape-capability-host/';

const RUNTIME_ASSETS = {
  'app-layout.css': {
    build: 'tailwind',
    contentType: 'text/css; charset=utf-8',
    paths: [
      CAPABILITY_HOST_CSS_OUTPUT,
      '.next/static/css/app/layout.css',
    ],
  },
  'react.production.min.js': {
    contentType: 'application/javascript; charset=utf-8',
    paths: ['node_modules/react/umd/react.production.min.js'],
  },
  'react-dom.production.min.js': {
    contentType: 'application/javascript; charset=utf-8',
    paths: ['node_modules/react-dom/umd/react-dom.production.min.js'],
  },
  'shell-runtime.browser.js': {
    contentType: 'application/javascript; charset=utf-8',
    paths: ['dev-proxy/capability-host-shell/shell-runtime.browser.js'],
  },
};

export { prepareCapabilityHostRuntimeAssets };

export function isCapabilityHostRuntimeAssetRequest(method = 'GET', requestUrl = '/') {
  if (String(method || 'GET').toUpperCase() !== 'GET') {
    return false;
  }
  try {
    const parsed = new URL(requestUrl, 'http://localhost');
    return parsed.pathname.startsWith(RUNTIME_ASSET_PREFIX)
      && Object.prototype.hasOwnProperty.call(
        RUNTIME_ASSETS,
        parsed.pathname.slice(RUNTIME_ASSET_PREFIX.length),
      );
  } catch {
    return false;
  }
}

async function resolveRuntimeAssetPath(asset) {
  if (asset.build === 'tailwind') {
    return resolveCapabilityHostStylesheetPath(asset.paths || []);
  }
  return findReadableRuntimeAssetPath(asset.paths || []);
}

function writePlainResponse(res, statusCode, body) {
  res.writeHead(statusCode, {
    'content-type': 'text/plain; charset=utf-8',
    'cache-control': 'no-store',
    'content-length': String(Buffer.byteLength(body)),
  });
  res.end(body);
  return {
    statusCode,
    bodyBytes: Buffer.byteLength(body),
  };
}

export async function writeCapabilityHostRuntimeAsset(res, requestUrl = '/') {
  let assetName = '';
  try {
    const parsed = new URL(requestUrl, 'http://localhost');
    assetName = parsed.pathname.slice(RUNTIME_ASSET_PREFIX.length);
  } catch {
    assetName = '';
  }
  const asset = RUNTIME_ASSETS[assetName];
  if (!asset) {
    return writePlainResponse(res, 404, 'Not found');
  }
  const absolutePath = await resolveRuntimeAssetPath(asset);
  if (!absolutePath) {
    return writePlainResponse(res, 503, 'Runtime asset unavailable');
  }
  try {
    const body = fs.readFileSync(absolutePath);
    res.writeHead(200, {
      'content-type': asset.contentType,
      'cache-control': 'no-store',
      'content-length': String(body.length),
    });
    res.end(body);
    return {
      statusCode: 200,
      bodyBytes: body.length,
    };
  } catch (error) {
    return writePlainResponse(res, 500, `Unable to read runtime asset: ${error?.message || 'unknown_error'}`);
  }
}
