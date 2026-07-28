'use client';

import { useEffect, useMemo, useState } from 'react';

import type { MotionPracticeLessonHandoff } from './motionPracticeLessonHandoff';
import {
  fetchMotionPracticeReferenceProfileSelection,
  MotionPracticeReferenceProfileClientError,
  type MotionPracticeReferenceProfileSelection,
} from './motionPracticeReferenceProfileClient';

export type MotionPracticeResolvedLessonState = {
  status: 'idle' | 'resolving' | 'ready' | 'failed';
  handoff: MotionPracticeLessonHandoff | null;
  error: string | null;
};

const MAX_RETAINED_RESOLUTIONS = 64;
const profileResolutions = new Map<
  string,
  Promise<MotionPracticeReferenceProfileSelection>
>();

function resolutionKey(input: {
  apiUrl: string;
  workspaceId: string;
  handoff: MotionPracticeLessonHandoff;
}): string {
  return [
    input.apiUrl.trim().replace(/\/+$/, ''),
    input.workspaceId.trim(),
    input.handoff.sourceValue.trim(),
    input.handoff.motionReferenceProfileArtifactId?.trim() || '',
  ].join('|');
}

function resolveOnce(input: {
  apiUrl: string;
  workspaceId: string;
  handoff: MotionPracticeLessonHandoff;
}): Promise<MotionPracticeReferenceProfileSelection> {
  const key = resolutionKey(input);
  const existing = profileResolutions.get(key);
  if (existing) {
    return existing;
  }
  const pending = fetchMotionPracticeReferenceProfileSelection({
    apiUrl: input.apiUrl,
    workspaceId: input.workspaceId,
    sourceRef: input.handoff.sourceValue,
    artifactId: input.handoff.motionReferenceProfileArtifactId,
  });
  profileResolutions.set(key, pending);
  void pending.then(
    () => {
      if (profileResolutions.get(key) === pending) {
        profileResolutions.delete(key);
      }
    },
    () => {
      if (profileResolutions.get(key) === pending) {
        profileResolutions.delete(key);
      }
    },
  );
  while (profileResolutions.size > MAX_RETAINED_RESOLUTIONS) {
    const oldestKey = profileResolutions.keys().next().value;
    if (typeof oldestKey !== 'string') {
      break;
    }
    profileResolutions.delete(oldestKey);
  }
  return pending;
}

function readableResolutionError(error: unknown): string {
  const code = error instanceof MotionPracticeReferenceProfileClientError
    ? error.code
    : error instanceof Error
      ? error.message
      : 'motion_reference_profile_request_failed';
  if (code === 'motion_reference_profile_not_materialized') {
    return 'The selected reference does not have a ready motion profile.';
  }
  if (code === 'motion_reference_profile_source_conflict') {
    return 'The selected reference has conflicting terminal motion profiles.';
  }
  if (code === 'motion_reference_profile_selection_mismatch') {
    return 'The selected reference does not match its motion profile.';
  }
  return `Reference profile resolution failed: ${code}`;
}

export function buildResolvedMotionPracticeLessonHandoff(
  handoff: MotionPracticeLessonHandoff,
  selection: MotionPracticeReferenceProfileSelection,
): MotionPracticeLessonHandoff {
  return {
    ...handoff,
    sourceValue: selection.source_ref,
    courseChaptersInput: JSON.stringify(selection.chapters),
    motionReferenceProfileArtifactId: selection.artifact_id,
    referenceProfileResolutionStatus: 'ready',
    referenceProfileResolutionError: undefined,
  };
}

function needsProfileResolution(
  handoff: MotionPracticeLessonHandoff | null,
): handoff is MotionPracticeLessonHandoff {
  return Boolean(
    handoff
    && handoff.sourceValue.trim()
    && (
      !handoff.courseChaptersInput?.trim()
      || !handoff.motionReferenceProfileArtifactId?.trim()
    ),
  );
}

export function useMotionPracticeResolvedLesson(input: {
  apiUrl: string;
  workspaceId: string;
  handoff: MotionPracticeLessonHandoff | null;
}): MotionPracticeResolvedLessonState {
  const inputKey = useMemo(
    () => input.handoff ? resolutionKey({
      apiUrl: input.apiUrl,
      workspaceId: input.workspaceId,
      handoff: input.handoff,
    }) : '',
    [input.apiUrl, input.handoff, input.workspaceId],
  );
  const [state, setState] = useState<MotionPracticeResolvedLessonState>(() => ({
    status: input.handoff ? (needsProfileResolution(input.handoff) ? 'resolving' : 'ready') : 'idle',
    handoff: input.handoff && needsProfileResolution(input.handoff)
      ? {
          ...input.handoff,
          referenceProfileResolutionStatus: 'resolving',
        }
      : input.handoff,
    error: null,
  }));

  useEffect(() => {
    const handoff = input.handoff;
    if (!handoff) {
      setState({ status: 'idle', handoff: null, error: null });
      return undefined;
    }
    if (!needsProfileResolution(handoff)) {
      setState({ status: 'ready', handoff, error: null });
      return undefined;
    }
    let current = true;
    setState({
      status: 'resolving',
      handoff: {
        ...handoff,
        referenceProfileResolutionStatus: 'resolving',
        referenceProfileResolutionError: undefined,
      },
      error: null,
    });
    void resolveOnce({
      apiUrl: input.apiUrl,
      workspaceId: input.workspaceId,
      handoff,
    }).then((selection) => {
      if (!current) {
        return;
      }
      setState({
        status: 'ready',
        handoff: buildResolvedMotionPracticeLessonHandoff(handoff, selection),
        error: null,
      });
    }).catch((error) => {
      if (!current) {
        return;
      }
      const message = readableResolutionError(error);
      setState({
        status: 'failed',
        handoff: {
          ...handoff,
          referenceProfileResolutionStatus: 'failed',
          referenceProfileResolutionError: message,
        },
        error: message,
      });
    });
    return () => {
      current = false;
    };
  }, [input.apiUrl, input.handoff, input.workspaceId, inputKey]);

  return state;
}

export function clearMotionPracticeReferenceProfileResolutionCacheForTests(): void {
  profileResolutions.clear();
}
