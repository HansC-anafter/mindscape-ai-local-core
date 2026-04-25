'use client';

import React, { useCallback, useEffect, useState, Suspense } from 'react';
import { useParams, usePathname, useRouter, useSearchParams } from 'next/navigation';
import { loadCapabilityUIComponent } from '@/lib/capability-ui-loader';
import { getApiBaseUrl } from '@/lib/api-url';
import {
  attachAddressableObjectToMeeting,
  resolveAddressableSelection,
  type AddressableObjectHostBridge,
  type AddressableObjectRole,
  type AddressableRuntimeError,
  type AddressableSelectionTarget,
  type ObjectMeetingAttachResponse,
  type ResolvedAddressableObject,
} from '@/lib/addressable-object-layer';

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

type AOLPanelPhase = 'idle' | 'resolving' | 'ready' | 'attaching';

interface AOLPanelState {
  phase: AOLPanelPhase;
  selection: AddressableSelectionTarget | null;
  resolvedObject: ResolvedAddressableObject | null;
  warnings: AddressableRuntimeError[];
  attachResponse: ObjectMeetingAttachResponse | null;
  error: string | null;
}

function isMainPageComponent(component: UIComponentInfo): boolean {
  return Boolean(component.code && (component.code.endsWith('Page') || component.code.endsWith('StudioPage')));
}

function buildComponentKey(capabilityId: string, componentCode: string): string {
  return `${capabilityId}:${componentCode}`;
}

function buildComponentSurfaceId(capabilityCode: string, componentCode: string): string {
  return `capability_page:${capabilityCode}:${componentCode}`;
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

function AddressableObjectPanel({
  state,
  onDismiss,
  onAttach,
}: {
  state: AOLPanelState;
  onDismiss: () => void;
  onAttach: () => void;
}) {
  if (state.phase === 'idle') {
    return null;
  }

  const summary = state.resolvedObject?.summary ?? null;
  const actions = state.resolvedObject?.actions ?? [];
  const attachAction = actions.find((action) => action.action_code === 'attach_to_meeting') ?? null;
  const ownerSurfaceAction = actions.find((action) => action.action_code === 'open_owner_surface') ?? null;
  const warnings = [
    ...state.warnings,
    ...(state.attachResponse?.errors || []),
  ];

  return (
    <div
      className="fixed bottom-4 right-4 z-50 w-[360px] max-w-[calc(100vw-2rem)] rounded-xl border border-gray-200 bg-white/95 shadow-2xl backdrop-blur dark:border-gray-700 dark:bg-gray-900/95"
      data-testid="aol-host-panel"
    >
      <div className="flex items-start justify-between gap-3 border-b border-gray-200 px-4 py-3 dark:border-gray-700">
        <div className="min-w-0">
          <div className="text-xs font-semibold uppercase tracking-wide text-blue-600 dark:text-blue-300">
            Addressable Object
          </div>
          <div className="mt-1 truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
            {summary?.title || state.selection?.label || 'Contextual object selection'}
          </div>
          {summary?.subtitle ? (
            <div className="mt-0.5 truncate text-xs text-gray-500 dark:text-gray-400">
              {summary.subtitle}
            </div>
          ) : null}
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-md px-2 py-1 text-xs text-gray-500 transition-colors hover:bg-gray-100 hover:text-gray-800 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100"
        >
          Close
        </button>
      </div>

      <div className="space-y-3 px-4 py-3">
        {state.phase === 'resolving' ? (
          <div className="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-700 dark:bg-blue-950/30 dark:text-blue-200">
            Resolving object context...
          </div>
        ) : null}

        {state.error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-300">
            {state.error}
          </div>
        ) : null}

        {summary?.summary_text ? (
          <p className="text-sm leading-5 text-gray-600 dark:text-gray-300">{summary.summary_text}</p>
        ) : null}

        {summary?.labels?.length ? (
          <div className="flex flex-wrap gap-1">
            {summary.labels.map((label) => (
              <span
                key={label}
                className="rounded-full bg-gray-100 px-2 py-1 text-[11px] text-gray-600 dark:bg-gray-800 dark:text-gray-300"
              >
                {label}
              </span>
            ))}
          </div>
        ) : null}

        {state.attachResponse ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 dark:border-emerald-900/40 dark:bg-emerald-950/20">
            <div className="text-xs font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">
              {state.attachResponse.status === 'materialized' ? 'Materialized' : 'Attached'}
            </div>
            <div className="mt-1 text-sm text-emerald-800 dark:text-emerald-100">
              Meeting ID: <span className="font-mono">{state.attachResponse.meeting_id}</span>
            </div>
            {state.attachResponse.review_routes.length > 0 ? (
              <div className="mt-2 space-y-1">
                {state.attachResponse.review_routes.map((route) => (
                  <a
                    key={route}
                    href={route}
                    className="block text-xs text-emerald-700 underline-offset-2 hover:underline dark:text-emerald-300"
                  >
                    Review route: {route}
                  </a>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        {warnings.length > 0 ? (
          <div className="space-y-1">
            {warnings.map((warning) => (
              <div
                key={`${warning.code}:${warning.message}`}
                className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:bg-amber-950/20 dark:text-amber-300"
              >
                {warning.message}
              </div>
            ))}
          </div>
        ) : null}

        {(attachAction || ownerSurfaceAction) ? (
          <div className="flex flex-wrap gap-2">
            {attachAction ? (
              <button
                type="button"
                onClick={onAttach}
                disabled={state.phase === 'attaching'}
                className="rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {state.phase === 'attaching' ? 'Attaching...' : attachAction.label}
              </button>
            ) : null}
            {ownerSurfaceAction && summary?.owner_surface_url ? (
              <a
                href={summary.owner_surface_url}
                className="rounded-md border border-gray-200 px-3 py-2 text-sm text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
              >
                {ownerSurfaceAction.label}
              </a>
            ) : null}
          </div>
        ) : null}

        {summary ? (
          <div className="rounded-lg bg-gray-50 px-3 py-2 text-[11px] text-gray-500 dark:bg-gray-800/60 dark:text-gray-400">
            <div>Owner: {summary.ref.owner_pack}</div>
            <div>Kind: {summary.ref.object_kind}</div>
            <div className="truncate">Object ID: {summary.ref.object_id}</div>
          </div>
        ) : null}
      </div>
    </div>
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
  const [aolPanelState, setAOLPanelState] = useState<AOLPanelState>({
    phase: 'idle',
    selection: null,
    resolvedObject: null,
    warnings: [],
    attachResponse: null,
    error: null,
  });

  useEffect(() => {
    void loadCapabilityData();
  }, [capabilityCode]);

  useEffect(() => {
    setAOLPanelState({
      phase: 'idle',
      selection: null,
      resolvedObject: null,
      warnings: [],
      attachResponse: null,
      error: null,
    });
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

  const handleDismissAOLPanel = useCallback(() => {
    setAOLPanelState({
      phase: 'idle',
      selection: null,
      resolvedObject: null,
      warnings: [],
      attachResponse: null,
      error: null,
    });
  }, []);

  const handleSelectAddressableObject = useCallback(async (
    componentCode: string,
    selection: AddressableSelectionTarget,
  ) => {
    setAOLPanelState({
      phase: 'resolving',
      selection,
      resolvedObject: null,
      warnings: [],
      attachResponse: null,
      error: null,
    });

    try {
      const response = await resolveAddressableSelection({
        apiUrl,
        workspaceId,
        capabilityCode,
        route: pathname,
        surfaceId: buildComponentSurfaceId(capabilityCode, componentCode),
        selection,
      });

      if (response.status !== 'resolved' || response.resolved_objects.length === 0) {
        setAOLPanelState({
          phase: 'ready',
          selection,
          resolvedObject: null,
          warnings: response.errors,
          attachResponse: null,
          error: response.errors[0]?.message || 'Selection did not resolve to an addressable object.',
        });
        return;
      }

      setAOLPanelState({
        phase: 'ready',
        selection,
        resolvedObject: response.resolved_objects[0],
        warnings: response.errors,
        attachResponse: null,
        error: null,
      });
    } catch (resolveError) {
      setAOLPanelState({
        phase: 'ready',
        selection,
        resolvedObject: null,
        warnings: [],
        attachResponse: null,
        error: resolveError instanceof Error
          ? resolveError.message
          : 'Failed to resolve addressable object selection.',
      });
    }
  }, [apiUrl, capabilityCode, pathname, workspaceId]);

  const handleAttachResolvedObject = useCallback(async () => {
    if (!aolPanelState.resolvedObject) {
      return;
    }

    setAOLPanelState((current) => ({
      ...current,
      phase: 'attaching',
      error: null,
      attachResponse: null,
    }));

    try {
      const response = await attachAddressableObjectToMeeting({
        apiUrl,
        workspaceId,
        resolvedObject: aolPanelState.resolvedObject,
        role: (aolPanelState.selection?.role ?? 'source') as AddressableObjectRole,
      });

      setAOLPanelState((current) => ({
        ...current,
        phase: 'ready',
        attachResponse: response,
        error: response.status === 'rejected'
          ? (response.errors[0]?.message || 'Meeting attach was rejected.')
          : null,
      }));
    } catch (attachError) {
      setAOLPanelState((current) => ({
        ...current,
        phase: 'ready',
        attachResponse: null,
        error: attachError instanceof Error
          ? attachError.message
          : 'Failed to attach object to meeting.',
      }));
    }
  }, [aolPanelState.resolvedObject, aolPanelState.selection?.role, apiUrl, workspaceId]);

  const buildHostBridge = useCallback((componentCode: string): AddressableObjectHostBridge => ({
    onSelectObject: (selection) => {
      void handleSelectAddressableObject(componentCode, selection);
    },
  }), [handleSelectAddressableObject]);

  const renderLoadedComponent = (
    key: string,
    Component: React.ComponentType<any>,
    componentCode: string,
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
          aolHost={buildHostBridge(componentCode)}
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
      <div
        className={shouldUseScrollableShell ? 'relative h-full overflow-y-auto overflow-x-hidden bg-white dark:bg-gray-950' : 'relative h-full'}
        data-testid={shouldUseScrollableShell ? 'capability-mainpage-scroll-shell' : undefined}
      >
        {renderLoadedComponent(key, Component, componentCode)}
        <AddressableObjectPanel
          state={aolPanelState}
          onDismiss={handleDismissAOLPanel}
          onAttach={handleAttachResolvedObject}
        />
      </div>
    );
  }

  if (resolvedMainPageEntry && resolvedMainPageComponentInfo) {
    const [key, Component] = resolvedMainPageEntry;
    const [, renderedComponentCode] = key.split(':');
    const defaultComponentCode = mainPageComponents[0]?.code || resolvedMainPageComponentInfo.code;

    return (
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
          {renderLoadedComponent(key, Component, renderedComponentCode)}
        </div>
        <AddressableObjectPanel
          state={aolPanelState}
          onDismiss={handleDismissAOLPanel}
          onAttach={handleAttachResolvedObject}
        />
      </div>
    );
  }

  return (
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

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
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
              {renderLoadedComponent(key, Component, componentCode, true)}
            </div>
          );
        })}

        {loadedComponents.size === 0 ? (
          <div className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">
            No components loaded. Some components may have failed to load.
          </div>
        ) : null}
      </div>

      <AddressableObjectPanel
        state={aolPanelState}
        onDismiss={handleDismissAOLPanel}
        onAttach={handleAttachResolvedObject}
      />
    </div>
  );
}
