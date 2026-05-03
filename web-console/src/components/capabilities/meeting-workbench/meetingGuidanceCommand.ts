import type { MeetingNode, MeetingPackTool } from './meetingWorkbenchTypes';
import { isRecord, readString } from './meetingWorkbenchUtils';

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
  const guidanceMetadata = isRecord(node?.metadata?.guidance_metadata)
    ? node?.metadata?.guidance_metadata
    : null;
  const recommendedPack = readString(guidanceMetadata?.recommended_pack);
  const recommendedPlaybook = readString(guidanceMetadata?.recommended_playbook);
  const projectedTool = recommendedPlaybook || recommendedPack
    ? packTools.find((tool) => {
      const qualifiedId = tool.capabilityCode ? `${tool.capabilityCode}.${tool.id}` : tool.id;
      return (
        tool.id === recommendedPlaybook ||
        qualifiedId === recommendedPlaybook ||
        (tool.capabilityCode === recommendedPack && (!recommendedPlaybook || tool.id === recommendedPlaybook))
      );
    })
    : null;
  if (projectedTool) {
    onPackToolSelect(projectedTool.id);
  }
}
