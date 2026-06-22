import { describe, expect, it } from 'vitest';

import { presentLifecycleStatus } from './lifecycleStatusPresenter';


describe('presentLifecycleStatus', () => {
  it('presents running lifecycle state from backend summary', () => {
    const result = presentLifecycleStatus({
      status: 'running',
      phase: 'execution',
      label: 'Running',
      owner: 'worker',
    });

    expect(result).toEqual({
      label: 'Running',
      detail: 'worker',
      tone: 'info',
      terminal: false,
    });
  });

  it('uses terminal lifecycle summary as successful closure', () => {
    const result = presentLifecycleStatus({
      status: 'completed',
      phase: 'artifact_ready',
      label: 'Artifact ready',
      terminal: true,
      next_step: 'Open outputs',
    });

    expect(result).toEqual({
      label: 'Artifact ready',
      detail: 'Open outputs',
      tone: 'success',
      terminal: true,
    });
  });

  it('falls back to execution status when lifecycle summary is missing', () => {
    const result = presentLifecycleStatus(null, 'failed');

    expect(result).toEqual({
      label: 'Failed',
      detail: 'Failed',
      tone: 'danger',
      terminal: false,
    });
  });
});
