import { redirect } from 'next/navigation';
import { buildCapabilityWorkbenchPath } from '@/lib/capability-static-hosts';

interface UIComponentInfo {
  code: string;
  path: string;
  description: string;
  export: string;
  artifact_types: string[];
  playbook_codes: string[];
  import_path: string;
}

interface CapabilityInfo {
  id?: string;
  code?: string;
  display_name?: string;
}

interface RedirectOptions {
  workspaceId: string;
  capabilityCode: string;
  searchParams?: Record<string, string | string[] | undefined>;
}

const DEFAULT_BACKEND_URL = 'http://backend:8200';

function normalizeBaseUrl(value: string | undefined, fallback: string): string {
  const resolved = value?.trim() || fallback;
  return resolved.replace(/\/+$/, '');
}

function getServerBackendBaseUrl(): string {
  return normalizeBaseUrl(
    process.env.WEB_CONSOLE_BACKEND_URL ||
      process.env.BACKEND_URL ||
      process.env.NEXT_PUBLIC_BACKEND_URL,
    DEFAULT_BACKEND_URL,
  );
}

async function fetchBackendJson<T>(path: string): Promise<{ ok: boolean; status: number; data: T | null }> {
  const response = await fetch(`${getServerBackendBaseUrl()}${path}`, {
    cache: 'no-store',
  });

  if (!response.ok) {
    return { ok: false, status: response.status, data: null };
  }

  return {
    ok: true,
    status: response.status,
    data: await response.json() as T,
  };
}

export async function redirectToCapabilityWorkbenchOrRenderFallback({
  workspaceId,
  capabilityCode,
  searchParams,
}: RedirectOptions) {
  const encodedCapabilityCode = encodeURIComponent(capabilityCode);
  const capabilityResponse = await fetchBackendJson<CapabilityInfo>(
    `/api/v1/capability-packs/installed-capabilities/${encodedCapabilityCode}`,
  );

  if (!capabilityResponse.ok || !capabilityResponse.data) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-4">
        <div className="max-w-md text-center">
          <h2 className="mb-2 text-lg font-semibold text-gray-900 dark:text-gray-100">
            Capability not found
          </h2>
          <div className="mb-4 text-sm text-red-500 dark:text-red-400">
            Failed to load capability metadata: {capabilityResponse.status}
          </div>
          <div className="mb-4 text-xs text-gray-500 dark:text-gray-400">
            Capability code: <code className="rounded bg-gray-100 px-2 py-1 dark:bg-gray-800">{capabilityCode}</code>
          </div>
          <a
            href={`/workspaces/${workspaceId}`}
            className="inline-flex rounded bg-gray-200 px-4 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
          >
            Go back
          </a>
        </div>
      </div>
    );
  }

  const capabilityInfo = capabilityResponse.data;
  const apiCapabilityCode = capabilityInfo.code || capabilityInfo.id || capabilityCode;
  const componentsResponse = await fetchBackendJson<UIComponentInfo[]>(
    `/api/v1/capability-packs/installed-capabilities/${encodeURIComponent(apiCapabilityCode)}/ui-components`,
  );
  const uiComponents = Array.isArray(componentsResponse.data) ? componentsResponse.data : [];

  if (componentsResponse.ok && uiComponents.length > 0) {
    redirect(
      buildCapabilityWorkbenchPath(workspaceId, apiCapabilityCode, {
        searchParams,
      }),
    );
  }

  return (
    <div className="p-4">
      <div className="mb-2 text-sm text-gray-500 dark:text-gray-400">
        No UI components available for {capabilityInfo.display_name || apiCapabilityCode}
      </div>
      <a
        href={`/workspaces/${workspaceId}`}
        className="inline-flex rounded bg-gray-200 px-3 py-1 text-xs text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
      >
        Go Back
      </a>
    </div>
  );
}
