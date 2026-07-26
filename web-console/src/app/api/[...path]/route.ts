import {
  proxyToUpstream,
  resolveApiProxyUpstream,
} from '@/lib/server-api-proxy';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function isRemoteProfilePreferencesRequest(request: Request): boolean {
  if (
    request.headers.get('x-mindscape-remote-ingress') !== 'remote_workbench'
  ) {
    return false;
  }
  const pathname = new URL(request.url).pathname;
  return (
    pathname === '/api/v1/mindscape/profiles/me/preferences'
    || pathname === '/api/v1/mindscape/profiles/me/preferences/ui-language'
  );
}

function proxy(request: Request): Promise<Response> {
  if (isRemoteProfilePreferencesRequest(request)) {
    return Promise.resolve(Response.json(
      { error: 'remote_profile_preferences_forbidden' },
      { status: 403, headers: { 'Cache-Control': 'no-store' } },
    ));
  }
  return proxyToUpstream(
    request,
    resolveApiProxyUpstream(request.url, request.method)
  );
}

export const GET = proxy;
export const HEAD = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
