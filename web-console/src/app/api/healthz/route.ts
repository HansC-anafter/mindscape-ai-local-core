export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export async function GET(): Promise<Response> {
  return Response.json(
    {
      status: 'ok',
      service: 'web-console',
      liveness: true,
    },
    {
      headers: {
        'Cache-Control': 'no-store',
      },
    }
  );
}
