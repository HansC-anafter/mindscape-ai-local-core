import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { attachResponse, summary } from './meetingWorkbenchTestData';
import { MeetingHeaderToolbar } from './SemanticFlowCanvas';
import { ObjectOutlinerPanel } from './ObjectOutlinerPanel';
import type { MeetingTranslate } from './meetingWorkbenchTypes';

describe('AOLMeetingBottomShell context navigation', () => {
  it('routes context bar chips as graph navigation without dispatching work', () => {
    const onSelectNextStep = vi.fn();
    const onSelectMissingContext = vi.fn();
    const t: MeetingTranslate = (key, params) => {
      if (key === 'meetingWorkbenchFocusPrefix') {
        return `Focus: ${params?.value || ''}`;
      }
      if (key === 'meetingWorkbenchNextPrefix') {
        return `Next: ${params?.value || ''}`;
      }
      if (key === 'meetingWorkbenchMissingContextPrefix') {
        return `Missing: ${params?.value || ''}`;
      }
      if (key === 'meetingWorkbenchWork') {
        return 'Work';
      }
      return String(key);
    };

    render(
      <MeetingHeaderToolbar
        activePanel={null}
        activeMeetingId="mtg_global"
        sessionsCount={1}
        sessionsLoading={false}
        objectTitle="Global Reference"
        hasObjectContext={true}
        graphViewMode="work"
        primaryCount={4}
        traceCount={2}
        workStatus="Ready"
        nextStepTitle="Ready for instruction"
        runtimeLabel="Default runtime"
        focusRoleLabel="Source"
        missingContextLabel="Target"
        onSelectNextStep={onSelectNextStep}
        onSelectMissingContext={onSelectMissingContext}
        onTogglePanel={vi.fn()}
        onGraphViewModeChange={vi.fn()}
        t={t}
      />,
    );

    fireEvent.click(screen.getByTestId('meeting-work-next-chip'));
    fireEvent.click(screen.getByTestId('meeting-work-missing-context-chip'));

    expect(onSelectNextStep).toHaveBeenCalledTimes(1);
    expect(onSelectMissingContext).toHaveBeenCalledTimes(1);
  });

  it('lets missing role placeholders select missing context without dispatch controls', () => {
    const onSelectMissingContext = vi.fn();
    const t: MeetingTranslate = (key) => {
      if (key === 'meetingWorkbenchMissingTarget') {
        return 'Missing target';
      }
      if (key === 'meetingWorkbenchMissingTargetDetail') {
        return 'Attach or mention a target object before dispatch.';
      }
      if (key === 'meetingWorkbenchObjectOutliner') {
        return 'Object Outliner';
      }
      if (key === 'meetingWorkbenchOutlinerTarget') {
        return 'Target';
      }
      if (key === 'meetingWorkbenchEmpty') {
        return 'Empty';
      }
      return String(key);
    };

    const { rerender } = render(
      <ObjectOutlinerPanel
        graphViewMode="work"
        nodes={[]}
        summary={summary}
        attachResponse={attachResponse}
        selectedNodeId="ready"
        activeMissingContext={null}
        onSelectNode={vi.fn()}
        onSelectMissingContext={onSelectMissingContext}
        t={t}
      />,
    );

    fireEvent.click(screen.getByTestId('meeting-object-outliner-node-missing-target'));
    expect(onSelectMissingContext).toHaveBeenCalledWith('target');

    rerender(
      <ObjectOutlinerPanel
        graphViewMode="work"
        nodes={[]}
        summary={summary}
        attachResponse={attachResponse}
        selectedNodeId="ready"
        activeMissingContext="target"
        onSelectNode={vi.fn()}
        onSelectMissingContext={onSelectMissingContext}
        t={t}
      />,
    );

    expect(screen.getByTestId('meeting-object-outliner-node-missing-target')).toHaveAttribute('aria-pressed', 'true');
  });
});
