'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { llmConfigService } from '@/services/LLMConfigService';
import { useWorkspaceMetadata, type ChatModel } from '@/contexts/WorkspaceMetadataContext';

interface UseChatModelOptions {
  workspaceId?: string;
  profileId?: string;
  timeout?: number;
  enabled?: boolean;
  maxRetries?: number;
  retryDelay?: number;
  onSuccess?: (model: ChatModel | null) => void;
  onError?: (error: Error) => void;
}

/**
 * useChatModel Hook
 * Manages chat model loading and selection using LLMConfigService and useEnabledModels.
 *
 * @param apiUrl The base API URL for the LLM models endpoint.
 * @param options Optional configuration options.
 * @returns An object containing model information and control functions.
 */
export function useChatModel(
  apiUrl: string,
  options?: UseChatModelOptions
) {
  const {
    currentChatModel,
    setCurrentChatModel,
    availableChatModels,
    setAvailableChatModels,
  } = useWorkspaceMetadata();

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef(true);
  const loadedApiUrlRef = useRef<string | null>(null);

  const {
    workspaceId,
    profileId = 'default-user',
    timeout,
    enabled = true,
    maxRetries = 2,
    retryDelay = 1000,
    onSuccess,
    onError,
  } = options || {};

  const requestKey = `${apiUrl}:${workspaceId || 'default'}:${profileId}`;

  const loadModel = useCallback(async (retryCount = 0, force = false) => {
    if (!enabled || apiUrl == null) {
      return;
    }

    // Prevent duplicate loads for the same API URL
    if ((!force && loadedApiUrlRef.current === requestKey) || !isMountedRef.current) {
      return;
    }

    // Cancel previous request if any
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsLoading(true);
    setError(null);

    try {
      const data = await llmConfigService.loadChatModel(apiUrl, {
        workspaceId,
        profileId,
        timeout,
        signal: controller.signal,
      });

      if (!isMountedRef.current) {
        return;
      }

      setCurrentChatModel(data.current_selection?.id || '');
      setAvailableChatModels(data.available_models || []);

      // Mark as loaded only on success
      loadedApiUrlRef.current = requestKey;
      setIsLoading(false);
      onSuccess?.(data.current_selection || null);
    } catch (err: any) {
      if (!isMountedRef.current) {
        return;
      }

      // Don't retry for aborted requests
      if (err.name === 'AbortError') {
        setIsLoading(false);
        return;
      }

      // Handle Content-Length mismatch and network errors with retry
      const isContentLengthError =
        err?.message?.includes('Content-Length') ||
        err?.message?.includes('ERR_CONTENT_LENGTH_MISMATCH') ||
        (err?.name === 'TypeError' && err?.message?.includes('Failed to fetch'));

      if (isContentLengthError && retryCount < maxRetries) {
        // Retry after a delay
        setTimeout(() => {
          loadModel(retryCount + 1, force);
        }, retryDelay * (retryCount + 1));
        return;
      }

      // Only set error if not a retry attempt or final failure
      if (retryCount === 0 || retryCount >= maxRetries) {
        const error = err instanceof Error ? err : new Error(String(err));
        setError(error);
        setIsLoading(false);
        onError?.(error);
      }
    }
  }, [
    apiUrl,
    workspaceId,
    profileId,
    timeout,
    enabled,
    maxRetries,
    retryDelay,
    setCurrentChatModel,
    setAvailableChatModels,
    onSuccess,
    onError,
    requestKey,
  ]);

  // Initial load on mount or when dependencies change
  useEffect(() => {
    isMountedRef.current = true;
    if (enabled && apiUrl) {
      // Reset loaded flag when API URL changes
      if (loadedApiUrlRef.current !== requestKey) {
        loadedApiUrlRef.current = null;
      }
      loadModel();
    }

    return () => {
      isMountedRef.current = false;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [apiUrl, enabled, loadModel, requestKey]);

  const selectModel = useCallback((selectionId: string) => {
    if (isMountedRef.current) {
      setCurrentChatModel(selectionId);
    }
  }, [setCurrentChatModel]);

  return {
    currentChatModel,
    availableChatModels,
    isLoading,
    error,
    loadModel,
    selectModel,
  };
}
