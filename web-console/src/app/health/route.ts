import {
  proxyToUpstream,
  resolveBackendPathProxyUpstream,
} from '@/lib/server-api-proxy';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export function GET(request: Request): Promise<Response> {
  return proxyToUpstream(request, resolveBackendPathProxyUpstream(request.url, '/health'));
}
