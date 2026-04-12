import React, { useEffect, useMemo, useState } from 'react';

import { BaseModal } from '../../../../../components/BaseModal';
import { Loader2 } from 'lucide-react';
import { fetchWithApiFallback } from '../../../../../lib/api-fetch';

interface ReferenceTrainingSource {
  reference_id: string;
  source_handle: string;
  source_shortcode: string;
  analysis_status: string;
  analysis_profile?: string;
  schema_version?: string;
}

interface DraftCandidateView {
  candidate_id: string;
  display_name: string;
  source_refs?: Array<Record<string, unknown>>;
  metadata?: {
    training_intake?: {
      intents?: Array<Record<string, unknown>>;
    };
  };
  updated_at?: string;
}

interface TrainingIntentPresetView {
  intent_code: string;
  display_name: string;
  package_kind: string;
  dataset_kind: string;
  training_mode: string;
  allowed_model_families: string[];
  default_model_families: string[];
  recommended_consumption_modes: string[];
  expected_artifact_kinds: string[];
  rollout_status: string;
}

interface TrainingIntentSelectionState {
  enabled: boolean;
  targetModelFamilies: string[];
  preferredBaseModelRefsText: string;
}

interface TrainingIntakeSuccessPayload {
  mode: 'create' | 'append';
  candidateId: string;
  candidateDisplayName: string;
  addedCount: number;
  dedupedCount: number;
  trainingIntentCount: number;
  trainingIntentAddedCount: number;
  trainingIntentDedupedCount: number;
}

interface AddToTrainingCandidateModalProps {
  isOpen: boolean;
  apiUrl?: string;
  workspaceId: string;
  selectedReferences: ReferenceTrainingSource[];
  onClose: () => void;
  onSuccess: (payload: TrainingIntakeSuccessPayload) => void;
}

function resolveUrl(apiUrl: string | undefined, path: string): string {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }
  if (!apiUrl) {
    return path;
  }
  return path.startsWith('/') ? `${apiUrl}${path}` : `${apiUrl}/${path}`;
}

function slugifyToken(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/^@+/, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function buildSuggestedCandidateName(
  references: ReferenceTrainingSource[],
  workspaceId: string,
): string {
  const handles = Array.from(
    new Set(
      references
        .map((item) => slugifyToken(item.source_handle || ''))
        .filter(Boolean),
    ),
  );
  if (handles.length === 1) {
    return `${handles[0]}-draft`;
  }
  if (handles.length > 1) {
    return `${handles[0]}-multi-ref-draft`;
  }
  const firstReferenceId = references[0]?.reference_id || workspaceId;
  return `ig-intake-${slugifyToken(firstReferenceId) || 'draft'}`;
}

function extractErrorMessage(payload: any, status: number): string {
  if (typeof payload?.detail === 'string') {
    return payload.detail;
  }
  if (Array.isArray(payload?.detail)) {
    return payload.detail
      .map((item: any) => item?.msg || JSON.stringify(item))
      .join('; ');
  }
  if (payload?.detail && typeof payload.detail === 'object') {
    return JSON.stringify(payload.detail);
  }
  if (typeof payload?.error === 'string') {
    return payload.error;
  }
  return `HTTP ${status}`;
}

function buildSourceRefsPayload(
  references: ReferenceTrainingSource[],
  workspaceId: string,
) {
  return references.map((reference) => {
    const metadata: Record<string, unknown> = {
      intake_origin: 'ig.references_panel',
    };
    if (reference.schema_version) {
      metadata.schema_version = reference.schema_version;
    }

    const payload: Record<string, unknown> = {
      source_pack: 'ig',
      source_type: 'reference',
      reference_id: reference.reference_id,
      source_handle: reference.source_handle,
      source_shortcode: reference.source_shortcode,
      analysis_status: reference.analysis_status,
      workspace_id: workspaceId,
      metadata,
    };

    if (reference.analysis_profile) {
      payload.analysis_profile = reference.analysis_profile;
    }
    return payload;
  });
}

function formatTimestamp(value: string | undefined): string {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString('en-US', { hour12: false });
}

export default function AddToTrainingCandidateModal({
  isOpen,
  apiUrl,
  workspaceId,
  selectedReferences,
  onClose,
  onSuccess,
}: AddToTrainingCandidateModalProps) {
  const [mode, setMode] = useState<'create' | 'append'>('create');
  const [displayName, setDisplayName] = useState('');
  const [selectedCandidateId, setSelectedCandidateId] = useState('');
  const [draftCandidates, setDraftCandidates] = useState<DraftCandidateView[]>([]);
  const [presets, setPresets] = useState<TrainingIntentPresetView[]>([]);
  const [presetVersion, setPresetVersion] = useState('v1');
  const [intentSelections, setIntentSelections] = useState<
    Record<string, TrainingIntentSelectionState>
  >({});
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    if (!isOpen) {
      setLoading(false);
      setSubmitting(false);
      setErrorMessage('');
      return;
    }

    let cancelled = false;
    async function loadModalData() {
      setLoading(true);
      setErrorMessage('');

      try {
        const presetResponse = await fetchWithApiFallback(
          '/api/v1/capabilities/character_training/training-intent-presets',
          { cache: 'no-store' },
          apiUrl,
        );
        const presetPayload = await presetResponse.json();
        if (!presetResponse.ok) {
          throw new Error(extractErrorMessage(presetPayload, presetResponse.status));
        }

        let nextCandidates: DraftCandidateView[] = [];
        let candidateWarning = '';
        try {
          const candidateResponse = await fetchWithApiFallback(
            `/api/v1/capabilities/character_training/candidates?workspace_id=${encodeURIComponent(workspaceId)}&status=draft&limit=100`,
            { cache: 'no-store' },
            apiUrl,
          );
          const candidatePayload = await candidateResponse.json();
          if (!candidateResponse.ok) {
            throw new Error(extractErrorMessage(candidatePayload, candidateResponse.status));
          }
          nextCandidates = Array.isArray(candidatePayload?.candidates)
            ? (candidatePayload.candidates as DraftCandidateView[])
            : [];
        } catch (error) {
          candidateWarning = error instanceof Error ? error.message : 'Failed to load draft candidates';
        }

        if (cancelled) return;

        const nextPresets = Array.isArray(presetPayload?.presets)
          ? (presetPayload.presets as TrainingIntentPresetView[])
          : [];

        const defaultPreset =
          nextPresets.find((item) => item.rollout_status === 'active') || nextPresets[0];
        const nextSelections: Record<string, TrainingIntentSelectionState> = {};
        nextPresets.forEach((preset) => {
          nextSelections[preset.intent_code] = {
            enabled: preset.intent_code === defaultPreset?.intent_code,
            targetModelFamilies: [...preset.default_model_families],
            preferredBaseModelRefsText: '',
          };
        });

        setPresets(nextPresets);
        setPresetVersion(String(presetPayload?.version || 'v1'));
        setDraftCandidates(nextCandidates);
        setMode('create');
        setSelectedCandidateId(nextCandidates[0]?.candidate_id || '');
        setDisplayName(buildSuggestedCandidateName(selectedReferences, workspaceId));
        setIntentSelections(nextSelections);
        if (candidateWarning) {
          setErrorMessage(`Existing draft candidates unavailable right now. Create mode still works. ${candidateWarning}`);
        }
      } catch (error) {
        if (cancelled) return;
        setErrorMessage(
          error instanceof Error ? error.message : 'Failed to load training intake data',
        );
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadModalData();
    return () => {
      cancelled = true;
    };
  }, [apiUrl, isOpen, selectedReferences, workspaceId]);

  const selectedIntents = useMemo(() => {
    return presets.filter((preset) => intentSelections[preset.intent_code]?.enabled);
  }, [intentSelections, presets]);

  const selectedCandidate = useMemo(() => {
    return draftCandidates.find((item) => item.candidate_id === selectedCandidateId) || null;
  }, [draftCandidates, selectedCandidateId]);

  function updateIntentSelection(
    intentCode: string,
    updater: (current: TrainingIntentSelectionState) => TrainingIntentSelectionState,
  ) {
    setIntentSelections((current) => {
      const existing = current[intentCode] || {
        enabled: false,
        targetModelFamilies: [],
        preferredBaseModelRefsText: '',
      };
      return {
        ...current,
        [intentCode]: updater(existing),
      };
    });
  }

  async function handleSubmit() {
    if (!selectedReferences.length || selectedIntents.length === 0) {
      setErrorMessage('Select at least one training intent');
      return;
    }
    if (mode === 'create' && !displayName.trim()) {
      setErrorMessage('Draft candidate name is required');
      return;
    }
    if (mode === 'append' && !selectedCandidateId) {
      setErrorMessage('Select a draft candidate to append');
      return;
    }

    const intentsPayload = selectedIntents.map((preset) => {
      const selection = intentSelections[preset.intent_code];
      const targetModelFamilies = selection.targetModelFamilies.length
        ? selection.targetModelFamilies
        : preset.default_model_families;

      return {
        intent_code: preset.intent_code,
        target_model_families: targetModelFamilies,
        preferred_base_model_refs: selection.preferredBaseModelRefsText
          .split('\n')
          .map((item) => item.trim())
          .filter(Boolean),
        dispatch_status: 'planned',
      };
    });

    const sourceRefs = buildSourceRefsPayload(selectedReferences, workspaceId);
    const trainingIntake = {
      schema_version: 'v1',
      intake_origin: 'ig.references_panel',
      intent_presets_version: presetVersion || 'v1',
      intents: intentsPayload,
    };

    setSubmitting(true);
    setErrorMessage('');

    try {
      if (mode === 'create') {
        const response = await fetch(
          resolveUrl(apiUrl, '/api/v1/capabilities/character_training/candidates'),
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              workspace_id: workspaceId,
              display_name: displayName.trim(),
              source_kind: 'ig_refs',
              source_refs: sourceRefs,
              metadata: {
                intake_origin: 'ig.references_panel',
                training_intake: trainingIntake,
              },
            }),
          },
        );
        const payload = await response.json();
        if (!response.ok || !payload?.candidate) {
          throw new Error(extractErrorMessage(payload, response.status));
        }
        onSuccess({
          mode: 'create',
          candidateId: payload.candidate.candidate_id,
          candidateDisplayName: payload.candidate.display_name || displayName.trim(),
          addedCount: selectedReferences.length,
          dedupedCount: 0,
          trainingIntentCount: selectedIntents.length,
          trainingIntentAddedCount: selectedIntents.length,
          trainingIntentDedupedCount: 0,
        });
        onClose();
        return;
      }

      const response = await fetch(
        resolveUrl(
          apiUrl,
          `/api/v1/capabilities/character_training/candidates/${selectedCandidateId}/intake:append`,
        ),
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            source_refs: sourceRefs,
            metadata: {
              training_intake: trainingIntake,
            },
          }),
        },
      );
      const payload = await response.json();
      if (!response.ok || !payload?.candidate) {
        throw new Error(extractErrorMessage(payload, response.status));
      }

      onSuccess({
        mode: 'append',
        candidateId: payload.candidate.candidate_id,
        candidateDisplayName:
          payload.candidate.display_name || selectedCandidate?.display_name || 'draft candidate',
        addedCount: Number(payload.added_count || 0),
        dedupedCount: Number(payload.deduped_count || 0),
        trainingIntentCount: selectedIntents.length,
        trainingIntentAddedCount: Number(payload.training_intent_added_count || 0),
        trainingIntentDedupedCount: Number(payload.training_intent_deduped_count || 0),
      });
      onClose();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Training intake failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      title="Add References To Training"
      maxWidth="max-w-4xl"
    >
      <div className="space-y-5">
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          This action only creates or appends a draft candidate intake. It does not prepare a
          dataset or dispatch training jobs.
        </div>

        <div className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-700">
          <div className="font-medium text-gray-900">
            {selectedReferences.length} reference{selectedReferences.length === 1 ? '' : 's'} selected
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {selectedReferences.slice(0, 6).map((reference) => (
              <span
                key={reference.reference_id}
                className="rounded-full border border-gray-200 bg-white px-3 py-1 text-xs text-gray-600"
              >
                {(reference.source_shortcode || reference.reference_id || '').trim()}
              </span>
            ))}
            {selectedReferences.length > 6 && (
              <span className="rounded-full border border-gray-200 bg-white px-3 py-1 text-xs text-gray-500">
                +{selectedReferences.length - 6} more
              </span>
            )}
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12 text-sm text-gray-500">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Loading training intake options...
          </div>
        ) : (
          <>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="rounded-xl border border-gray-200 p-4 text-sm text-gray-700">
                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="training-candidate-mode"
                    checked={mode === 'create'}
                    onChange={() => setMode('create')}
                  />
                  <span className="font-medium text-gray-900">Create new draft candidate</span>
                </div>
                <p className="mt-2 text-xs text-gray-500">
                  Start a fresh `character_training` draft candidate from these IG references.
                </p>
              </label>

              <label className="rounded-xl border border-gray-200 p-4 text-sm text-gray-700">
                <div className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="training-candidate-mode"
                    checked={mode === 'append'}
                    onChange={() => setMode('append')}
                    disabled={!draftCandidates.length}
                  />
                  <span className="font-medium text-gray-900">Add to existing draft candidate</span>
                </div>
                <p className="mt-2 text-xs text-gray-500">
                  Append refs and `training_intents[]` to an existing draft candidate.
                </p>
              </label>
            </div>

            {mode === 'create' ? (
              <label className="block text-sm text-gray-700">
                <span className="mb-2 block font-medium text-gray-900">Draft candidate name</span>
                <input
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  className="w-full rounded-xl border border-gray-300 px-3 py-2 outline-none transition focus:border-emerald-500"
                  placeholder="soft-gaze-draft"
                />
              </label>
            ) : (
              <label className="block text-sm text-gray-700">
                <span className="mb-2 block font-medium text-gray-900">Target draft candidate</span>
                <select
                  value={selectedCandidateId}
                  onChange={(event) => setSelectedCandidateId(event.target.value)}
                  className="w-full rounded-xl border border-gray-300 px-3 py-2 outline-none transition focus:border-emerald-500"
                >
                  {draftCandidates.map((candidate) => (
                    <option key={candidate.candidate_id} value={candidate.candidate_id}>
                      {candidate.display_name} · {candidate.candidate_id}
                    </option>
                  ))}
                </select>
                {selectedCandidate && (
                  <p className="mt-2 text-xs text-gray-500">
                    updated: {formatTimestamp(selectedCandidate.updated_at)} · source refs:{' '}
                    {selectedCandidate.source_refs?.length || 0}
                  </p>
                )}
              </label>
            )}

            <div className="rounded-xl border border-gray-200 p-4">
              <div className="mb-3 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-medium text-gray-900">Training intent presets</h3>
                  <p className="text-xs text-gray-500">
                    Canonical source of truth comes from `character_training` preset registry.
                  </p>
                </div>
                <span className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs text-gray-500">
                  version {presetVersion}
                </span>
              </div>

              <div className="space-y-3">
                {presets.map((preset) => {
                  const selection = intentSelections[preset.intent_code] || {
                    enabled: false,
                    targetModelFamilies: [...preset.default_model_families],
                    preferredBaseModelRefsText: '',
                  };
                  const hasSingleAllowedFamily = preset.allowed_model_families.length <= 1;

                  return (
                    <div key={preset.intent_code} className="rounded-xl border border-gray-200 p-4">
                      <label className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          checked={selection.enabled}
                          onChange={(event) =>
                            updateIntentSelection(preset.intent_code, (current) => ({
                              ...current,
                              enabled: event.target.checked,
                              targetModelFamilies: current.targetModelFamilies.length
                                ? current.targetModelFamilies
                                : [...preset.default_model_families],
                            }))
                          }
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium text-gray-900">{preset.display_name}</span>
                            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-600">
                              {preset.rollout_status}
                            </span>
                            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] text-gray-600">
                              {preset.package_kind} / {preset.training_mode}
                            </span>
                          </div>
                          <p className="mt-1 text-xs text-gray-500">
                            dataset: {preset.dataset_kind} · expected artifacts:{' '}
                            {preset.expected_artifact_kinds.join(', ')}
                          </p>
                        </div>
                      </label>

                      {selection.enabled && (
                        <div className="mt-4 space-y-3 pl-6">
                          <div>
                            <div className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
                              Target model families
                            </div>
                            <div className="flex flex-wrap gap-2">
                              {preset.allowed_model_families.map((family) => {
                                const checked = selection.targetModelFamilies.includes(family);
                                return (
                                  <label
                                    key={family}
                                    className="inline-flex items-center gap-2 rounded-full border border-gray-200 px-3 py-1 text-xs text-gray-700"
                                  >
                                    <input
                                      type="checkbox"
                                      checked={checked}
                                      disabled={hasSingleAllowedFamily}
                                      onChange={(event) =>
                                        updateIntentSelection(preset.intent_code, (current) => {
                                          const nextFamilies = event.target.checked
                                            ? [...current.targetModelFamilies, family]
                                            : current.targetModelFamilies.filter(
                                                (item) => item !== family,
                                              );
                                          return {
                                            ...current,
                                            targetModelFamilies: Array.from(new Set(nextFamilies)),
                                          };
                                        })
                                      }
                                    />
                                    {family}
                                  </label>
                                );
                              })}
                            </div>
                          </div>

                          <label className="block text-sm text-gray-700">
                            <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-gray-500">
                              Preferred base model refs
                            </span>
                            <textarea
                              value={selection.preferredBaseModelRefsText}
                              onChange={(event) =>
                                updateIntentSelection(preset.intent_code, (current) => ({
                                  ...current,
                                  preferredBaseModelRefsText: event.target.value,
                                }))
                              }
                              rows={2}
                              placeholder="models/sdxl/base.safetensors"
                              className="w-full rounded-xl border border-gray-300 px-3 py-2 text-sm outline-none transition focus:border-emerald-500"
                            />
                          </label>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}

        {errorMessage && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {errorMessage}
          </div>
        )}

        <div className="flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-gray-300 px-4 py-2 text-sm text-gray-700 transition hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => {
              void handleSubmit();
            }}
            disabled={loading || submitting}
            className="inline-flex items-center rounded-xl bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {mode === 'create' ? 'Create Draft Candidate' : 'Append To Draft Candidate'}
          </button>
        </div>
      </div>
    </BaseModal>
  );
}
