'use client';

import { useState, useCallback, useRef } from 'react';

export interface UploadedFile {
  id: string;
  file: File;
  name: string;
  size: number;
  type: string;
  preview?: string;
  analysisStatus?: 'pending' | 'analyzing' | 'completed' | 'failed';
  analysisError?: string;
  fileId?: string;
  filePath?: string;
}

export function useFileUpload(workspaceId: string, apiUrl: string = '') {
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [analyzingFiles, setAnalyzingFiles] = useState<Set<string>>(new Set());
  const [isDragging, setIsDragging] = useState(false);
  const uploadedFilesRef = useRef<UploadedFile[]>([]);

  if (uploadedFilesRef.current !== uploadedFiles) {
    uploadedFilesRef.current = uploadedFiles;
  }

  const uploadFile = useCallback(async (file: UploadedFile): Promise<{ fileId: string; filePath: string }> => {
    try {
      const formData = new FormData();
      formData.append('file', file.file);
      if (file.name) formData.append('file_name', file.name);
      if (file.type) formData.append('file_type', file.type);
      if (file.size) formData.append('file_size', file.size.toString());

      const url = `${apiUrl}/api/v1/workspaces/${workspaceId}/files/upload`;
      const uploadResponse = await fetch(url, {
        method: 'POST',
        body: formData,
      });

      if (!uploadResponse.ok) {
        const responseText = await uploadResponse.clone().text();

        let errorData: any = {};
        try {
          errorData = JSON.parse(responseText);
        } catch {
          errorData = { detail: responseText || `Upload failed: ${uploadResponse.status}` };
        }

        let errorMessage: string;
        if (Array.isArray(errorData.detail)) {
          errorMessage = errorData.detail.map((err: any) => {
            if (typeof err === 'object') {
              return `${err.loc?.join('.') || 'unknown'}: ${err.msg || JSON.stringify(err)}`;
            }
            return String(err);
          }).join('\n');
        } else if (typeof errorData.detail === 'object') {
          errorMessage = JSON.stringify(errorData.detail, null, 2);
        } else {
          errorMessage = errorData.detail || errorData.message || `Upload failed: ${uploadResponse.status}`;
        }

        throw new Error(errorMessage);
      }

      const uploadResult = await uploadResponse.json();
      const fileId = uploadResult.file_id;
      const filePath = uploadResult.file_path;

      if (!fileId) {
        throw new Error('File upload succeeded but no file_id was returned');
      }

      setUploadedFiles(prev => prev.map(f =>
        f.id === file.id
          ? {
              ...f,
              fileId: fileId,
              filePath: filePath
            }
          : f
      ));

      return { fileId, filePath };
    } catch (err: any) {
      const errorMessage = err.message || 'File upload failed';
      setUploadedFiles(prev => prev.map(f =>
        f.id === file.id
          ? { ...f, analysisStatus: 'failed' as const, analysisError: errorMessage }
          : f
      ));
      throw err;
    }
  }, [workspaceId, apiUrl]);

  const analyzeFile = useCallback(async (file: UploadedFile): Promise<any> => {
    try {
      setAnalyzingFiles(prev => new Set(prev).add(file.id));
      setUploadedFiles(prev => prev.map(f =>
        f.id === file.id
          ? { ...f, analysisStatus: 'analyzing' as const }
          : f
      ));

      let fileId = file.fileId;
      let filePath = file.filePath;

      if (!fileId) {
        const uploadResult = await uploadFile(file);
        fileId = uploadResult.fileId;
        filePath = uploadResult.filePath;
      }

      const response = await fetch(
        `${apiUrl}/api/v1/workspaces/${workspaceId}/files/analyze`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            file_id: fileId,
            file_name: file.name,
            file_type: file.type,
            file_size: file.size
          })
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Analysis failed: ${response.status}`);
      }

      const result = await response.json();

      const returnedFileId = result.file_id || result.fileId || result.event_id || fileId;
      const returnedFilePath = result.file_path || result.saved_file_path || filePath;

      setUploadedFiles(prev => prev.map(f =>
        f.id === file.id
          ? {
              ...f,
              analysisStatus: 'completed' as const,
              fileId: returnedFileId,
              filePath: returnedFilePath
            }
          : f
      ));

      window.dispatchEvent(new CustomEvent('workspace-chat-updated'));

      return { ...result, fileId: returnedFileId, filePath: returnedFilePath };
    } catch (err: any) {
      const errorMessage = err.message || 'File analysis failed';
      setUploadedFiles(prev => prev.map(f =>
        f.id === file.id
          ? { ...f, analysisStatus: 'failed' as const, analysisError: errorMessage }
          : f
      ));
      throw err;
    } finally {
      setAnalyzingFiles(prev => {
        const next = new Set(prev);
        next.delete(file.id);
        return next;
      });
    }
  }, [workspaceId, apiUrl, uploadFile]);

  const addFiles = useCallback((files: FileList | null): UploadedFile[] => {
    if (!files || files.length === 0) {
      return [];
    }

    const currentFiles = uploadedFilesRef.current;
    const existingFiles = new Set(
      currentFiles.map(f => `${f.name}:${f.size}`)
    );

    const filesArray = Array.from(files);

    const newFiles = filesArray
      .filter(file => {
        const key = `${file.name}:${file.size}`;
        return !existingFiles.has(key);
      })
      .map((file) => {
        const id = `file-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const preview = file.type.startsWith('image/') ? URL.createObjectURL(file) : undefined;
        return {
          id,
          file,
          name: file.name,
          size: file.size,
          type: file.type,
          preview,
          analysisStatus: 'pending' as const
        };
      });

    setUploadedFiles(prev => {
      const updated = [...prev, ...newFiles];
      uploadedFilesRef.current = updated;
      return updated;
    });

    return newFiles;
  }, []);

  const removeFile = useCallback((fileId: string) => {
    setUploadedFiles(prev => {
      const file = prev.find(f => f.id === fileId);
      if (file?.preview) {
        URL.revokeObjectURL(file.preview);
      }
      return prev.filter(f => f.id !== fileId);
    });
  }, []);

  const clearFiles = useCallback(() => {
    setUploadedFiles(prev => {
      prev.forEach(file => {
        if (file.preview) {
          URL.revokeObjectURL(file.preview);
        }
      });
      return [];
    });
  }, []);

  return {
    uploadedFiles,
    analyzingFiles,
    isDragging,
    setIsDragging,
    uploadFile,
    analyzeFile,
    addFiles,
    removeFile,
    clearFiles,
    setUploadedFiles
  };
}

