'use client';

import React from 'react';

const workspaceSurfaceShellModule = import('./WorkspaceSurfaceShell');
const capabilityUiHostClientLoaderModule = import('./CapabilityUiHostClientLoader');

type WorkspaceSurfaceShellComponent = typeof import('./WorkspaceSurfaceShell').default;
type CapabilityUiHostClientLoaderComponent = typeof import('./CapabilityUiHostClientLoader').default;

interface CapabilityUiHostRouteModules {
  WorkspaceSurfaceShell: WorkspaceSurfaceShellComponent;
  CapabilityUiHostClientLoader: CapabilityUiHostClientLoaderComponent;
}

let loadedRouteModules: CapabilityUiHostRouteModules | null = null;

const routeModulesPromise = Promise.all([
  workspaceSurfaceShellModule,
  capabilityUiHostClientLoaderModule,
]).then(([workspaceSurfaceShell, capabilityUiHostClientLoader]) => {
  loadedRouteModules = {
    WorkspaceSurfaceShell: workspaceSurfaceShell.default,
    CapabilityUiHostClientLoader: capabilityUiHostClientLoader.default,
  };
  return loadedRouteModules;
});

interface CapabilityUiHostRouteClientProps {
  workspaceId: string;
  capabilityCode: string;
  surfacePath?: readonly string[];
}

function CapabilityUiHostRouteLoadingState() {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="text-sm text-gray-500 dark:text-gray-400">Loading capability UI...</div>
    </div>
  );
}

export default function CapabilityUiHostRouteClient({
  workspaceId,
  capabilityCode,
  surfacePath = [],
}: CapabilityUiHostRouteClientProps) {
  const [modules, setModules] = React.useState<CapabilityUiHostRouteModules | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    if (loadedRouteModules) {
      setModules(loadedRouteModules);
      return () => {
        cancelled = true;
      };
    }
    void routeModulesPromise
      .then((nextModules) => {
        if (!cancelled) {
          setModules(nextModules);
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : 'Capability UI host failed to load');
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className="max-w-md text-center">
          <h2 className="mb-2 text-lg font-semibold text-gray-900 dark:text-gray-100">
            Capability UI failed to load
          </h2>
          <div className="mb-4 text-sm text-red-500 dark:text-red-400">{error}</div>
        </div>
      </div>
    );
  }

  if (!modules) {
    return <CapabilityUiHostRouteLoadingState />;
  }

  const {
    WorkspaceSurfaceShell,
    CapabilityUiHostClientLoader,
  } = modules;

  return (
    <WorkspaceSurfaceShell
      workspaceId={workspaceId}
      activeCapabilityCode={capabilityCode}
      surfacePath={surfacePath}
    >
      <CapabilityUiHostClientLoader
        workspaceId={workspaceId}
        capabilityCode={capabilityCode}
        surfacePath={surfacePath}
      />
    </WorkspaceSurfaceShell>
  );
}
