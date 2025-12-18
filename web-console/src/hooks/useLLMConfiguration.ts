'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { llmConfigService } from '@/services/LLMConfigService';
import { useUIState } from '@/contexts/UIStateContext';

interface UseLLMConfigurationOptions {
  workspaceId?: string;
  profileId?: string;
  timeout?: number;
  enabled?: boolean;
  onSuccess?: (configured: boolean) => void;
  onError?: (error: Error) => void;
}

/**
 * useLLMConfiguration Hook
 * Manages LLM configuration status checking using LLMConfigService.
 *
 * @param apiUrl The base API URL for the LLM configuration endpoint.
 * @param options Optional configuration options.
 * @returns An object containing configuration status and control functions.
 */
export function useLLMConfiguration(
  apiUrl: string,
  options?: UseLLMConfigurationOptions
) {
  const { llmConfigured, setLlmConfigured } = useUIState();
  const [isChecking, setIsChecking] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef(true);

  const {
    workspaceId,
    profileId = 'default-user',
    timeout,
    enabled = true,
    onSuccess,
    onError,
  } = options || {};

  const checkConfiguration = useCallback(async () => {
    if (!enabled || !apiUrl) {
      return;
    }

    // Cancel previous request if any
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsChecking(true);
    setError(null);

    try {
      const configured = await llmConfigService.checkLLMConfiguration(apiUrl, {
        workspaceId,
        profileId,
        timeout,
        signal: controller.signal,
      });

      if (!isMountedRef.current) {
        return;
      }

      setLlmConfigured(configured);
      setIsChecking(false);
      onSuccess?.(configured);
    } catch (err: any) {
      if (!isMountedRef.current) {
        return;
      }

      // Don't set error for aborted requests
      if (err.name === 'AbortError') {
        setIsChecking(false);
        return;
      }

      const error = err instanceof Error ? err : new Error(String(err));
      setError(error);
      setLlmConfigured(false);
      setIsChecking(false);
      onError?.(error);
    }
  }, [apiUrl, workspaceId, profileId, timeout, enabled, setLlmConfigured, onSuccess, onError]);

  // Initial check on mount or when dependencies change
  useEffect(() => {
    if (enabled && apiUrl) {
      checkConfiguration();
    }

    return () => {
      isMountedRef.current = false;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [apiUrl, enabled, checkConfiguration]);

  return {
    llmConfigured,
    isChecking,
    error,
    checkConfiguration,
  };
}

