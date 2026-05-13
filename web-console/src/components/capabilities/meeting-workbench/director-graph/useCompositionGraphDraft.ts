import { useCallback, useState } from 'react';

import {
  createCompositionGraphDraft,
  updateCompositionGraphDraft,
  type CompositionGraphDraft,
  type CompositionGraphDraftMutation,
} from '@/lib/composition-graph';

export function useCompositionGraphDraft({
  apiUrl,
  workspaceId,
}: {
  apiUrl: string;
  workspaceId: string;
}) {
  const [draft, setDraft] = useState<CompositionGraphDraft | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const saveDraft = useCallback(
    async (payload: CompositionGraphDraftMutation) => {
      setSaving(true);
      setSaveError(null);
      try {
        const response = draft?.id
          ? await updateCompositionGraphDraft(apiUrl, workspaceId, draft.id, payload)
          : await createCompositionGraphDraft(apiUrl, workspaceId, payload);
        setDraft(response.draft);
        return response.draft;
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : 'Failed to save composition graph draft.';
        setSaveError(message);
        throw cause;
      } finally {
        setSaving(false);
      }
    },
    [apiUrl, draft?.id, workspaceId],
  );

  return {
    draft,
    saveDraft,
    saveError,
    saving,
  };
}
