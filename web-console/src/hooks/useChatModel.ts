'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { llmConfigService } from '@/services/LLMConfigService';
import { useEnabledModels } from '@/app/settings/hooks/useEnabledModels';
import { useWorkspaceMetadata } from '@/contexts/WorkspaceMetadataContext';

interface ChatModelInfo {
  model_name: string;
  provider: string;
}

interface UseChatModelOptions {
  workspaceId?: string;
  profileId?: string;
  timeout?: number;
  enabled?: boolean;
  maxRetries?: number;
  retryDelay?: number;
  onSuccess?: (model: ChatModelInfo | null) => void;
  onError?: (error: Error) => void;
}

export function useChatModel(
  apiUrl: string,
  options?: UseChatModelOptions
) {
  const { enabledModels: enabledChatModels, loading: modelsLoading } = useEnabledModels('chat');
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
  const loadedKeyRef = useRef<string | null>(null);

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

  const loadModel = useCallback(async (retryCount = 0) => {
    if (!enabled || apiUrl == null) {
      return;
    }

    if (loadedKeyRef.current === requestKey || !isMountedRef.current) {
      return;
    }

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

      if (data.chat_model) {
        setCurrentChatModel(data.chat_model.model_name);
      }

      if (!modelsLoading) {
        setAvailableChatModels(
          enabledChatModels.map(m => ({
            model_name: m.model_name,
            provider: m.provider,
          }))
        );
      }

      loadedKeyRef.current = requestKey;
      setIsLoading(false);
      onSuccess?.(data.chat_model || null);
    } catch (err: any) {
      if (!isMountedRef.current) {
        return;
      }

      if (err.name === 'AbortError') {
        setIsLoading(false);
        return;
      }

      const isContentLengthError =
        err?.message?.includes('Content-Length') ||
        err?.message?.includes('ERR_CONTENT_LENGTH_MISMATCH') ||
        (err?.name === 'TypeError' && err?.message?.includes('Failed to fetch'));

      if (isContentLengthError && retryCount < maxRetries) {
        setTimeout(() => {
          loadModel(retryCount + 1);
        }, retryDelay * (retryCount + 1));
        return;
      }

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
    requestKey,
    timeout,
    enabled,
    maxRetries,
    retryDelay,
    enabledChatModels,
    modelsLoading,
    setCurrentChatModel,
    setAvailableChatModels,
    onSuccess,
    onError,
  ]);

  useEffect(() => {
    if (enabledChatModels.length > 0 && !modelsLoading) {
      setAvailableChatModels(
        enabledChatModels.map(m => ({
          model_name: m.model_name,
          provider: m.provider,
        }))
      );
    }
  }, [enabledChatModels, modelsLoading, setAvailableChatModels]);

  useEffect(() => {
    isMountedRef.current = true;
    if (enabled && apiUrl) {
      if (loadedKeyRef.current !== requestKey) {
        loadedKeyRef.current = null;
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

  const selectModel = useCallback((modelName: string) => {
    if (isMountedRef.current) {
      setCurrentChatModel(modelName);
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
