import { redirectToCapabilityWorkbenchOrRenderFallback } from '../capabilityWorkbenchRedirect';

interface CapabilityUiPageProps {
  params: {
    workspaceId: string;
    capabilityCode: string;
  };
  searchParams?: Record<string, string | string[] | undefined>;
}

export default async function CapabilityUiPage({
  params,
  searchParams,
}: CapabilityUiPageProps) {
  return redirectToCapabilityWorkbenchOrRenderFallback({
    workspaceId: params.workspaceId,
    capabilityCode: params.capabilityCode,
    searchParams,
  });
}
