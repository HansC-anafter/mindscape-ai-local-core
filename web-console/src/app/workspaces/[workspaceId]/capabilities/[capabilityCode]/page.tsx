'use client';

import React, { useState, useEffect, Suspense } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { loadCapabilityUIComponent } from '@/lib/capability-ui-loader';

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

export default function CapabilityPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = params?.workspaceId as string;
  const capabilityCode = params?.capabilityCode as string;

  // 从环境变量或配置获取 API URL
  const apiUrl = typeof window !== 'undefined'
    ? window.location.origin.replace(/:\d+$/, ':8200')
    : 'http://localhost:8200';

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
      // 先从列表 API 获取所有 installed capabilities，然后查找匹配的
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

      // 后端 UI components API 使用 id 来匹配，所以使用 id 而不是 code
      const capabilityId = capabilityData.id || capabilityCode;

      // 加载 UI components 信息
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
      const mainPageComponents = componentsData.filter((c: UIComponentInfo) =>
        c.code && (c.code.endsWith('Page') || c.code.endsWith('StudioPage'))
      );
      const otherComponents = componentsData.filter((c: UIComponentInfo) =>
        c.code && !c.code.endsWith('Page') && !c.code.endsWith('StudioPage')
      );

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
      // 即使 capability 不存在，也设置 loading 为 false 以显示错误信息
    } finally {
      setLoading(false);
    }
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

  const mainPageComponent = Array.from(loadedComponents.entries()).find(([key]) => {
    const [, componentCode] = key.split(':');
    return componentCode.endsWith('Page') || componentCode.endsWith('StudioPage');
  });

  // If main page component exists, render it fullscreen without wrapper
  if (mainPageComponent) {
    const [key, Component] = mainPageComponent;
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
          const componentInfo = uiComponents.find(c => c.code === componentCode);

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
