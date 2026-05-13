import { redirectToCapabilityWorkbenchOrRenderFallback } from './capabilityWorkbenchRedirect';

interface CapabilityPageProps {
  params: {
    workspaceId: string;
    capabilityCode: string;
  };
  searchParams?: Record<string, string | string[] | undefined>;
}

export default async function CapabilityPage({
  params,
  searchParams,
}: CapabilityPageProps) {
  return redirectToCapabilityWorkbenchOrRenderFallback({
    workspaceId: params.workspaceId,
    capabilityCode: params.capabilityCode,
    searchParams,
  });
}
