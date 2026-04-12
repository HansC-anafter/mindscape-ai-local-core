import React from 'react';

import { CaptureAccountSnapshotCard } from './CaptureAccountSnapshotCard';
import { CaptureFollowingListCard } from './CaptureFollowingListCard';
import { RefreshAvatarsCard } from './RefreshAvatarsCard';

export function CapturesTab(props: {
  snapshotHandleInput: string;
  onSnapshotHandleInputChange: (value: string) => void;
  onCaptureSnapshot: () => void;
  captureDisabled: boolean;
  snapshotError: string | null;
  snapshotFocusToken?: number;

  onOpenFollowingAnalyzer: () => void;
  onRefreshTargets: () => void;

  // Avatar refresh props
  onRefreshAvatars: () => void;
  avatarRefreshLoading: boolean;
  avatarRefreshResult: {
    summary: {
      refreshed_count: number;
      skipped_count: number;
      failed_count: number;
    };
  } | null;
  avatarRefreshError: string | null;
  totalAccounts: number;
}) {
  const {
    snapshotHandleInput,
    onSnapshotHandleInputChange,
    onCaptureSnapshot,
    captureDisabled,
    snapshotError,
    snapshotFocusToken,
    onOpenFollowingAnalyzer,
    onRefreshTargets,
    onRefreshAvatars,
    avatarRefreshLoading,
    avatarRefreshResult,
    avatarRefreshError,
    totalAccounts,
  } = props;

  return (
    <div className="flex-1 overflow-y-auto space-y-2">
      <CaptureFollowingListCard
        onOpenFollowingAnalyzer={onOpenFollowingAnalyzer}
        onRefreshTargets={onRefreshTargets}
      />

      <CaptureAccountSnapshotCard
        snapshotHandleInput={snapshotHandleInput}
        onSnapshotHandleInputChange={onSnapshotHandleInputChange}
        onCaptureSnapshot={onCaptureSnapshot}
        captureDisabled={captureDisabled}
        snapshotError={snapshotError}
        focusToken={snapshotFocusToken}
      />

      <RefreshAvatarsCard
        onRefresh={onRefreshAvatars}
        loading={avatarRefreshLoading}
        result={avatarRefreshResult}
        error={avatarRefreshError}
        totalAccounts={totalAccounts}
      />
    </div>
  );
}
