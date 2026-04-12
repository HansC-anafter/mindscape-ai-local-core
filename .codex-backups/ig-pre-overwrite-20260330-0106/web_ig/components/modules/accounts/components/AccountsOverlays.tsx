import React from 'react';

import IGFollowingAnalyzer from '../../../IGFollowingAnalyzer';
import { ImportAccountsDialog } from './ImportAccountsDialog';

export function AccountsOverlays(props: {
  showImportDialog: boolean;
  importHandles: string;
  onImportHandlesChange: (value: string) => void;
  onConfirmImport: () => void;
  confirmImportDisabled: boolean;
  onCancelImport: () => void;

  showFollowingAnalyzer: boolean;
  onCloseFollowingAnalyzer: () => void;
  workspaceId: string;
  apiUrl: string;
  onFollowingAnalyzerComplete: () => void;
  defaultUserDataDir: string;
  defaultUsername?: string;
}) {
  const {
    showImportDialog,
    importHandles,
    onImportHandlesChange,
    onConfirmImport,
    confirmImportDisabled,
    onCancelImport,
    showFollowingAnalyzer,
    onCloseFollowingAnalyzer,
    workspaceId,
    apiUrl,
    onFollowingAnalyzerComplete,
    defaultUserDataDir,
    defaultUsername,
  } = props;

  return (
    <>
      <ImportAccountsDialog
        isOpen={showImportDialog}
        importHandles={importHandles}
        onImportHandlesChange={onImportHandlesChange}
        onConfirm={onConfirmImport}
        confirmDisabled={confirmImportDisabled}
        onCancel={onCancelImport}
      />
      {showFollowingAnalyzer && (
        <IGFollowingAnalyzer
          isOpen={showFollowingAnalyzer}
          onClose={onCloseFollowingAnalyzer}
          workspaceId={workspaceId}
          apiUrl={apiUrl}
          onComplete={onFollowingAnalyzerComplete}
          defaultUserDataDir={defaultUserDataDir}
          defaultUsername={defaultUsername}
        />
      )}
    </>
  );
}
