import { RUNTIME_ASSET_PREFIX } from './runtime-asset-server.mjs';
import { createCapabilityHostConfig } from './shell-contract.mjs';

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function jsonScript(value) {
  return JSON.stringify(value).replaceAll('<', '\\u003c');
}

export function renderCapabilityHostDocument(route) {
  const title = `${route.capabilityCode} capability host`;
  const config = createCapabilityHostConfig(route);
  const scope = new URLSearchParams({
    workspace_id: route.workspaceId,
    capability_code: route.capabilityCode,
  }).toString();
  const runtimeAsset = (name) => `${RUNTIME_ASSET_PREFIX}${name}?${scope}`;
  return `<!doctype html>
<html lang="en" class="theme-warm">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(title)}</title>
  <link rel="stylesheet" href="${runtimeAsset('app-layout.css')}" />
  <style>
    html, body, #root { height: 100%; margin: 0; }
    body { background: var(--color-surface, #fff); color: var(--color-text-primary, #111827); font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .capability-host-status { align-items: center; display: flex; height: 100%; justify-content: center; padding: 24px; text-align: center; }
    .capability-host-status > div { color: var(--color-text-secondary, #6b7280); font-size: 14px; line-height: 1.5; max-width: 480px; }
    .capability-host-status strong { color: var(--color-text-primary, #111827); display: block; font-size: 16px; margin-bottom: 8px; }
  </style>
</head>
<body>
  <div id="root">
    <div class="capability-host-status"><div>Loading capability UI...</div></div>
  </div>
  <script id="mindscape-capability-host-config" type="application/json">${jsonScript(config)}</script>
  <script src="${runtimeAsset('react.production.min.js')}"></script>
  <script src="${runtimeAsset('react-dom.production.min.js')}"></script>
  <script type="module" src="${runtimeAsset('shell-runtime.browser.js')}"></script>
</body>
</html>`;
}
