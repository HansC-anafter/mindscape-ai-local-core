import { describe, expect, it } from 'vitest';

import {
  classifyMeetingWorkbenchViewportWidth,
  getMeetingWorkbenchDefaultPanePreset,
  isCompactMeetingWorkbenchViewport,
  resolveMeetingWorkbenchSecondarySurface,
} from './meetingWorkbenchPanelLayoutState';

describe('meetingWorkbenchPanelLayoutState', () => {
  it('classifies viewport widths into mobile, tablet, and desktop', () => {
    expect(classifyMeetingWorkbenchViewportWidth(390)).toBe('mobile');
    expect(classifyMeetingWorkbenchViewportWidth(820)).toBe('tablet');
    expect(classifyMeetingWorkbenchViewportWidth(1280)).toBe('desktop');
  });

  it('uses expanded pane presets for compact viewports only', () => {
    expect(getMeetingWorkbenchDefaultPanePreset('mobile')).toBe('expanded');
    expect(getMeetingWorkbenchDefaultPanePreset('tablet')).toBe('expanded');
    expect(getMeetingWorkbenchDefaultPanePreset('desktop')).toBe('default');
    expect(isCompactMeetingWorkbenchViewport('mobile')).toBe(true);
    expect(isCompactMeetingWorkbenchViewport('tablet')).toBe(true);
    expect(isCompactMeetingWorkbenchViewport('desktop')).toBe(false);
  });

  it('resolves one active secondary surface at a time', () => {
    expect(resolveMeetingWorkbenchSecondarySurface({
      activeInfoPanel: 'object',
      activeInspector: 'trace',
      isConsoleOpen: true,
    })).toBe('object');
    expect(resolveMeetingWorkbenchSecondarySurface({
      activeInfoPanel: null,
      activeInspector: 'trace',
      isConsoleOpen: true,
    })).toBe('inspector');
    expect(resolveMeetingWorkbenchSecondarySurface({
      activeInfoPanel: null,
      activeInspector: null,
      isConsoleOpen: true,
    })).toBe('console');
    expect(resolveMeetingWorkbenchSecondarySurface({
      activeInfoPanel: null,
      activeInspector: null,
      isConsoleOpen: false,
    })).toBeNull();
  });
});
