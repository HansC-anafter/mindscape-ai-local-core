import { renderCapabilityHostDocument } from './host-document.mjs';
import {
  isCapabilityHostRuntimeAssetRequest,
  prepareCapabilityHostRuntimeAssets,
  writeCapabilityHostRuntimeAsset,
} from './runtime-asset-server.mjs';
import {
  isCapabilityHostBootstrapRequest,
  parseCapabilityHostBootstrapRoute,
} from './shell-contract.mjs';

export {
  isCapabilityHostBootstrapRequest,
  isCapabilityHostRuntimeAssetRequest,
  parseCapabilityHostBootstrapRoute,
  prepareCapabilityHostRuntimeAssets,
  writeCapabilityHostRuntimeAsset,
};

function writeTextResponse(res, statusCode, body, headers = {}) {
  const bodyBytes = Buffer.byteLength(body);
  res.writeHead(statusCode, {
    'content-type': 'text/html; charset=utf-8',
    'cache-control': 'no-store',
    'content-length': String(bodyBytes),
    ...headers,
  });
  res.end(body);
  return {
    statusCode,
    bodyBytes,
  };
}

export function writeCapabilityHostBootstrap(res, requestUrl = '/') {
  const route = parseCapabilityHostBootstrapRoute(requestUrl);
  if (!route) {
    return writeTextResponse(res, 404, '<!doctype html><title>Not found</title>Not found');
  }
  return writeTextResponse(res, 200, renderCapabilityHostDocument(route));
}
