'use client';

import { useState, useCallback } from 'react';

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

  const convertFileToBase64 = useCallback((file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        resolve(result);
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }, []);

  const uploadFile = useCallback(async (file: UploadedFile): Promise<{ fileId: string; filePath: string }> => {
    const requestId = `req-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    try {
      console.log(`[${requestId}] === FRONTEND: FILE UPLOAD REQUEST START ===`);
      console.log(`[${requestId}] File info:`, {
        name: file.name,
        type: file.type,
        size: file.size,
        workspaceId: workspaceId,
        apiUrl: apiUrl
      });

      const formData = new FormData();
      formData.append('file', file.file);
      if (file.name) formData.append('file_name', file.name);
      if (file.type) formData.append('file_type', file.type);
      if (file.size) formData.append('file_size', file.size.toString());

      const formDataKeys = Array.from(formData.keys());
      console.log(`[${requestId}] FormData keys:`, formDataKeys);
      console.log(`[${requestId}] FormData entries:`, formDataKeys.map(key => {
        const value = formData.get(key);
        return { key, value: value instanceof File ? `File(${value.name}, ${value.size} bytes)` : value };
      }));

      const url = `${apiUrl}/api/v1/workspaces/${workspaceId}/files/upload`;
      console.log(`[${requestId}] Request URL:`, url);
      console.log(`[${requestId}] Request method: POST`);
      console.log(`[${requestId}] Sending fetch request...`);

      const requestStartTime = Date.now();

      // Ensure using native fetch, bypassing any interceptors
      console.log(`[${requestId}] FormData type check:`, formData instanceof FormData);
      console.log(`[${requestId}] FormData entries before fetch:`, Array.from(formData.entries()).map(([k, v]) => [k, v instanceof File ? `File(${v.name})` : v]));

      const uploadResponse = await fetch(url, {
        method: 'POST',
        body: formData,
        // Explicitly don't set Content-Type, let browser auto-set multipart/form-data with boundary
        headers: {
          // Don't set any headers, let browser handle automatically
        }
      });
      const requestDuration = Date.now() - requestStartTime;

      console.log(`[${requestId}] Fetch completed, checking response...`);

      console.log(`[${requestId}] === FRONTEND: RESPONSE RECEIVED ===`);
      console.log(`[${requestId}] Response status:`, uploadResponse.status);
      console.log(`[${requestId}] Response statusText:`, uploadResponse.statusText);
      console.log(`[${requestId}] Response headers:`, Object.fromEntries(uploadResponse.headers.entries()));
      console.log(`[${requestId}] Request duration:`, requestDuration, 'ms');

      if (!uploadResponse.ok) {
        console.error(`[${requestId}] === FRONTEND: ERROR RESPONSE ===`);
        // Get raw response text first
        const responseText = await uploadResponse.clone().text();
        console.error(`[${requestId}] Status:`, uploadResponse.status);
        console.error(`[${requestId}] Status Text:`, uploadResponse.statusText);
        console.error(`[${requestId}] Raw Response Text:`, responseText);
        console.error(`[${requestId}] Headers:`, Object.fromEntries(uploadResponse.headers.entries()));

        let errorData: any = {};
        try {
          errorData = JSON.parse(responseText);
          console.error(`[${requestId}] Parsed Error Data:`, JSON.stringify(errorData, null, 2));
        } catch (e) {
          console.error(`[${requestId}] Failed to parse JSON:`, e);
          errorData = { detail: responseText || `上傳失敗: ${uploadResponse.status}` };
        }

        // Build error message
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
          errorMessage = errorData.detail || errorData.message || `上傳失敗: ${uploadResponse.status}`;
        }

        console.error(`[${requestId}] Final Error Message:`, errorMessage);
        console.error(`[${requestId}] === FRONTEND: ERROR END ===`);
        throw new Error(errorMessage);
      }

      console.log(`[${requestId}] Response OK, parsing JSON...`);
      const uploadResult = await uploadResponse.json();
      console.log(`[${requestId}] Parsed result:`, uploadResult);
      const fileId = uploadResult.file_id;
      const filePath = uploadResult.file_path;

      console.log(`[${requestId}] Extracted fileId:`, fileId);
      console.log(`[${requestId}] Extracted filePath:`, filePath);

      if (!fileId) {
        console.error(`[${requestId}] ERROR: No file_id in response`);
        throw new Error('上傳成功但未返回 file_id');
      }

      console.log(`[${requestId}] Updating uploadedFiles state...`);
      setUploadedFiles(prev => prev.map(f =>
        f.id === file.id
          ? {
              ...f,
              fileId: fileId,
              filePath: filePath
            }
          : f
      ));

      console.log(`[${requestId}] === FRONTEND: FILE UPLOAD SUCCESS ===`);
      return { fileId, filePath };
    } catch (err: any) {
      console.error(`[${requestId}] === FRONTEND: EXCEPTION CAUGHT ===`);
      console.error(`[${requestId}] Error:`, err);
      console.error(`[${requestId}] Error message:`, err.message);
      console.error(`[${requestId}] Error stack:`, err.stack);
      const errorMessage = err.message || '文件上傳失敗';
      setUploadedFiles(prev => prev.map(f =>
        f.id === file.id
          ? { ...f, analysisStatus: 'failed' as const, analysisError: errorMessage }
          : f
      ));
      console.error(`[${requestId}] === FRONTEND: FILE UPLOAD FAILED ===`);
      throw err;
    }
  }, [workspaceId, apiUrl, convertFileToBase64]);

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
        throw new Error(errorData.detail || `分析失敗: ${response.status}`);
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
      const errorMessage = err.message || '文件分析失敗';
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

  const addFiles = useCallback((files: FileList | null) => {
    if (!files || files.length === 0) return;

    const newFiles: UploadedFile[] = Array.from(files).map((file) => {
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

    setUploadedFiles(prev => [...prev, ...newFiles]);
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


