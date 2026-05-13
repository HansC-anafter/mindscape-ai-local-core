import { redirectToCapabilityWorkbenchOrRenderFallback } from '../../capabilityWorkbenchRedirect';

interface CapabilityUiGenericPageProps {
  params: {
    workspaceId: string;
    capabilityCode: string;
  };
  searchParams?: Record<string, string | string[] | undefined>;
}

export default async function CapabilityUiGenericPage({
  params,
  searchParams,
}: CapabilityUiGenericPageProps) {
  return redirectToCapabilityWorkbenchOrRenderFallback({
    workspaceId: params.workspaceId,
    capabilityCode: params.capabilityCode,
    searchParams,
  });
}
