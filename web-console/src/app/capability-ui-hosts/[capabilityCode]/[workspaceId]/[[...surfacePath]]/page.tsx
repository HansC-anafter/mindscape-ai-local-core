import { redirect } from 'next/navigation';
import { buildCapabilityWorkbenchPath } from '@/lib/capability-static-hosts';

interface LegacyCapabilityUiHostRedirectPageProps {
  params: {
    capabilityCode: string;
    workspaceId: string;
    surfacePath?: string[];
  };
  searchParams?: Record<string, string | string[] | undefined>;
}

export default function LegacyCapabilityUiHostRedirectPage({
  params,
  searchParams,
}: LegacyCapabilityUiHostRedirectPageProps) {
  redirect(
    buildCapabilityWorkbenchPath(params.workspaceId, params.capabilityCode, {
      surfacePath: params.surfacePath || [],
      searchParams,
    }),
  );
}
