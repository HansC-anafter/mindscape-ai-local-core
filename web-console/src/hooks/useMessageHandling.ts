'use client';

import { useCallback, useRef } from 'react';
import { useSendMessage } from '@/hooks/useSendMessage';
import { useMessages } from '@/contexts/MessagesContext';
import { useUIState } from '@/contexts/UIStateContext';
import { useLatest } from '@/hooks/useLatest';
import { useWorkspaceMetadata } from '@/contexts/WorkspaceMetadataContext';
import { useWorkspaceData } from '@/hooks/useWorkspaceData';
import { useScrollManagement } from '@/hooks/useScrollManagement';
import { ChatMessage } from '@/hooks/useChatEvents';
import { UploadedFile } from '@/hooks/useFileUpload';
import { t } from '@/lib/i18n';

interface UseMessageHandlingOptions {
  projectId?: string;
  threadId?: string | null;  // 🆕 Conversation thread ID
  onFileAnalyzed?: () => void;
  onMessageSent?: (message: ChatMessage) => void;
  onError?: (error: Error) => void;
}

/**
 * useMessageHandling Hook
 * Manages message sending, streaming message handling, error handling, and message copying.
 *
 * @param workspaceId The workspace ID.
 * @param apiUrl The base API URL.
 * @param options Optional configuration options.
 * @returns An object containing message handling functions.
 */
export function useMessageHandling(
  workspaceId: string,
  apiUrl: string = '',
  options?: UseMessageHandlingOptions
) {
  const { messages, setMessages } = useMessages();
  const { input, setInput, isStreaming, setIsStreaming, firstChunkReceived, setFirstChunkReceived } = useUIState();
  const { setContextTokenCount, setIsFallbackUsed } = useWorkspaceMetadata();
  const { loadContextTokenCount } = useWorkspaceData(workspaceId, apiUrl, { enabled: false });
  const { scrollToBottom } = useScrollManagement();
  const { sendMessage, isLoading: sendLoading, error: sendError } = useSendMessage(
    workspaceId,
    apiUrl,
    options?.projectId,
    options?.threadId  // 🆕 傳遞 threadId
  );

  const {
    onFileAnalyzed,
    onMessageSent,
    onError,
  } = options || {};

  const handleSend = useCallback(async (
    e: React.FormEvent,
    uploadedFiles: UploadedFile[],
    analyzingFiles: Set<string>,
    handleAnalyzeFile: (file: UploadedFile) => Promise<any>
  ) => {
    e.preventDefault();
    if ((!input.trim() && uploadedFiles.length === 0)) {
      return;
    }

    // Reset fallback state on new message
    setIsFallbackUsed(false);

    const currentInput = input.trim();
    const currentFiles = [...uploadedFiles];

    if (currentInput.trim()) {
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: currentInput,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, userMessage]);
      onMessageSent?.(userMessage);
    }
    setInput('');

    setTimeout(() => {
      scrollToBottom(true);
    }, 50);

    try {
      if (currentFiles.length > 0 && !currentInput.trim()) {
        for (const file of currentFiles) {
          await handleAnalyzeFile(file);
        }
        return;
      }

      if (currentFiles.length > 0) {
        const filesToAnalyze = currentFiles.filter(file => !analyzingFiles.has(file.id));
        if (filesToAnalyze.length > 0) {
          await Promise.all(
            filesToAnalyze.map(file => handleAnalyzeFile(file).catch(err => {
              console.error(`Error analyzing file ${file.name}:`, err);
            }))
          );
        }

        const stillAnalyzing = currentFiles.filter(file => analyzingFiles.has(file.id));
        if (stillAnalyzing.length > 0) {
          const maxWait = 2000;
          const startTime = Date.now();
          while (stillAnalyzing.some(file => analyzingFiles.has(file.id)) && (Date.now() - startTime) < maxWait) {
            await new Promise(resolve => setTimeout(resolve, 100));
          }
        }
      }

      const fileIds = currentFiles
        .filter(f => f.analysisStatus === 'completed' && f.fileId)
        .map(f => f.fileId!)
        .filter(Boolean);

      let assistantMessageId: string | null = null;
      let accumulatedText = '';

      const messageText = currentInput || (currentFiles.length > 0 ? `${t('uploadedFile')}：${currentFiles.map(f => f.name).join(', ')}` : '');

      setFirstChunkReceived(false);
      setIsStreaming(true);

      await sendMessage({
        message: messageText,
        files: fileIds,
        mode: 'auto',
        stream: true,
        onChunk: (chunk: string, metadata?: any) => {
          if (!accumulatedText) {
            setFirstChunkReceived(true);
          }
          if (metadata?.is_fallback) {
            setIsFallbackUsed(true);
          }
          accumulatedText += chunk;
          setMessages(prev => {
            const existingIndex = prev.findIndex(m => m.id === assistantMessageId);
            if (existingIndex >= 0) {
              const updated = [...prev];
              updated[existingIndex] = {
                ...updated[existingIndex],
                content: accumulatedText
              };
              return updated;
            } else {
              assistantMessageId = `assistant-${Date.now()}`;
              return [...prev, {
                id: assistantMessageId,
                role: 'assistant',
                content: accumulatedText,
                timestamp: new Date()
              }];
            }
          });

          setTimeout(() => {
            scrollToBottom();
          }, 50);
        },
        onComplete: (fullText: string, contextTokens?: number) => {
          setIsStreaming(false);
          setFirstChunkReceived(false);
          if (assistantMessageId) {
            setMessages(prev => prev.map(m =>
              m.id === assistantMessageId
                ? { ...m, content: fullText }
                : m
            ));
          }
          if (contextTokens !== undefined) {
            setContextTokenCount(contextTokens);
          } else {
            loadContextTokenCount();
          }
          setTimeout(() => {
            scrollToBottom();
          }, 150);
        }
      });

      onFileAnalyzed?.();
    } catch (err: any) {
      setIsStreaming(false);
      const error = err instanceof Error ? err : new Error(String(err));
      const errorMessage = error.message || t('failedToSendMessage');
      const errorChatMessage: ChatMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: errorMessage,
        timestamp: new Date(),
        event_type: 'error'
      };
      setMessages(prev => [...prev, errorChatMessage]);
      onError?.(error);
    }
  }, [
    input,
    setInput,
    setMessages,
    setIsStreaming,
    setContextTokenCount,
    scrollToBottom,
    sendMessage,
    onFileAnalyzed,
    onMessageSent,
    onError,
  ]);

  const { copiedAll, setCopiedAll } = useUIState();
  const messagesRef = useLatest(messages);

  const handleCopyAll = useCallback(async () => {
    const currentMessages = messagesRef.current;
    if (currentMessages.length === 0) {
      return;
    }

    const allMessagesText = currentMessages
      .filter((msg) => msg.event_type !== 'playbook_step')
      .map(msg => {
        const timestamp = msg.timestamp instanceof Date
          ? msg.timestamp
          : new Date(msg.timestamp);
        const formattedTime = timestamp.toLocaleTimeString(undefined, {
          hour: '2-digit',
          minute: '2-digit',
          hour12: true
        });
        const roleLabel = msg.role === 'user' ? t('user') : t('assistant');
        return `[${formattedTime}] ${roleLabel}: ${msg.content}`;
      }).join('\n\n');

    try {
      await navigator.clipboard.writeText(allMessagesText);
      setCopiedAll(true);
      setTimeout(() => setCopiedAll(false), 2000);
      return true;
    } catch (err) {
      console.error('Failed to copy all messages:', err);
      return false;
    }
  }, [messagesRef, setCopiedAll]);

  const handleCopyMessage = useCallback(async (messageId: string) => {
    const message = messages.find(m => m.id === messageId);
    if (message) {
      try {
        await navigator.clipboard.writeText(message.content);
        return true;
      } catch (err) {
        console.error('Failed to copy message:', err);
        return false;
      }
    }
    return false;
  }, [messages]);

  return {
    handleSend,
    handleCopyAll,
    handleCopyMessage,
    isLoading: sendLoading,
    error: sendError,
  };
}

