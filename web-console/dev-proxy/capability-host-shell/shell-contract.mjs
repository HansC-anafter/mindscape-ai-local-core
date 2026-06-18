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

export function createCapabilityHostConfig(route) {
  return {
    workspaceId: route.workspaceId,
    capabilityCode: route.capabilityCode,
    surfacePath: route.surfacePath,
  };
}
