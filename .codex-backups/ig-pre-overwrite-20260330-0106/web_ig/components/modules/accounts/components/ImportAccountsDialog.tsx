import React from 'react';

export function ImportAccountsDialog(props: {
  isOpen: boolean;
  importHandles: string;
  onImportHandlesChange: (value: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
  confirmDisabled: boolean;
}) {
  const {
    isOpen,
    importHandles,
    onImportHandlesChange,
    onConfirm,
    onCancel,
    confirmDisabled,
  } = props;

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 max-w-md w-full mx-4">
        <h3 className="text-lg font-bold text-gray-900 dark:text-gray-100 mb-4">
          Import Accounts
        </h3>
        <div className="space-y-4">
          <div>
            <label className="text-sm text-gray-700 dark:text-gray-300 mb-1 block">
              Account Handles (one per line)
            </label>
            <textarea
              value={importHandles}
              onChange={(e) => onImportHandlesChange(e.target.value)}
              placeholder="Example:&#10;username1&#10;username2&#10;username3"
              rows={6}
              className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600 font-mono"
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onConfirm}
              disabled={confirmDisabled}
              className="flex-1 px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              Import
            </button>
            <button
              onClick={onCancel}
              className="flex-1 px-4 py-2 text-sm bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

