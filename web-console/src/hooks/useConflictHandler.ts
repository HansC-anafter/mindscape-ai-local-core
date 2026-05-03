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

export function useConflictHandler() {
  const [conflictDialog, setConflictDialog] = useState<{
    isOpen: boolean;
    conflict: ConflictInfo;
    onConfirm: () => void;
    onCancel: () => void;
    onUseNewVersion?: () => void;
  } | null>(null);

  const detectConflict = useCallback((response: any): ConflictInfo | null => {
    if (response?.conflict?.hasConflict) {
      return {
        hasConflict: true,
        suggestedVersion: response.conflict.suggestedVersion,
        message: response.conflict.message,
        path: response.conflict.file_path
      };
    }

    if (response?.conflict && typeof response.conflict === 'object') {
      if (response.conflict.file_exists || response.conflict.force_required) {
        return {
          hasConflict: true,
          suggestedVersion: response.conflict.suggestedVersion || response.suggested_version,
          message: response.conflict.message || 'File conflict detected',
          path: response.conflict.file_path
        };
      }
    }

    if (response?.error && response.error.includes('conflict')) {
      return {
        hasConflict: true,
        message: response.error
      };
    }

    if (response?.status === 409) {
      return {
        hasConflict: true,
        message: response.message || 'File conflict detected'
      };
    }

    return null;
  }, []);

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
        if (onSuccess) {
          onSuccess(response);
        }
      }
    },
    [detectConflict]
  );

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
