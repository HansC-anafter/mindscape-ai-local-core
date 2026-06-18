'use client';

import React from 'react';

import { getApiBaseUrl } from '@/lib/api-url';
import type { UIComponentInfo } from '@/lib/capability-ui-loader-types';

interface CapabilityUiHostStandaloneClientProps {
  workspaceId: string;
  capabilityCode: string;
  surfacePath?: readonly string[];
}

interface CapabilityInfo {
  id?: string;
  code?: string;
  display_name?: string;
  description?: string;
}

interface CapabilityUiMetadata {
  capabilityInfo: CapabilityInfo;
  uiComponents: UIComponentInfo[];
}

const CAPABILITY_UI_METADATA_TIMEOUT_MS = 30000;

const NOOP_AOL_HOST = {
  mode: 'idle',
  selection: null,
  graphSelection: null,
  currentMeetingId: null,
  requestObjectTargeting: () => {},
  cancelObjectTargeting: () => {},
  onSelectObject: () => {},
  onSelectGraph: () => {},
  clearCurrentObject: () => {},
  openCurrentMeeting: () => {},
};

function CapabilityUiStandaloneLoadingState() {
  return (
    <div className="flex h-screen items-center justify-center bg-white dark:bg-gray-950">
      <div className="text-sm text-gray-500 dark:text-gray-400">Loading capability UI...</div>
    </div>
  );
}

function CapabilityUiStandaloneErrorState({ message }: { message: string }) {
  return (
    <div className="flex h-screen items-center justify-center bg-white p-4 dark:bg-gray-950">
      <div className="max-w-md text-center">
        <h2 className="mb-2 text-lg font-semibold text-gray-900 dark:text-gray-100">
          Capability UI failed to load
        </h2>
        <div className="text-sm text-red-500 dark:text-red-400">{message}</div>
      </div>
    </div>
  );
}

class CapabilityStandaloneErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('[CapabilityUiHostStandaloneClient] Component failed to render:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return <CapabilityUiStandaloneErrorState message="Capability component failed to render." />;
    }
    return this.props.children;
  }
}

async function fetchJsonWithTimeout<T>(url: string, timeoutMs: number): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }
    return await response.json() as T;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

async function loadCapabilityUiMetadata(
  apiUrl: string,
  capabilityCode: string,
): Promise<CapabilityUiMetadata> {
  const encodedCapabilityCode = encodeURIComponent(capabilityCode);
  const [capabilityInfo, codeUiComponents] = await Promise.all([
    fetchJsonWithTimeout<CapabilityInfo>(
      `${apiUrl}/api/v1/capability-packs/installed-capabilities/${encodedCapabilityCode}`,
      CAPABILITY_UI_METADATA_TIMEOUT_MS,
    ),
    fetchJsonWithTimeout<UIComponentInfo[]>(
      `${apiUrl}/api/v1/capability-packs/installed-capabilities/${encodedCapabilityCode}/ui-components`,
      CAPABILITY_UI_METADATA_TIMEOUT_MS,
    ),
  ]);
  const capabilityId = capabilityInfo.id || capabilityCode;
  let uiComponents = codeUiComponents;
  if ((!Array.isArray(uiComponents) || uiComponents.length === 0) && capabilityId !== capabilityCode) {
    uiComponents = await fetchJsonWithTimeout<UIComponentInfo[]>(
      `${apiUrl}/api/v1/capability-packs/installed-capabilities/${encodeURIComponent(capabilityId)}/ui-components`,
      CAPABILITY_UI_METADATA_TIMEOUT_MS,
    );
  }
  if (!Array.isArray(uiComponents) || uiComponents.length === 0) {
    throw new Error('No UI components available');
  }
  return {
    capabilityInfo,
    uiComponents,
  };
}

function isMainPageComponent(component: UIComponentInfo): boolean {
  return Boolean(
    component.code
      && (
        component.code.endsWith('Page')
        || component.code.endsWith('StudioPage')
        || component.code.endsWith('Workbench')
      ),
  );
}

function selectComponent(uiComponents: UIComponentInfo[]): UIComponentInfo | null {
  const selectedComponentCode = typeof window === 'undefined'
    ? null
    : new URLSearchParams(window.location.search).get('component');
  if (selectedComponentCode) {
    const selected = uiComponents.find((component) => component.code === selectedComponentCode);
    if (selected) {
      return selected;
    }
  }
  const mainPageComponents = uiComponents.filter(isMainPageComponent);
  return mainPageComponents[0] || uiComponents[0] || null;
}

function describeCapabilityUiError(error: unknown): string {
  if (error instanceof DOMException && error.name === 'AbortError') {
    return `Capability UI metadata request timed out after ${Math.round(CAPABILITY_UI_METADATA_TIMEOUT_MS / 1000)} seconds`;
  }
  return error instanceof Error ? error.message : 'Capability UI failed to load';
}

export default function CapabilityUiHostStandaloneClient({
  workspaceId,
  capabilityCode,
  surfacePath = [],
}: CapabilityUiHostStandaloneClientProps) {
  const apiUrl = getApiBaseUrl();
  const [Component, setComponent] = React.useState<React.ComponentType<any> | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;

    async function load() {
      setError(null);
      setComponent(null);
      const metadata = await loadCapabilityUiMetadata(apiUrl, capabilityCode);
      const componentInfo = selectComponent(metadata.uiComponents);
      if (!componentInfo) {
        throw new Error('No UI component selected');
      }
      const capabilityId = metadata.capabilityInfo.id || capabilityCode;
      const {
        loadCapabilityUIComponent,
        primeCapabilityUIComponentMetadata,
      } = await import('@/lib/capability-ui-loader');
      primeCapabilityUIComponentMetadata(capabilityId, metadata.uiComponents);
      const LoadedComponent = await loadCapabilityUIComponent(
        capabilityId,
        componentInfo.code,
        apiUrl,
      );
      if (!LoadedComponent) {
        const source = componentInfo.asset_url || componentInfo.import_path || componentInfo.path;
        throw new Error(`No React component was resolved from ${source}`);
      }
      if (!cancelled) {
        setComponent(() => LoadedComponent);
      }
    }

    void load().catch((loadError) => {
      if (!cancelled) {
        setError(describeCapabilityUiError(loadError));
      }
    });

    return () => {
      cancelled = true;
    };
  }, [apiUrl, capabilityCode]);

  if (error) {
    return <CapabilityUiStandaloneErrorState message={error} />;
  }

  if (!Component) {
    return <CapabilityUiStandaloneLoadingState />;
  }

  return (
    <div
      className="h-screen min-h-0 overflow-hidden bg-white dark:bg-gray-950"
      data-testid="capability-ui-host-standalone"
      data-active-capability-code={capabilityCode}
      data-surface-path={surfacePath.join('/')}
    >
      <CapabilityStandaloneErrorBoundary>
        <React.Suspense fallback={<CapabilityUiStandaloneLoadingState />}>
          <Component
            workspaceId={workspaceId}
            apiUrl={apiUrl}
            aolHost={NOOP_AOL_HOST}
            surfacePath={surfacePath}
          />
        </React.Suspense>
      </CapabilityStandaloneErrorBoundary>
    </div>
  );
}
