const metadataCache = globalThis.__mindscapeCapabilityHostMetadataCache instanceof Map
  ? globalThis.__mindscapeCapabilityHostMetadataCache
  : new Map();
globalThis.__mindscapeCapabilityHostMetadataCache = metadataCache;

function readConfig() {
  const element = document.getElementById('mindscape-capability-host-config');
  if (!element?.textContent) {
    throw new Error('Capability host config is missing');
  }
  return JSON.parse(element.textContent);
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function renderStatus(rootElement, message, title = '') {
  if (!rootElement) {
    return;
  }
  rootElement.innerHTML = '<div class="capability-host-status"><div>' +
    (title ? '<strong>' + escapeHtml(title) + '</strong>' : '') +
    escapeHtml(message) +
    '</div></div>';
}

async function fetchJson(url, cacheKey = '') {
  if (cacheKey && metadataCache.has(cacheKey)) {
    return metadataCache.get(cacheKey);
  }
  const promise = fetch(url, { credentials: 'same-origin', cache: 'no-store' })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`Request failed: ${response.status} ${url}`);
      }
      return response.json();
    })
    .catch((error) => {
      if (cacheKey) {
        metadataCache.delete(cacheKey);
      }
      throw error;
    });
  if (cacheKey) {
    metadataCache.set(cacheKey, promise);
  }
  return promise;
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
    if (selected) {
      return selected;
    }
  }
  return components.filter(isMainPageComponent)[0] || components[0] || null;
}

function createNoopHost() {
  return {
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
}

async function loadCapabilityComponents(config) {
  const encodedCapabilityCode = encodeURIComponent(config.capabilityCode);
  const capabilityInfo = await fetchJson(
    `/api/v1/capability-packs/installed-capabilities/${encodedCapabilityCode}`,
    `capability:${config.capabilityCode}`,
  );
  const capabilityId = capabilityInfo.id || config.capabilityCode;
  let components = await fetchJson(
    `/api/v1/capability-packs/installed-capabilities/${encodedCapabilityCode}/ui-components`,
    `components:${config.capabilityCode}`,
  );
  if ((!Array.isArray(components) || components.length === 0) && capabilityId !== config.capabilityCode) {
    components = await fetchJson(
      `/api/v1/capability-packs/installed-capabilities/${encodeURIComponent(capabilityId)}/ui-components`,
      `components:${capabilityId}`,
    );
  }
  if (!Array.isArray(components) || components.length === 0) {
    throw new Error('No UI components available');
  }
  return components;
}

async function load() {
  const config = readConfig();
  const React = globalThis.React;
  const ReactDOM = globalThis.ReactDOM;
  if (!React || !ReactDOM?.createRoot) {
    throw new Error('React runtime is unavailable');
  }
  globalThis.MindscapeRuntimeReact = { React, ReactDOM };
  const rootElement = document.getElementById('root');
  if (!rootElement) {
    throw new Error('Capability host root is missing');
  }
  const root = ReactDOM.createRoot(rootElement);
  const components = await loadCapabilityComponents(config);
  const componentInfo = selectComponent(components);
  if (!componentInfo?.asset_url) {
    throw new Error('Selected component does not expose a runtime asset');
  }
  renderStatus(rootElement, `Loading ${componentInfo.code}...`);
  const componentModule = await import(componentInfo.asset_url);
  const Component = componentModule[componentInfo.export || 'default'] || componentModule.default;
  if (!Component) {
    throw new Error('Runtime asset did not export a React component');
  }
  root.render(React.createElement(Component, {
    workspaceId: config.workspaceId,
    apiUrl: window.location.origin,
    aolHost: createNoopHost(),
    surfacePath: config.surfacePath,
  }));
}

load().catch((error) => {
  const rootElement = document.getElementById('root');
  console.error('[capability-host-shell] failed', error);
  renderStatus(rootElement, error?.message || 'Capability UI failed to load', 'Capability UI failed to load');
});
