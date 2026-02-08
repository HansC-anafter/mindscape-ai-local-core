'use client';

import React, { useRef, useState } from 'react';
import { t } from '../../../lib/i18n';
import { settingsApi } from '../utils/settingsApi';
import { InlineAlert } from './InlineAlert';

interface InstallFromFileButtonProps {
  onSuccess: () => void;
}

type InstallPhase = 'idle' | 'installing' | 'mapping_roles' | 'completed' | 'error';

export function InstallFromFileButton({ onSuccess }: InstallFromFileButtonProps) {
  const [phase, setPhase] = useState<InstallPhase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [allowOverwrite, setAllowOverwrite] = useState(false);
  const [roleMappings, setRoleMappings] = useState<Array<{role_id: string; brief_label: string; blurb: string; is_fallback?: boolean}>>([]);
  const [mappingWarning, setMappingWarning] = useState<string | null>(null);
  const [installResult, setInstallResult] = useState<{has_fallback_mapping?: boolean} | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith('.mindpack')) {
      setError('File must be .mindpack format');
      // Clear file input on validation error
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
      return;
    }

    // Reset all states before starting new installation
    // This ensures clean state even if previous attempt failed
    setError(null);
    setSuccess(null);
    setRoleMappings([]);
    setMappingWarning(null);
    setInstallResult(null);
    setPhase('installing');

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('allow_overwrite', allowOverwrite.toString());

      // Phase 1: Install package
      setPhase('installing');
      const result = await settingsApi.postFormData<{
        capability_id: string;
        version: string;
        role_mappings?: Array<{role_id: string; brief_label: string; blurb: string; suggested_entry_prompt: string; is_fallback?: boolean}>;
        mapping_warning?: string;
        mapping_info?: string;
        has_fallback_mapping?: boolean;
      }>('/api/v1/capability-packs/install-from-file', formData);

      // Phase 2: Show role mapping results
      // Always show mapping phase if summary_for_roles exists (even if mapping failed)
      if (result.role_mappings !== undefined) {
        setPhase('mapping_roles');
        if (result.role_mappings && result.role_mappings.length > 0) {
          setRoleMappings(result.role_mappings);
        }
        // Wait a moment to show the mapping phase
        await new Promise(resolve => setTimeout(resolve, 1000));
      }

      // Store result for display
      setInstallResult(result);

      if (result.mapping_warning) {
        setMappingWarning(result.mapping_warning);
      } else if (result.mapping_info) {
        setMappingWarning(result.mapping_info);
      }

      setPhase('completed');
      setSuccess(
        `${t('successfullyInstalled' as any)}: ${result.capability_id} v${result.version}`
      );

      // Reset checkbox after successful installation
      setAllowOverwrite(false);

      // Clear file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }

      // Trigger refresh of installed capabilities list
      onSuccess();
    } catch (err) {
      setPhase('error');
      const errorMessage = err instanceof Error ? err.message : 'Installation failed';
      setError(errorMessage);
      // Clear file input on error to allow retry with same file
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  return (
    <div className="flex items-center gap-2">
      <label className="flex items-center space-x-1 cursor-pointer">
        <input
          type="checkbox"
          checked={allowOverwrite}
          onChange={(e) => setAllowOverwrite(e.target.checked)}
          className="rounded border-gray-300 text-gray-600 focus:ring-gray-500 w-3.5 h-3.5"
        />
        <span className="text-xs text-gray-700">
          {t('allowOverwrite' as any)}
        </span>
      </label>
      <input
        ref={fileInputRef}
        type="file"
        accept=".mindpack"
        onChange={handleFileSelect}
        onClick={(e) => {
          // Reset error state when user clicks to select a new file
          if (phase === 'error') {
            setError(null);
            setPhase('idle');
          }
        }}
        className="hidden"
        id="mindpack-file-input"
        disabled={phase === 'installing' || phase === 'mapping_roles'}
      />
      <label
        htmlFor="mindpack-file-input"
        className="inline-block px-3 py-1.5 text-sm bg-gray-600 text-white rounded-md hover:bg-gray-700 cursor-pointer disabled:opacity-50"
        style={{
          opacity: (phase === 'installing' || phase === 'mapping_roles') ? 0.5 : 1,
          cursor: (phase === 'installing' || phase === 'mapping_roles') ? 'not-allowed' : 'pointer',
          pointerEvents: (phase === 'installing' || phase === 'mapping_roles') ? 'none' : 'auto'
        }}
      >
        {phase === 'installing' ? t('installing' as any) :
         phase === 'mapping_roles' ? t('mappingRoles' as any) :
         phase === 'completed' ? t('selectMindpackFile' as any) :
         phase === 'error' ? t('selectMindpackFile' as any) :
         t('selectMindpackFile' as any)}
      </label>

      {/* Installation Progress */}
      {phase === 'installing' && (
        <div className="mt-3">
          <div className="flex items-center space-x-2 text-sm text-gray-600">
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-600"></div>
            <span>{t('installingCapabilityPack' as any)}</span>
          </div>
        </div>
      )}

      {phase === 'mapping_roles' && (
        <div className="mt-3 space-y-2">
          <div className="flex items-center space-x-2 text-sm text-gray-600">
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-gray-600"></div>
            <span>{t('analyzingRoleCapabilities' as any)}</span>
          </div>
        </div>
      )}

      {/* Role Mappings Display */}
      {phase === 'completed' && (
        <>
          {roleMappings.length > 0 && (
            <div className="mt-4 p-3 bg-blue-50 rounded-lg border border-blue-200">
              <p className="text-sm font-medium text-blue-900 mb-2">
                ✅ {t('rolesAddedCapabilities' as any)}
              </p>
              <ul className="space-y-1">
                {roleMappings.map((mapping, idx) => (
                  <li key={idx} className="text-sm text-blue-800">
                    • <strong>{mapping.role_id}</strong>: {mapping.brief_label} - {mapping.blurb}
                    {mapping.is_fallback && (
                      <span className="ml-2 text-xs text-blue-600">({t('temporarilyStoredInDefaultRole' as any)})</span>
                    )}
                  </li>
                ))}
              </ul>
              {installResult?.has_fallback_mapping && (
                <div className="mt-2 p-2 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-800">
                  💡 {t('capabilityStoredInDefaultAssistant' as any)}
                </div>
              )}
            </div>
          )}
          {installResult?.has_fallback_mapping && roleMappings.length === 0 && (
            <div className="mt-4 p-3 bg-yellow-50 rounded-lg border border-yellow-200">
              <p className="text-sm font-medium text-yellow-900 mb-2">
                💡 {t('capabilityStoredInDefaultAssistantTitle' as any)}
              </p>
              <p className="text-xs text-yellow-800">
                {t('capabilityAssignedToDefaultAssistant' as any)}
              </p>
            </div>
          )}
        </>
      )}

      {error && (
        <InlineAlert
          type="error"
          message={error}
          onDismiss={() => {
            setError(null);
            setPhase('idle');
            setRoleMappings([]);
            setMappingWarning(null);
            setInstallResult(null);
            // Clear file input to allow selecting the same file again
            if (fileInputRef.current) {
              fileInputRef.current.value = '';
            }
          }}
          className="mt-2"
        />
      )}

      {mappingWarning && (
        <InlineAlert
          type="warning"
          message={mappingWarning}
          onDismiss={() => setMappingWarning(null)}
          className="mt-2"
        />
      )}

      {success && (
        <InlineAlert
          type="success"
          message={success}
          onDismiss={() => {
            setSuccess(null);
            setPhase('idle');
            setRoleMappings([]);
            setInstallResult(null);
          }}
          className="mt-2"
        />
      )}
    </div>
  );
}
