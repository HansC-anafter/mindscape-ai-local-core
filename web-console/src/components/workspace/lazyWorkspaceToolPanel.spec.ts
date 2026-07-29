import { describe, expect, it, vi } from 'vitest';

import {
  isWorkspaceToolChunkLoadError,
  loadWorkspaceToolPanelModule,
} from './lazyWorkspaceToolPanel';
import {
  MotionSourceRailPanel,
  WorkspacePackToolPanel,
  WorkspaceRunsPanel,
  WorkspaceSettingsToolPanel,
} from './workspaceCoreToolPanelLazyComponents';

function chunkLoadError(chunkName: string): Error {
  const error = new Error(`Loading chunk ${chunkName} failed.\n(timeout: /_next/static/chunks/${chunkName}.js)`);
  error.name = 'ChunkLoadError';
  return error;
}

describe('workspace tool panel chunk recovery', () => {
  it('publishes all core tool panels through the shared lazy seam', () => {
    expect([
      WorkspaceRunsPanel,
      WorkspaceSettingsToolPanel,
      WorkspacePackToolPanel,
      MotionSourceRailPanel,
    ]).toHaveLength(4);
  });

  it('loads a healthy module exactly once', async () => {
    const panelModule = { default: () => null };
    const importer = vi.fn().mockResolvedValue(panelModule);

    await expect(loadWorkspaceToolPanelModule(importer)).resolves.toBe(panelModule);
    expect(importer).toHaveBeenCalledTimes(1);
  });

  it('retries one exact webpack chunk failure and returns the recovered module', async () => {
    const panelModule = { default: () => null };
    const importer = vi.fn()
      .mockRejectedValueOnce(chunkLoadError('workspace-pack'))
      .mockResolvedValueOnce(panelModule);

    await expect(loadWorkspaceToolPanelModule(importer)).resolves.toBe(panelModule);
    expect(importer).toHaveBeenCalledTimes(2);
  });

  it('does not retry a non-chunk error', async () => {
    const error = new TypeError('component initialization failed');
    const importer = vi.fn().mockRejectedValue(error);

    await expect(loadWorkspaceToolPanelModule(importer)).rejects.toBe(error);
    expect(importer).toHaveBeenCalledTimes(1);
  });

  it('stops after the second chunk failure', async () => {
    const firstError = chunkLoadError('workspace-pack-first');
    const terminalError = chunkLoadError('workspace-pack-terminal');
    const importer = vi.fn()
      .mockRejectedValueOnce(firstError)
      .mockRejectedValueOnce(terminalError);

    await expect(loadWorkspaceToolPanelModule(importer)).rejects.toBe(terminalError);
    expect(importer).toHaveBeenCalledTimes(2);
  });

  it('only classifies the exact webpack error shape', () => {
    expect(isWorkspaceToolChunkLoadError(chunkLoadError('workspace-pack'))).toBe(true);
    expect(isWorkspaceToolChunkLoadError(new Error('Loading chunk workspace-pack failed.'))).toBe(false);
    expect(isWorkspaceToolChunkLoadError({ name: 'ChunkLoadError', message: 'network failed' })).toBe(false);
  });
});
