import { NextRequest } from 'next/server';

const _HOP_BY_HOP_HEADERS = new Set([
  'connection',
  'content-length',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
]);

function _backendBaseUrl(): string {
  return (
    process.env.BACKEND_URL ||
    process.env.NEXT_PUBLIC_BACKEND_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    'http://localhost:8200'
  );
}

function _forwardHeaders(request: NextRequest): Headers {
  const headers = new Headers(request.headers);
  for (const headerName of Array.from(_HOP_BY_HOP_HEADERS)) {
    headers.delete(headerName);
  }
  return headers;
}

function _responseHeaders(headers: Headers): Headers {
  const forwarded = new Headers(headers);
  for (const headerName of Array.from(_HOP_BY_HOP_HEADERS)) {
    forwarded.delete(headerName);
  }
  return forwarded;
}

export async function proxyVideoRendererRequest(
  request: NextRequest,
  backendPath: string,
): Promise<Response> {
  const upstreamUrl = new URL(backendPath, _backendBaseUrl());
  const requestBody =
    request.method === 'GET' || request.method === 'HEAD'
      ? undefined
      : Buffer.from(await request.arrayBuffer());

  try {
    const upstream = await fetch(upstreamUrl, {
      method: request.method,
      headers: _forwardHeaders(request),
      body: requestBody,
      redirect: 'manual',
      cache: 'no-store',
    });

    const responseBody = request.method === 'HEAD' ? null : await upstream.arrayBuffer();
    return new Response(responseBody, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: _responseHeaders(upstream.headers),
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    return Response.json(
      {
        error: 'video_renderer_proxy_error',
        detail,
        backend_url: upstreamUrl.toString(),
      },
      { status: 502 },
    );
  }
}
