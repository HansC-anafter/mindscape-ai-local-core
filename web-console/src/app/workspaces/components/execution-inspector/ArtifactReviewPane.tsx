'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type {
  ReviewBundleArtifact,
  ReviewChecklistItemView,
  VisualAcceptanceBundleContent,
  VisualAcceptanceSlotView,
} from './types/execution';
import {
  buildSuggestedFollowupActions,
  FOLLOWUP_ACTION_OPTIONS,
  followupActionDescription,
  followupActionLabel,
  normalizeFollowupActions,
} from './utils/artifact-review';

interface ArtifactReviewPaneProps {
  artifact: ReviewBundleArtifact | null;
  workspaceId?: string;
  apiUrl?: string;
  onArtifactUpdated?: (artifact: ReviewBundleArtifact) => void;
}

interface ReviewMediaEntry {
  id: string;
  title: string;
  url: string;
  kind: string;
}

interface RelatedBundleCandidateView {
  artifact: ReviewBundleArtifact;
  score: number;
  reasons: string[];
}

interface ComparePresetOption {
  id: string;
  label: string;
  count: number;
}

type OverlayCompareMode = 'overlay' | 'difference';

interface OverlayComparePair {
  id: string;
  current: ReviewMediaEntry;
  compare: ReviewMediaEntry;
}

interface BaselineGalleryItem {
  artifact: ReviewBundleArtifact;
  preview: ReviewMediaEntry | null;
}

interface RunMatrixRow {
  runId: string;
  bundleCount: number;
  acceptedCount: number;
  needsTuneCount: number;
  rejectedCount: number;
  pendingCount: number;
  presets: string[];
  latestReviewedAt?: string;
}

function resolveUrl(apiUrl: string | undefined, url: string): string {
  if (!url) return '';
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url;
  }
  if (!apiUrl) {
    return url;
  }
  return url.startsWith('/') ? `${apiUrl}${url}` : `${apiUrl}/${url}`;
}

function formatTimestampLabel(value: string | undefined): string {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString('en-US', { hour12: false });
}

function formatBBoxLabel(
  bbox:
    | {
        x?: number;
        y?: number;
        width?: number;
        height?: number;
      }
    | null
    | undefined,
): string {
  if (!bbox) return '-';
  return `x=${bbox.x ?? 0}, y=${bbox.y ?? 0}, w=${bbox.width ?? 0}, h=${bbox.height ?? 0}`;
}

function checklistScoreLabel(score: number): string {
  if (score >= 1) return 'Good';
  if (score >= 0.5) return 'Fair';
  return 'Poor';
}

function stateTone(value: string | undefined): string {
  const normalized = String(value || '').toLowerCase();
  if (['accepted', 'auto_approved', 'completed', 'ok'].includes(normalized)) {
    return 'border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-950/30 dark:text-green-300';
  }
  if (['needs_tune', 'pending_review', 'manual_required'].includes(normalized)) {
    return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-300';
  }
  if (['blocked', 'rejected', 'escalate_local_scene'].includes(normalized)) {
    return 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-300';
  }
  if (['contact_zone', 'object_only', 'local_scene'].includes(normalized)) {
    return 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950/30 dark:text-blue-300';
  }
  return 'border-gray-200 bg-gray-50 text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300';
}

function stateLabel(value: string | undefined): string {
  const normalized = String(value || '').toLowerCase();
  const labels: Record<string, string> = {
    accepted: 'Accepted',
    auto_approved: 'Auto Approved',
    pending_review: 'Pending Review',
    needs_tune: 'Needs Tune',
    rejected: 'Rejected',
    manual_required: 'Manual Required',
    blocked: 'Blocked',
    contact_zone: 'Contact Zone',
    object_only: 'Object Only',
    local_scene: 'Local Scene',
    escalate_local_scene: 'Escalate Local Scene',
  };
  return labels[normalized] || value || '-';
}

function normalizeReviewBundleArtifact(apiArtifact: any): ReviewBundleArtifact {
  return {
    id: apiArtifact.id,
    name: apiArtifact.title || apiArtifact.name || 'Untitled',
    title: apiArtifact.title,
    description: apiArtifact.description,
    type: apiArtifact.type || apiArtifact.artifact_type || 'other',
    createdAt: apiArtifact.created_at,
    updatedAt: apiArtifact.updated_at,
    filePath: apiArtifact.file_path || undefined,
    metadata: apiArtifact.metadata || {},
    content: (apiArtifact.content || {}) as VisualAcceptanceBundleContent,
    executionId: apiArtifact.execution_id,
    artifactType: apiArtifact.artifact_type || null,
  };
}

function StatusBadge({ label, value }: { label: string; value: string | undefined }) {
  return (
    <span
      className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${stateTone(value)}`}
    >
      {label}: {stateLabel(value)}
    </span>
  );
}

function MediaPreviewCard({
  title,
  url,
  kind,
  apiUrl,
}: {
  title: string;
  url: string;
  kind: string;
  apiUrl?: string;
}) {
  const resolvedUrl = resolveUrl(apiUrl, url);
  if (!resolvedUrl) {
    return null;
  }

  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
      <div className="border-b border-gray-200 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:border-gray-700 dark:text-gray-400">
        {title}
      </div>
      <div className="bg-gray-100 dark:bg-gray-950">
        {kind === 'video' ? (
          <video
            src={resolvedUrl}
            controls
            preload="metadata"
            className="h-56 w-full bg-black object-contain"
          />
        ) : kind === 'image' ? (
          <img
            src={resolvedUrl}
            alt={title}
            className="h-56 w-full bg-black object-contain"
          />
        ) : (
          <div className="flex h-56 items-center justify-center px-4 text-sm text-gray-500 dark:text-gray-400">
            This slot is not a directly embeddable media preview.
          </div>
        )}
      </div>
      <div className="border-t border-gray-200 px-3 py-2 text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400">
        <a href={resolvedUrl} target="_blank" rel="noreferrer" className="break-all hover:text-gray-700 dark:hover:text-gray-200">
          {url}
        </a>
      </div>
    </div>
  );
}

function OverlayCompareCard({
  pair,
  apiUrl,
  mode,
  overlayOpacity,
}: {
  pair: OverlayComparePair;
  apiUrl?: string;
  mode: OverlayCompareMode;
  overlayOpacity: number;
}) {
  const currentUrl = resolveUrl(apiUrl, pair.current.url);
  const compareUrl = resolveUrl(apiUrl, pair.compare.url);

  if (!currentUrl || !compareUrl || pair.current.kind !== 'image' || pair.compare.kind !== 'image') {
    return (
      <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400">
        Overlay and diff compare are currently available only for image-to-image pairs.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900">
      <div className="border-b border-gray-200 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:border-gray-700 dark:text-gray-400">
        {pair.current.title}
      </div>
      <div className="relative h-72 overflow-hidden bg-black">
        <img
          src={currentUrl}
          alt={`${pair.current.title} current`}
          className="absolute inset-0 h-full w-full object-contain"
        />
        <img
          src={compareUrl}
          alt={`${pair.current.title} compare`}
          className="absolute inset-0 h-full w-full object-contain"
          style={
            mode === 'overlay'
              ? { opacity: overlayOpacity / 100 }
              : { mixBlendMode: 'difference', opacity: 1 }
          }
        />
        <div className="absolute left-3 top-3 rounded-full bg-black/65 px-2 py-1 text-[11px] text-white">
          current
        </div>
        <div className="absolute right-3 top-3 rounded-full bg-white/85 px-2 py-1 text-[11px] text-gray-900">
          compare
        </div>
      </div>
      <div className="grid gap-2 border-t border-gray-200 px-3 py-3 text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400">
        <div>current={pair.current.url}</div>
        <div>compare={pair.compare.url}</div>
      </div>
    </div>
  );
}

function buildMediaEntries(slots: VisualAcceptanceSlotView[] | undefined): ReviewMediaEntry[] {
  if (!slots?.length) {
    return [];
  }

  const entries: ReviewMediaEntry[] = [];
  slots.forEach((slot, index) => {
    const label = slot.label || slot.slot_key || `slot_${index}`;
    if (slot.preview_url) {
      entries.push({
        id: `${label}:preview`,
        title: `${label} / preview`,
        url: slot.preview_url,
        kind: slot.preview_kind || 'image',
      });
    }
    if (slot.mask_preview_url) {
      entries.push({
        id: `${label}:mask`,
        title: `${label} / mask`,
        url: slot.mask_preview_url,
        kind: slot.mask_preview_kind || 'image',
      });
    }
    if (slot.alpha_preview_url) {
      entries.push({
        id: `${label}:alpha`,
        title: `${label} / alpha`,
        url: slot.alpha_preview_url,
        kind: slot.alpha_preview_kind || 'image',
      });
    }
  });
  return entries;
}

function buildPrimaryMediaEntry(slots: VisualAcceptanceSlotView[] | undefined): ReviewMediaEntry | null {
  const entries = buildMediaEntries(slots);
  if (!entries.length) {
    return null;
  }
  return entries.find((entry) => entry.kind === 'image') || entries[0] || null;
}

function buildOverlayPairs(
  currentEntries: ReviewMediaEntry[],
  compareEntries: ReviewMediaEntry[],
): OverlayComparePair[] {
  const currentImages = currentEntries.filter((entry) => entry.kind === 'image');
  const compareImages = compareEntries.filter((entry) => entry.kind === 'image');
  if (!currentImages.length || !compareImages.length) {
    return [];
  }

  const compareById = new Map(compareImages.map((entry) => [entry.id, entry]));
  const usedIds = new Set<string>();
  const pairs: OverlayComparePair[] = [];

  currentImages.forEach((entry, index) => {
    let match = compareById.get(entry.id);
    if (!match) {
      match = compareImages.find((candidate, candidateIndex) => (
        !usedIds.has(candidate.id) && candidateIndex === index
      ));
    }
    if (!match || usedIds.has(match.id)) {
      return;
    }
    usedIds.add(match.id);
    pairs.push({
      id: `${entry.id}:${match.id}`,
      current: entry,
      compare: match,
    });
  });

  return pairs.slice(0, 4);
}

function buildRunMatrixRows(artifacts: ReviewBundleArtifact[]): RunMatrixRow[] {
  const rows = new Map<string, RunMatrixRow>();

  artifacts.forEach((artifact) => {
    const content = artifact.content || {};
    const runId = String(content.run_id || '').trim() || 'unknown';
    const decision = reviewDecisionValue(artifact);
    const preset = presetLabel(content.preset_id);
    const reviewedAt = reviewedAtValue(artifact);

    const row = rows.get(runId) || {
      runId,
      bundleCount: 0,
      acceptedCount: 0,
      needsTuneCount: 0,
      rejectedCount: 0,
      pendingCount: 0,
      presets: [],
      latestReviewedAt: undefined,
    };

    row.bundleCount += 1;
    if (!row.presets.includes(preset)) {
      row.presets.push(preset);
      row.presets.sort((left, right) => left.localeCompare(right));
    }

    if (decision === 'accepted') {
      row.acceptedCount += 1;
    } else if (decision === 'needs_tune') {
      row.needsTuneCount += 1;
    } else if (decision === 'rejected' || decision === 'manual_required') {
      row.rejectedCount += 1;
    } else {
      row.pendingCount += 1;
    }

    if (toTimestamp(reviewedAt) > toTimestamp(row.latestReviewedAt)) {
      row.latestReviewedAt = reviewedAt;
    }

    rows.set(runId, row);
  });

  return Array.from(rows.values()).sort((left, right) => {
    const timeDelta = toTimestamp(right.latestReviewedAt) - toTimestamp(left.latestReviewedAt);
    if (timeDelta !== 0) {
      return timeDelta;
    }
    return right.bundleCount - left.bundleCount;
  });
}

function toTimestamp(value: string | undefined): number {
  if (!value) return 0;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? 0 : parsed.getTime();
}

function normalizedPresetKey(value: string | null | undefined): string {
  const normalized = String(value || '').trim();
  return normalized || '__none__';
}

function presetLabel(value: string | null | undefined): string {
  const normalized = String(value || '').trim();
  return normalized || 'unassigned';
}

function bundleTitle(artifact: ReviewBundleArtifact | null | undefined): string {
  const content = artifact?.content || {};
  return content.scene_id || artifact?.name || artifact?.id || 'bundle';
}

function reviewDecisionValue(artifact: ReviewBundleArtifact | null | undefined): string {
  const content = artifact?.content || {};
  return String(content.latest_review_decision?.decision || content.status || '').trim().toLowerCase();
}

function reviewedAtValue(artifact: ReviewBundleArtifact | null | undefined): string | undefined {
  const content = artifact?.content || {};
  return content.latest_review_decision?.reviewed_at || artifact?.updatedAt || artifact?.createdAt;
}

function buildRelatedBundleCandidate(
  currentArtifact: ReviewBundleArtifact,
  candidateArtifact: ReviewBundleArtifact,
): RelatedBundleCandidateView | null {
  if (currentArtifact.id === candidateArtifact.id) {
    return null;
  }
  const current = currentArtifact.content || {};
  const candidate = candidateArtifact.content || {};

  const reasons: string[] = [];
  let score = 0;

  if (current.scene_id && candidate.scene_id && current.scene_id === candidate.scene_id) {
    reasons.push('same_scene');
    score += 6;
  }
  if (current.package_id && candidate.package_id && current.package_id === candidate.package_id) {
    reasons.push('same_package');
    score += 5;
  }
  if (current.preset_id && candidate.preset_id && current.preset_id === candidate.preset_id) {
    reasons.push('same_preset');
    score += 4;
  }
  if (current.source_kind && candidate.source_kind && current.source_kind === candidate.source_kind) {
    reasons.push('same_source_kind');
    score += 3;
  }
  if (current.binding_mode && candidate.binding_mode && current.binding_mode === candidate.binding_mode) {
    reasons.push('same_binding_mode');
    score += 2;
  }

  if (!score) {
    return null;
  }

  return {
    artifact: candidateArtifact,
    score,
    reasons,
  };
}

export default function ArtifactReviewPane({
  artifact,
  workspaceId,
  apiUrl,
  onArtifactUpdated,
}: ArtifactReviewPaneProps) {
  const initializedArtifactKeyRef = useRef('');
  const [reviewerId, setReviewerId] = useState('');
  const [reviewNotes, setReviewNotes] = useState('');
  const [reviewChecklistScores, setReviewChecklistScores] = useState<Record<string, number>>({});
  const [selectedFollowupActions, setSelectedFollowupActions] = useState<string[]>([]);
  const [savingReviewDecision, setSavingReviewDecision] = useState(false);
  const [reviewDecisionResult, setReviewDecisionResult] = useState<string | null>(null);
  const [relatedBundleCatalog, setRelatedBundleCatalog] = useState<ReviewBundleArtifact[]>([]);
  const [relatedCatalogLoading, setRelatedCatalogLoading] = useState(false);
  const [selectedBaselineId, setSelectedBaselineId] = useState<string | null>(null);
  const [selectedHistoryBundleId, setSelectedHistoryBundleId] = useState<string | null>(null);
  const [selectedComparePresetId, setSelectedComparePresetId] = useState<string>('all');
  const [selectedCompareArtifactIds, setSelectedCompareArtifactIds] = useState<string[]>([]);
  const [overlayCompareTargetId, setOverlayCompareTargetId] = useState<string | null>(null);
  const [overlayCompareMode, setOverlayCompareMode] = useState<OverlayCompareMode>('overlay');
  const [overlayOpacity, setOverlayOpacity] = useState(50);

  const content = artifact?.content;
  const latestDecision = content?.latest_review_decision;
  const checklistTemplate = content?.checklist_template || [];
  const mediaEntries = useMemo(() => buildMediaEntries(content?.slots), [content?.slots]);
  const relatedCandidates = useMemo(
    () =>
      artifact
        ? relatedBundleCatalog
            .map((candidate) => buildRelatedBundleCandidate(artifact, candidate))
            .filter((candidate): candidate is RelatedBundleCandidateView => Boolean(candidate))
            .sort((left, right) => {
              if (right.score !== left.score) {
                return right.score - left.score;
              }
              return toTimestamp(reviewedAtValue(right.artifact)) - toTimestamp(reviewedAtValue(left.artifact));
            })
        : [],
    [artifact, relatedBundleCatalog],
  );
  const baselineCandidates = useMemo(
    () =>
      relatedCandidates
        .filter((candidate) => reviewDecisionValue(candidate.artifact) === 'accepted')
        .slice(0, 6),
    [relatedCandidates],
  );
  const historyCandidates = useMemo(
    () => relatedCandidates.slice(0, 12),
    [relatedCandidates],
  );
  const comparePresetOptions = useMemo(() => {
    const counts = new Map<string, number>();
    relatedCandidates.forEach((candidate) => {
      const key = normalizedPresetKey(candidate.artifact.content?.preset_id);
      counts.set(key, (counts.get(key) || 0) + 1);
    });

    return [
      { id: 'all', label: 'all presets', count: relatedCandidates.length },
      ...Array.from(counts.entries())
        .map(([key, count]) => ({
          id: key,
          label: presetLabel(key === '__none__' ? '' : key),
          count,
        }))
        .sort((left, right) => {
          if (right.count !== left.count) {
            return right.count - left.count;
          }
          return left.label.localeCompare(right.label);
        }),
    ] satisfies ComparePresetOption[];
  }, [relatedCandidates]);
  const filteredCompareCandidates = useMemo(
    () =>
      relatedCandidates.filter((candidate) => (
        selectedComparePresetId === 'all'
          ? true
          : normalizedPresetKey(candidate.artifact.content?.preset_id) === selectedComparePresetId
      )),
    [relatedCandidates, selectedComparePresetId],
  );
  const selectedCompareCandidates = useMemo(
    () =>
      selectedCompareArtifactIds
        .map((artifactId) => filteredCompareCandidates.find((candidate) => candidate.artifact.id === artifactId))
        .filter((candidate): candidate is RelatedBundleCandidateView => Boolean(candidate)),
    [filteredCompareCandidates, selectedCompareArtifactIds],
  );
  const compareBoardBundles = useMemo(
    () => [
      artifact,
      ...selectedCompareCandidates.map((candidate) => candidate.artifact),
    ].filter((item): item is ReviewBundleArtifact => Boolean(item)),
    [artifact, selectedCompareCandidates],
  );
  const relatedBundleUniverse = useMemo(() => {
    const items = [artifact, ...relatedCandidates.map((candidate) => candidate.artifact)]
      .filter((item): item is ReviewBundleArtifact => Boolean(item));
    const seen = new Set<string>();
    return items.filter((item) => {
      if (seen.has(item.id)) {
        return false;
      }
      seen.add(item.id);
      return true;
    });
  }, [artifact, relatedCandidates]);
  const baselineGalleryItems = useMemo(
    () =>
      baselineCandidates
        .map((candidate) => ({
          artifact: candidate.artifact,
          preview: buildPrimaryMediaEntry(candidate.artifact.content?.slots),
        }))
        .slice(0, 12),
    [baselineCandidates],
  );
  const runMatrixRows = useMemo(
    () => buildRunMatrixRows(relatedBundleUniverse),
    [relatedBundleUniverse],
  );
  const overlayCompareTarget = useMemo(
    () =>
      selectedCompareCandidates.find((candidate) => candidate.artifact.id === overlayCompareTargetId)
      || selectedCompareCandidates[0]
      || null,
    [overlayCompareTargetId, selectedCompareCandidates],
  );
  const overlayComparePairs = useMemo(
    () => buildOverlayPairs(
      mediaEntries,
      buildMediaEntries(overlayCompareTarget?.artifact.content?.slots),
    ),
    [mediaEntries, overlayCompareTarget?.artifact.content?.slots],
  );
  const selectedBaseline = useMemo(
    () =>
      baselineCandidates.find((candidate) => candidate.artifact.id === selectedBaselineId)
      || baselineCandidates[0]
      || null,
    [baselineCandidates, selectedBaselineId],
  );
  const baselineMediaEntries = useMemo(
    () => buildMediaEntries(selectedBaseline?.artifact.content?.slots),
    [selectedBaseline?.artifact.content?.slots],
  );
  const selectedHistoryBundle = useMemo(
    () =>
      historyCandidates.find((candidate) => candidate.artifact.id === selectedHistoryBundleId)
      || historyCandidates[0]
      || null,
    [historyCandidates, selectedHistoryBundleId],
  );
  const historyMediaEntries = useMemo(
    () => buildMediaEntries(selectedHistoryBundle?.artifact.content?.slots),
    [selectedHistoryBundle?.artifact.content?.slots],
  );
  const checklistAverage = useMemo(() => {
    const scores = Object.values(reviewChecklistScores);
    if (!scores.length) {
      return null;
    }
    return Number((scores.reduce((sum, score) => sum + score, 0) / scores.length).toFixed(2));
  }, [reviewChecklistScores]);
  const latestDecisionFollowupActions = useMemo(
    () => (
      Array.isArray(latestDecision?.followup_actions)
        ? normalizeFollowupActions(latestDecision?.followup_actions)
        : null
    ),
    [latestDecision?.followup_actions],
  );
  const suggestedFollowupActions = useMemo(
    () => buildSuggestedFollowupActions(content, { hasAcceptedBaseline: baselineCandidates.length > 0 }),
    [content, baselineCandidates.length],
  );

  useEffect(() => {
    const artifactResetKey = `${artifact?.id || ''}:${artifact?.updatedAt || ''}`;
    if (artifactResetKey && initializedArtifactKeyRef.current === artifactResetKey) {
      return;
    }
    initializedArtifactKeyRef.current = artifactResetKey;
    setReviewerId(latestDecision?.reviewer_id || '');
    setReviewNotes(latestDecision?.notes || '');
    setReviewChecklistScores(latestDecision?.checklist_scores || {});
    setSelectedFollowupActions(latestDecisionFollowupActions ?? suggestedFollowupActions);
    setReviewDecisionResult(null);
  }, [
    artifact?.id,
    artifact?.updatedAt,
    latestDecision?.checklist_scores,
    latestDecision?.notes,
    latestDecision?.reviewer_id,
    latestDecisionFollowupActions,
    suggestedFollowupActions,
  ]);

  useEffect(() => {
    if (latestDecisionFollowupActions) {
      return;
    }
    if (selectedFollowupActions.length > 0 || suggestedFollowupActions.length === 0) {
      return;
    }
    setSelectedFollowupActions(suggestedFollowupActions);
  }, [latestDecisionFollowupActions, selectedFollowupActions.length, suggestedFollowupActions]);

  useEffect(() => {
    setSelectedComparePresetId('all');
    setSelectedCompareArtifactIds([]);
    setOverlayCompareTargetId(null);
    setOverlayCompareMode('overlay');
    setOverlayOpacity(50);
  }, [artifact?.id]);

  useEffect(() => {
    if (!baselineCandidates.length) {
      setSelectedBaselineId(null);
      return;
    }
    if (!selectedBaselineId || !baselineCandidates.some((candidate) => candidate.artifact.id === selectedBaselineId)) {
      setSelectedBaselineId(baselineCandidates[0].artifact.id);
    }
  }, [baselineCandidates, selectedBaselineId]);

  useEffect(() => {
    if (!historyCandidates.length) {
      setSelectedHistoryBundleId(null);
      return;
    }
    if (!selectedHistoryBundleId || !historyCandidates.some((candidate) => candidate.artifact.id === selectedHistoryBundleId)) {
      setSelectedHistoryBundleId(historyCandidates[0].artifact.id);
    }
  }, [historyCandidates, selectedHistoryBundleId]);

  useEffect(() => {
    const presetStillExists = comparePresetOptions.some((option) => option.id === selectedComparePresetId);
    if (!presetStillExists) {
      setSelectedComparePresetId('all');
    }
  }, [comparePresetOptions, selectedComparePresetId]);

  useEffect(() => {
    const allowedIds = new Set(filteredCompareCandidates.map((candidate) => candidate.artifact.id));
    const keptIds = selectedCompareArtifactIds.filter((artifactId) => allowedIds.has(artifactId)).slice(0, 3);

    if (keptIds.length > 0) {
      if (
        keptIds.length !== selectedCompareArtifactIds.length
        || keptIds.some((artifactId, index) => artifactId !== selectedCompareArtifactIds[index])
      ) {
        setSelectedCompareArtifactIds(keptIds);
      }
      return;
    }

    if (!filteredCompareCandidates.length) {
      if (selectedCompareArtifactIds.length) {
        setSelectedCompareArtifactIds([]);
      }
      return;
    }

    setSelectedCompareArtifactIds(filteredCompareCandidates.slice(0, 3).map((candidate) => candidate.artifact.id));
  }, [filteredCompareCandidates, selectedCompareArtifactIds]);

  useEffect(() => {
    if (!selectedCompareCandidates.length) {
      setOverlayCompareTargetId(null);
      return;
    }
    if (!overlayCompareTargetId || !selectedCompareCandidates.some((candidate) => candidate.artifact.id === overlayCompareTargetId)) {
      setOverlayCompareTargetId(selectedCompareCandidates[0].artifact.id);
    }
  }, [overlayCompareTargetId, selectedCompareCandidates]);

  useEffect(() => {
    if (!artifact?.id || !workspaceId || !apiUrl) {
      setRelatedBundleCatalog([]);
      setRelatedCatalogLoading(false);
      return;
    }

    let cancelled = false;
    setRelatedCatalogLoading(true);

    const loadRelatedBundleCatalog = async () => {
      try {
        const params = new URLSearchParams({
          kind: 'visual_acceptance_bundle',
          include_content: 'true',
          limit: '200',
        });
        const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts?${params.toString()}`);
        if (cancelled) return;
        if (!response.ok) {
          throw new Error(`Failed to load related bundles: ${response.status}`);
        }
        const data = await response.json();
        if (!cancelled) {
          setRelatedBundleCatalog((data.artifacts || []).map((item: any) => normalizeReviewBundleArtifact(item)));
        }
      } catch (error) {
        console.error('[ArtifactReviewPane] Failed to load related bundle catalog:', error);
        if (!cancelled) {
          setRelatedBundleCatalog([]);
        }
      } finally {
        if (!cancelled) {
          setRelatedCatalogLoading(false);
        }
      }
    };

    void loadRelatedBundleCatalog();

    return () => {
      cancelled = true;
    };
  }, [apiUrl, artifact?.id, artifact?.updatedAt, workspaceId]);

  const refreshArtifact = useCallback(async () => {
    if (!artifact?.id || !apiUrl) {
      return;
    }
    const response = await fetch(`${apiUrl}/api/v1/artifacts/${artifact.id}?include_content=true`);
    if (!response.ok) {
      throw new Error(`Failed to reload artifact: ${response.status}`);
    }
    const data = await response.json();
    onArtifactUpdated?.(normalizeReviewBundleArtifact(data));
  }, [apiUrl, artifact?.id, onArtifactUpdated]);

  const submitReviewDecision = useCallback(
    async (decision: string) => {
      if (!workspaceId || !apiUrl || !artifact?.id) {
        setReviewDecisionResult('Missing workspace or artifact context; cannot save the review decision.');
        return;
      }

      setSavingReviewDecision(true);
      setReviewDecisionResult(null);
      try {
        const response = await fetch(
          `${apiUrl}/api/v1/workspaces/${workspaceId}/artifacts/${artifact.id}/review-decision`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              decision,
              reviewer_id: reviewerId,
              notes: reviewNotes,
              checklist_scores: reviewChecklistScores,
              followup_actions: selectedFollowupActions.length
                ? selectedFollowupActions
                : suggestedFollowupActions,
            }),
          },
        );
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.detail || `Failed to save review decision: ${response.status}`);
        }
        await refreshArtifact();
        setReviewDecisionResult(`Recorded ${stateLabel(decision)}`);
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unknown error';
        setReviewDecisionResult(`Save failed: ${message}`);
      } finally {
        setSavingReviewDecision(false);
      }
    },
    [
      apiUrl,
      artifact?.id,
      refreshArtifact,
      reviewChecklistScores,
      reviewNotes,
      reviewerId,
      selectedFollowupActions,
      suggestedFollowupActions,
      workspaceId,
    ],
  );

  const toggleCompareArtifact = useCallback((artifactId: string) => {
    setSelectedCompareArtifactIds((current) => {
      if (current.includes(artifactId)) {
        return current.filter((value) => value !== artifactId);
      }
      if (current.length >= 3) {
        return [...current.slice(1), artifactId];
      }
      return [...current, artifactId];
    });
  }, []);

  const focusRelatedArtifact = useCallback((artifactId: string) => {
    setSelectedBaselineId(artifactId);
    setSelectedHistoryBundleId(artifactId);
    setOverlayCompareTargetId(artifactId);
    setSelectedCompareArtifactIds((current) => {
      if (current.includes(artifactId)) {
        return current;
      }
      if (current.length >= 3) {
        return [...current.slice(1), artifactId];
      }
      return [...current, artifactId];
    });
  }, []);

  const toggleFollowupAction = useCallback((actionId: string) => {
    setSelectedFollowupActions((current) => {
      if (current.includes(actionId)) {
        return current.filter((value) => value !== actionId);
      }
      return [...current, actionId];
    });
  }, []);

  if (!artifact || !content) {
    return (
      <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 px-4 py-6 text-sm text-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400">
        No matching review bundle was found.
      </div>
    );
  }

  const workload = content.object_workload_snapshot || {};

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            {content.scene_id || artifact.name}
          </div>
          <StatusBadge label="bundle" value={content.source_kind} />
          <StatusBadge label="status" value={latestDecision?.decision || content.status} />
        </div>
        <div className="mt-3 grid gap-2 text-xs text-gray-600 dark:text-gray-300 md:grid-cols-2">
          <div>review_bundle_id={content.review_bundle_id || artifact.id}</div>
          <div>run_id={content.run_id || '-'}</div>
          <div>scene_id={content.scene_id || '-'}</div>
          <div>source_kind={content.source_kind || '-'}</div>
          <div>binding_mode={content.binding_mode || '-'}</div>
          <div>package_id={content.package_id || '-'}</div>
          <div>preset_id={content.preset_id || '-'}</div>
          <div>artifact_ids={(content.artifact_ids || []).join(', ') || '-'}</div>
        </div>
        <div className="mt-3 grid gap-2 text-xs text-gray-600 dark:text-gray-300 md:grid-cols-2">
          <div>impact_region_mode={String(workload.impact_region_mode || '-')}</div>
          <div>quality_gate_state={String(workload.quality_gate_state || '-')}</div>
          <div>affected_count={Array.isArray(workload.affected_object_instance_ids) ? workload.affected_object_instance_ids.length : 0}</div>
          <div>impact_region_bbox={formatBBoxLabel(workload.impact_region_bbox)}</div>
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
        <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">Visual Compare</div>
        {mediaEntries.length ? (
          <div className="mt-3 grid gap-3 xl:grid-cols-2">
            {mediaEntries.map((entry) => (
              <MediaPreviewCard
                key={entry.id}
                title={entry.title}
                url={entry.url}
                kind={entry.kind}
                apiUrl={apiUrl}
              />
            ))}
          </div>
        ) : (
          <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">
            This bundle does not expose any embeddable media slots yet.
          </div>
        )}
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">Preset Compare Board</div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Pick related bundles by preset. The board can compare the current bundle with up to three related bundles.
            </div>
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">
            compare={compareBoardBundles.length} bundles
          </div>
        </div>

        {relatedCatalogLoading ? (
          <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">Loading preset compare candidates...</div>
        ) : relatedCandidates.length ? (
          <>
            <div className="mt-3 flex flex-wrap gap-2">
              {comparePresetOptions.map((option) => {
                const isSelected = option.id === selectedComparePresetId;
                return (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => setSelectedComparePresetId(option.id)}
                    className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                      isSelected
                        ? 'border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-700 dark:bg-blue-950/20 dark:text-blue-200'
                        : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800'
                    }`}
                  >
                    {option.label} ({option.count})
                  </button>
                );
              })}
            </div>

            <div className="mt-4 grid gap-2 lg:grid-cols-2">
              {filteredCompareCandidates.slice(0, 12).map((candidate) => {
                const candidateContent = candidate.artifact.content || {};
                const decision = reviewDecisionValue(candidate.artifact);
                const isSelected = selectedCompareArtifactIds.includes(candidate.artifact.id);
                return (
                  <button
                    key={candidate.artifact.id}
                    type="button"
                    onClick={() => toggleCompareArtifact(candidate.artifact.id)}
                    className={`rounded-xl border px-3 py-3 text-left transition ${
                      isSelected
                        ? 'border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/20'
                        : 'border-gray-200 bg-gray-50 hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700'
                    }`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {bundleTitle(candidate.artifact)}
                      </div>
                      <span className={`rounded-full border px-2 py-0.5 text-[11px] ${stateTone(decision)}`}>
                        {stateLabel(decision || candidateContent.status)}
                      </span>
                      <span className="rounded-full border border-gray-200 bg-white px-2 py-0.5 text-[11px] text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300">
                        preset={presetLabel(candidateContent.preset_id)}
                      </span>
                    </div>
                    <div className="mt-2 space-y-1 text-[11px] text-gray-500 dark:text-gray-400">
                      <div>run_id={candidateContent.run_id || '-'}</div>
                      <div>package_id={candidateContent.package_id || '-'}</div>
                      <div>reviewed_at={formatTimestampLabel(reviewedAtValue(candidate.artifact))}</div>
                      <div>match={candidate.reasons.join(', ')}</div>
                    </div>
                  </button>
                );
              })}
            </div>

            <div className={`mt-4 grid gap-4 ${compareBoardBundles.length >= 4 ? 'xl:grid-cols-4' : compareBoardBundles.length === 3 ? 'xl:grid-cols-3' : 'xl:grid-cols-2'}`}>
              {compareBoardBundles.map((compareArtifact, index) => {
                const compareContent = compareArtifact.content || {};
                const compareMediaEntries = buildMediaEntries(compareContent.slots).slice(0, 2);
                const decision = reviewDecisionValue(compareArtifact);
                return (
                  <div
                    key={compareArtifact.id}
                    className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-800"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                        {index === 0 ? 'Current' : `Compare ${index}`}
                      </div>
                      <span className={`rounded-full border px-2 py-0.5 text-[11px] ${stateTone(decision)}`}>
                        {stateLabel(decision || compareContent.status)}
                      </span>
                    </div>
                    <div className="mt-2 space-y-1 text-xs text-gray-500 dark:text-gray-400">
                      <div>title={bundleTitle(compareArtifact)}</div>
                      <div>preset={presetLabel(compareContent.preset_id)}</div>
                      <div>package_id={compareContent.package_id || '-'}</div>
                      <div>run_id={compareContent.run_id || '-'}</div>
                      <div>reviewed_at={formatTimestampLabel(reviewedAtValue(compareArtifact))}</div>
                    </div>
                    {compareMediaEntries.length ? (
                      <div className="mt-3 space-y-3">
                        {compareMediaEntries.map((entry) => (
                          <MediaPreviewCard
                            key={`${compareArtifact.id}:${entry.id}`}
                            title={entry.title}
                            url={entry.url}
                            kind={entry.kind}
                            apiUrl={apiUrl}
                          />
                        ))}
                      </div>
                    ) : (
                      <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">
                        This bundle does not have previewable media.
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="mt-5 rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-800">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">Overlay / Diff Compare</div>
                  <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    Pick one of the selected compare bundles as the target for image overlay or difference compare.
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {(['overlay', 'difference'] as OverlayCompareMode[]).map((mode) => {
                    const isSelected = overlayCompareMode === mode;
                    return (
                      <button
                        key={mode}
                        type="button"
                        onClick={() => setOverlayCompareMode(mode)}
                        className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                          isSelected
                            ? 'border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-700 dark:bg-blue-950/20 dark:text-blue-200'
                            : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800'
                        }`}
                      >
                        {mode}
                      </button>
                    );
                  })}
                </div>
              </div>

              {selectedCompareCandidates.length ? (
                <>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {selectedCompareCandidates.map((candidate) => {
                      const isSelected = overlayCompareTarget?.artifact.id === candidate.artifact.id;
                      return (
                        <button
                          key={candidate.artifact.id}
                          type="button"
                          onClick={() => setOverlayCompareTargetId(candidate.artifact.id)}
                          className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                            isSelected
                              ? 'border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-700 dark:bg-blue-950/20 dark:text-blue-200'
                              : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800'
                          }`}
                        >
                          {bundleTitle(candidate.artifact)}
                        </button>
                      );
                    })}
                  </div>

                  {overlayCompareMode === 'overlay' ? (
                    <div className="mt-3">
                      <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                        overlay opacity
                      </label>
                      <input
                        type="range"
                        min={0}
                        max={100}
                        value={overlayOpacity}
                        onChange={(event) => setOverlayOpacity(Number(event.target.value))}
                        className="w-full accent-blue-600"
                      />
                      <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        compare opacity={overlayOpacity}%
                      </div>
                    </div>
                  ) : null}

                  {overlayComparePairs.length ? (
                    <div className="mt-4 grid gap-4 xl:grid-cols-2">
                      {overlayComparePairs.map((pair) => (
                        <OverlayCompareCard
                          key={pair.id}
                          pair={pair}
                          apiUrl={apiUrl}
                          mode={overlayCompareMode}
                          overlayOpacity={overlayOpacity}
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="mt-4 text-sm text-gray-500 dark:text-gray-400">
                      No matching image slots were found for overlay compare. The target may only contain video, or the slot keys do not line up.
                    </div>
                  )}
                </>
              ) : (
                <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">
                  Select at least one related bundle from the compare board before using overlay or diff compare.
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">
            No related bundles are available for multi-preset compare.
          </div>
        )}
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">Baseline Gallery</div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Surface accepted baselines as a fast visual gallery so you can jump back into a reference quickly.
            </div>
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">
            accepted={baselineGalleryItems.length}
          </div>
        </div>

        {relatedCatalogLoading ? (
          <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">Loading baseline gallery...</div>
        ) : baselineGalleryItems.length ? (
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {baselineGalleryItems.map((item) => {
              const candidateContent = item.artifact.content || {};
              const decision = reviewDecisionValue(item.artifact);
              const isSelected = item.artifact.id === selectedBaseline?.artifact.id;
              const previewUrl = item.preview ? resolveUrl(apiUrl, item.preview.url) : '';
              return (
                <button
                  key={item.artifact.id}
                  type="button"
                  onClick={() => focusRelatedArtifact(item.artifact.id)}
                  className={`overflow-hidden rounded-xl border text-left transition ${
                    isSelected
                      ? 'border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/20'
                      : 'border-gray-200 bg-gray-50 hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700'
                  }`}
                >
                  <div className="relative h-40 overflow-hidden bg-black">
                    {previewUrl && item.preview?.kind === 'image' ? (
                      <img
                        src={previewUrl}
                        alt={bundleTitle(item.artifact)}
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <div className="flex h-full items-center justify-center px-4 text-sm text-gray-300">
                        no preview
                      </div>
                    )}
                    <div className="absolute left-3 top-3 rounded-full bg-black/65 px-2 py-1 text-[11px] text-white">
                      {presetLabel(candidateContent.preset_id)}
                    </div>
                  </div>
                  <div className="space-y-1 px-3 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {bundleTitle(item.artifact)}
                      </div>
                      <span className={`rounded-full border px-2 py-0.5 text-[11px] ${stateTone(decision)}`}>
                        {stateLabel(decision || candidateContent.status)}
                      </span>
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      run_id={candidateContent.run_id || '-'}
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      reviewed_at={formatTimestampLabel(reviewedAtValue(item.artifact))}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">
            There is no accepted baseline gallery to display yet.
          </div>
        )}
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">Run-Level Matrix</div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Aggregate related bundles by run so you can see accepted, needs_tune, rejected, and preset distribution at a glance.
            </div>
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">
            runs={runMatrixRows.length}
          </div>
        </div>

        {relatedCatalogLoading ? (
          <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">Loading run-level matrix...</div>
        ) : runMatrixRows.length ? (
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 text-left text-sm dark:divide-gray-700">
              <thead>
                <tr className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  <th className="px-3 py-2 font-semibold">run_id</th>
                  <th className="px-3 py-2 font-semibold">bundles</th>
                  <th className="px-3 py-2 font-semibold">accepted</th>
                  <th className="px-3 py-2 font-semibold">needs_tune</th>
                  <th className="px-3 py-2 font-semibold">rejected</th>
                  <th className="px-3 py-2 font-semibold">pending</th>
                  <th className="px-3 py-2 font-semibold">presets</th>
                  <th className="px-3 py-2 font-semibold">latest_reviewed_at</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                {runMatrixRows.map((row) => (
                  <tr key={row.runId} className="align-top text-gray-700 dark:text-gray-300">
                    <td className="px-3 py-3 text-xs font-medium text-gray-900 dark:text-gray-100">
                      {row.runId}
                    </td>
                    <td className="px-3 py-3 text-xs">{row.bundleCount}</td>
                    <td className="px-3 py-3 text-xs text-green-700 dark:text-green-300">{row.acceptedCount}</td>
                    <td className="px-3 py-3 text-xs text-amber-700 dark:text-amber-300">{row.needsTuneCount}</td>
                    <td className="px-3 py-3 text-xs text-red-700 dark:text-red-300">{row.rejectedCount}</td>
                    <td className="px-3 py-3 text-xs text-gray-500 dark:text-gray-400">{row.pendingCount}</td>
                    <td className="px-3 py-3">
                      <div className="flex max-w-sm flex-wrap gap-1">
                        {row.presets.map((preset) => (
                          <span
                            key={`${row.runId}:${preset}`}
                            className="rounded-full border border-gray-200 bg-gray-50 px-2 py-0.5 text-[11px] text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
                          >
                            {preset}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-3 py-3 text-xs text-gray-500 dark:text-gray-400">
                      {formatTimestampLabel(row.latestReviewedAt)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">
            There is no run-level matrix to summarize yet.
          </div>
        )}
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">Accepted Baselines</div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Use the most recent accepted bundle for the same scene, package, preset, and source kind as the manual reference.
            </div>
          </div>
          {selectedBaseline ? (
            <div className="text-xs text-gray-500 dark:text-gray-400">
              match={selectedBaseline.reasons.join(', ')} / score={selectedBaseline.score}
            </div>
          ) : null}
        </div>

        {relatedCatalogLoading ? (
          <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">Loading accepted baselines...</div>
        ) : baselineCandidates.length ? (
          <>
            <div className="mt-3 grid gap-2 lg:grid-cols-2">
              {baselineCandidates.map((candidate) => {
                const candidateContent = candidate.artifact.content || {};
                const isSelected = candidate.artifact.id === selectedBaseline?.artifact.id;
                return (
                  <button
                    key={candidate.artifact.id}
                    type="button"
                    onClick={() => setSelectedBaselineId(candidate.artifact.id)}
                    className={`rounded-xl border px-3 py-3 text-left transition ${
                      isSelected
                        ? 'border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/20'
                        : 'border-gray-200 bg-gray-50 hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700'
                    }`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {candidateContent.scene_id || candidate.artifact.name}
                      </div>
                      <span className="rounded-full border border-gray-200 bg-white px-2 py-0.5 text-[11px] text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300">
                        {candidateContent.source_kind || 'bundle'}
                      </span>
                    </div>
                    <div className="mt-2 space-y-1 text-[11px] text-gray-500 dark:text-gray-400">
                      <div>decision={candidateContent.latest_review_decision?.decision || candidateContent.status || '-'}</div>
                      <div>package_id={candidateContent.package_id || '-'}</div>
                      <div>preset_id={candidateContent.preset_id || '-'}</div>
                      <div>match={candidate.reasons.join(', ')}</div>
                    </div>
                  </button>
                );
              })}
            </div>

            {selectedBaseline ? (
              <div className="mt-4 grid gap-4 xl:grid-cols-2">
                <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-800">
                  <div className="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">Current Bundle</div>
                  {mediaEntries.length ? (
                    <div className="space-y-3">
                      {mediaEntries.slice(0, 3).map((entry) => (
                        <MediaPreviewCard
                          key={`current:${entry.id}`}
                          title={entry.title}
                          url={entry.url}
                          kind={entry.kind}
                          apiUrl={apiUrl}
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-gray-500 dark:text-gray-400">The current bundle does not have previewable media.</div>
                  )}
                </div>

                <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-800">
                  <div className="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">
                    Accepted Baseline
                  </div>
                  <div className="mb-3 space-y-1 text-xs text-gray-500 dark:text-gray-400">
                    <div>artifact_id={selectedBaseline.artifact.id}</div>
                    <div>reviewed_at={formatTimestampLabel(selectedBaseline.artifact.content?.latest_review_decision?.reviewed_at)}</div>
                    <div>checklist_avg={selectedBaseline.artifact.content?.latest_review_decision?.checklist_summary?.average_score ?? '-'}</div>
                  </div>
                  {baselineMediaEntries.length ? (
                    <div className="space-y-3">
                      {baselineMediaEntries.slice(0, 3).map((entry) => (
                        <MediaPreviewCard
                          key={`baseline:${entry.id}`}
                          title={entry.title}
                          url={entry.url}
                          kind={entry.kind}
                          apiUrl={apiUrl}
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-gray-500 dark:text-gray-400">This baseline does not have previewable media.</div>
                  )}
                </div>
              </div>
            ) : null}
          </>
        ) : (
          <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">
            No accepted baseline is available for comparison.
          </div>
        )}
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">History Browser</div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Show related bundles for the same scene, package, preset, and source kind so you can review how this line evolved.
            </div>
          </div>
          {selectedHistoryBundle ? (
            <div className="text-xs text-gray-500 dark:text-gray-400">
              match={selectedHistoryBundle.reasons.join(', ')} / score={selectedHistoryBundle.score}
            </div>
          ) : null}
        </div>

        {relatedCatalogLoading ? (
          <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">Loading related bundle history...</div>
        ) : historyCandidates.length ? (
          <>
            <div className="mt-3 grid gap-2 lg:grid-cols-2">
              {historyCandidates.map((candidate) => {
                const candidateContent = candidate.artifact.content || {};
                const isSelected = candidate.artifact.id === selectedHistoryBundle?.artifact.id;
                const decision = reviewDecisionValue(candidate.artifact);
                return (
                  <button
                    key={candidate.artifact.id}
                    type="button"
                    onClick={() => setSelectedHistoryBundleId(candidate.artifact.id)}
                    className={`rounded-xl border px-3 py-3 text-left transition ${
                      isSelected
                        ? 'border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/20'
                        : 'border-gray-200 bg-gray-50 hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700'
                    }`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                        {candidateContent.scene_id || candidate.artifact.name}
                      </div>
                      <span className={`rounded-full border px-2 py-0.5 text-[11px] ${stateTone(decision)}`}>
                        {stateLabel(decision || candidateContent.status)}
                      </span>
                    </div>
                    <div className="mt-2 space-y-1 text-[11px] text-gray-500 dark:text-gray-400">
                      <div>run_id={candidateContent.run_id || '-'}</div>
                      <div>package_id={candidateContent.package_id || '-'}</div>
                      <div>preset_id={candidateContent.preset_id || '-'}</div>
                      <div>reviewed_at={formatTimestampLabel(reviewedAtValue(candidate.artifact))}</div>
                      <div>match={candidate.reasons.join(', ')}</div>
                    </div>
                  </button>
                );
              })}
            </div>

            {selectedHistoryBundle ? (
              <div className="mt-4 grid gap-4 xl:grid-cols-2">
                <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-800">
                  <div className="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">Current Bundle</div>
                  <div className="mb-3 space-y-1 text-xs text-gray-500 dark:text-gray-400">
                    <div>artifact_id={artifact.id}</div>
                    <div>decision={stateLabel(reviewDecisionValue(artifact) || content.status)}</div>
                    <div>reviewed_at={formatTimestampLabel(reviewedAtValue(artifact))}</div>
                  </div>
                  {mediaEntries.length ? (
                    <div className="space-y-3">
                      {mediaEntries.slice(0, 3).map((entry) => (
                        <MediaPreviewCard
                          key={`history-current:${entry.id}`}
                          title={entry.title}
                          url={entry.url}
                          kind={entry.kind}
                          apiUrl={apiUrl}
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-gray-500 dark:text-gray-400">The current bundle does not have previewable media.</div>
                  )}
                </div>

                <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-800">
                  <div className="mb-3 text-sm font-semibold text-gray-900 dark:text-gray-100">Related History Bundle</div>
                  <div className="mb-3 space-y-1 text-xs text-gray-500 dark:text-gray-400">
                    <div>artifact_id={selectedHistoryBundle.artifact.id}</div>
                    <div>decision={stateLabel(reviewDecisionValue(selectedHistoryBundle.artifact) || selectedHistoryBundle.artifact.content?.status)}</div>
                    <div>reviewed_at={formatTimestampLabel(reviewedAtValue(selectedHistoryBundle.artifact))}</div>
                    <div>checklist_avg={selectedHistoryBundle.artifact.content?.latest_review_decision?.checklist_summary?.average_score ?? '-'}</div>
                  </div>
                  {historyMediaEntries.length ? (
                    <div className="space-y-3">
                      {historyMediaEntries.slice(0, 3).map((entry) => (
                        <MediaPreviewCard
                          key={`history-related:${entry.id}`}
                          title={entry.title}
                          url={entry.url}
                          kind={entry.kind}
                          apiUrl={apiUrl}
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-gray-500 dark:text-gray-400">This history bundle does not have previewable media.</div>
                  )}
                </div>
              </div>
            ) : null}
          </>
        ) : (
          <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">
            No history bundles were found for the same scene, package, preset, and source kind.
          </div>
        )}
      </div>

      {content.slots?.length ? (
        <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
          <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">Slot Inventory</div>
          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            {content.slots.map((slot, index) => (
              <div
                key={`${slot.slot_key || slot.label || 'slot'}:${index}`}
                className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 text-xs text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
              >
                <div className="font-medium text-gray-900 dark:text-gray-100">
                  {slot.label || slot.slot_key || `slot_${index}`}
                </div>
                <div className="mt-2 space-y-1">
                  <div className="break-all">storage={slot.storage_key || '-'}</div>
                  <div className="break-all">preview={slot.preview_url || '-'}</div>
                  <div className="break-all">mask={slot.mask_storage_key || '-'}</div>
                  <div className="break-all">mask_preview={slot.mask_preview_url || '-'}</div>
                  <div className="break-all">alpha={slot.alpha_storage_key || '-'}</div>
                  <div className="break-all">alpha_preview={slot.alpha_preview_url || '-'}</div>
                  <div className="break-all">fingerprint={slot.source_reference_fingerprint || '-'}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,0.8fr),minmax(0,1fr)]">
        <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-800">
          <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">Latest Decision</div>
          <div className="mt-3 space-y-2 text-sm text-gray-700 dark:text-gray-300">
            <div>decision={stateLabel(latestDecision?.decision || content.status)}</div>
            <div>reviewer={latestDecision?.reviewer_id || '-'}</div>
            <div>reviewed_at={formatTimestampLabel(latestDecision?.reviewed_at)}</div>
            <div>
              checklist_avg={latestDecision?.checklist_summary?.average_score ?? '-'} / scored_checks={latestDecision?.checklist_summary?.scored_checks ?? 0}
            </div>
            {latestDecision?.checklist_scores && Object.keys(latestDecision.checklist_scores).length ? (
              <div className="flex flex-wrap gap-2">
                {Object.entries(latestDecision.checklist_scores).map(([checkId, score]) => (
                  <span
                    key={checkId}
                    className="rounded-full bg-white px-2 py-1 text-[11px] text-gray-600 dark:bg-gray-900 dark:text-gray-300"
                  >
                    {checkId}={score}
                  </span>
                ))}
              </div>
            ) : null}
            {latestDecision?.followup_actions?.length ? (
              <div className="flex flex-wrap gap-2">
                {latestDecision.followup_actions.map((actionId) => (
                  <span
                    key={actionId}
                    className="rounded-full bg-white px-2 py-1 text-[11px] text-gray-600 dark:bg-gray-900 dark:text-gray-300"
                  >
                    {followupActionLabel(actionId)}
                  </span>
                ))}
              </div>
            ) : null}
            <div className="whitespace-pre-wrap break-words text-xs text-gray-500 dark:text-gray-400">
              {latestDecision?.notes || 'No notes yet.'}
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-900">
          <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">Review Decision</div>
          <div className="mt-3 space-y-3">
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                reviewer_id
              </label>
              <input
                value={reviewerId}
                onChange={(event) => setReviewerId(event.target.value)}
                placeholder="For example, art_director"
                className="w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-sm outline-none placeholder:text-gray-400 focus:border-blue-500 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                Notes
              </label>
              <textarea
                value={reviewNotes}
                onChange={(event) => setReviewNotes(event.target.value)}
                placeholder="Capture visual deltas, identity issues, edge defects, or the next tuning focus."
                rows={5}
                className="w-full rounded-xl border border-gray-300 bg-white px-3 py-3 text-sm outline-none placeholder:text-gray-400 focus:border-blue-500 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-100"
              />
            </div>
            {checklistTemplate.length ? (
              <div>
                <div className="mb-2 flex items-center justify-between gap-3">
                  <label className="block text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                    Checklist
                  </label>
                  <div className="text-xs text-gray-500 dark:text-gray-400">
                    scored={Object.keys(reviewChecklistScores).length} / avg={checklistAverage ?? '-'}
                  </div>
                </div>
                <div className="space-y-3">
                  {checklistTemplate.map((item: ReviewChecklistItemView) => {
                    const currentScore = reviewChecklistScores[item.check_id];
                    return (
                      <div
                        key={item.check_id}
                        className="rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 dark:border-gray-700 dark:bg-gray-800"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                            {item.label || item.check_id}
                          </div>
                          <span className="rounded-full border border-gray-200 bg-white px-2 py-0.5 text-[11px] text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300">
                            {item.focus === 'primary' ? 'Primary' : 'Secondary'}
                          </span>
                          {typeof currentScore === 'number' ? (
                            <span className={`rounded-full border px-2 py-0.5 text-[11px] ${stateTone(currentScore >= 1 ? 'accepted' : currentScore >= 0.5 ? 'needs_tune' : 'rejected')}`}>
                              {checklistScoreLabel(currentScore)} {currentScore}
                            </span>
                          ) : null}
                        </div>
                        <div className="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400">
                          {item.description || 'No description'}
                        </div>
                        <div className="mt-3 grid grid-cols-3 gap-2">
                          {[
                            [0, 'Poor'],
                            [0.5, 'Fair'],
                            [1, 'Good'],
                          ].map(([score, label]) => (
                            <button
                              key={`${item.check_id}:${score}`}
                              type="button"
                              onClick={() =>
                                setReviewChecklistScores((current) => ({
                                  ...current,
                                  [item.check_id]: Number(score),
                                }))
                              }
                              className={`rounded-xl border px-3 py-2 text-xs font-medium transition ${
                                currentScore === score
                                  ? 'border-blue-400 bg-blue-50 text-blue-800 dark:border-blue-600 dark:bg-blue-950/30 dark:text-blue-200'
                                  : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800'
                              }`}
                            >
                              {label} {score}
                            </button>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}
            <div>
              <div className="mb-2 flex items-center justify-between gap-3">
                <label className="block text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  Follow-up Workflow
                </label>
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  selected={selectedFollowupActions.length} / suggested={suggestedFollowupActions.length}
                </div>
              </div>
              <div className="mb-2 text-xs text-gray-500 dark:text-gray-400">
                Suggested follow-up actions were preselected from `source_kind / baseline / quality gate`. Adjust them before submitting if needed.
              </div>
              <div className="grid gap-2">
                {FOLLOWUP_ACTION_OPTIONS.map((option) => {
                  const isSelected = selectedFollowupActions.includes(option.id);
                  const isSuggested = suggestedFollowupActions.includes(option.id);
                  return (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => toggleFollowupAction(option.id)}
                      className={`rounded-xl border px-3 py-3 text-left transition ${
                        isSelected
                          ? 'border-blue-300 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/20'
                          : 'border-gray-200 bg-gray-50 hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700'
                      }`}
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          {option.label}
                        </div>
                        {isSuggested ? (
                          <span className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] text-amber-800 dark:border-amber-700 dark:bg-amber-950/20 dark:text-amber-200">
                            Suggested
                          </span>
                        ) : null}
                      </div>
                      <div className="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400">
                        {followupActionDescription(option.id)}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
            {!workspaceId ? (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-300">
                This page does not have workspace_id context, so it is view-only and cannot save decisions.
              </div>
            ) : null}
            <div className="grid gap-2">
              {[
                ['accepted', 'border-green-300 bg-green-50 text-green-800 hover:border-green-400 hover:bg-green-100 dark:border-green-800 dark:bg-green-950/30 dark:text-green-200 dark:hover:bg-green-950/40'],
                ['needs_tune', 'border-amber-300 bg-amber-50 text-amber-800 hover:border-amber-400 hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200 dark:hover:bg-amber-950/40'],
                ['rejected', 'border-red-300 bg-red-50 text-red-800 hover:border-red-400 hover:bg-red-100 dark:border-red-800 dark:bg-red-950/30 dark:text-red-200 dark:hover:bg-red-950/40'],
                ['manual_required', 'border-gray-300 bg-gray-100 text-gray-800 hover:border-gray-400 hover:bg-gray-200 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700'],
              ].map(([decision, className]) => (
                <button
                  key={decision}
                  onClick={() => {
                    void submitReviewDecision(decision);
                  }}
                  disabled={savingReviewDecision || !workspaceId}
                  className={`rounded-xl border px-3 py-2 text-sm font-medium transition ${className} ${
                    savingReviewDecision || !workspaceId
                      ? 'cursor-not-allowed border-gray-200 bg-gray-100 text-gray-400 hover:border-gray-200 hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-500'
                      : ''
                  }`}
                >
                  {savingReviewDecision ? 'Saving...' : `Mark as ${stateLabel(decision)}`}
                </button>
              ))}
            </div>
            {reviewDecisionResult ? (
              <div
                className={`rounded-xl border px-3 py-2 text-xs ${
                  reviewDecisionResult.startsWith('Recorded')
                    ? 'border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-950/30 dark:text-green-300'
                    : 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-300'
                }`}
              >
                {reviewDecisionResult}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
