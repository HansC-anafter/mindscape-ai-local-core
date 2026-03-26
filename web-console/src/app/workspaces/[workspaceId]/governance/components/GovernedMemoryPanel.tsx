'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, Clock3, GitBranchPlus, RefreshCw } from 'lucide-react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useT, type MessageKey } from '@/lib/i18n';
import { formatLocalDateTime } from '@/lib/time';
import { getApiBaseUrl } from '../../../../../lib/api-url';
import { WorkflowEvidenceHealthSummary } from '@/components/workspace/meeting/WorkflowEvidenceHealthSummary';

interface WorkspaceMemoryItemSummary {
  id: string;
  kind: string;
  layer: string;
  title: string;
  claim: string;
  summary: string;
  lifecycle_status: string;
  verification_status: string;
  salience: number;
  confidence: number;
  subject_type: string;
  subject_id: string;
  supersedes_memory_id?: string | null;
  observed_at: string;
  last_confirmed_at?: string | null;
  created_at: string;
  updated_at: string;
}

interface WorkspaceMemoryListResponse {
  workspace_id: string;
  items: WorkspaceMemoryItemSummary[];
  total: number;
  limit: number;
}

interface MemoryVersionSummary {
  id: string;
  version_no: number;
  update_mode: string;
  claim_snapshot: string;
  summary_snapshot?: string | null;
  metadata_snapshot: Record<string, unknown>;
  created_at: string;
  created_from_run_id?: string | null;
}

interface MemoryEvidenceSummary {
  id: string;
  evidence_type: string;
  evidence_id: string;
  link_role: string;
  excerpt?: string | null;
  confidence?: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
  artifact_landing?: ArtifactLandingDrilldownSummary | null;
  execution_trace_drilldown?: ExecutionTraceDrilldownSummary | null;
}

interface ArtifactLandingDrilldownSummary {
  artifact_dir?: string | null;
  result_json_path?: string | null;
  summary_md_path?: string | null;
  attachments_count: number;
  attachments: string[];
  landed_at?: string | null;
  artifact_dir_exists: boolean;
  result_json_exists: boolean;
  summary_md_exists: boolean;
}

interface ExecutionTraceDrilldownSummary {
  trace_source?: string | null;
  trace_file_path?: string | null;
  trace_file_exists: boolean;
  sandbox_path?: string | null;
  tool_call_count: number;
  file_change_count: number;
  files_created_count: number;
  files_modified_count: number;
  success?: boolean | null;
  duration_seconds?: number | null;
  task_description?: string | null;
  output_summary?: string | null;
}

interface MemoryEdgeSummary {
  id: string;
  from_memory_id: string;
  to_memory_id: string;
  edge_type: string;
  weight?: number | null;
  valid_from: string;
  valid_to?: string | null;
  evidence_strength?: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

interface PersonalKnowledgeProjectionSummary {
  id: string;
  knowledge_type: string;
  content: string;
  status: string;
  confidence: number;
  created_at: string;
  last_verified_at?: string | null;
}

interface GoalLedgerProjectionSummary {
  id: string;
  title: string;
  description: string;
  status: string;
  horizon: string;
  created_at: string;
  confirmed_at?: string | null;
}

interface WorkspaceMemoryDetailResponse {
  workspace_id: string;
  memory_item: WorkspaceMemoryItemSummary;
  versions: MemoryVersionSummary[];
  evidence: MemoryEvidenceSummary[];
  outgoing_edges: MemoryEdgeSummary[];
  personal_knowledge_projections: PersonalKnowledgeProjectionSummary[];
  goal_projections: GoalLedgerProjectionSummary[];
  evidence_coverage?: EvidenceCoverageSummary;
  transition_cues?: TransitionCue[];
  successor_draft_suggestion?: SuccessorDraftSuggestion | null;
  transition_reason_suggestions?: {
    verify: string;
    stale: string;
    supersede: string;
  };
}

interface MemoryTransitionResponse {
  workspace_id: string;
  memory_item_id: string;
  transition: 'verify' | 'stale' | 'supersede';
  noop: boolean;
  lifecycle_status: string;
  verification_status: string;
  run_id: string;
  successor_memory_item_id?: string | null;
}

interface GovernedMemoryPanelProps {
  workspaceId: string;
}

interface EvidenceCoverageSummary {
  deliberation: number;
  execution: number;
  governance: number;
  support: number;
  derived: number;
}

interface TransitionCue {
  id: string;
  tone: 'positive' | 'neutral' | 'caution';
  title: string;
  body: string;
}

interface SuccessorDraftSuggestion {
  title: string;
  claim: string;
  summary: string;
  primary_evidence_id?: string | null;
  primary_evidence_type?: string | null;
}

type TranslateFn = (key: MessageKey, params?: Record<string, string>) => string;

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

const EVIDENCE_ROLE_KEYS: Partial<Record<string, MessageKey>> = {
  supports: 'evidenceRoleSupports',
  derived_from: 'evidenceRoleDerivedFrom',
};

function badgeClass(status: string): string {
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

function prettyLabel(value: string): string {
  return value.replace(/_/g, ' ');
}

function translateMappedValue(
  value: string,
  translate: TranslateFn,
  mapping: Partial<Record<string, MessageKey>>
): string {
  const key = mapping[value];
  return key ? translate(key) : prettyLabel(value);
}

function translateMemoryStatus(value: string, translate: TranslateFn): string {
  return translateMappedValue(value, translate, MEMORY_STATUS_KEYS);
}

function fileLabelFromPath(path: string): string {
  const segments = path.split('/');
  return segments[segments.length - 1] || path;
}

function evidenceDisplayName(evidenceType: string, translate: TranslateFn): string {
  return translateMappedValue(evidenceType, translate, EVIDENCE_TYPE_KEYS);
}

function evidenceMetadataRows(
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

function cueToneClass(tone: TransitionCue['tone']): string {
  if (tone === 'positive') {
    return 'border-green-200 bg-green-50 text-green-900 dark:border-green-900/50 dark:bg-green-900/20 dark:text-green-200';
  }
  if (tone === 'caution') {
    return 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/50 dark:bg-amber-900/20 dark:text-amber-200';
  }
  return 'border-slate-200 bg-slate-50 text-slate-900 dark:border-slate-700 dark:bg-slate-900/30 dark:text-slate-200';
}

function buildEvidenceCoverage(evidence: MemoryEvidenceSummary[]): EvidenceCoverageSummary {
  return evidence.reduce<EvidenceCoverageSummary>(
    (acc, link) => {
      if (
        link.evidence_type === 'session_digest' ||
        link.evidence_type === 'meeting_decision' ||
        link.evidence_type === 'reasoning_trace'
      ) {
        acc.deliberation += 1;
      }
      if (
        link.evidence_type === 'task_execution' ||
        link.evidence_type === 'execution_trace' ||
        link.evidence_type === 'stage_result' ||
        link.evidence_type === 'artifact_result' ||
        link.evidence_type === 'lens_receipt'
      ) {
        acc.execution += 1;
      }
      if (
        link.evidence_type === 'writeback_receipt' ||
        link.evidence_type === 'intent_log' ||
        link.evidence_type === 'governance_decision' ||
        link.evidence_type === 'lens_patch'
      ) {
        acc.governance += 1;
      }
      if (link.link_role === 'supports') {
        acc.support += 1;
      }
      if (link.link_role === 'derived_from') {
        acc.derived += 1;
      }
      return acc;
    },
    {
      deliberation: 0,
      execution: 0,
      governance: 0,
      support: 0,
      derived: 0,
    }
  );
}

function buildTransitionCues(
  item: WorkspaceMemoryItemSummary,
  evidence: MemoryEvidenceSummary[],
  coverage: EvidenceCoverageSummary,
  translate: TranslateFn
): TransitionCue[] {
  const cues: TransitionCue[] = [];
  const hasOperationalEvidence = coverage.execution > 0 || coverage.governance > 0;
  const hasDeliberationEvidence = coverage.deliberation > 0;
  const hasArtifactOrTaskEvidence = evidence.some(
    (link) =>
      link.evidence_type === 'task_execution' ||
      link.evidence_type === 'execution_trace' ||
      link.evidence_type === 'stage_result' ||
      link.evidence_type === 'artifact_result'
  );
  const hasDecisionEvidence = evidence.some(
    (link) =>
      link.evidence_type === 'meeting_decision' ||
      link.evidence_type === 'intent_log' ||
      link.evidence_type === 'governance_decision' ||
      link.evidence_type === 'lens_patch'
  );

  if (item.lifecycle_status === 'candidate') {
    if (hasDeliberationEvidence && hasOperationalEvidence) {
      cues.push({
        id: 'verify-ready',
        tone: 'positive',
        title: translate('memoryCueVerifyReadyTitle'),
        body: translate('memoryCueVerifyReadyBody'),
      });
    } else {
      cues.push({
        id: 'verify-hold',
        tone: 'caution',
        title: translate('memoryCueHoldTitle'),
        body: translate('memoryCueHoldBody'),
      });
    }
  }

  if (item.lifecycle_status === 'active') {
    cues.push({
      id: 'stale-usage',
      tone: 'neutral',
      title: translate('memoryCueStaleTitle'),
      body: translate('memoryCueStaleBody'),
    });
    if (hasArtifactOrTaskEvidence || hasDecisionEvidence) {
      cues.push({
        id: 'supersede-usage',
        tone: 'positive',
        title: translate('memoryCueSupersedeTitle'),
        body: translate('memoryCueSupersedeBody'),
      });
    }
  }

  if (coverage.support === 0 && coverage.derived > 0) {
    cues.push({
      id: 'support-gap',
      tone: 'caution',
      title: translate('memoryCueSupportGapTitle'),
      body: translate('memoryCueSupportGapBody'),
    });
  }

  if (cues.length === 0) {
    cues.push({
      id: 'baseline',
      tone: 'neutral',
      title: translate('memoryCueBaselineTitle'),
      body: translate('memoryCueBaselineBody'),
    });
  }

  return cues;
}

function evidencePriority(link: MemoryEvidenceSummary): number {
  if (link.link_role === 'supports' && link.evidence_type === 'artifact_result') {
    return 0;
  }
  if (link.link_role === 'supports' && link.evidence_type === 'stage_result') {
    return 1;
  }
  if (link.link_role === 'supports' && link.evidence_type === 'task_execution') {
    return 2;
  }
  if (link.link_role === 'supports' && link.evidence_type === 'execution_trace') {
    return 3;
  }
  if (link.link_role === 'supports' && link.evidence_type === 'meeting_decision') {
    return 4;
  }
  if (link.link_role === 'supports' && link.evidence_type === 'governance_decision') {
    return 5;
  }
  if (link.link_role === 'supports' && link.evidence_type === 'lens_patch') {
    return 6;
  }
  if (link.link_role === 'supports' && link.evidence_type === 'intent_log') {
    return 7;
  }
  if (link.link_role === 'supports' && link.evidence_type === 'reasoning_trace') {
    return 8;
  }
  if (link.evidence_type === 'session_digest') {
    return 9;
  }
  if (link.evidence_type === 'lens_receipt') {
    return 10;
  }
  if (link.evidence_type === 'writeback_receipt') {
    return 11;
  }
  return 12;
}

function selectPrimaryEvidence(evidence: MemoryEvidenceSummary[]): MemoryEvidenceSummary | null {
  if (evidence.length === 0) {
    return null;
  }
  const ranked = [...evidence].sort((a, b) => {
    const priorityDiff = evidencePriority(a) - evidencePriority(b);
    if (priorityDiff !== 0) {
      return priorityDiff;
    }
    return b.created_at.localeCompare(a.created_at);
  });
  return ranked[0] || null;
}

function buildSuccessorDraftSuggestion(
  item: WorkspaceMemoryItemSummary,
  evidence: MemoryEvidenceSummary[],
  coverage: EvidenceCoverageSummary,
  translate: TranslateFn
): SuccessorDraftSuggestion {
  const primaryEvidence = selectPrimaryEvidence(evidence);
  const primaryExcerpt = primaryEvidence?.excerpt?.trim();
  const revisionSuffix = translate('revisionSuffix');
  const primaryLabel = primaryEvidence
    ? evidenceDisplayName(primaryEvidence.evidence_type, translate)
    : translate('evidence');
  const claim =
    primaryExcerpt ||
    item.claim ||
    item.summary ||
    translate('refineClaimFromEvidence');
  const title = item.title.toLowerCase().includes('revision') || item.title.endsWith(revisionSuffix)
    ? item.title
    : `${item.title} ${revisionSuffix}`;
  const summaryParts = [
    translate('successorDraftFromEvidence', { source: primaryLabel }),
    translate('successorDraftCoverage', {
      deliberation: String(coverage.deliberation),
      execution: String(coverage.execution),
      governance: String(coverage.governance),
    }),
  ];
  if (primaryEvidence?.evidence_id) {
    summaryParts.push(
      translate('successorDraftAnchorEvidence', {
        evidenceId: primaryEvidence.evidence_id,
      })
    );
  }
  return {
    title,
    claim,
    summary: summaryParts.join(' '),
  };
}

function buildTransitionReasonSuggestion(
  action: MemoryTransitionResponse['transition'],
  item: WorkspaceMemoryItemSummary,
  primaryEvidence: MemoryEvidenceSummary | null,
  coverage: EvidenceCoverageSummary,
  translate: TranslateFn
): string {
  const anchor = primaryEvidence
    ? `${evidenceDisplayName(primaryEvidence.evidence_type, translate)} ${primaryEvidence.evidence_id}`
    : translate('evidence');

  if (action === 'verify') {
    return translate('verifyReasonSuggestion', {
      anchor,
      deliberation: String(coverage.deliberation),
      downstream: String(coverage.execution + coverage.governance),
    });
  }
  if (action === 'stale') {
    return translate('staleReasonSuggestion', { anchor });
  }
  return translate('supersedeReasonSuggestion', {
    anchor,
    title: item.title,
  });
}

export function GovernedMemoryPanel({ workspaceId }: GovernedMemoryPanelProps) {
  const t = useT();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [items, setItems] = useState<WorkspaceMemoryItemSummary[]>([]);
  const [selectedMemoryId, setSelectedMemoryId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<WorkspaceMemoryDetailResponse | null>(null);
  const [lifecycleStatus, setLifecycleStatus] = useState<string>('');
  const [verificationStatus, setVerificationStatus] = useState<string>('');
  const [transitionReason, setTransitionReason] = useState('');
  const [supersedeDraftOpen, setSupersedeDraftOpen] = useState(false);
  const [successorTitle, setSuccessorTitle] = useState('');
  const [successorClaim, setSuccessorClaim] = useState('');
  const [successorSummary, setSuccessorSummary] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [evidenceTypeFilter, setEvidenceTypeFilter] = useState<string>('all');
  const queryMemoryId = searchParams?.get('memoryId') || null;

  const syncMemoryIdInUrl = useCallback((nextMemoryId: string | null) => {
    const nextParams = new URLSearchParams(searchParams?.toString() || '');
    if (nextMemoryId) {
      nextParams.set('memoryId', nextMemoryId);
    } else {
      nextParams.delete('memoryId');
    }
    const nextUrl = nextParams.toString() ? `${pathname}?${nextParams.toString()}` : pathname;
    router.replace(nextUrl, { scroll: false });
  }, [pathname, router, searchParams]);

  const selectMemoryItem = useCallback((nextMemoryId: string | null) => {
    setSelectedMemoryId(nextMemoryId);
    syncMemoryIdInUrl(nextMemoryId);
  }, [syncMemoryIdInUrl]);

  const loadItems = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const params = new URLSearchParams({ limit: '50' });
      if (lifecycleStatus) {
        params.append('lifecycle_status', lifecycleStatus);
      }
      if (verificationStatus) {
        params.append('verification_status', verificationStatus);
      }

      const apiUrl = getApiBaseUrl();
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/governance/memory?${params.toString()}`
      );
      if (!response.ok) {
        throw new Error(t('failedToLoadGovernedMemory'));
      }

      const data: WorkspaceMemoryListResponse = await response.json();
      setItems(data.items || []);
      const preferredMemoryId =
        (queryMemoryId && data.items.some((item) => item.id === queryMemoryId)
          ? queryMemoryId
          : null) ||
        (selectedMemoryId && data.items.some((item) => item.id === selectedMemoryId)
          ? selectedMemoryId
          : null) ||
        data.items[0]?.id ||
        null;

      if (preferredMemoryId !== selectedMemoryId) {
        setSelectedMemoryId(preferredMemoryId);
      }
      if (preferredMemoryId !== queryMemoryId) {
        syncMemoryIdInUrl(preferredMemoryId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t('failedToLoadGovernedMemory'));
    } finally {
      setLoading(false);
    }
  }, [
    lifecycleStatus,
    queryMemoryId,
    selectedMemoryId,
    syncMemoryIdInUrl,
    t,
    verificationStatus,
    workspaceId,
  ]);

  const loadDetail = useCallback(async (memoryItemId: string) => {
    try {
      setDetailLoading(true);
      setDetailError(null);
      setActionError(null);

      const apiUrl = getApiBaseUrl();
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/governance/memory/${memoryItemId}`
      );
      if (!response.ok) {
        throw new Error(t('failedToLoadMemoryDetail'));
      }

      const data: WorkspaceMemoryDetailResponse = await response.json();
      setSelectedDetail(data);
      setEvidenceTypeFilter('all');
      setSuccessorTitle('');
      setSuccessorClaim('');
      setSuccessorSummary('');
      setSupersedeDraftOpen(false);
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : t('failedToLoadMemoryDetail'));
    } finally {
      setDetailLoading(false);
    }
  }, [t, workspaceId]);

  useEffect(() => {
    void loadItems();
  }, [loadItems]);

  useEffect(() => {
    if (!queryMemoryId || queryMemoryId === selectedMemoryId) {
      return;
    }
    setSelectedMemoryId(queryMemoryId);
  }, [queryMemoryId, selectedMemoryId]);

  useEffect(() => {
    if (!selectedMemoryId) {
      setSelectedDetail(null);
      return;
    }
    void loadDetail(selectedMemoryId);
  }, [loadDetail, selectedMemoryId]);

  const handleTransition = async (
    action: 'verify' | 'stale' | 'supersede',
    options?: {
      successor_title?: string;
      successor_claim?: string;
      successor_summary?: string;
    }
  ) => {
    if (!selectedMemoryId) {
      return;
    }

    try {
      setActionLoading(true);
      setActionError(null);

      const apiUrl = getApiBaseUrl();
      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/governance/memory/${selectedMemoryId}/transition`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action,
            reason: transitionReason,
            ...options,
          }),
        }
      );

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail || t('failedToApplyMemoryTransition'));
      }

      const data: MemoryTransitionResponse = await response.json();
      const nextMemoryId = data.successor_memory_item_id || selectedMemoryId;
      await loadItems();
      await loadDetail(nextMemoryId);
      selectMemoryItem(nextMemoryId);
      setTransitionReason('');
    } catch (err) {
      setActionError(err instanceof Error ? err.message : t('failedToApplyMemoryTransition'));
    } finally {
      setActionLoading(false);
    }
  };

  const selectedItem = selectedDetail?.memory_item;
  const evidenceTypeCounts = (selectedDetail?.evidence || []).reduce<Record<string, number>>(
    (acc, link) => {
      acc[link.evidence_type] = (acc[link.evidence_type] || 0) + 1;
      return acc;
    },
    {}
  );
  const filteredEvidence = (selectedDetail?.evidence || [])
    .filter((link) => evidenceTypeFilter === 'all' || link.evidence_type === evidenceTypeFilter)
    .sort((a, b) => {
      const sortWeight = (evidenceType: string): number => {
        if (evidenceType === 'session_digest') return 0;
        if (evidenceType === 'meeting_decision') return 1;
        if (evidenceType === 'task_execution') return 2;
        if (evidenceType === 'execution_trace') return 3;
        if (evidenceType === 'artifact_result') return 4;
        if (evidenceType === 'governance_decision') return 5;
        if (evidenceType === 'lens_patch') return 6;
        if (evidenceType === 'intent_log') return 7;
        if (evidenceType === 'reasoning_trace') return 8;
        if (evidenceType === 'lens_receipt') return 9;
        if (evidenceType === 'writeback_receipt') return 10;
        return 10;
      };
      const weightDiff = sortWeight(a.evidence_type) - sortWeight(b.evidence_type);
      if (weightDiff !== 0) {
        return weightDiff;
      }
      return a.created_at.localeCompare(b.created_at);
    });
  const evidenceCoverage =
    selectedDetail?.evidence_coverage || buildEvidenceCoverage(selectedDetail?.evidence || []);
  const primaryEvidence = selectPrimaryEvidence(selectedDetail?.evidence || []);
  const transitionCues =
    selectedDetail?.transition_cues ||
    (selectedItem
      ? buildTransitionCues(selectedItem, selectedDetail?.evidence || [], evidenceCoverage, t)
      : []);
  const successorDraftSuggestion =
    selectedDetail?.successor_draft_suggestion ||
    (selectedItem && selectedItem.lifecycle_status === 'active'
      ? buildSuccessorDraftSuggestion(selectedItem, selectedDetail?.evidence || [], evidenceCoverage, t)
      : null);
  const verifyReasonSuggestion =
    selectedDetail?.transition_reason_suggestions?.verify ||
    (selectedItem
      ? buildTransitionReasonSuggestion('verify', selectedItem, primaryEvidence, evidenceCoverage, t)
      : '');
  const staleReasonSuggestion =
    selectedDetail?.transition_reason_suggestions?.stale ||
    (selectedItem
      ? buildTransitionReasonSuggestion('stale', selectedItem, primaryEvidence, evidenceCoverage, t)
      : '');
  const supersedeReasonSuggestion =
    selectedDetail?.transition_reason_suggestions?.supersede ||
    (selectedItem
      ? buildTransitionReasonSuggestion('supersede', selectedItem, primaryEvidence, evidenceCoverage, t)
      : '');

  useEffect(() => {
    if (!supersedeDraftOpen || !successorDraftSuggestion) {
      return;
    }
    if (successorTitle || successorClaim || successorSummary) {
      return;
    }
    setSuccessorTitle(successorDraftSuggestion.title);
    setSuccessorClaim(successorDraftSuggestion.claim);
    setSuccessorSummary(successorDraftSuggestion.summary);
  }, [
    successorClaim,
    successorDraftSuggestion,
    successorSummary,
    successorTitle,
    supersedeDraftOpen,
  ]);

  return (
    <div className="space-y-4">
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-primary dark:text-gray-100">
              {t('governedMemory' as any) || 'Governed Memory'}
            </h2>
            <p className="text-sm text-secondary dark:text-gray-400 mt-1">
              {t('governedMemoryDescription' as any) || 'Inspect canonical memory, evidence, projections, and lifecycle transitions for this workspace.'}
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('lifecycle' as any) || 'Lifecycle'}
              </label>
              <select
                value={lifecycleStatus}
                onChange={(e) => setLifecycleStatus(e.target.value)}
                className="w-full sm:w-40 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              >
                <option value="">{t('all' as any) || 'All'}</option>
                <option value="candidate">{translateMemoryStatus('candidate', t)}</option>
                <option value="active">{translateMemoryStatus('active', t)}</option>
                <option value="stale">{translateMemoryStatus('stale', t)}</option>
                <option value="superseded">{translateMemoryStatus('superseded', t)}</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('verification' as any) || 'Verification'}
              </label>
              <select
                value={verificationStatus}
                onChange={(e) => setVerificationStatus(e.target.value)}
                className="w-full sm:w-40 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
              >
                <option value="">{t('all' as any) || 'All'}</option>
                <option value="observed">{translateMemoryStatus('observed', t)}</option>
                <option value="verified">{translateMemoryStatus('verified', t)}</option>
                <option value="challenged">{translateMemoryStatus('challenged', t)}</option>
              </select>
            </div>
            <button
              onClick={() => void loadItems()}
              className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
            >
              <RefreshCw size={14} />
              {t('refresh' as any) || 'Refresh'}
            </button>
          </div>
        </div>
      </div>

      <WorkflowEvidenceHealthSummary
        workspaceId={workspaceId}
        apiUrl={getApiBaseUrl()}
        limit={8}
        showRecentSessions
      />

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <p className="text-sm text-red-800 dark:text-red-300">{error}</p>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[360px_minmax(0,1fr)] gap-4">
        <div className="space-y-2">
          {loading ? (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 text-center text-secondary dark:text-gray-400">
              {t('loading' as any) || 'Loading...'}
            </div>
          ) : items.length === 0 ? (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 text-center text-secondary dark:text-gray-400">
              {t('noGovernedMemory' as any) || 'No governed memory found for this workspace.'}
            </div>
          ) : (
            items.map((item) => (
              <button
                key={item.id}
                onClick={() => selectMemoryItem(item.id)}
                className={`w-full text-left rounded-lg border p-4 transition-colors ${
                  selectedMemoryId === item.id
                    ? 'border-blue-500 dark:border-blue-400 bg-blue-50 dark:bg-blue-900/20'
                    : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <span className={`px-2 py-1 text-xs font-medium rounded ${badgeClass(item.lifecycle_status)}`}>
                    {translateMemoryStatus(item.lifecycle_status, t)}
                  </span>
                  <span className={`px-2 py-1 text-xs font-medium rounded ${badgeClass(item.verification_status)}`}>
                    {translateMemoryStatus(item.verification_status, t)}
                  </span>
                  <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
                    {prettyLabel(item.kind)}
                  </span>
                </div>
                <div className="text-sm font-semibold text-primary dark:text-gray-100 mb-1">
                  {item.title}
                </div>
                <div className="text-xs text-secondary dark:text-gray-400 mb-2">
                  {prettyLabel(item.layer)} · {formatLocalDateTime(item.observed_at)}
                </div>
                <p className="text-sm text-gray-700 dark:text-gray-300 line-clamp-3">
                  {item.summary || item.claim}
                </p>
              </button>
            ))
          )}
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-5">
          {detailLoading ? (
            <div className="text-center py-8 text-secondary dark:text-gray-400">
              {t('loading' as any) || 'Loading...'}
            </div>
          ) : detailError ? (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
              <p className="text-sm text-red-800 dark:text-red-300">{detailError}</p>
            </div>
          ) : !selectedDetail || !selectedItem ? (
            <div className="text-center py-8 text-secondary dark:text-gray-400">
              {t('selectMemoryItem' as any) || 'Select a memory item to inspect its detail.'}
            </div>
          ) : (
            <div className="space-y-5">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <div className="flex flex-wrap gap-2 mb-2">
                    <span className={`px-2 py-1 text-xs font-medium rounded ${badgeClass(selectedItem.lifecycle_status)}`}>
                      {translateMemoryStatus(selectedItem.lifecycle_status, t)}
                    </span>
                    <span className={`px-2 py-1 text-xs font-medium rounded ${badgeClass(selectedItem.verification_status)}`}>
                      {translateMemoryStatus(selectedItem.verification_status, t)}
                    </span>
                    <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
                      {prettyLabel(selectedItem.kind)}
                    </span>
                    <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
                      {prettyLabel(selectedItem.layer)}
                    </span>
                  </div>
                  <h3 className="text-xl font-semibold text-primary dark:text-gray-100">
                    {selectedItem.title}
                  </h3>
                  <p className="text-xs text-secondary dark:text-gray-400 mt-1 font-mono break-all">
                    {selectedItem.id}
                  </p>
                  {selectedItem.supersedes_memory_id && (
                    <button
                      onClick={() => selectMemoryItem(selectedItem.supersedes_memory_id || null)}
                      className="mt-2 inline-flex items-center px-2.5 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                    >
                      {t('openPredecessor' as any) || 'Open Predecessor'}: {selectedItem.supersedes_memory_id}
                    </button>
                  )}
                </div>
                <div className="text-xs text-secondary dark:text-gray-400 space-y-1">
                  <div>{t('observedAt' as any) || 'Observed'}: {formatLocalDateTime(selectedItem.observed_at)}</div>
                  <div>{t('updatedAt' as any) || 'Updated'}: {formatLocalDateTime(selectedItem.updated_at)}</div>
                  {selectedItem.last_confirmed_at && (
                    <div>{t('confirmedAt' as any) || 'Confirmed'}: {formatLocalDateTime(selectedItem.last_confirmed_at)}</div>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="rounded-lg bg-surface-accent dark:bg-gray-900/50 border border-default dark:border-gray-700 p-4">
                  <div className="text-xs font-medium text-secondary dark:text-gray-400 mb-2">
                    {t('claim' as any) || 'Claim'}
                  </div>
                  <p className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                    {selectedItem.claim}
                  </p>
                </div>
                <div className="rounded-lg bg-surface-accent dark:bg-gray-900/50 border border-default dark:border-gray-700 p-4">
                  <div className="text-xs font-medium text-secondary dark:text-gray-400 mb-2">
                    {t('summary' as any) || 'Summary'}
                  </div>
                  <p className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                    {selectedItem.summary}
                  </p>
                </div>
              </div>

              <div className="rounded-lg border border-default dark:border-gray-700 p-4 space-y-3">
                <div className="text-sm font-semibold text-primary dark:text-gray-100">
                  {t('memoryTransitions' as any) || 'Memory Transitions'}
                </div>
                <div className="grid grid-cols-2 xl:grid-cols-4 gap-2">
                  <div className="rounded border border-default dark:border-gray-700 bg-surface-accent dark:bg-gray-900/40 px-3 py-2">
                    <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
                      {t('deliberation' as any) || 'Deliberation'}
                    </div>
                    <div className="mt-1 text-sm font-semibold text-primary dark:text-gray-100">
                      {evidenceCoverage.deliberation}
                    </div>
                  </div>
                  <div className="rounded border border-default dark:border-gray-700 bg-surface-accent dark:bg-gray-900/40 px-3 py-2">
                    <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
                      {t('execution' as any) || 'Execution'}
                    </div>
                    <div className="mt-1 text-sm font-semibold text-primary dark:text-gray-100">
                      {evidenceCoverage.execution}
                    </div>
                  </div>
                  <div className="rounded border border-default dark:border-gray-700 bg-surface-accent dark:bg-gray-900/40 px-3 py-2">
                    <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
                      {t('governance' as any) || 'Governance'}
                    </div>
                    <div className="mt-1 text-sm font-semibold text-primary dark:text-gray-100">
                      {evidenceCoverage.governance}
                    </div>
                  </div>
                  <div className="rounded border border-default dark:border-gray-700 bg-surface-accent dark:bg-gray-900/40 px-3 py-2">
                    <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
                      {t('supportLinks' as any) || 'Support Links'}
                    </div>
                    <div className="mt-1 text-sm font-semibold text-primary dark:text-gray-100">
                      {evidenceCoverage.support}
                    </div>
                  </div>
                </div>
                <div className="space-y-2">
                  {transitionCues.map((cue) => (
                    <div
                      key={cue.id}
                      className={`rounded border px-3 py-2 ${cueToneClass(cue.tone)}`}
                    >
                      <div className="text-sm font-medium">{cue.title}</div>
                      <div className="mt-1 text-xs leading-5 opacity-90">{cue.body}</div>
                    </div>
                  ))}
                </div>
                <textarea
                  value={transitionReason}
                  onChange={(e) => setTransitionReason(e.target.value)}
                  placeholder={t('transitionReasonPlaceholder' as any) || 'Optional reason for this transition'}
                  className="w-full min-h-[88px] px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                />
                <div className="flex flex-wrap gap-2">
                  {selectedItem.lifecycle_status === 'candidate' && (
                    <button
                      type="button"
                      onClick={() => setTransitionReason(verifyReasonSuggestion)}
                      className="inline-flex items-center gap-2 px-2.5 py-1.5 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                    >
                      {t('useVerifyReason' as any) || 'Use verify reason'}
                    </button>
                  )}
                  {selectedItem.lifecycle_status === 'active' && (
                    <>
                      <button
                        type="button"
                        onClick={() => setTransitionReason(staleReasonSuggestion)}
                        className="inline-flex items-center gap-2 px-2.5 py-1.5 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                      >
                        {t('useStaleReason' as any) || 'Use stale reason'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setTransitionReason(supersedeReasonSuggestion)}
                        className="inline-flex items-center gap-2 px-2.5 py-1.5 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                      >
                        {t('useSupersedeReason' as any) || 'Use supersede reason'}
                      </button>
                    </>
                  )}
                </div>
                {actionError && (
                  <div className="text-sm text-red-700 dark:text-red-300">{actionError}</div>
                )}
                <div className="flex flex-wrap gap-2">
                  {selectedItem.lifecycle_status === 'candidate' && (
                    <button
                      onClick={() => void handleTransition('verify')}
                      disabled={actionLoading}
                      className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-60"
                    >
                      <CheckCircle2 size={14} />
                      {t('verify' as any) || 'Verify'}
                    </button>
                  )}
                  {selectedItem.lifecycle_status === 'active' && (
                    <>
                      <button
                        onClick={() => void handleTransition('stale')}
                        disabled={actionLoading}
                        className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded bg-slate-600 text-white hover:bg-slate-700 disabled:opacity-60"
                      >
                        <Clock3 size={14} />
                        {t('markStale' as any) || 'Mark Stale'}
                      </button>
                      <button
                        onClick={() => setSupersedeDraftOpen((value) => !value)}
                        disabled={actionLoading}
                        className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-60"
                      >
                        <GitBranchPlus size={14} />
                        {t('supersede' as any) || 'Supersede'}
                      </button>
                    </>
                  )}
                </div>

                {supersedeDraftOpen && selectedItem.lifecycle_status === 'active' && (
                  <div className="grid grid-cols-1 gap-3 border-t border-default dark:border-gray-700 pt-3">
                    {successorDraftSuggestion && (
                      <div className="rounded border border-default dark:border-gray-700 bg-surface-accent dark:bg-gray-900/40 px-3 py-3">
                        <div className="text-xs font-medium text-secondary dark:text-gray-400">
                          {t('suggestedSuccessorDraft' as any) || 'Suggested successor draft'}
                        </div>
                        <div className="mt-1 text-sm text-gray-800 dark:text-gray-200">
                          {t('primaryAnchor' as any) || 'Primary anchor'}:{' '}
                          {successorDraftSuggestion?.primary_evidence_id ||
                            primaryEvidence?.evidence_id ||
                            (t('currentMemoryClaim' as any) || 'current memory claim')}
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => {
                              setSuccessorTitle(successorDraftSuggestion.title);
                              setSuccessorClaim(successorDraftSuggestion.claim);
                              setSuccessorSummary(successorDraftSuggestion.summary);
                            }}
                            className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                          >
                            {t('useSuggestedDraft' as any) || 'Use Suggested Draft'}
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setSuccessorTitle('');
                              setSuccessorClaim('');
                              setSuccessorSummary('');
                            }}
                            className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded bg-surface-secondary dark:bg-gray-700 text-primary dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                          >
                            {t('clearDraft' as any) || 'Clear Draft'}
                          </button>
                        </div>
                      </div>
                    )}
                    <input
                      value={successorTitle}
                      onChange={(e) => setSuccessorTitle(e.target.value)}
                      placeholder={t('successorTitle' as any) || 'Successor title (optional)'}
                      className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                    <textarea
                      value={successorClaim}
                      onChange={(e) => setSuccessorClaim(e.target.value)}
                      placeholder={t('successorClaim' as any) || 'Successor claim (optional)'}
                      className="w-full min-h-[88px] px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                    <textarea
                      value={successorSummary}
                      onChange={(e) => setSuccessorSummary(e.target.value)}
                      placeholder={t('successorSummary' as any) || 'Successor summary (optional)'}
                      className="w-full min-h-[88px] px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                    <div className="flex justify-end">
                      <button
                        onClick={() =>
                          void handleTransition('supersede', {
                            successor_title: successorTitle || undefined,
                            successor_claim: successorClaim || undefined,
                            successor_summary: successorSummary || undefined,
                          })
                        }
                        disabled={actionLoading}
                        className="inline-flex items-center gap-2 px-3 py-2 text-sm rounded bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-60"
                      >
                        <GitBranchPlus size={14} />
                        {t('createSuccessor' as any) || 'Create Successor'}
                      </button>
                    </div>
                  </div>
                )}
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                <div className="rounded-lg border border-default dark:border-gray-700 p-4">
                  <div className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
                    {t('versions' as any) || 'Versions'}
                  </div>
                  <div className="space-y-3">
                    {selectedDetail.versions.length === 0 ? (
                      <div className="text-sm text-secondary dark:text-gray-400">
                        {t('noVersions' as any) || 'No versions recorded.'}
                      </div>
                    ) : (
                      selectedDetail.versions.map((version) => (
                        <div key={version.id} className="rounded bg-surface-accent dark:bg-gray-900/40 p-3">
                          <div className="flex items-center justify-between gap-3 mb-1">
                            <div className="text-xs font-medium text-primary dark:text-gray-100">
                              v{version.version_no}
                            </div>
                            <div className="text-xs text-secondary dark:text-gray-400">
                              {prettyLabel(version.update_mode)}
                            </div>
                          </div>
                          <div className="text-xs text-secondary dark:text-gray-400 mb-2">
                            {formatLocalDateTime(version.created_at)}
                          </div>
                          <div className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                            {version.summary_snapshot || version.claim_snapshot}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div className="rounded-lg border border-default dark:border-gray-700 p-4">
                  <div className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
                    {t('evidence' as any) || 'Evidence'}
                  </div>
                  {selectedDetail.evidence.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-3">
                      <button
                        onClick={() => setEvidenceTypeFilter('all')}
                        className={`px-2.5 py-1 text-xs rounded transition-colors ${
                          evidenceTypeFilter === 'all'
                            ? 'bg-blue-600 text-white'
                            : 'bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300'
                        }`}
                      >
                        {t('all' as any) || 'All'} ({selectedDetail.evidence.length})
                      </button>
                      {Object.entries(evidenceTypeCounts).map(([evidenceType, count]) => (
                        <button
                          key={evidenceType}
                          onClick={() => setEvidenceTypeFilter(evidenceType)}
                          className={`px-2.5 py-1 text-xs rounded transition-colors ${
                          evidenceTypeFilter === evidenceType
                              ? 'bg-blue-600 text-white'
                              : 'bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300'
                          }`}
                        >
                          {evidenceDisplayName(evidenceType, t)} ({count})
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="space-y-3">
                    {selectedDetail.evidence.length === 0 ? (
                      <div className="text-sm text-secondary dark:text-gray-400">
                        {t('noEvidence' as any) || 'No evidence links recorded.'}
                      </div>
                    ) : filteredEvidence.length === 0 ? (
                      <div className="text-sm text-secondary dark:text-gray-400">
                        {t('noEvidenceForFilter' as any) || 'No evidence matches this filter.'}
                      </div>
                    ) : (
                      filteredEvidence.map((link) => {
                        const metadataRows = evidenceMetadataRows(link, t);
                        return (
                        <div key={link.id} className="rounded bg-surface-accent dark:bg-gray-900/40 p-3">
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
                              {evidenceDisplayName(link.evidence_type, t)}
                            </span>
                            <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
                              {translateMappedValue(link.link_role, t, EVIDENCE_ROLE_KEYS)}
                            </span>
                            {typeof link.confidence === 'number' && (
                              <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
                                {(t('confidence' as any) || 'Confidence')} {Math.round(link.confidence * 100)}%
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-secondary dark:text-gray-400 mb-2 font-mono break-all">
                            {link.evidence_id}
                          </div>
                          {link.excerpt && (
                            <div className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap mb-3">
                              {link.excerpt}
                            </div>
                          )}
                          {metadataRows.length > 0 && (
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                              {metadataRows.map((row) => (
                                <div
                                  key={`${link.id}-${row.label}`}
                                  className="rounded border border-default dark:border-gray-700 px-2.5 py-2"
                                >
                                  <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
                                    {row.label}
                                  </div>
                                  <div className="text-xs text-primary dark:text-gray-200 break-all">
                                    {row.value}
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                          {link.artifact_landing && (
                            <div className="mt-3 rounded border border-default dark:border-gray-700 p-3">
                              <div className="text-xs font-semibold uppercase tracking-wide text-secondary dark:text-gray-400 mb-2">
                                {t('landing' as any) || 'Landing'}
                              </div>
                              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-3">
                                <div className="rounded border border-default dark:border-gray-700 px-2.5 py-2">
                                  <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
                                    {t('artifactDir' as any) || 'Artifact Dir'}
                                  </div>
                                  <div className="text-xs text-primary dark:text-gray-200">
                                    {link.artifact_landing.artifact_dir_exists
                                      ? t('available' as any) || 'Available'
                                      : t('missing' as any) || 'Missing'}
                                  </div>
                                </div>
                                <div className="rounded border border-default dark:border-gray-700 px-2.5 py-2">
                                  <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
                                    {t('resultJson' as any) || 'Result JSON'}
                                  </div>
                                  <div className="text-xs text-primary dark:text-gray-200">
                                    {link.artifact_landing.result_json_exists
                                      ? t('available' as any) || 'Available'
                                      : t('missing' as any) || 'Missing'}
                                  </div>
                                </div>
                                <div className="rounded border border-default dark:border-gray-700 px-2.5 py-2">
                                  <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
                                    {t('summaryFile' as any) || 'Summary File'}
                                  </div>
                                  <div className="text-xs text-primary dark:text-gray-200">
                                    {link.artifact_landing.summary_md_exists
                                      ? t('available' as any) || 'Available'
                                      : t('missing' as any) || 'Missing'}
                                  </div>
                                </div>
                              </div>
                              <div className="space-y-2">
                                {link.artifact_landing.landed_at && (
                                  <div className="text-xs text-secondary dark:text-gray-400">
                                    {(t('landedAt' as any) || 'Landed at')} {formatLocalDateTime(link.artifact_landing.landed_at)}
                                  </div>
                                )}
                                {link.artifact_landing.attachments.length > 0 && (
                                  <div>
                                    <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400 mb-1">
                                      {(t('attachments' as any) || 'Attachments')} ({link.artifact_landing.attachments_count})
                                    </div>
                                    <div className="flex flex-wrap gap-2">
                                      {link.artifact_landing.attachments.map((attachmentPath) => (
                                        <span
                                          key={`${link.id}-${attachmentPath}`}
                                          className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300"
                                          title={attachmentPath}
                                        >
                                          {fileLabelFromPath(attachmentPath)}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}
                          {link.execution_trace_drilldown && (
                            <div className="mt-3 rounded border border-default dark:border-gray-700 p-3">
                              <div className="text-xs font-semibold uppercase tracking-wide text-secondary dark:text-gray-400 mb-2">
                                {t('trace' as any) || 'Trace'}
                              </div>
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                <div className="rounded border border-default dark:border-gray-700 px-2.5 py-2">
                                  <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
                                    {t('traceFile' as any) || 'Trace File'}
                                  </div>
                                  <div className="text-xs text-primary dark:text-gray-200 break-all">
                                    {link.execution_trace_drilldown.trace_file_path || (t('unavailable' as any) || 'Unavailable')}
                                  </div>
                                </div>
                                <div className="rounded border border-default dark:border-gray-700 px-2.5 py-2">
                                  <div className="text-[11px] uppercase tracking-wide text-secondary dark:text-gray-400">
                                    {t('traceFileStatus' as any) || 'Trace File Status'}
                                  </div>
                                  <div className="text-xs text-primary dark:text-gray-200">
                                    {link.execution_trace_drilldown.trace_file_exists
                                      ? t('available' as any) || 'Available'
                                      : t('missing' as any) || 'Missing'}
                                  </div>
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      )})
                    )}
                  </div>
                </div>

                <div className="rounded-lg border border-default dark:border-gray-700 p-4">
                  <div className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
                    {t('relatedKnowledge' as any) || 'Related Knowledge'}
                  </div>
                  <div className="space-y-3">
                    {selectedDetail.personal_knowledge_projections.length === 0 ? (
                      <div className="text-sm text-secondary dark:text-gray-400">
                        {t('noKnowledgeProjections' as any) || 'No personal knowledge projections.'}
                      </div>
                    ) : (
                      selectedDetail.personal_knowledge_projections.map((entry) => (
                        <div key={entry.id} className="rounded bg-surface-accent dark:bg-gray-900/40 p-3">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
                              {entry.knowledge_type}
                            </span>
                            <span className={`px-2 py-1 text-xs rounded ${badgeClass(entry.status)}`}>
                              {translateMemoryStatus(entry.status, t)}
                            </span>
                          </div>
                          <div className="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">
                            {entry.content}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div className="rounded-lg border border-default dark:border-gray-700 p-4">
                  <div className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
                    {t('relatedGoals' as any) || 'Related Goals'}
                  </div>
                  <div className="space-y-3">
                    {selectedDetail.goal_projections.length === 0 ? (
                      <div className="text-sm text-secondary dark:text-gray-400">
                        {t('noGoalProjections' as any) || 'No goal projections.'}
                      </div>
                    ) : (
                      selectedDetail.goal_projections.map((entry) => (
                        <div key={entry.id} className="rounded bg-surface-accent dark:bg-gray-900/40 p-3">
                          <div className="flex items-center gap-2 mb-1">
                            <span className={`px-2 py-1 text-xs rounded ${badgeClass(entry.status)}`}>
                              {translateMemoryStatus(entry.status, t)}
                            </span>
                            <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
                              {prettyLabel(entry.horizon)}
                            </span>
                          </div>
                          <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                            {entry.title}
                          </div>
                          <div className="text-sm text-gray-700 dark:text-gray-300">
                            {entry.description}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>

              <div className="rounded-lg border border-default dark:border-gray-700 p-4">
                <div className="text-sm font-semibold text-primary dark:text-gray-100 mb-3">
                  {t('outgoingEdges' as any) || 'Outgoing Edges'}
                </div>
                <div className="space-y-3">
                  {selectedDetail.outgoing_edges.length === 0 ? (
                    <div className="text-sm text-secondary dark:text-gray-400">
                      {t('noOutgoingEdges' as any) || 'No outgoing edges recorded.'}
                    </div>
                  ) : (
                    selectedDetail.outgoing_edges.map((edge) => (
                        <div key={edge.id} className="rounded bg-surface-accent dark:bg-gray-900/40 p-3">
                          <div className="flex flex-wrap items-center gap-2 mb-1">
                            <span className="px-2 py-1 text-xs rounded bg-surface-secondary dark:bg-gray-700 text-secondary dark:text-gray-300">
                              {prettyLabel(edge.edge_type)}
                            </span>
                          <span className="text-xs text-secondary dark:text-gray-400">
                            {formatLocalDateTime(edge.created_at)}
                          </span>
                        </div>
                        <button
                          onClick={() => selectMemoryItem(edge.to_memory_id)}
                          className="text-xs text-blue-700 dark:text-blue-300 font-mono break-all hover:underline"
                        >
                          {edge.to_memory_id}
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
