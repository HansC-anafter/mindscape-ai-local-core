'use client';

import { useState, useCallback } from 'react';

export interface ConflictInfo {
  hasConflict: boolean;
  suggestedVersion?: number;
  message?: string;
  path?: string;
}

export interface ConflictResponse {
  conflict?: ConflictInfo;
  error?: string;
}

/**
 * Hook for handling file conflicts when saving artifacts
 *
 * When a backend API returns a conflict response, this hook will:
 * 1. Detect the conflict
 * 2. Show a confirmation dialog
 * 3. Retry the operation with force=true if user confirms
 */
export function useConflictHandler() {
  const [conflictDialog, setConflictDialog] = useState<{
    isOpen: boolean;
    conflict: ConflictInfo;
    onConfirm: () => void;
    onCancel: () => void;
    onUseNewVersion?: () => void;
  } | null>(null);

  /**
   * Check if a response indicates a conflict
   */
  const detectConflict = useCallback((response: any): ConflictInfo | null => {
    // Check for conflict in response.conflict (priority check)
    if (response?.conflict?.hasConflict) {
      return {
        hasConflict: true,
        suggestedVersion: response.conflict.suggestedVersion,
        message: response.conflict.message,
        path: response.conflict.file_path
      };
    }

    // Check for conflict in response (directly check if response has conflict field)
    if (response?.conflict && typeof response.conflict === 'object') {
      // If conflict object exists but no hasConflict, check other markers
      if (response.conflict.file_exists || response.conflict.force_required) {
        return {
          hasConflict: true,
          suggestedVersion: response.conflict.suggestedVersion || response.suggested_version,
          message: response.conflict.message || 'File conflict detected',
          path: response.conflict.file_path
        };
      }
    }

    // Check for conflict in error response
    if (response?.error && response.error.includes('conflict')) {
      return {
        hasConflict: true,
        message: response.error
      };
    }

    // Check for HTTP 409 Conflict status
    if (response?.status === 409) {
      return {
        hasConflict: true,
        message: response.message || 'File conflict detected'
      };
    }

    return null;
  }, []);

  /**
   * Handle a response that may contain a conflict
   *
   * @param response - The API response
   * @param retryWithForce - Function to retry the operation with force=true
   * @param onSuccess - Callback when operation succeeds without conflict
   * @param onError - Callback when operation fails
   * @param onUseNewVersion - Optional callback when user chooses to use new version
   */
  const handleConflict = useCallback(
    async (
      response: any,
      retryWithForce: () => Promise<any>,
      onSuccess?: (data: any) => void,
      onError?: (error: Error) => void,
      onUseNewVersion?: () => Promise<any>
    ) => {
      const conflict = detectConflict(response);

      if (conflict) {
        // Show confirmation dialog
        setConflictDialog({
          isOpen: true,
          conflict,
          onConfirm: async () => {
            try {
              const result = await retryWithForce();
              setConflictDialog(null);
              if (onSuccess) {
                onSuccess(result);
              }
            } catch (err) {
              setConflictDialog(null);
              if (onError) {
                onError(err instanceof Error ? err : new Error(String(err)));
              }
            }
          },
          onCancel: () => {
            setConflictDialog(null);
            if (onError) {
              onError(new Error('Operation cancelled by user'));
            }
          },
          onUseNewVersion: onUseNewVersion ? async () => {
            try {
              const result = await onUseNewVersion();
              setConflictDialog(null);
              if (onSuccess) {
                onSuccess(result);
              }
            } catch (err) {
              setConflictDialog(null);
              if (onError) {
                onError(err instanceof Error ? err : new Error(String(err)));
              }
            }
          } : undefined
        });
      } else {
        // No conflict, proceed normally
        if (onSuccess) {
          onSuccess(response);
        }
      }
    },
    [detectConflict]
  );

  /**
   * Close the conflict dialog
   */
  const closeConflictDialog = useCallback(() => {
    setConflictDialog(null);
  }, []);

  return {
    conflictDialog,
    handleConflict,
    closeConflictDialog,
    detectConflict
  };
}

