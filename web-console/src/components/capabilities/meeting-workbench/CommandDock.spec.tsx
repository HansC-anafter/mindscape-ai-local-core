import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { MeetingCommandBar } from './CommandDock';
import type { MeetingTranslate } from './meetingWorkbenchTypes';

const t: MeetingTranslate = (key, params) => {
  const labels: Partial<Record<Parameters<MeetingTranslate>[0], string>> = {
    meetingWorkbenchOpenConsole: 'Open console',
    meetingWorkbenchCollapseConsole: 'Collapse console',
    meetingWorkbenchPackTools: 'Pack tools',
    meetingWorkbenchPackToolSelect: 'Meeting pack tool',
    meetingWorkbenchAutoRouteDescription: 'Auto route through the workspace runtime',
    meetingWorkbenchLoadingTools: 'Loading tools...',
    meetingWorkbenchAutoRoute: 'Auto route',
    meetingWorkbenchDispatching: 'Dispatching...',
    meetingWorkbenchSelectMeetingFirst: 'Select a meeting session first...',
    meetingWorkbenchAskPackToolPlaceholder: `Ask ${params?.value || ''} to do the next step...`,
    meetingWorkbenchCommandPlaceholder: 'Ask a pack tool or type @ to reference context...',
    meetingWorkbenchCommandInputLabel: 'Meeting instruction',
    meetingWorkbenchInsertReference: 'Insert reference',
    meetingWorkbenchLoadingReferences: 'Loading references...',
    meetingWorkbenchReferenceSearchUnavailable: `Reference search partially unavailable: ${params?.value || ''}`,
    meetingWorkbenchNoMatchingReference: 'No matching object, storyboard, scene, character, session, node, or pack.',
    meetingWorkbenchSendInstruction: 'Send meeting instruction',
  };
  if (labels[key]) {
    return labels[key];
  }
  if (key === 'meetingWorkbenchCommandMissingContext') {
    return `Missing context: ${params?.value || ''}`;
  }
  if (key === 'meetingWorkbenchCommandMissingContextDetail') {
    return 'Type @ to reference the required object before dispatch.';
  }
  return key;
};

function renderCommandBar(overrides: Partial<React.ComponentProps<typeof MeetingCommandBar>> = {}) {
  const props: React.ComponentProps<typeof MeetingCommandBar> = {
    command: '',
    onCommandChange: vi.fn(),
    onSubmitCommand: vi.fn(),
    isDispatching: false,
    isConsoleOpen: false,
    onToggleConsole: vi.fn(),
    packTools: [],
    selectedPackToolId: 'auto',
    onSelectedPackToolChange: vi.fn(),
    packToolsLoading: false,
    packToolsError: null,
    hasActiveMeeting: true,
    mentionItems: [],
    mentionItemsLoading: false,
    mentionItemsError: null,
    onApplyMention: vi.fn(),
    missingContextLabel: null,
    t,
    ...overrides,
  };
  render(<MeetingCommandBar {...props} />);
  return props;
}

describe('MeetingCommandBar', () => {
  it('shows missing context as command input guidance', () => {
    renderCommandBar({ missingContextLabel: 'Target' });

    expect(screen.getByTestId('meeting-command-missing-context')).toHaveTextContent('Missing context: Target');
    expect(screen.getByTestId('meeting-command-missing-context')).toHaveTextContent(
      'Type @ to reference the required object before dispatch.',
    );
    expect(screen.getByLabelText('Meeting instruction')).toHaveAttribute(
      'aria-describedby',
      'meeting-command-missing-context',
    );
  });

  it('keeps command submit routed through the command dock while context is incomplete', () => {
    const onSubmitCommand = vi.fn();
    renderCommandBar({
      command: 'Draft a plan',
      missingContextLabel: 'Target',
      onSubmitCommand,
    });

    fireEvent.submit(screen.getByTestId('meeting-command-bar'));

    expect(onSubmitCommand).toHaveBeenCalledTimes(1);
  });
});
