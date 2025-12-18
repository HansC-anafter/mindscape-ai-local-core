'use client';

import { useCallback, useRef } from 'react';
import { useFileUpload, UploadedFile } from '@/hooks/useFileUpload';
import { useUIState } from '@/contexts/UIStateContext';
import { useWorkspaceRefs } from '@/contexts/WorkspaceRefsContext';
import { t } from '@/lib/i18n';

interface UseFileHandlingOptions {
  onFileAnalyzed?: () => void;
  onAnalysisError?: (error: Error, file: UploadedFile) => void;
  duplicateToastDuration?: number;
  analysisDelay?: number;
}

/**
 * useFileHandling Hook
 * Wraps useFileUpload and provides file selection, drag-and-drop handling,
 * duplicate file detection, and file analysis orchestration.
 *
 * @param workspaceId The workspace ID.
 * @param apiUrl The base API URL.
 * @param options Optional configuration options.
 * @returns An object containing file handling functions and state.
 */
export function useFileHandling(
  workspaceId: string,
  apiUrl: string = '',
  options?: UseFileHandlingOptions
) {
  const {
    analyzingFile,
    setAnalyzingFile,
    duplicateFileToast,
    setDuplicateFileToast,
  } = useUIState();

  const { fileInputRef } = useWorkspaceRefs();

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
    setUploadedFiles,
  } = fileUpload;

  const duplicateToastTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const {
    onFileAnalyzed,
    onAnalysisError,
    duplicateToastDuration = 2000,
    analysisDelay = 200,
  } = options || {};

  const handleAnalyzeFile = useCallback(async (file: UploadedFile) => {
    try {
      setAnalyzingFile(true);
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

      onFileAnalyzed?.();
      return result;
    } catch (err: any) {
      const error = err instanceof Error ? err : new Error(String(err));
      onAnalysisError?.(error, file);
      throw error;
    } finally {
      setAnalyzingFile(false);
    }
  }, [analyzeFile, setAnalyzingFile, setUploadedFiles, onFileAnalyzed, onAnalysisError]);

  const handleFileSelect = useCallback((files: FileList | null) => {
    if (!files || files.length === 0) return;

    const filesArray = Array.from(files);
    const newFiles = addFiles(files);

    const duplicateCount = filesArray.length - (newFiles?.length || 0);
    if (duplicateCount > 0) {
      if (duplicateToastTimeoutRef.current) {
        clearTimeout(duplicateToastTimeoutRef.current);
      }
      setDuplicateFileToast({
        message: duplicateCount === 1
          ? 'Duplicate file skipped'
          : `${duplicateCount} duplicate files skipped`,
        count: duplicateCount
      });
      duplicateToastTimeoutRef.current = setTimeout(() => {
        setDuplicateFileToast(null);
      }, duplicateToastDuration);
    }

    if (!newFiles || newFiles.length === 0) {
      return;
    }

    newFiles.forEach((file, index) => {
      setTimeout(() => {
        handleAnalyzeFile(file).catch(err => {
          console.error(`[useFileHandling] Failed to analyze file ${file.name}:`, err);
        });
      }, index * analysisDelay);
    });
  }, [addFiles, handleAnalyzeFile, setDuplicateFileToast, duplicateToastDuration, analysisDelay]);

  const handleFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    handleFileSelect(e.target.files);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }, [handleFileSelect, fileInputRef]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, [setIsDragging]);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, [setIsDragging]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      handleFileSelect(files);
    }
  }, [handleFileSelect, setIsDragging]);

  return {
    ...fileUpload,
    uploadedFiles,
    analyzingFiles,
    isDragging,
    analyzingFile,
    duplicateFileToast,
    handleFileSelect,
    handleFileInputChange,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleAnalyzeFile,
    removeFile,
    clearFiles,
  };
}

