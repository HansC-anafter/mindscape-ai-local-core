'use client';

import React, { createContext, useContext, useState, useMemo, ReactNode } from 'react';

export interface DataPrompt {
  taskTitle?: string;
  description: string;
  dataType: 'file' | 'text' | 'both';
  prompt?: string;
  taskId?: string;
}

export interface DuplicateFileToast {
  message: string;
  count: number;
}

export interface UIState {
  input: string;
  setInput: (value: string) => void;
  llmConfigured: boolean | null;
  setLlmConfigured: (value: boolean | null) => void;
  isStreaming: boolean;
  setIsStreaming: (value: boolean) => void;
  copiedAll: boolean;
  setCopiedAll: (value: boolean) => void;
  dataPrompt: DataPrompt | null;
  setDataPrompt: (value: DataPrompt | null) => void;
  analyzingFile: boolean;
  setAnalyzingFile: (value: boolean) => void;
  duplicateFileToast: DuplicateFileToast | null;
  setDuplicateFileToast: (value: DuplicateFileToast | null) => void;
}

const UIStateContext = createContext<UIState | null>(null);

export function UIStateProvider({ children }: { children: ReactNode }) {
  const [input, setInput] = useState('');
  const [llmConfigured, setLlmConfigured] = useState<boolean | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [copiedAll, setCopiedAll] = useState(false);
  const [dataPrompt, setDataPrompt] = useState<DataPrompt | null>(null);
  const [analyzingFile, setAnalyzingFile] = useState(false);
  const [duplicateFileToast, setDuplicateFileToast] = useState<DuplicateFileToast | null>(null);

  const value = useMemo(
    () => ({
      input,
      setInput,
      llmConfigured,
      setLlmConfigured,
      isStreaming,
      setIsStreaming,
      copiedAll,
      setCopiedAll,
      dataPrompt,
      setDataPrompt,
      analyzingFile,
      setAnalyzingFile,
      duplicateFileToast,
      setDuplicateFileToast,
    }),
    [input, llmConfigured, isStreaming, copiedAll, dataPrompt, analyzingFile, duplicateFileToast]
  );

  return <UIStateContext.Provider value={value}>{children}</UIStateContext.Provider>;
}

export function useUIState() {
  const context = useContext(UIStateContext);
  if (!context) {
    throw new Error('useUIState must be used within UIStateProvider');
  }
  return context;
}

