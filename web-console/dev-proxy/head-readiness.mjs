export function isFrontendDocumentHeadReadinessRequest(method = 'GET', requestUrl = '/') {
  if (String(method || 'GET').toUpperCase() !== 'HEAD') {
    return false;
  }
  try {
    const parsed = new URL(requestUrl, 'http://localhost');
    if (parsed.pathname.startsWith('/api/')) {
      return false;
    }
    if (parsed.pathname === '/') {
      return true;
    }
    return (
      parsed.pathname.startsWith('/workspaces/') ||
      parsed.pathname.startsWith('/device-link/')
    );
  } catch {
    return requestUrl === '/';
  }
}

export function writeFrontendDocumentHeadReadiness(res, nextRunning) {
  res.writeHead(nextRunning ? 200 : 503, {
    'cache-control': 'no-store',
    'content-length': '0',
    'x-mindscape-frontend-readiness': nextRunning ? 'ready' : 'next_dev_unavailable',
  });
  res.end();
}
