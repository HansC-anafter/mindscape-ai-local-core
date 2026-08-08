import React from 'react';

type WorkspaceToolPanelModule<TProps> = {
  default: React.ComponentType<TProps>;
};
type WorkspaceToolPanelImporter<TProps> = (
  () => Promise<WorkspaceToolPanelModule<TProps>>
);

export function isWorkspaceToolChunkLoadError(error: unknown): boolean {
  if (!error || typeof error !== 'object') {
    return false;
  }
  const candidate = error as { message?: unknown; name?: unknown };
  return candidate.name === 'ChunkLoadError'
    && typeof candidate.message === 'string'
    && /^Loading chunk .+ failed\./m.test(candidate.message);
}

export async function loadWorkspaceToolPanelModule<TProps>(
  importer: WorkspaceToolPanelImporter<TProps>,
): Promise<WorkspaceToolPanelModule<TProps>> {
  try {
    return await importer();
  } catch (error) {
    if (!isWorkspaceToolChunkLoadError(error)) {
      throw error;
    }
    return await importer();
  }
}

export function lazyWorkspaceToolPanel<TProps>(
  importer: WorkspaceToolPanelImporter<TProps>,
): React.LazyExoticComponent<React.ComponentType<TProps>> {
  return React.lazy(() => loadWorkspaceToolPanelModule(importer));
}
