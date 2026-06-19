import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { MeetingGraphViewModeSwitch } from './MeetingGraphViewModeSwitch';
import type { MeetingTranslate } from './meetingWorkbenchTypes';

const t: MeetingTranslate = (key) => String(key);

describe('MeetingGraphViewModeSwitch', () => {
  it('renders RUNS and TRACE as the only top-level planes', () => {
    render(<MeetingGraphViewModeSwitch graphViewMode="work" onGraphViewModeChange={vi.fn()} t={t} />);

    expect(screen.getByTestId('meeting-graph-view-runs')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('meeting-graph-view-trace')).toBeInTheDocument();
    expect(screen.queryByTestId('meeting-graph-view-work')).toBeNull();
    expect(screen.queryByTestId('meeting-graph-view-director')).toBeNull();
    expect(screen.getByTestId('meeting-workbench-preset-select')).toHaveValue('context_workbench');
  });

  it('routes preset changes through the legacy graph surface compatibility seam', () => {
    const onGraphViewModeChange = vi.fn();
    render(
      <MeetingGraphViewModeSwitch
        graphViewMode="runs"
        onGraphViewModeChange={onGraphViewModeChange}
        t={t}
      />,
    );

    fireEvent.change(screen.getByTestId('meeting-workbench-preset-select'), {
      target: { value: 'director_graph' },
    });
    expect(onGraphViewModeChange).toHaveBeenCalledWith('director');

    fireEvent.click(screen.getByTestId('meeting-graph-view-trace'));
    expect(onGraphViewModeChange).toHaveBeenCalledWith('trace');
  });
});
