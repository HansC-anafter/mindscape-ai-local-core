import { NextRequest } from 'next/server';

import { proxyVideoRendererRequest } from '../../../../_proxy/video-renderer';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 300;

export async function POST(request: NextRequest): Promise<Response> {
  return proxyVideoRendererRequest(
    request,
    '/api/v1/capabilities/video_renderer/render-generative',
  );
}
