import type {
  AddressableGraphSelection,
  AddressableObjectSummary,
  AddressableSelectionTarget,
} from '@/lib/addressable-object-layer';
import type { MeetingVoiceCommandContext } from '@/lib/meeting-voice/voiceTurnClient';

import {
  buildObjectActionPlanEntries,
  extractMentionReferences,
  isCharacterReference,
  isStoryboardReference,
  isStoryboardSceneReference,
} from './meetingMentions';
import {
  formatCommandContextRole,
  getGuidanceRequiredRoles,
  getMissingCommandContextRoles,
} from './meetingCommandValidation';
import type {
  MeetingMentionItem,
  MeetingNode,
  MeetingPackTool,
  MeetingTranslate,
} from './meetingWorkbenchTypes';
import { isRecord, readString } from './meetingWorkbenchUtils';

export type MeetingCommandIntentSource =
  | { kind: 'composer' }
  | { kind: 'provided_text'; text: string };

export type MeetingCommandContextSnapshot = {
  command: string;
  originSurface: string;
  mentionRefs: ReturnType<typeof extractMentionReferences>;
  objectActionEntries: ReturnType<typeof buildObjectActionPlanEntries>;
  selectedPackTool: MeetingPackTool | null;
  actionParameters: Record<string, unknown>;
  metadata: Record<string, unknown>;
  missingRequiredRoles: ReturnType<typeof getMissingCommandContextRoles>;
  voiceCommandContext: MeetingVoiceCommandContext;
};

export type BuildMeetingCommandContextSnapshotArgs = {
  source: MeetingCommandIntentSource;
  composerCommand: string;
  activeMeetingId: string;
  mentionItems: MeetingMentionItem[];
  packTools: MeetingPackTool[];
  selectedPackToolId: string;
  effectiveSummary: AddressableObjectSummary | null;
  effectiveSelection: AddressableSelectionTarget | null;
  selectedNode: MeetingNode | null;
  objectTitle: string;
  activeCapabilityCode: string;
  graphSelection?: AddressableGraphSelection | null;
};

function buildSelectedGuidanceObjectRef(
  node: MeetingNode | null,
): Record<string, unknown> | null {
  const metadata = node?.metadata;
  if (!isRecord(metadata)) {
    return null;
  }
  const uri = readString(metadata.object_uri);
  const ownerPack = readString(metadata.owner_pack);
  const objectKind = readString(metadata.object_kind);
  const objectId = readString(metadata.object_id);
  if (!uri || !ownerPack || !objectKind || !objectId) {
    return null;
  }
  return {
    uri,
    owner_pack: ownerPack,
    object_kind: objectKind,
    object_id: objectId,
    source_surface: 'selected_guidance',
  };
}

export function buildMeetingCommandContextSnapshot({
  source,
  composerCommand,
  activeMeetingId,
  mentionItems,
  packTools,
  selectedPackToolId,
  effectiveSummary,
  effectiveSelection,
  selectedNode,
  objectTitle,
  activeCapabilityCode,
  graphSelection,
}: BuildMeetingCommandContextSnapshotArgs): MeetingCommandContextSnapshot | null {
  const command = source.kind === 'composer' ? composerCommand : source.text;
  const trimmedCommand = command.trim();
  if (!trimmedCommand) {
    return null;
  }

  const mentionRefs = extractMentionReferences(trimmedCommand, mentionItems);
  const explicitPackRef = mentionRefs.find((ref) => ref.kind === 'pack');
  const selectedPackTool =
    (explicitPackRef
      ? packTools.find((tool) => {
        const qualifiedId = tool.capabilityCode
          ? `${tool.capabilityCode}.${tool.id}`
          : tool.id;
        return tool.id === explicitPackRef.id || qualifiedId === explicitPackRef.id;
      }) ?? null
      : null) ?? packTools.find((tool) => tool.id === selectedPackToolId) ?? null;
  const objectActionEntries = buildObjectActionPlanEntries(
    effectiveSummary?.ref,
    mentionRefs,
  );
  const selectedGuidanceMetadata = isRecord(selectedNode?.metadata?.guidance_metadata)
    ? selectedNode?.metadata?.guidance_metadata
    : null;
  const selectedGuidanceId = readString(selectedNode?.metadata?.guidance_id);
  const selectedGuidanceObjectRef = buildSelectedGuidanceObjectRef(selectedNode);
  const selectedGuidanceCard = selectedGuidanceId || selectedGuidanceMetadata
    ? {
      id: selectedGuidanceId || null,
      title: selectedNode?.title,
      intent: readString(selectedNode?.metadata?.guidance_intent) || null,
      command_template: readString(selectedNode?.metadata?.command_template) || null,
      required_roles: Array.isArray(selectedNode?.metadata?.required_roles)
        ? selectedNode?.metadata?.required_roles
        : [],
      target_ref: selectedNode?.metadata?.target_ref || null,
      review_routes: Array.isArray(selectedNode?.metadata?.review_routes)
        ? selectedNode?.metadata?.review_routes
        : [],
      metadata: selectedGuidanceMetadata || {},
      object_ref: selectedGuidanceObjectRef,
    }
    : null;
  const missingRequiredRoles = getMissingCommandContextRoles(
    getGuidanceRequiredRoles(selectedNode),
    objectActionEntries,
  );
  const actionParameters = {
    meeting_id: activeMeetingId,
    meeting_session_id: activeMeetingId,
    thread_id: activeMeetingId,
    meeting_command: trimmedCommand,
    selected_object_uri: effectiveSummary?.ref.uri,
    selected_object_title: objectTitle,
    selected_object_kind:
      effectiveSummary?.ref.object_kind || effectiveSelection?.objectKind,
    source_surface: effectiveSummary?.ref.source_surface || 'meeting_graph',
    meeting_mentions: mentionRefs,
    target_storyboards: mentionRefs.filter(isStoryboardReference),
    target_storyboard_scenes: mentionRefs.filter(isStoryboardSceneReference),
    character_refs: mentionRefs.filter(isCharacterReference),
    object_action_entries: objectActionEntries,
    selected_guidance_id: selectedGuidanceId || null,
    selected_guidance_ids: selectedGuidanceId ? [selectedGuidanceId] : [],
    selected_guidance_metadata: selectedGuidanceMetadata,
    selected_guidance_cards: selectedGuidanceCard ? [selectedGuidanceCard] : [],
    selected_guidance_object_ref: selectedGuidanceObjectRef,
    graph_selection: graphSelection || null,
    active_capability_code: activeCapabilityCode,
    active_pack_code: activeCapabilityCode,
    force_meeting_orchestration: true,
  };
  const metadata = {
    active_capability_code: activeCapabilityCode,
    active_pack_code: activeCapabilityCode,
    force_meeting_orchestration: true,
  };
  const requestedAction = selectedPackTool
    ? {
      verb: 'execute_playbook',
      pack_code: selectedPackTool.capabilityCode,
      playbook_code: selectedPackTool.id,
      write_mode: 'recommendation_only',
      parameters: {
        ...actionParameters,
        playbook_code: selectedPackTool.id,
        instruction: trimmedCommand,
        message: trimmedCommand,
      },
    }
    : null;
  const voiceCommandContext: MeetingVoiceCommandContext = {
    context_objects: objectActionEntries,
    requested_action: requestedAction,
    expected_outputs: [],
    write_mode: 'recommendation_only',
    thread_id: activeMeetingId,
    meeting_mentions: mentionRefs,
    metadata: {
      ...metadata,
      raw_intent_text: trimmedCommand,
      dispatch_mode: 'route_meeting_orchestration',
      selected_pack_tool_id: selectedPackTool?.id || null,
      selected_guidance_id: actionParameters.selected_guidance_id,
      selected_guidance_ids: actionParameters.selected_guidance_ids,
      selected_guidance_metadata: actionParameters.selected_guidance_metadata,
      selected_guidance_cards: actionParameters.selected_guidance_cards,
      selected_guidance_object_ref: actionParameters.selected_guidance_object_ref,
      action_parameters: actionParameters,
    },
  };

  return {
    command: trimmedCommand,
    originSurface: effectiveSummary?.ref.source_surface || 'meeting_workbench',
    mentionRefs,
    objectActionEntries,
    selectedPackTool,
    actionParameters,
    metadata,
    missingRequiredRoles,
    voiceCommandContext,
  };
}

export function missingMeetingCommandContextMessage(
  missingRequiredRoles: ReturnType<typeof getMissingCommandContextRoles>,
  t: MeetingTranslate,
): string | null {
  if (missingRequiredRoles.length === 0) {
    return null;
  }
  return t('meetingWorkbenchCommandRequiredContextMissing', {
    value: missingRequiredRoles.map(formatCommandContextRole).join(', '),
  });
}
