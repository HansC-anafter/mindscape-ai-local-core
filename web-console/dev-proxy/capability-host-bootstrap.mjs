import fs from 'node:fs';
import path from 'node:path';

const RUNTIME_ASSET_PREFIX = '/__mindscape-capability-host/';
const RUNTIME_ASSETS = {
  'react.production.min.js': 'node_modules/react/umd/react.production.min.js',
  'react-dom.production.min.js': 'node_modules/react-dom/umd/react-dom.production.min.js',
};

export function parseCapabilityHostBootstrapRoute(requestUrl = '/') {
  let parsed;
  try {
    parsed = new URL(requestUrl, 'http://localhost');
  } catch {
    return null;
  }
  const match = /^\/workspaces\/([^/]+)\/capability-ui-hosts\/([^/]+)(?:\/(.*))?$/.exec(parsed.pathname);
  if (!match) {
    return null;
  }
  return {
    workspaceId: decodeURIComponent(match[1]),
    capabilityCode: decodeURIComponent(match[2]),
    surfacePath: match[3]
      ? match[3].split('/').filter(Boolean).map((segment) => decodeURIComponent(segment))
      : [],
  };
}

export function isCapabilityHostBootstrapRequest(method = 'GET', requestUrl = '/') {
  return String(method || 'GET').toUpperCase() === 'GET'
    && Boolean(parseCapabilityHostBootstrapRoute(requestUrl));
}

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

function writeTextResponse(res, statusCode, body, headers = {}) {
  res.writeHead(statusCode, {
    'content-type': 'text/html; charset=utf-8',
    'cache-control': 'no-store',
    ...headers,
  });
  res.end(body);
}

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

export function writeCapabilityHostRuntimeAsset(res, requestUrl = '/') {
  let assetName = '';
  try {
    const parsed = new URL(requestUrl, 'http://localhost');
    assetName = parsed.pathname.slice(RUNTIME_ASSET_PREFIX.length);
  } catch {
    assetName = '';
  }
  const assetPath = RUNTIME_ASSETS[assetName];
  if (!assetPath) {
    res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' });
    res.end('Not found');
    return;
  }
  const absolutePath = path.resolve(process.cwd(), assetPath);
  try {
    const body = fs.readFileSync(absolutePath);
    res.writeHead(200, {
      'content-type': 'application/javascript; charset=utf-8',
      'cache-control': 'no-store',
      'content-length': String(body.length),
    });
    res.end(body);
  } catch (error) {
    res.writeHead(500, { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' });
    res.end(`Unable to read runtime asset: ${error?.message || 'unknown_error'}`);
  }
}

export function writeCapabilityHostBootstrap(res, requestUrl = '/') {
  const route = parseCapabilityHostBootstrapRoute(requestUrl);
  if (!route) {
    writeTextResponse(res, 404, '<!doctype html><title>Not found</title>Not found');
    return;
  }
  const title = `${route.capabilityCode} capability host`;
  const config = {
    workspaceId: route.workspaceId,
    capabilityCode: route.capabilityCode,
    surfacePath: route.surfacePath,
  };
  writeTextResponse(res, 200, `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(title)}</title>
  <style>
    html, body, #root { height: 100%; margin: 0; }
    body { background: #fff; color: #111827; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    .capability-host-status { align-items: center; display: flex; height: 100%; justify-content: center; padding: 24px; text-align: center; }
    .capability-host-status > div { color: #6b7280; font-size: 14px; line-height: 1.5; max-width: 480px; }
    .capability-host-status strong { color: #111827; display: block; font-size: 16px; margin-bottom: 8px; }
    @media (prefers-color-scheme: dark) {
      body { background: #030712; color: #f9fafb; }
      .capability-host-status > div { color: #9ca3af; }
      .capability-host-status strong { color: #f9fafb; }
    }
  </style>
</head>
<body>
  <div id="root">
    <div class="capability-host-status"><div>Loading capability UI...</div></div>
  </div>
  <script src="${RUNTIME_ASSET_PREFIX}react.production.min.js"></script>
  <script src="${RUNTIME_ASSET_PREFIX}react-dom.production.min.js"></script>
  <script type="module">
    const config = ${jsonScript(config)};
    const React = globalThis.React;
    const ReactDOM = globalThis.ReactDOM;
    globalThis.MindscapeRuntimeReact = { React, ReactDOM };
    const rootElement = document.getElementById('root');
    const root = ReactDOM.createRoot(rootElement);
    const noopHost = {
      mode: 'idle',
      selection: null,
      graphSelection: null,
      currentMeetingId: null,
      requestObjectTargeting: () => {},
      cancelObjectTargeting: () => {},
      onSelectObject: () => {},
      onSelectGraph: () => {},
      clearCurrentObject: () => {},
      openCurrentMeeting: () => {},
    };

    function renderStatus(message, title = '') {
      rootElement.innerHTML = '<div class="capability-host-status"><div>' +
        (title ? '<strong>' + escapeHtml(title) + '</strong>' : '') +
        escapeHtml(message) +
        '</div></div>';
    }

    function escapeHtml(value) {
      return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }

    async function fetchJson(url) {
      const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok) {
        throw new Error('Request failed: ' + response.status + ' ' + url);
      }
      return response.json();
    }

    function isMainPageComponent(component) {
      return Boolean(
        component?.code &&
        (component.code.endsWith('Page') || component.code.endsWith('StudioPage') || component.code.endsWith('Workbench'))
      );
    }

    function selectComponent(components) {
      const requested = new URLSearchParams(window.location.search).get('component');
      if (requested) {
        const selected = components.find((component) => component.code === requested);
        if (selected) return selected;
      }
      return components.filter(isMainPageComponent)[0] || components[0] || null;
    }

    async function load() {
      const encodedCapabilityCode = encodeURIComponent(config.capabilityCode);
      const capabilityInfo = await fetchJson('/api/v1/capability-packs/installed-capabilities/' + encodedCapabilityCode);
      const capabilityId = capabilityInfo.id || config.capabilityCode;
      let components = await fetchJson('/api/v1/capability-packs/installed-capabilities/' + encodedCapabilityCode + '/ui-components');
      if ((!Array.isArray(components) || components.length === 0) && capabilityId !== config.capabilityCode) {
        components = await fetchJson('/api/v1/capability-packs/installed-capabilities/' + encodeURIComponent(capabilityId) + '/ui-components');
      }
      if (!Array.isArray(components) || components.length === 0) {
        throw new Error('No UI components available');
      }
      const componentInfo = selectComponent(components);
      if (!componentInfo?.asset_url) {
        throw new Error('Selected component does not expose a runtime asset');
      }
      renderStatus('Loading ' + componentInfo.code + '...');
      const componentModule = await import(componentInfo.asset_url);
      const Component = componentModule[componentInfo.export || 'default'] || componentModule.default;
      if (!Component) {
        throw new Error('Runtime asset did not export a React component');
      }
      root.render(React.createElement(Component, {
        workspaceId: config.workspaceId,
        apiUrl: window.location.origin,
        aolHost: noopHost,
        surfacePath: config.surfacePath,
      }));
    }

    load().catch((error) => {
      console.error('[capability-host-bootstrap] failed', error);
      renderStatus(error?.message || 'Capability UI failed to load', 'Capability UI failed to load');
    });
  </script>
</body>
</html>`);
}
