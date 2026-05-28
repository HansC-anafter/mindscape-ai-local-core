import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ScenePatchConsole } from './ScenePatchConsole';

describe('ScenePatchConsole', () => {
  it('renders generic object actions without pack-specific props', () => {
    const onApply = vi.fn();
    render(
      <ScenePatchConsole
        description="Patch console"
        patchMode="editable"
        patchJson='{"source_scene_id":"sc01"}'
        summary={{
          sourceSceneId: 'sc01',
          objectAssetCount: 0,
          usageBindingCount: 0,
        }}
        sceneId="sc01"
        onSceneIdChange={() => undefined}
        objectAction={{
          id: 'apply-scene-patch',
          title: 'Apply scene patch',
          applying: false,
          onApply,
          fields: [
            {
              kind: 'text',
              id: 'artifact-id',
              label: 'artifact_id',
              value: '',
              onChange: () => undefined,
            },
          ],
        }}
      />,
    );

    expect(screen.getAllByText('Apply scene patch')).toHaveLength(2);
    expect(screen.queryByText(/PD Storyboard/)).toBeNull();
    expect(screen.queryByText(/MMS Storyboard/)).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Apply scene patch' }));
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it('blocks disabled generic object actions', () => {
    const onApply = vi.fn();
    render(
      <ScenePatchConsole
        description="Patch console"
        patchMode="editable"
        patchJson=""
        sceneId="sc01"
        onSceneIdChange={() => undefined}
        objectAction={{
          id: 'blocked-scene-patch',
          title: 'Apply scene patch',
          applying: false,
          disabled: true,
          disabledReason: 'No canonical storyboard_scene ObjectRef is attached.',
          onApply,
        }}
      />,
    );

    expect(screen.getByText('No canonical storyboard_scene ObjectRef is attached.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Apply scene patch' })).toBeDisabled();
    expect(onApply).not.toHaveBeenCalled();
  });
});
