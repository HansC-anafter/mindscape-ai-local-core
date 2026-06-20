import type { MessageKey } from '@/lib/i18n';

import type { MemoryEvidenceSummary, TranslateFn } from './types';

const MEMORY_STATUS_KEYS: Partial<Record<string, MessageKey>> = {
  candidate: 'memoryLifecycleCandidate',
  active: 'memoryLifecycleActive',
  stale: 'memoryLifecycleStale',
  superseded: 'memoryLifecycleSuperseded',
  observed: 'memoryVerificationObserved',
  verified: 'memoryVerificationVerified',
  challenged: 'memoryVerificationChallenged',
  pending_confirmation: 'memoryVerificationPendingConfirmation',
  deprecated: 'memoryVerificationDeprecated',
};

const EVIDENCE_TYPE_KEYS: Partial<Record<string, MessageKey>> = {
  session_digest: 'evidenceTypeSessionDigest',
  reasoning_trace: 'evidenceTypeReasoningTrace',
  meeting_decision: 'evidenceTypeMeetingDecision',
  intent_log: 'evidenceTypeIntentLog',
  governance_decision: 'evidenceTypeGovernanceDecision',
  lens_patch: 'evidenceTypeLensPatch',
  writeback_receipt: 'evidenceTypeWritebackReceipt',
  lens_receipt: 'evidenceTypeLensReceipt',
  task_execution: 'evidenceTypeTaskExecution',
  execution_trace: 'evidenceTypeExecutionTrace',
  stage_result: 'evidenceTypeStageResult',
  artifact_result: 'evidenceTypeArtifactResult',
};

export const EVIDENCE_ROLE_KEYS: Partial<Record<string, MessageKey>> = {
  supports: 'evidenceRoleSupports',
  derived_from: 'evidenceRoleDerivedFrom',
};

export function badgeClass(status: string): string {
  if (status === 'active' || status === 'verified') {
    return 'bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300';
  }
  if (status === 'candidate' || status === 'observed' || status === 'pending_confirmation') {
    return 'bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300';
  }
  if (status === 'stale' || status === 'challenged') {
    return 'bg-slate-200 dark:bg-slate-800 text-slate-800 dark:text-slate-300';
  }
  if (status === 'superseded' || status === 'deprecated') {
    return 'bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300';
  }
  return 'bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-300';
}

export function prettyLabel(value: string): string {
  return value.replace(/_/g, ' ');
}

export function translateMappedValue(
  value: string,
  translate: TranslateFn,
  mapping: Partial<Record<string, MessageKey>>
): string {
  const key = mapping[value];
  return key ? translate(key) : prettyLabel(value);
}

export function translateMemoryStatus(value: string, translate: TranslateFn): string {
  return translateMappedValue(value, translate, MEMORY_STATUS_KEYS);
}

export function fileLabelFromPath(path: string): string {
  const segments = path.split('/');
  return segments[segments.length - 1] || path;
}

export function evidenceDisplayName(evidenceType: string, translate: TranslateFn): string {
  return translateMappedValue(evidenceType, translate, EVIDENCE_TYPE_KEYS);
}

export function evidenceMetadataRows(
  link: MemoryEvidenceSummary,
  translate: TranslateFn
): Array<{ label: string; value: string }> {
  const rows: Array<{ label: string; value: string }> = [];
  if (link.evidence_type === 'session_digest') {
    const sourceType = typeof link.metadata.source_type === 'string' ? link.metadata.source_type : null;
    const sourceId = typeof link.metadata.source_id === 'string' ? link.metadata.source_id : null;
    if (sourceType) {
      rows.push({ label: translate('sourceType'), value: sourceType });
    }
    if (sourceId) {
      rows.push({ label: translate('sourceId'), value: sourceId });
    }
  }
  if (link.evidence_type === 'reasoning_trace') {
    const executionId = typeof link.metadata.execution_id === 'string' ? link.metadata.execution_id : null;
    const meetingSessionId =
      typeof link.metadata.meeting_session_id === 'string' ? link.metadata.meeting_session_id : null;
    const nodeCount = typeof link.metadata.node_count === 'number' ? String(link.metadata.node_count) : null;
    const edgeCount = typeof link.metadata.edge_count === 'number' ? String(link.metadata.edge_count) : null;
    if (executionId) {
      rows.push({ label: translate('execution'), value: executionId });
    }
    if (meetingSessionId) {
      rows.push({ label: translate('meeting'), value: meetingSessionId });
    }
    if (nodeCount) {
      rows.push({ label: translate('nodes'), value: nodeCount });
    }
    if (edgeCount) {
      rows.push({ label: translate('edges'), value: edgeCount });
    }
  }
  if (link.evidence_type === 'meeting_decision') {
    const category = typeof link.metadata.category === 'string' ? link.metadata.category : null;
    const status = typeof link.metadata.status === 'string' ? link.metadata.status : null;
    const meetingSessionId =
      typeof link.metadata.meeting_session_id === 'string' ? link.metadata.meeting_session_id : null;
    if (category) {
      rows.push({ label: translate('category'), value: category });
    }
    if (status) {
      rows.push({ label: translate('status'), value: status });
    }
    if (meetingSessionId) {
      rows.push({ label: translate('meeting'), value: meetingSessionId });
    }
  }
  if (link.evidence_type === 'intent_log') {
    const channel = typeof link.metadata.channel === 'string' ? link.metadata.channel : null;
    const selectedPlaybookCode =
      typeof link.metadata.selected_playbook_code === 'string'
        ? link.metadata.selected_playbook_code
        : null;
    const resolutionStrategy =
      typeof link.metadata.resolution_strategy === 'string'
        ? link.metadata.resolution_strategy
        : null;
    const requiresUserApproval =
      typeof link.metadata.requires_user_approval === 'boolean'
        ? String(link.metadata.requires_user_approval)
        : null;
    const hasUserOverride =
      typeof link.metadata.has_user_override === 'boolean'
        ? String(link.metadata.has_user_override)
        : null;
    if (channel) {
      rows.push({ label: translate('channel'), value: channel });
    }
    if (selectedPlaybookCode) {
      rows.push({ label: translate('selectedPlaybook'), value: selectedPlaybookCode });
    }
    if (resolutionStrategy) {
      rows.push({ label: translate('resolution'), value: resolutionStrategy });
    }
    if (requiresUserApproval) {
      rows.push({ label: translate('requiresApproval'), value: requiresUserApproval });
    }
    if (hasUserOverride) {
      rows.push({ label: translate('userOverride'), value: hasUserOverride });
    }
  }
  if (link.evidence_type === 'governance_decision') {
    const executionId = typeof link.metadata.execution_id === 'string' ? link.metadata.execution_id : null;
    const layer = typeof link.metadata.layer === 'string' ? link.metadata.layer : null;
    const approved =
      typeof link.metadata.approved === 'boolean' ? String(link.metadata.approved) : null;
    const reason = typeof link.metadata.reason === 'string' ? link.metadata.reason : null;
    const playbookCode =
      typeof link.metadata.playbook_code === 'string' ? link.metadata.playbook_code : null;
    if (executionId) {
      rows.push({ label: translate('execution'), value: executionId });
    }
    if (layer) {
      rows.push({ label: translate('layer'), value: layer });
    }
    if (approved) {
      rows.push({ label: translate('approved'), value: approved });
    }
    if (reason) {
      rows.push({ label: translate('reason'), value: reason });
    }
    if (playbookCode) {
      rows.push({ label: translate('playbook'), value: playbookCode });
    }
  }
  if (link.evidence_type === 'lens_patch') {
    const lensId = typeof link.metadata.lens_id === 'string' ? link.metadata.lens_id : null;
    const status = typeof link.metadata.status === 'string' ? link.metadata.status : null;
    const lensVersionBefore =
      typeof link.metadata.lens_version_before === 'number'
        ? String(link.metadata.lens_version_before)
        : null;
    const lensVersionAfter =
      typeof link.metadata.lens_version_after === 'number'
        ? String(link.metadata.lens_version_after)
        : null;
    const deltaMagnitude =
      typeof link.metadata.delta_magnitude === 'number'
        ? String(link.metadata.delta_magnitude)
        : null;
    const evidenceRefCount =
      typeof link.metadata.evidence_ref_count === 'number'
        ? String(link.metadata.evidence_ref_count)
        : null;
    if (lensId) {
      rows.push({ label: translate('lensId'), value: lensId });
    }
    if (status) {
      rows.push({ label: translate('status'), value: status });
    }
    if (lensVersionBefore) {
      rows.push({ label: translate('versionBefore'), value: lensVersionBefore });
    }
    if (lensVersionAfter) {
      rows.push({ label: translate('versionAfter'), value: lensVersionAfter });
    }
    if (deltaMagnitude) {
      rows.push({ label: translate('deltaSize'), value: deltaMagnitude });
    }
    if (evidenceRefCount) {
      rows.push({ label: translate('evidenceRefs'), value: evidenceRefCount });
    }
  }
  if (link.evidence_type === 'writeback_receipt') {
    const targetTable = typeof link.metadata.target_table === 'string' ? link.metadata.target_table : null;
    const targetId = typeof link.metadata.target_id === 'string' ? link.metadata.target_id : null;
    const writebackType =
      typeof link.metadata.writeback_type === 'string' ? link.metadata.writeback_type : null;
    const status = typeof link.metadata.status === 'string' ? link.metadata.status : null;
    if (targetTable) {
      rows.push({ label: translate('targetTable'), value: targetTable });
    }
    if (targetId) {
      rows.push({ label: translate('targetId'), value: targetId });
    }
    if (writebackType) {
      rows.push({ label: translate('writebackType'), value: writebackType });
    }
    if (status) {
      rows.push({ label: translate('status'), value: status });
    }
  }
  if (link.evidence_type === 'lens_receipt') {
    const executionId = typeof link.metadata.execution_id === 'string' ? link.metadata.execution_id : null;
    const effectiveLensHash =
      typeof link.metadata.effective_lens_hash === 'string' ? link.metadata.effective_lens_hash : null;
    const triggeredNodeCount =
      typeof link.metadata.triggered_node_count === 'number'
        ? String(link.metadata.triggered_node_count)
        : null;
    if (executionId) {
      rows.push({ label: translate('execution'), value: executionId });
    }
    if (effectiveLensHash) {
      rows.push({ label: translate('lensHash'), value: effectiveLensHash });
    }
    if (triggeredNodeCount) {
      rows.push({ label: translate('triggeredNodes'), value: triggeredNodeCount });
    }
  }
  if (link.evidence_type === 'task_execution') {
    const taskId = typeof link.metadata.task_id === 'string' ? link.metadata.task_id : null;
    const executionId = typeof link.metadata.execution_id === 'string' ? link.metadata.execution_id : null;
    const status = typeof link.metadata.status === 'string' ? link.metadata.status : null;
    const packId = typeof link.metadata.pack_id === 'string' ? link.metadata.pack_id : null;
    const taskType = typeof link.metadata.task_type === 'string' ? link.metadata.task_type : null;
    if (taskId) {
      rows.push({ label: translate('taskId'), value: taskId });
    }
    if (executionId) {
      rows.push({ label: translate('execution'), value: executionId });
    }
    if (status) {
      rows.push({ label: translate('status'), value: status });
    }
    if (packId) {
      rows.push({ label: translate('pack'), value: packId });
    }
    if (taskType) {
      rows.push({ label: translate('taskType'), value: taskType });
    }
  }
  if (link.evidence_type === 'execution_trace') {
    const taskId = typeof link.metadata.task_id === 'string' ? link.metadata.task_id : null;
    const executionId = typeof link.metadata.execution_id === 'string' ? link.metadata.execution_id : null;
    const agent = typeof link.metadata.agent === 'string' ? link.metadata.agent : null;
    const traceId = typeof link.metadata.trace_id === 'string' ? link.metadata.trace_id : null;
    const toolCallCount =
      typeof link.metadata.tool_call_count === 'number' ? String(link.metadata.tool_call_count) : null;
    const fileChangeCount =
      typeof link.metadata.file_change_count === 'number'
        ? String(link.metadata.file_change_count)
        : null;
    const filesCreatedCount =
      typeof link.metadata.files_created_count === 'number'
        ? String(link.metadata.files_created_count)
        : null;
    const filesModifiedCount =
      typeof link.metadata.files_modified_count === 'number'
        ? String(link.metadata.files_modified_count)
        : null;
    const sandboxPath =
      typeof link.metadata.sandbox_path === 'string' ? link.metadata.sandbox_path : null;
    const taskDescription =
      typeof link.metadata.task_description === 'string'
        ? link.metadata.task_description
        : null;
    const outputSummary =
      typeof link.metadata.output_summary === 'string' ? link.metadata.output_summary : null;
    const success =
      typeof link.metadata.success === 'boolean' ? String(link.metadata.success) : null;
    const durationSeconds =
      typeof link.metadata.duration_seconds === 'number'
        ? String(link.metadata.duration_seconds)
        : null;
    const traceSource =
      typeof link.metadata.trace_source === 'string' ? link.metadata.trace_source : null;
    const traceFilePath =
      typeof link.metadata.trace_file_path === 'string' ? link.metadata.trace_file_path : null;
    if (taskId) {
      rows.push({ label: translate('taskId'), value: taskId });
    }
    if (executionId) {
      rows.push({ label: translate('execution'), value: executionId });
    }
    if (traceId) {
      rows.push({ label: translate('traceId'), value: traceId });
    }
    if (agent) {
      rows.push({ label: translate('agent'), value: agent });
    }
    if (toolCallCount) {
      rows.push({ label: translate('toolCalls'), value: toolCallCount });
    }
    if (fileChangeCount) {
      rows.push({ label: translate('fileChanges'), value: fileChangeCount });
    }
    if (filesCreatedCount) {
      rows.push({ label: translate('filesCreated'), value: filesCreatedCount });
    }
    if (filesModifiedCount) {
      rows.push({ label: translate('filesModified'), value: filesModifiedCount });
    }
    if (sandboxPath) {
      rows.push({ label: translate('sandbox'), value: sandboxPath });
    }
    if (durationSeconds) {
      rows.push({ label: translate('durationSeconds'), value: durationSeconds });
    }
    if (success) {
      rows.push({ label: translate('success'), value: success });
    }
    if (traceSource) {
      rows.push({ label: translate('traceSource'), value: traceSource });
    }
    if (traceFilePath) {
      rows.push({ label: translate('traceFile'), value: traceFilePath });
    }
    if (taskDescription) {
      rows.push({ label: translate('task'), value: taskDescription });
    }
    if (outputSummary) {
      rows.push({ label: translate('outputSummary'), value: outputSummary });
    }
  }
  if (link.evidence_type === 'stage_result') {
    const executionId = typeof link.metadata.execution_id === 'string' ? link.metadata.execution_id : null;
    const stepId = typeof link.metadata.step_id === 'string' ? link.metadata.step_id : null;
    const stageName = typeof link.metadata.stage_name === 'string' ? link.metadata.stage_name : null;
    const resultType = typeof link.metadata.result_type === 'string' ? link.metadata.result_type : null;
    const reviewStatus =
      typeof link.metadata.review_status === 'string' ? link.metadata.review_status : null;
    const artifactId = typeof link.metadata.artifact_id === 'string' ? link.metadata.artifact_id : null;
    if (executionId) {
      rows.push({ label: translate('execution'), value: executionId });
    }
    if (stepId) {
      rows.push({ label: translate('stepId'), value: stepId });
    }
    if (stageName) {
      rows.push({ label: translate('stage'), value: stageName });
    }
    if (resultType) {
      rows.push({ label: translate('resultType'), value: resultType });
    }
    if (reviewStatus) {
      rows.push({ label: translate('reviewStatus'), value: reviewStatus });
    }
    if (artifactId) {
      rows.push({ label: translate('artifactId'), value: artifactId });
    }
  }
  if (link.evidence_type === 'artifact_result') {
    const artifactId = typeof link.metadata.artifact_id === 'string' ? link.metadata.artifact_id : null;
    const executionId = typeof link.metadata.execution_id === 'string' ? link.metadata.execution_id : null;
    const artifactType =
      typeof link.metadata.artifact_type === 'string' ? link.metadata.artifact_type : null;
    const playbookCode =
      typeof link.metadata.playbook_code === 'string' ? link.metadata.playbook_code : null;
    const storageRef = typeof link.metadata.storage_ref === 'string' ? link.metadata.storage_ref : null;
    const landingArtifactDir =
      typeof link.metadata.landing_artifact_dir === 'string'
        ? link.metadata.landing_artifact_dir
        : null;
    const landingResultJsonPath =
      typeof link.metadata.landing_result_json_path === 'string'
        ? link.metadata.landing_result_json_path
        : null;
    const landingSummaryMdPath =
      typeof link.metadata.landing_summary_md_path === 'string'
        ? link.metadata.landing_summary_md_path
        : null;
    const landingAttachmentsCount =
      typeof link.metadata.landing_attachments_count === 'number'
        ? String(link.metadata.landing_attachments_count)
        : null;
    if (artifactId) {
      rows.push({ label: translate('artifactId'), value: artifactId });
    }
    if (executionId) {
      rows.push({ label: translate('execution'), value: executionId });
    }
    if (artifactType) {
      rows.push({ label: translate('artifactType'), value: artifactType });
    }
    if (playbookCode) {
      rows.push({ label: translate('playbook'), value: playbookCode });
    }
    if (storageRef) {
      rows.push({ label: translate('storage'), value: storageRef });
    }
    if (landingArtifactDir) {
      rows.push({ label: translate('landingDir'), value: landingArtifactDir });
    }
    if (landingResultJsonPath) {
      rows.push({ label: translate('resultJson'), value: landingResultJsonPath });
    }
    if (landingSummaryMdPath) {
      rows.push({ label: translate('summaryFile'), value: landingSummaryMdPath });
    }
    if (landingAttachmentsCount) {
      rows.push({ label: translate('attachments'), value: landingAttachmentsCount });
    }
  }
  return rows;
}

export function cueToneClass(tone: 'positive' | 'neutral' | 'caution'): string {
  if (tone === 'positive') {
    return 'border-green-200 bg-green-50 text-green-900 dark:border-green-900/50 dark:bg-green-900/20 dark:text-green-200';
  }
  if (tone === 'caution') {
    return 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/50 dark:bg-amber-900/20 dark:text-amber-200';
  }
  return 'border-slate-200 bg-slate-50 text-slate-900 dark:border-slate-700 dark:bg-slate-900/30 dark:text-slate-200';
}
