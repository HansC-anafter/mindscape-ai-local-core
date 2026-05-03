'use client';

import React, { useEffect, useState, Suspense } from 'react';
import { useParams, usePathname, useRouter, useSearchParams } from 'next/navigation';
import { loadCapabilityUIComponent } from '@/lib/capability-ui-loader';
import { getApiBaseUrl } from '@/lib/api-url';
import {
  AOLRuntimeShell,
  buildCapabilitySurfaceId,
} from '@/components/capabilities/aol-runtime-shell';

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
        <div className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-500 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
          <div className="mb-1 font-medium">Component failed to render</div>
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

function shouldWrapScrollableMainPage(
  capabilityCode: string,
  componentCode: string | null | undefined,
): boolean {
  return (
    capabilityCode === 'blender_bridge' ||
    capabilityCode === 'performance_direction' ||
    componentCode === 'BlenderBridgeWorkbenchPage' ||
    componentCode === 'PerformanceDirectionStoryboardEditorPage'
  );
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
    void loadCapabilityData();
  }, [capabilityCode]);

  const loadCapabilityData = async () => {
    setLoading(true);
    setError(null);

    try {
      const listResponse = await fetch(`${apiUrl}/api/v1/capability-packs/installed-capabilities`);

      if (!listResponse.ok) {
        throw new Error(`Failed to load capabilities list: ${listResponse.status}`);
      }

      const capabilitiesList = await listResponse.json();
      const capabilityData = capabilitiesList.find(
        (cap: CapabilityInfo) => cap.code === capabilityCode || cap.id === capabilityCode,
      );

      if (!capabilityData) {
        throw new Error(`Capability "${capabilityCode}" 未找到或未安裝`);
      }

      setCapabilityInfo(capabilityData);

      const capabilityId = capabilityData.id || capabilityCode;
      const componentsResponse = await fetch(
        `${apiUrl}/api/v1/capability-packs/installed-capabilities/${capabilityId}/ui-components`,
      );

      if (!componentsResponse.ok) {
        console.warn(`No UI components found for ${capabilityCode}`);
        setUIComponents([]);
        setLoading(false);
        return;
      }

      const componentsData = await componentsResponse.json();
      setUIComponents(componentsData || []);

      const mainPageComponents = componentsData.filter(isMainPageComponent);
      const otherComponents = componentsData.filter((component: UIComponentInfo) => !isMainPageComponent(component));
      const componentsToLoad = mainPageComponents.length > 0 ? mainPageComponents : otherComponents;
      const nextLoadedComponents = new Map<string, React.ComponentType<any>>();

      for (const componentInfo of componentsToLoad) {
        try {
          const Component = await loadCapabilityUIComponent(
            capabilityId,
            componentInfo.code,
            apiUrl,
          );

          if (Component) {
            nextLoadedComponents.set(buildComponentKey(capabilityId, componentInfo.code), Component);
          }
        } catch (componentLoadError) {
          console.warn(`Failed to load component ${componentInfo.code}:`, componentLoadError);
        }
      }

      setLoadedComponents(nextLoadedComponents);
    } catch (loadError) {
      console.error(`[CapabilityPage] Failed to load capability ${capabilityCode}:`, loadError);
      setError(loadError instanceof Error ? loadError.message : 'Failed to load capability');
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

  const renderLoadedComponent = (
    key: string,
    Component: React.ComponentType<any>,
    componentCode: string,
    aolHost: any,
    compactFallback = false,
  ) => (
    <ComponentErrorBoundary componentName={key}>
      <Suspense fallback={
        compactFallback ? (
          <div className="p-4 text-center text-xs text-gray-500 dark:text-gray-400">
            Loading component...
          </div>
        ) : (
          <div className="flex h-full items-center justify-center">
            <div className="text-sm text-gray-500 dark:text-gray-400">Loading component...</div>
          </div>
        )
      }>
        <Component
          workspaceId={workspaceId}
          apiUrl={apiUrl}
          aolHost={aolHost}
        />
      </Suspense>
    </ComponentErrorBoundary>
  );

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-sm text-gray-500 dark:text-gray-400">Loading capability UI...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center p-4">
        <div className="max-w-md text-center">
          <div className="mb-4 text-4xl">⚠️</div>
          <h2 className="mb-2 text-lg font-semibold text-gray-900 dark:text-gray-100">Capability 未找到</h2>
          <div className="mb-4 text-sm text-red-500 dark:text-red-400">{error}</div>
          <div className="mb-4 text-xs text-gray-500 dark:text-gray-400">
            Capability code: <code className="rounded bg-gray-100 px-2 py-1 dark:bg-gray-800">{capabilityCode}</code>
          </div>
          <div className="flex justify-center gap-2">
            <button
              onClick={() => router.back()}
              className="rounded bg-gray-200 px-4 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
            >
              返回
            </button>
            <button
              onClick={() => window.close()}
              className="rounded bg-blue-500 px-4 py-2 text-sm text-white transition-colors hover:bg-blue-600 dark:bg-blue-600 dark:hover:bg-blue-700"
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
        <div className="mb-2 text-sm text-gray-500 dark:text-gray-400">
          No UI components available for {capabilityInfo?.display_name || capabilityCode}
        </div>
        <button
          onClick={() => router.back()}
          className="rounded bg-gray-200 px-3 py-1 text-xs text-gray-700 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
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
          buildComponentKey(capabilityInfo?.id || capabilityCode, resolvedMainPageComponentInfo.code),
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

  if (resolvedMainPageEntry && mainPageComponents.length <= 1) {
    const [key, Component] = resolvedMainPageEntry;
    const componentCode = mainPageComponents[0]?.code || key.split(':')[1] || key;
    const shouldUseScrollableShell = shouldWrapScrollableMainPage(capabilityCode, componentCode);

    return (
      <AOLRuntimeShell
        apiUrl={apiUrl}
        workspaceId={workspaceId}
        capabilityCode={capabilityCode}
        route={pathname}
        surfaceId={buildCapabilitySurfaceId(capabilityCode, componentCode)}
      >
        {(aolHost) => (
          <div
            className={shouldUseScrollableShell ? 'relative h-full overflow-y-auto overflow-x-hidden bg-white dark:bg-gray-950' : 'relative h-full'}
            data-testid={shouldUseScrollableShell ? 'capability-mainpage-scroll-shell' : undefined}
          >
            {renderLoadedComponent(key, Component, componentCode, aolHost)}
          </div>
        )}
      </AOLRuntimeShell>
    );
  }

  if (resolvedMainPageEntry && resolvedMainPageComponentInfo) {
    const [key, Component] = resolvedMainPageEntry;
    const [, renderedComponentCode] = key.split(':');
    const defaultComponentCode = mainPageComponents[0]?.code || resolvedMainPageComponentInfo.code;

    return (
      <AOLRuntimeShell
        apiUrl={apiUrl}
        workspaceId={workspaceId}
        capabilityCode={capabilityCode}
        route={pathname}
        surfaceId={buildCapabilitySurfaceId(capabilityCode, renderedComponentCode)}
      >
        {(aolHost) => (
          <div className="flex h-full flex-col overflow-hidden bg-white dark:bg-gray-950">
            <div className="flex-shrink-0 border-b bg-white px-4 py-3 dark:border-gray-700 dark:bg-gray-900">
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
                  className="rounded bg-gray-200 px-3 py-1.5 text-xs text-gray-700 transition-colors hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
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
              {renderLoadedComponent(key, Component, renderedComponentCode, aolHost)}
            </div>
          </div>
        )}
      </AOLRuntimeShell>
    );
  }

  return (
    <AOLRuntimeShell
      apiUrl={apiUrl}
      workspaceId={workspaceId}
      capabilityCode={capabilityCode}
      route={pathname}
      surfaceId={buildCapabilitySurfaceId(capabilityCode, 'fallback_component_gallery')}
    >
      {(aolHost) => (
        <div className="relative flex h-full flex-col overflow-hidden">
          <div className="flex-shrink-0 border-b bg-white px-4 py-3 dark:border-gray-700 dark:bg-gray-900">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                  {capabilityInfo?.display_name || capabilityCode}
                </h1>
                {capabilityInfo?.description ? (
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{capabilityInfo.description}</p>
                ) : null}
              </div>
              <button
                onClick={() => router.back()}
                className="rounded bg-gray-200 px-3 py-1.5 text-xs text-gray-700 transition-colors hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
              >
                Back
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto space-y-4 p-4">
            {Array.from(loadedComponents.entries()).map(([key, Component]) => {
              const [, componentCode] = key.split(':');
              const componentInfo = otherComponents.find((component) => component.code === componentCode);

              return (
                <div
                  key={key}
                  className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800"
                >
                  {componentInfo ? (
                    <div className="mb-3 border-b pb-3 dark:border-gray-700">
                      <h2 className="mb-1 text-xs font-semibold text-gray-900 dark:text-gray-100">
                        {componentInfo.description || componentCode}
                      </h2>
                      <div className="text-[10px] text-gray-500 dark:text-gray-400">
                        Component: {componentCode}
                      </div>
                    </div>
                  ) : null}
                  {renderLoadedComponent(key, Component, componentCode, aolHost, true)}
                </div>
              );
            })}

            {loadedComponents.size === 0 ? (
              <div className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">
                No components loaded. Some components may have failed to load.
              </div>
            ) : null}
          </div>
        </div>
      )}
    </AOLRuntimeShell>
  );
}
