import { describe, expect, it } from 'vitest';

import {
  buildCapabilityWorkbenchHref,
  capabilitySupportsWorkbenchRoute,
} from './StepDetailPanel';

describe('StepDetailPanel capability workbench link', () => {
  it('builds canonical workbench hrefs for review bundle artifacts', () => {
    expect(
      buildCapabilityWorkbenchHref({
        workspaceId: 'ws demo',
        capabilityCode: 'performance_direction',
        artifactId: 'artifact 001',
        runId: 'run 001',
        sceneId: 'scene 001',
      }),
    ).toBe(
      '/workspaces/ws%20demo/capability-ui-hosts/performance_direction?artifact_id=artifact+001&run_id=run+001&scene_id=scene+001',
    );
  });

  it('does not build a link without both workspace and capability code', () => {
    expect(
      buildCapabilityWorkbenchHref({
        workspaceId: '',
        capabilityCode: 'performance_direction',
        artifactId: 'artifact_001',
      }),
    ).toBeNull();
    expect(
      buildCapabilityWorkbenchHref({
        workspaceId: 'ws_demo',
        capabilityCode: null,
        artifactId: 'artifact_001',
      }),
    ).toBeNull();
  });

  it('requires installed capability metadata with UI components before showing workbench routes', () => {
    expect(
      capabilitySupportsWorkbenchRoute(
        [
          {
            code: 'performance_direction',
            ui_components: [{ code: 'PerformanceDirectionStoryboardEditorPage' }],
          },
        ],
        'performance_direction',
      ),
    ).toBe(true);
    expect(
      capabilitySupportsWorkbenchRoute(
        [
          {
            code: 'performance_direction',
            ui_components: [],
          },
        ],
        'performance_direction',
      ),
    ).toBe(false);
    expect(
      capabilitySupportsWorkbenchRoute(
        [
          {
            code: 'ig',
            ui_components: [{ code: 'IGWorkbenchPage' }],
          },
        ],
        'performance_direction',
      ),
    ).toBe(false);
  });
});
