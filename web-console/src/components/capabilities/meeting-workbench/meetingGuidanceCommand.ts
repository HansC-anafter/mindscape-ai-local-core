import type { MeetingNode, MeetingPackTool } from './meetingWorkbenchTypes';
import { readString } from './meetingWorkbenchUtils';

export function applyGuidanceCommandDraft({
  node,
  packTools,
  currentCommand,
  onCommandDraft,
  onPackToolSelect,
}: {
  node: MeetingNode | null;
  packTools: MeetingPackTool[];
  currentCommand: string;
  onCommandDraft: (command: string) => void;
  onPackToolSelect: (toolId: string) => void;
}) {
  if (currentCommand.trim()) {
    return;
  }
  const commandTemplate = readString(node?.metadata?.command_template);
  if (!commandTemplate) {
    return;
  }

  onCommandDraft(commandTemplate);
  const ownerPack = readString(node?.metadata?.owner_pack);
  const projectedTool = ownerPack
    ? packTools.find((tool) => tool.id === ownerPack || tool.capabilityCode === ownerPack)
    : null;
  if (projectedTool) {
    onPackToolSelect(projectedTool.id);
  }
}
