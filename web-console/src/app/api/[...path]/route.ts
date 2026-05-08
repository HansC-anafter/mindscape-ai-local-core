import {
  proxyToUpstream,
  resolveApiProxyUpstream,
} from '@/lib/server-api-proxy';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

function proxy(request: Request): Promise<Response> {
  return proxyToUpstream(request, resolveApiProxyUpstream(request.url));
}

export const GET = proxy;
export const HEAD = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
