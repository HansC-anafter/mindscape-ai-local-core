import { redirectToCapabilityWorkbenchOrRenderFallback } from '../../capabilityWorkbenchRedirect';

interface CapabilityUiLoadedPageProps {
  params: {
    workspaceId: string;
    capabilityCode: string;
  };
  searchParams?: Record<string, string | string[] | undefined>;
}

export default async function CapabilityUiLoadedPage({
  params,
  searchParams,
}: CapabilityUiLoadedPageProps) {
  return redirectToCapabilityWorkbenchOrRenderFallback({
    workspaceId: params.workspaceId,
    capabilityCode: params.capabilityCode,
    searchParams,
  });
}
