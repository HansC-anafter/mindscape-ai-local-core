import type { GraphViewMode, InspectorTab } from './meetingWorkbenchTypes';

const COMPACT_INSPECTOR_FALLBACK_BY_MODE: Record<GraphViewMode, InspectorTab> = {
  work: 'object',
  director: 'object',
  runs: 'runtime',
  trace: 'trace',
};

export function resolveCompactMeetingInspectorTab(
  activeInspector: InspectorTab | null,
  graphViewMode: GraphViewMode,
): InspectorTab {
  return activeInspector ?? COMPACT_INSPECTOR_FALLBACK_BY_MODE[graphViewMode];
}
