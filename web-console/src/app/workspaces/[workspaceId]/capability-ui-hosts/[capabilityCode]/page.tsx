import { redirect } from 'next/navigation';

interface CapabilityUiHostPageProps {
  params: {
    workspaceId: string;
    capabilityCode: string;
  };
  searchParams?: Record<string, string | string[] | undefined>;
}

function encodeSearchParams(searchParams?: Record<string, string | string[] | undefined>): string {
  if (!searchParams) {
    return '';
  }

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    if (Array.isArray(value)) {
      for (const item of value) {
        params.append(key, item);
      }
    } else if (typeof value === 'string') {
      params.set(key, value);
    }
  }

  const encoded = params.toString();
  return encoded ? `?${encoded}` : '';
}

export default function CapabilityUiHostPage({
  params,
  searchParams,
}: CapabilityUiHostPageProps) {
  if (params.capabilityCode === 'ig') {
    redirect(
      `/capability-ui-hosts/ig/${encodeURIComponent(params.workspaceId)}${encodeSearchParams(searchParams)}`,
    );
  }

  redirect(
    `/workspaces/${encodeURIComponent(params.workspaceId)}/capabilities/${encodeURIComponent(params.capabilityCode)}/ui/generic${encodeSearchParams(searchParams)}`,
  );
}
