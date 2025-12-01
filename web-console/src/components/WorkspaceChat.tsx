'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { t } from '@/lib/i18n';
import SystemHealthCard from './SystemHealthCard';
import MultiAICollaborationCard from './MultiAICollaborationCard';
import { MessageItem } from './MessageItem';
import { useChatEvents, ChatMessage } from '@/hooks/useChatEvents';
import { useSendMessage } from '@/hooks/useSendMessage';
import { useFileUpload, UploadedFile } from '@/hooks/useFileUpload';
import IntentChips from '../app/workspaces/components/IntentChips';

interface WorkspaceChatProps {
  workspaceId: string;
  apiUrl?: string;
  onFileAnalyzed?: () => void;
}

export default function WorkspaceChat({
  workspaceId,
  apiUrl = '',
  onFileAnalyzed
}: WorkspaceChatProps) {
  const [input, setInput] = useState('');
  const [workspaceTitle, setWorkspaceTitle] = useState<string>('');
  const [llmConfigured, setLlmConfigured] = useState<boolean | null>(null);
  const [systemHealth, setSystemHealth] = useState<any>(null);
  const [showHealthCard, setShowHealthCard] = useState(false);
  const [analyzingFile, setAnalyzingFile] = useState(false);
  const [currentChatModel, setCurrentChatModel] = useState<string>('');
  const [availableChatModels, setAvailableChatModels] = useState<Array<{model_name: string; provider: string}>>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [contextTokenCount, setContextTokenCount] = useState<number | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [userScrolled, setUserScrolled] = useState(false);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [isInitialLoad, setIsInitialLoad] = useState(true);
  const [copiedAll, setCopiedAll] = useState(false);
  const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const scrollPositionRef = useRef<{ scrollTop: number; scrollHeight: number } | null>(null);
  const userScrolledRef = useRef(false);
  const autoScrollRef = useRef(true);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const messagesScrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const selectedMessageRef = useRef<string | null>(null);

  const {
    messages,
    loading: messagesLoading,
    error: messagesError,
    quickStartSuggestions,
    fileAnalysisResult,
    reload: reloadMessages,
    setMessages,
    setFileAnalysisResult,
    hasMore,
    loadingMore,
    loadMore
  } = useChatEvents(workspaceId, apiUrl);

  const prevMessagesLoadingRef = useRef<boolean>(true);

  const {
    sendMessage,
    isLoading: sendLoading,
    error: sendError
  } = useSendMessage(workspaceId, apiUrl);

  const fileUpload = useFileUpload(workspaceId, apiUrl);
  const {
    uploadedFiles,
    analyzingFiles,
    isDragging,
    setIsDragging,
    analyzeFile,
    addFiles,
    removeFile,
    clearFiles,
    setUploadedFiles
  } = fileUpload;

  const isLoading = sendLoading || messagesLoading;
  const error = sendError || messagesError;

  // Define scrollToBottom function early so it can be used in other functions
  const scrollToBottom = useCallback((force: boolean = false) => {
    if (!messagesScrollRef.current) return;

    if (force) {
      messagesScrollRef.current.scrollTo({
        top: messagesScrollRef.current.scrollHeight,
        behavior: 'smooth'
      });
      setAutoScroll(true);
      setUserScrolled(false);
    } else if (autoScroll && !userScrolled && messages.length > 0) {
      messagesScrollRef.current.scrollTo({
        top: messagesScrollRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, [messages.length, autoScroll, userScrolled]);

  // Check LLM configuration status and load chat model
  useEffect(() => {
    const checkLLMConfiguration = async () => {
      try {
        const response = await fetch(`${apiUrl}/api/v1/config/backend?profile_id=default-user`, {
          headers: { 'Content-Type': 'application/json' },
        });
        if (response.ok) {
          const config = await response.json();
          const currentBackend = config.available_backends?.[config.current_mode];
          setLlmConfigured(currentBackend?.available || false);
        } else {
          setLlmConfigured(false);
        }
      } catch (err) {
        console.error('Failed to check LLM configuration:', err);
        setLlmConfigured(false);
      }
    };

    const loadChatModel = async () => {
      try {
        const response = await fetch(`${apiUrl}/api/v1/system-settings/llm-models`);
        if (response.ok) {
          const data = await response.json();
          if (data.chat_model) {
            setCurrentChatModel(data.chat_model.model_name);
          }
          if (data.available_chat_models) {
            setAvailableChatModels(data.available_chat_models);
          }
        }
      } catch (err) {
        console.error('Failed to load chat model:', err);
      }
    };

    checkLLMConfiguration();
    loadChatModel();
  }, [apiUrl]);

  useEffect(() => {
    loadWorkspaceInfo();
    loadSystemHealth();
  }, [workspaceId]);

  const loadSystemHealth = async () => {
    try {
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/health`);
      if (response.ok) {
        const health = await response.json();
        setSystemHealth(health);
        setShowHealthCard(false);
      }
    } catch (err) {
      console.error('Failed to load system health:', err);
    }
  };

  // Cleanup file preview URLs on unmount
  useEffect(() => {
    return () => {
      setUploadedFiles(prev => {
        prev.forEach(file => {
          if (file.preview) {
            URL.revokeObjectURL(file.preview);
          }
        });
        return [];
      });
    };
  }, []);

  // REMOVED: workspace-chat-updated event listener
  // This was causing unwanted message reloads when user scrolls up
  // Messages are now only loaded on initial mount and when explicitly requested

  // Load context token count
  const loadContextTokenCount = useCallback(async () => {
    if (!workspaceId || !apiUrl) return;
    try {
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}/workbench/context-token-count`);
      if (response.ok) {
        const data = await response.json();
        setContextTokenCount(data.context_tokens || null);
      } else if (response.status === 404) {
        // Route might not be available yet, silently ignore
        setContextTokenCount(null);
      }
    } catch (err) {
      // Silently fail - this is a non-critical feature
      setContextTokenCount(null);
    }
  }, [workspaceId, apiUrl]);

  // Load token count on mount and when messages change
  useEffect(() => {
    if (workspaceId && apiUrl && !messagesLoading) {
      loadContextTokenCount();
    }
  }, [workspaceId, apiUrl, messagesLoading, messages.length, loadContextTokenCount]);

  // Cleanup scroll timeout on unmount
  useEffect(() => {
    return () => {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
    };
  }, []);

  const loadWorkspaceInfo = async () => {
    try {
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspaceId}`);
      if (response.ok) {
        const data = await response.json();
        setWorkspaceTitle(data.title || 'Workspace');
      }
    } catch (err) {
      console.error('Failed to load workspace info:', err);
    }
  };


  const handleAnalyzeFile = async (file: UploadedFile) => {
    try {
      const userFileMessage: ChatMessage = {
        id: `file-upload-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        role: 'user',
        content: `${t('uploadedFile')}：${file.name}`,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, userFileMessage]);

      const result = await analyzeFile(file);

      if (result.fileId || result.file_path) {
        setUploadedFiles(prev => prev.map(f =>
          f.id === file.id
            ? {
                ...f,
                fileId: result.fileId || result.event_id,
                filePath: result.file_path || result.saved_file_path
              }
            : f
        ));
      }

      setFileAnalysisResult(result);

      if (onFileAnalyzed) {
        onFileAnalyzed();
      }

      setTimeout(() => {
        // Only scroll if user hasn't manually scrolled
        if (!userScrolledRef.current) {
          scrollToBottom();
        }
      }, 100);
      // Reset scroll state when new file analysis starts
      setUserScrolled(false);
      setAutoScroll(true);
      userScrolledRef.current = false;
      autoScrollRef.current = true;
    } catch (err: any) {
      console.error('Failed to analyze file:', err);
      const errorMessage = err.message || t('workspaceFileAnalysisFailed');
      const errorChatMessage: ChatMessage = {
        id: `file-error-${Date.now()}`,
        role: 'assistant',
        content: errorMessage,
        timestamp: new Date(),
        event_type: 'error'
      };
      setMessages(prev => [...prev, errorChatMessage]);
    }
  };

  const handlePathSelection = async (path: { type: string; action: string; data?: any }) => {
    setFileAnalysisResult(null);

    const fileIds = uploadedFiles
      .filter(f => f.analysisStatus === 'completed' && f.fileId)
      .map(f => f.fileId!)
      .filter(Boolean);

    try {
      const action = path.action || 'execute_playbook';
      const actionParams: Record<string, any> = {
        ...path.data
      };

      if (action === 'execute_playbook' && !actionParams.playbook_code) {
        actionParams.playbook_code = path.type;
        if (path.type === 'content_drafting' && path.data?.suggested_formats?.[0]) {
          actionParams.output_type = path.data.suggested_formats[0];
        }
      }

      await sendMessage({
        action: action,
        action_params: actionParams,
        files: fileIds,
        mode: 'auto'
      });

      if (onFileAnalyzed) {
        onFileAnalyzed();
      }
    } catch (err: any) {
      console.error('Failed to send message:', err);
      const errorMessage = err.message || t('workspaceSendMessageFailed');
      const errorChatMessage: ChatMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: errorMessage,
        timestamp: new Date(),
        event_type: 'error'
      };
      setMessages(prev => [...prev, errorChatMessage]);
    } finally {
      // Only scroll to bottom if user hasn't manually scrolled up
      if (!userScrolledRef.current) {
        scrollToBottom();
      }
    }
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    // Allow sending even when processing (non-blocking)
    if ((!input.trim() && uploadedFiles.length === 0)) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: input.trim() || (uploadedFiles.length > 0 ? `${t('uploadFile')} ${uploadedFiles.length} ${t('items')}` : ''),
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setUserScrolled(false);
    setAutoScroll(true);
    userScrolledRef.current = false;
    autoScrollRef.current = true;
    const currentInput = input.trim();
    const currentFiles = [...uploadedFiles];
    setInput('');
    clearFiles();

    // Immediately scroll to bottom when user sends message
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

      // Use streaming for better UX
      let assistantMessageId: string | null = null;
      let accumulatedText = '';
      let firstChunkReceived = false;

      await sendMessage({
        message: currentInput || (currentFiles.length > 0 ? `${t('uploadedFile')}：${currentFiles.map(f => f.name).join(', ')}` : ''),
        files: fileIds,
        mode: 'auto',
        stream: true,
        onChunk: (chunk: string) => {
          // Hide processing message when first chunk arrives
          if (!firstChunkReceived) {
            firstChunkReceived = true;
            setIsStreaming(true);
          }

          accumulatedText += chunk;
          // Update or create assistant message in real-time
          setMessages(prev => {
            const existingIndex = prev.findIndex(m => m.id === assistantMessageId);
            if (existingIndex >= 0) {
              // Update existing message
              const updated = [...prev];
              updated[existingIndex] = {
                ...updated[existingIndex],
                content: accumulatedText
              };
              return updated;
            } else {
              // Create new message
              assistantMessageId = `assistant-${Date.now()}`;
              return [...prev, {
                id: assistantMessageId,
                role: 'assistant',
                content: accumulatedText,
                timestamp: new Date()
              }];
            }
          });

          // Auto-scroll during streaming - use ref to get latest state
          setTimeout(() => {
            if (!userScrolledRef.current && autoScrollRef.current) {
              scrollToBottom();
            }
          }, 50);

        },
        onComplete: (fullText: string, contextTokens?: number) => {
          setIsStreaming(false);
          // Final update
          if (assistantMessageId) {
            setMessages(prev => prev.map(m =>
              m.id === assistantMessageId
                ? { ...m, content: fullText }
                : m
            ));
          }
          // Update token count if provided
          if (contextTokens !== undefined) {
            setContextTokenCount(contextTokens);
          } else {
            // Reload token count if not provided in response
            loadContextTokenCount();
          }
          // Scroll to bottom on completion only if user hasn't manually scrolled
          setTimeout(() => {
            if (!userScrolledRef.current && autoScrollRef.current) {
              scrollToBottom();
            }
          }, 150);
        }
      });

      if (onFileAnalyzed) {
        onFileAnalyzed();
      }
    } catch (err: any) {
      setIsStreaming(false);
      const errorMessage = err.message || t('failedToSendMessage');
      const errorChatMessage: ChatMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: errorMessage,
        timestamp: new Date(),
        event_type: 'error'
      };
      setMessages(prev => [...prev, errorChatMessage]);
    }
  };


  const handleScroll = useCallback(() => {
    if (!messagesScrollRef.current) return;

    const { scrollTop, scrollHeight, clientHeight } = messagesScrollRef.current;
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 150;
    const hasContentBelow = scrollHeight > scrollTop + clientHeight + 50;

    setShowScrollToBottom(hasContentBelow && !isNearBottom);

    if (isNearBottom) {
      setUserScrolled(false);
      setAutoScroll(true);
      userScrolledRef.current = false;
      autoScrollRef.current = true;
    } else {
      setUserScrolled(true);
      setAutoScroll(false);
      userScrolledRef.current = true;
      autoScrollRef.current = false;
    }
  }, []);

  // REMOVED: Auto-scroll on file analysis result
  // This was causing unwanted scroll resets when user scrolls up

  // Scroll to bottom on initial load
  useEffect(() => {
    if (prevMessagesLoadingRef.current !== messagesLoading) {
      prevMessagesLoadingRef.current = messagesLoading;
      if (isInitialLoad && !messagesLoading && messages.length > 0) {
        setIsInitialLoad(false);
        setTimeout(() => {
          if (messagesScrollRef.current) {
            messagesScrollRef.current.scrollTop = messagesScrollRef.current.scrollHeight;
          }
        }, 100);
      }
    }
  }, [messagesLoading, messages.length, isInitialLoad]);

  // Reset initial load flag when workspace changes
  useEffect(() => {
    setIsInitialLoad(true);
    prevMessagesLoadingRef.current = true;
  }, [workspaceId]);

  // Scroll to bottom when new messages arrive (only if user is at bottom)
  useEffect(() => {
    if (messages.length > 0 && !userScrolled && autoScroll && messagesScrollRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = messagesScrollRef.current;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 150;
      if (isNearBottom) {
        setTimeout(() => {
          if (messagesScrollRef.current) {
            messagesScrollRef.current.scrollTop = messagesScrollRef.current.scrollHeight;
          }
        }, 50);
      }
    }
  }, [messages.length, userScrolled, autoScroll]);

  // Auto-resize textarea based on content
  const adjustTextareaHeight = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      const maxHeight = 200; // Maximum height in pixels
      const lineHeight = 20; // Line height in pixels for text-xs
      const defaultHeight = lineHeight * 2; // Two lines visible by default
      const scrollHeight = textareaRef.current.scrollHeight;
      if (scrollHeight <= defaultHeight) {
        textareaRef.current.style.height = `${defaultHeight}px`;
      } else {
        textareaRef.current.style.height = `${Math.min(scrollHeight, maxHeight)}px`;
      }
    }
  };

  // Adjust height when input changes
  useEffect(() => {
    adjustTextareaHeight();
  }, [input]);

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend(e);
    }
  };

  // Copy all messages
  const handleCopyAll = useCallback(async () => {
    if (messages.length === 0) return;

    const allMessagesText = messages.map(msg => {
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
    } catch (err) {
      console.error('Failed to copy all messages:', err);
    }
  }, [messages]);

  // Keyboard shortcuts for copy
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd/Ctrl + Shift + C: Copy all messages
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'C') {
        e.preventDefault();
        handleCopyAll();
      }
      // Cmd/Ctrl + C: Copy selected message (if message is focused/selected)
      else if ((e.metaKey || e.ctrlKey) && e.key === 'c' && !e.shiftKey) {
        // Only handle if not in input field
        const activeElement = document.activeElement;
        if (activeElement && (
          activeElement.tagName === 'TEXTAREA' ||
          activeElement.tagName === 'INPUT' ||
          activeElement.isContentEditable
        )) {
          return; // Let default copy behavior work in input fields
        }

        // If a message is selected, copy it
        if (selectedMessageRef.current) {
          const message = messages.find(m => m.id === selectedMessageRef.current);
          if (message) {
            navigator.clipboard.writeText(message.content).catch(console.error);
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [messages, handleCopyAll]);

  const handleMessageCopy = (content: string) => {
    // Optional: Show toast notification
    if (process.env.NODE_ENV === 'development') {
      console.log('Message copied:', content.substring(0, 50) + '...');
    }
  };

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    const newFiles = addFiles(files);
    if (!newFiles || newFiles.length === 0) return;

    newFiles.forEach(file => {
      setTimeout(() => {
        handleAnalyzeFile(file).catch(err => {
          console.error(`Failed to analyze file ${file.name}:`, err);
        });
      }, 100);
    });
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    handleFileSelect(e.target.files);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    handleFileSelect(e.dataTransfer.files);
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  return (
    <div className="flex flex-col h-full bg-white relative">
      {/* LLM Not Configured Overlay */}
      {llmConfigured === false && (
        <div className="absolute inset-0 bg-white/95 backdrop-blur-sm z-50 flex items-center justify-center">
          <div className="max-w-md mx-4 p-6 bg-white rounded-lg shadow-lg border-2 border-yellow-300">
            <div className="flex items-start space-x-4">
              <div className="flex-shrink-0">
                <div className="w-12 h-12 bg-yellow-100 rounded-full flex items-center justify-center">
                  <svg className="w-6 h-6 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                </div>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900 mb-2">
                  {t('apiKeyNotConfigured')}
                </h3>
                <p className="text-sm text-gray-600 mb-4">
                  {t('settingsHint')}
                </p>
                <div className="flex space-x-3">
                  <a
                    href="/settings"
                    className="flex-1 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors text-center"
                  >
                    {t('goToSettings')} →
                  </a>
                  <button
                    onClick={() => {
                      // Re-check configuration when user dismisses
                      const recheck = async () => {
                        try {
                          const response = await fetch(`${apiUrl}/api/v1/config/backend?profile_id=default-user`, {
                            headers: { 'Content-Type': 'application/json' },
                          });
                          if (response.ok) {
                            const config = await response.json();
                            const currentBackend = config.available_backends?.[config.current_mode];
                            setLlmConfigured(currentBackend?.available || false);
                          } else {
                            setLlmConfigured(null); // Reset to checking state
                          }
                        } catch (err) {
                          setLlmConfigured(null); // Reset to checking state
                        }
                      };
                      recheck();
                    }}
                    className="px-4 py-2 bg-gray-200 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-300 transition-colors"
                  >
                    {t('cancel')}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}


      {/* Messages */}
      <div
        ref={messagesContainerRef}
        className="flex-1 overflow-hidden relative px-4 pt-4"
        style={{ minWidth: 0, maxWidth: '100%' }}
      >

        {analyzingFile && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-lg px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="flex space-x-1">
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0s' }} />
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                  <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }} />
                </div>
                <span className="text-sm text-gray-600">{t('thinking')}</span>
              </div>
            </div>
          </div>
        )}

        {/* Debug: Log when fileAnalysisResult exists but no collaboration_results */}
        {fileAnalysisResult && !fileAnalysisResult.collaboration_results && (() => {
          console.log('fileAnalysisResult exists but no collaboration_results:', fileAnalysisResult);
          return null;
        })()}

        {/* Debug: Show raw result if no collaboration results */}
        {fileAnalysisResult && !fileAnalysisResult.collaboration_results && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 mb-4">
            <p className="text-sm text-yellow-800">
              {t('workspaceAnalysisNoResults')}
            </p>
            <details className="mt-2">
              <summary className="text-xs text-yellow-600 cursor-pointer">查看原始回應</summary>
              <pre className="text-xs mt-2 overflow-auto">{JSON.stringify(fileAnalysisResult, null, 2)}</pre>
            </details>
          </div>
        )}

        <div
          ref={messagesScrollRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto"
          style={{ height: '100%', minHeight: 0 }}
        >
          {loadingMore && (
            <div className="flex justify-center py-2">
              <div className="text-xs text-gray-500 flex items-center gap-2">
                <div className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin"></div>
                <span>Loading older messages...</span>
              </div>
            </div>
          )}
          {messages.length === 0 && !messagesLoading ? (
            <div className="text-center text-gray-500 mt-8">
              <p>{t('noMessagesYet')}</p>
            </div>
          ) : (
            <div className="space-y-2 pb-4">
              {messages.map((message) => (
                <MessageItem
                  key={message.id}
                  message={message}
                  onCopy={handleMessageCopy}
                />
              ))}
            </div>
          )}
          {isLoading && !analyzingFile && !isStreaming && (
            <div className="flex justify-start py-4">
              <div className="bg-gray-100 rounded-lg px-6 py-4 shadow-sm">
                <div className="flex items-center gap-3">
                  <div className="w-5 h-5 border-2 border-gray-600 border-t-transparent rounded-full animate-spin" />
                  <span className="text-sm text-gray-700">{t('processingMessage')}</span>
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Scroll to bottom button - centered at bottom of messages area */}
        {showScrollToBottom && (
          <button
            onClick={() => scrollToBottom(true)}
            className="absolute bottom-4 left-1/2 transform -translate-x-1/2 z-50 bg-blue-500 hover:bg-blue-600 text-white rounded-full p-1.5 shadow-lg transition-all duration-200 hover:scale-110"
            aria-label="Scroll to bottom"
            title="Scroll to bottom"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-3 w-3"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 14l-7 7m0 0l-7-7m7 7V3"
              />
            </svg>
          </button>
        )}
      </div>

      {/* Error message */}
      {error && (
        <div className="px-4 py-2 bg-red-50 border-t border-red-200">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Quick Start Suggestions - Above input box */}
      {quickStartSuggestions.length > 0 && (
        <div className="px-4 pt-4 pb-2 border-t bg-gray-50">
          <div className="flex flex-wrap gap-2">
            {quickStartSuggestions.map((suggestion, idx) => (
              <button
                key={idx}
                onClick={() => {
                  setInput(suggestion);
                  // Auto focus on input after setting
                  setTimeout(() => {
                    const textarea = document.querySelector('textarea[name="workspace-chat-input"]') as HTMLTextAreaElement;
                    if (textarea) {
                      textarea.focus();
                    }
                  }, 100);
                }}
                className="px-3 py-1.5 text-xs bg-white border border-blue-300 text-blue-700 rounded-lg hover:bg-blue-50 hover:border-blue-400 transition-colors"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input form - Cursor-style expandable input */}
      <form
        onSubmit={handleSend}
        className="relative border-t bg-gray-50"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {llmConfigured === false && (
          <div className="mb-3 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
            <p className="text-sm text-yellow-800 mb-2">
              {t('apiKeyNotConfigured')}
            </p>
            <a
              href="/settings"
              className="text-sm text-blue-600 hover:text-blue-800 underline"
            >
              {t('goToSettings')} →
            </a>
          </div>
        )}

        {/* Uploaded files preview */}
        {uploadedFiles.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-2 w-full overflow-x-hidden" style={{ maxWidth: '100%' }}>
            {uploadedFiles.map((file) => (
              <div
                key={file.id}
                className="relative group flex items-center gap-2 bg-white border border-gray-300 rounded-lg px-3 py-2 flex-shrink-0"
                style={{
                  minWidth: 0,
                  maxWidth: 'calc(100% - 0.5rem)',
                  width: '100%'
                }}
              >
                {file.preview ? (
                  <img
                    src={file.preview}
                    alt={file.name}
                    className="w-10 h-10 object-cover rounded flex-shrink-0"
                  />
                ) : (
                  <div className="w-10 h-10 bg-gray-100 rounded flex items-center justify-center flex-shrink-0">
                    <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                )}
                <div className="flex-1 min-w-0 overflow-hidden" style={{ minWidth: 0 }}>
                  <p className="text-sm font-medium text-gray-900 truncate break-all" style={{
                    maxWidth: '100%',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap'
                  }}>{file.name}</p>
                  <div className="flex items-center gap-2">
                    <p className="text-xs text-gray-500 truncate">{formatFileSize(file.size)}</p>
                    {/* Analysis status indicator */}
                    {file.analysisStatus === 'analyzing' && (
                      <div className="flex items-center gap-1">
                        <div className="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                        <span className="text-xs text-blue-600">{t('workspaceAnalyzing')}</span>
                      </div>
                    )}
                    {file.analysisStatus === 'completed' && (
                      <div className="flex items-center gap-1">
                        <svg className="w-3 h-3 text-green-600" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                        </svg>
                        <span className="text-xs text-green-600">{t('workspaceAnalysisCompleted')}</span>
                      </div>
                    )}
                    {file.analysisStatus === 'failed' && (
                      <div className="flex items-center gap-1">
                        <svg className="w-3 h-3 text-red-600" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                        </svg>
                        <span className="text-xs text-red-600">{t('workspaceAnalysisFailed')}</span>
                      </div>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => removeFile(file.id)}
                  className="text-gray-400 hover:text-red-600 transition-colors flex-shrink-0 ml-1"
                  aria-label="Remove file"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Drag overlay */}
        {isDragging && (
          <div className="absolute inset-0 bg-blue-50/95 border-2 border-dashed border-blue-400 rounded-lg flex items-center justify-center z-10 backdrop-blur-sm">
            <div className="text-center">
              <svg className="w-16 h-16 text-blue-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              <p className="text-lg font-medium text-blue-600">{t('dropFilesHere')}</p>
            </div>
          </div>
        )}

        {/* Input container with expandable textarea */}
        <div className="flex flex-col border-t border-gray-200 bg-white">
          {/* Main input area */}
          <div className="flex-1 relative px-4 pt-3">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                adjustTextareaHeight();
              }}
              onKeyDown={handleKeyPress}
              placeholder={llmConfigured === false ? t('configureApiKeyFirst') : t('typeMessageOrDropFiles')}
              disabled={llmConfigured === false}
              className="w-full resize-none border-0 focus:outline-none focus:ring-0 disabled:bg-transparent disabled:cursor-not-allowed overflow-y-auto text-xs"
              style={{ minHeight: '2.5rem', maxHeight: '200px', lineHeight: '1.25rem' }}
              autoComplete="off"
              data-lpignore="true"
              data-form-type="other"
              data-1p-ignore="true"
              name="workspace-chat-input"
            />
            <input
              ref={fileInputRef}
              type="file"
              multiple
              onChange={handleFileInputChange}
              className="hidden"
              id="file-upload-input"
              disabled={llmConfigured === false}
            />
          </div>

          {/* Intent Chips - Show candidate intents after user input */}
          <IntentChips
            workspaceId={workspaceId}
            apiUrl={apiUrl || (typeof window !== 'undefined' ? window.location.origin.replace(':3000', ':8000') : 'http://localhost:8000')}
          />

          {/* Bottom bar with model selector and action buttons */}
          <div className="flex items-center justify-between px-4 pb-3 pt-2 border-t border-gray-100">
            {/* Left: Copy all button and Model selector */}
            <div className="flex items-center gap-2">
              {/* Copy all messages button */}
              {messages.length > 0 && (
                <button
                  onClick={handleCopyAll}
                  className={`text-xs px-2 py-1 border rounded transition-colors ${
                    copiedAll
                      ? 'bg-green-50 border-green-300 text-green-700'
                      : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
                  }`}
                  title={t('copyAllMessages') + ' (Cmd/Ctrl+Shift+C)'}
                >
                  {copiedAll ? (
                    <span className="flex items-center gap-1">
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      {t('copied')}
                    </span>
                  ) : (
                    <span className="flex items-center gap-1">
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                      </svg>
                      {t('copyAll')}
                    </span>
                  )}
                </button>
              )}
              <select
                value={currentChatModel}
                onChange={async (e) => {
                  const selectedModel = e.target.value;
                  const model = availableChatModels.find(m => m.model_name === selectedModel);
                  if (model) {
                    try {
                      const response = await fetch(
                        `${apiUrl}/api/v1/system-settings/llm-models/chat?model_name=${encodeURIComponent(model.model_name)}&provider=${encodeURIComponent(model.provider)}`,
                        { method: 'PUT', headers: { 'Content-Type': 'application/json' } }
                      );
                      if (response.ok) {
                        setCurrentChatModel(model.model_name);
                      }
                    } catch (err) {
                      console.error('Failed to update chat model:', err);
                    }
                  }
                }}
                className="text-xs px-2 py-1 border border-gray-300 rounded bg-white text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-1 focus:ring-blue-500"
                title={t('workspaceSelectChatModel')}
              >
                {availableChatModels.map((model) => (
                  <option key={model.model_name} value={model.model_name}>
                    {model.model_name}
                  </option>
                ))}
              </select>
              {currentChatModel && (
                <>
                  <span className="text-xs text-gray-500">✓ {currentChatModel}</span>
                  {contextTokenCount !== null && (
                    <span className="text-xs text-gray-400" title="Context tokens">
                      {contextTokenCount >= 1000
                        ? `${(contextTokenCount / 1000).toFixed(1)}k`
                        : contextTokenCount.toLocaleString()} tokens
                    </span>
                  )}
                </>
              )}
            </div>

            {/* Right: Action buttons */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={llmConfigured === false}
                className="p-2 rounded-lg text-gray-600 hover:bg-gray-100 transition-colors disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed"
                title={t('uploadFile')}
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                </svg>
              </button>
              <button
                type="submit"
                disabled={((!input.trim() && uploadedFiles.length === 0) || llmConfigured === false)}
                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  (!input.trim() && uploadedFiles.length === 0) || llmConfigured === false
                    ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                    : isLoading
                    ? 'bg-blue-500 text-white cursor-wait'
                    : 'bg-blue-600 text-white hover:bg-blue-700'
                }`}
              >
                {isLoading ? t('sending') : t('send')}
              </button>
            </div>
          </div>
        </div>
      </form>
    </div>
  );
}
