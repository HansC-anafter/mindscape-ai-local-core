'use client';

import React from 'react';
import { AlertTriangle } from 'lucide-react';

interface PathChangeConfirmDialogProps {
  isOpen: boolean;
  oldPath: string;
  newPath: string;
  oldArtifactsDir?: string;
  newArtifactsDir?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function PathChangeConfirmDialog({
  isOpen,
  oldPath,
  newPath,
  oldArtifactsDir,
  newArtifactsDir,
  onConfirm,
  onCancel
}: PathChangeConfirmDialogProps) {
  if (!isOpen) return null;

  const artifactsDirChanged = oldArtifactsDir !== newArtifactsDir;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div
        className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-6">
          {/* Header */}
          <div className="flex items-start mb-4">
            <div className="flex-shrink-0">
              <AlertTriangle className="h-6 w-6 text-yellow-500" aria-hidden="true" />
            </div>
            <div className="ml-3 flex-1">
              <h3 className="text-lg font-semibold text-gray-900">Confirm Storage Path Change</h3>
            </div>
          </div>

          {/* Warning Message */}
          <div className="mb-4">
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
              <p className="text-sm text-yellow-800 mb-3">
                <strong>Warning:</strong> Changing the storage path affects future artifact archiving. Existing files may not be found automatically.
              </p>
              <ul className="text-sm text-yellow-700 space-y-1 list-disc list-inside">
                <li>Existing artifact files remain at the old path, but the system may not find them automatically.</li>
                <li>Future artifacts will be stored at the new path.</li>
                <li>Move old files manually or with system tools if migration is required.</li>
              </ul>
            </div>
          </div>

          {/* Path Changes */}
          <div className="mb-4 space-y-3">
            {oldPath !== newPath && (
              <div>
                <p className="text-sm font-medium text-gray-700 mb-1">Base Storage Path Change:</p>
                <div className="bg-gray-50 rounded p-2 space-y-1">
                  <div className="text-xs text-gray-600">
                    <span className="font-medium">Old path:</span>
                    <code className="ml-1 text-red-600">{oldPath || '(not set)'}</code>
                  </div>
                  <div className="text-xs text-gray-600">
                    <span className="font-medium">New path:</span>
                    <code className="ml-1 text-green-600">{newPath}</code>
                  </div>
                </div>
              </div>
            )}

            {artifactsDirChanged && (
              <div>
                <p className="text-sm font-medium text-gray-700 mb-1">Artifact Directory Change:</p>
                <div className="bg-gray-50 rounded p-2 space-y-1">
                  <div className="text-xs text-gray-600">
                    <span className="font-medium">Old directory:</span>
                    <code className="ml-1 text-red-600">{oldArtifactsDir || 'artifacts'}</code>
                  </div>
                  <div className="text-xs text-gray-600">
                    <span className="font-medium">New directory:</span>
                    <code className="ml-1 text-green-600">{newArtifactsDir || 'artifacts'}</code>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-3">
            <button
              onClick={onCancel}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={onConfirm}
              className="px-4 py-2 text-sm font-medium text-white bg-yellow-600 rounded-md hover:bg-yellow-700 transition-colors"
            >
              Confirm Change
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
