import { GET as getFrontendLiveness } from '../api/healthz/route';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

export const GET = getFrontendLiveness;
