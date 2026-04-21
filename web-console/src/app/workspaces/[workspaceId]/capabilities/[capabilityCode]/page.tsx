'use client';

import React, { useState, useEffect, Suspense } from 'react';
import { useParams, usePathname, useRouter, useSearchParams } from 'next/navigation';
import { loadCapabilityUIComponent } from '@/lib/capability-ui-loader';
import { getApiBaseUrl } from '@/lib/api-url';

interface ComponentErrorBoundaryProps {
  children: React.ReactNode;
  componentName: string;
}

class ComponentErrorBoundary extends React.Component<ComponentErrorBoundaryProps, { hasError: boolean }> {
  constructor(props: ComponentErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error(`[CapabilityPage] Error in component ${this.props.componentName}:`, error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="p-4 text-sm text-red-500 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded border border-red-200 dark:border-red-800">
          <div className="font-medium mb-1">Component failed to render</div>
          <div className="text-xs text-red-400 dark:text-red-500">{this.props.componentName}</div>
        </div>
      );
    }
    return this.props.children;
  }
}

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
  version?: string;
  description?: string;
  scope?: string;
}

function isMainPageComponent(component: UIComponentInfo): boolean {
  return Boolean(component.code && (component.code.endsWith('Page') || component.code.endsWith('StudioPage')));
}

function buildComponentKey(capabilityId: string, componentCode: string): string {
  return `${capabilityId}:${componentCode}`;
}

export default function CapabilityPage() {
  const params = useParams();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceId = params?.workspaceId as string;
  const capabilityCode = params?.capabilityCode as string;

  const apiUrl = getApiBaseUrl();

  const [capabilityInfo, setCapabilityInfo] = useState<CapabilityInfo | null>(null);
  const [uiComponents, setUIComponents] = useState<UIComponentInfo[]>([]);
  const [loadedComponents, setLoadedComponents] = useState<Map<string, React.ComponentType<any>>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadCapabilityData();
  }, [capabilityCode]);

  const loadCapabilityData = async () => {
    setLoading(true);
    setError(null);

    try {
      // Fetch all installed capabilities then find the matching one
      const listResponse = await fetch(
        `${apiUrl}/api/v1/capability-packs/installed-capabilities`
      );

      if (!listResponse.ok) {
        throw new Error(`Failed to load capabilities list: ${listResponse.status}`);
      }

      const capabilitiesList = await listResponse.json();
      const capabilityData = capabilitiesList.find(
        (cap: CapabilityInfo) =>
          cap.code === capabilityCode || cap.id === capabilityCode
      );

      if (!capabilityData) {
        throw new Error(`Capability "${capabilityCode}" 未找到或未安裝`);
      }

      setCapabilityInfo(capabilityData);

      // Backend UI components API matches by id, not code
      const capabilityId = capabilityData.id || capabilityCode;

      // Load UI components info
      const componentsResponse = await fetch(
        `${apiUrl}/api/v1/capability-packs/installed-capabilities/${capabilityId}/ui-components`
      );

      if (!componentsResponse.ok) {
        console.warn(`No UI components found for ${capabilityCode}`);
        setUIComponents([]);
        setLoading(false);
        return;
      }

      const componentsData = await componentsResponse.json();
      setUIComponents(componentsData || []);

      // Prioritize main page components (components with code ending in "Page" or "StudioPage")
      // These are typically the entry points that contain the full layout
      const mainPageComponents = componentsData.filter(isMainPageComponent);
      const otherComponents = componentsData.filter((c: UIComponentInfo) => !isMainPageComponent(c));

      // Load main page components first, then others only if no main page component found
      const componentsToLoad = mainPageComponents.length > 0
        ? mainPageComponents
        : otherComponents;

      const newComponents = new Map<string, React.ComponentType<any>>();

      for (const componentInfo of componentsToLoad) {
        try {
          const Component = await loadCapabilityUIComponent(
            capabilityId,
            componentInfo.code,
            apiUrl
          );

          if (Component) {
            const key = `${capabilityId}:${componentInfo.code}`;
            newComponents.set(key, Component);
          }
        } catch (err) {
          console.warn(`Failed to load component ${componentInfo.code}:`, err);
        }
      }

      setLoadedComponents(newComponents);
    } catch (err) {
      console.error(`[CapabilityPage] Failed to load capability ${capabilityCode}:`, err);
      const errorMessage = err instanceof Error
        ? err.message
        : 'Failed to load capability';
      setError(errorMessage);
      // Set loading to false even on error to display error UI
    } finally {
      setLoading(false);
    }
  };

  const handleSelectComponent = (componentCode: string, defaultComponentCode: string) => {
    const nextParams = new URLSearchParams(searchParams?.toString() || '');
    if (componentCode === defaultComponentCode) {
      nextParams.delete('component');
    } else {
      nextParams.set('component', componentCode);
    }

    const nextUrl = nextParams.toString() ? `${pathname}?${nextParams.toString()}` : pathname;
    router.replace(nextUrl, { scroll: false });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-sm text-gray-500 dark:text-gray-400">Loading capability UI...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4">
        <div className="text-center max-w-md">
          <div className="text-4xl mb-4">⚠️</div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
            Capability 未找到
          </h2>
          <div className="text-sm text-red-500 dark:text-red-400 mb-4">{error}</div>
          <div className="text-xs text-gray-500 dark:text-gray-400 mb-4">
            Capability code: <code className="bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded">{capabilityCode}</code>
          </div>
          <div className="flex gap-2 justify-center">
            <button
              onClick={() => router.back()}
              className="px-4 py-2 text-sm bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
            >
              返回
            </button>
            <button
              onClick={() => window.close()}
              className="px-4 py-2 text-sm bg-blue-500 hover:bg-blue-600 dark:bg-blue-600 dark:hover:bg-blue-700 text-white rounded transition-colors"
            >
              關閉頁面
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (uiComponents.length === 0) {
    return (
      <div className="p-4">
        <div className="text-sm text-gray-500 dark:text-gray-400 mb-2">
          No UI components available for {capabilityInfo?.display_name || capabilityCode}
        </div>
        <button
          onClick={() => router.back()}
          className="px-3 py-1 text-xs bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600"
        >
          Go Back
        </button>
      </div>
    );
  }

  const mainPageComponents = uiComponents.filter(isMainPageComponent);
  const otherComponents = uiComponents.filter((component) => !isMainPageComponent(component));
  const selectedComponentCode = searchParams?.get('component') || null;
  const preferredMainPageComponent = selectedComponentCode
    ? mainPageComponents.find((component) => component.code === selectedComponentCode) || null
    : null;
  const resolvedMainPageComponentInfo = preferredMainPageComponent || mainPageComponents[0] || null;
  const resolvedMainPageEntry = resolvedMainPageComponentInfo
    ? (() => {
        const preferredEntry = loadedComponents.get(
          buildComponentKey(capabilityInfo?.id || capabilityCode, resolvedMainPageComponentInfo.code)
        );
        if (preferredEntry) {
          return [buildComponentKey(capabilityInfo?.id || capabilityCode, resolvedMainPageComponentInfo.code), preferredEntry] as const;
        }
        return Array.from(loadedComponents.entries()).find(([key]) => {
          const [, componentCode] = key.split(':');
          return mainPageComponents.some((component) => component.code === componentCode);
        }) || null;
      })()
    : null;

  // If main page component exists, render it fullscreen without wrapper
  if (resolvedMainPageEntry && mainPageComponents.length <= 1) {
    const [key, Component] = resolvedMainPageEntry;
    return (
      <ComponentErrorBoundary componentName={key}>
        <Suspense fallback={
          <div className="flex items-center justify-center h-full">
            <div className="text-sm text-gray-500 dark:text-gray-400">Loading component...</div>
          </div>
        }>
          <Component
            workspaceId={workspaceId}
            apiUrl={apiUrl}
          />
        </Suspense>
      </ComponentErrorBoundary>
    );
  }

  if (resolvedMainPageEntry && resolvedMainPageComponentInfo) {
    const [key, Component] = resolvedMainPageEntry;
    const [, renderedComponentCode] = key.split(':');
    const defaultComponentCode = mainPageComponents[0]?.code || resolvedMainPageComponentInfo.code;

    return (
      <div className="flex flex-col h-full overflow-hidden bg-white dark:bg-gray-950">
        <div className="flex-shrink-0 border-b dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-3">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <h1 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                {capabilityInfo?.display_name || capabilityCode}
              </h1>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                Select a workbench for this capability.
              </p>
            </div>
            <button
              onClick={() => router.back()}
              className="px-3 py-1.5 text-xs bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
            >
              Back
            </button>
          </div>
          <nav className="mt-3 flex gap-2 overflow-x-auto pb-1">
            {mainPageComponents.map((component) => {
              const isActive = component.code === renderedComponentCode;
              return (
                <button
                  key={component.code}
                  type="button"
                  data-testid={`capability-workbench-${component.code}`}
                  onClick={() => handleSelectComponent(component.code, defaultComponentCode)}
                  className={`whitespace-nowrap rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                    isActive
                      ? 'border-blue-500 bg-blue-50 text-blue-700 dark:border-blue-400 dark:bg-blue-900/30 dark:text-blue-200'
                      : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400 dark:hover:border-gray-600 dark:hover:text-gray-100'
                  }`}
                >
                  {component.description || component.code}
                </button>
              );
            })}
          </nav>
        </div>

        <div className="flex-1 overflow-auto">
          <ComponentErrorBoundary componentName={key}>
            <Suspense fallback={
              <div className="flex items-center justify-center h-full">
                <div className="text-sm text-gray-500 dark:text-gray-400">Loading component...</div>
              </div>
            }>
              <Component
                workspaceId={workspaceId}
                apiUrl={apiUrl}
              />
            </Suspense>
          </ComponentErrorBoundary>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 border-b dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {capabilityInfo?.display_name || capabilityCode}
            </h1>
            {capabilityInfo?.description && (
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                {capabilityInfo.description}
              </p>
            )}
          </div>
          <button
            onClick={() => router.back()}
            className="px-3 py-1.5 text-xs bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
          >
            Back
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {Array.from(loadedComponents.entries()).map(([key, Component]) => {
          const [, componentCode] = key.split(':');
          const componentInfo = otherComponents.find(c => c.code === componentCode);

          return (
            <div
              key={key}
              className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4"
            >
              {componentInfo && (
                <div className="mb-3 pb-3 border-b dark:border-gray-700">
                  <h2 className="text-xs font-semibold text-gray-900 dark:text-gray-100 mb-1">
                    {componentInfo.description || componentCode}
                  </h2>
                  <div className="text-[10px] text-gray-500 dark:text-gray-400">
                    Component: {componentCode}
                  </div>
                </div>
              )}
              <ComponentErrorBoundary componentName={key}>
                <Suspense fallback={
                  <div className="text-xs text-gray-500 dark:text-gray-400 p-4 text-center">
                    Loading component...
                  </div>
                }>
                  <Component
                    workspaceId={workspaceId}
                    apiUrl={apiUrl}
                  />
                </Suspense>
              </ComponentErrorBoundary>
            </div>
          );
        })}

        {loadedComponents.size === 0 && (
          <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-8">
            No components loaded. Some components may have failed to load.
          </div>
        )}
      </div>
    </div>
  );
}
