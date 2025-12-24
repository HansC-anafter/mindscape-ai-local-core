'use client';

import React, { useState } from 'react';
import { useLocale, t } from '../../lib/i18n';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface PlaybookInfoProps {
  playbook: {
    metadata: {
      icon?: string;
      name: string;
      playbook_code: string;
      version: string;
      description?: string;
      tags: string[];
    };
  };
  isFavorite: boolean;
  onToggleFavorite: () => void;
  profileId?: string;
}

export default function PlaybookInfo({
  playbook,
  isFavorite,
  onToggleFavorite,
  profileId = 'test-user'
}: PlaybookInfoProps) {
  const [locale] = useLocale();
  const playbookCode = playbook.metadata.playbook_code;
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    status: 'idle' | 'testing' | 'passed' | 'failed' | 'error';
    message?: string;
  }>({ status: 'idle' });
  const [showFileUpload, setShowFileUpload] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  // Check if this playbook needs file uploads
  const needsFileUpload = playbookCode === 'pdf_ocr_processing';

  const uploadTestFiles = async (files: File[]) => {
    setIsUploading(true);
    try {
      const formData = new FormData();
      files.forEach(file => {
        formData.append('files', file);
      });

      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(
        `${apiUrl}/api/v1/playbooks/${playbookCode}/smoke-test/upload-files?profile_id=${profileId}`,
        {
          method: 'POST',
          body: formData,
        }
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || t('fileUploadFailed'));
      }

      const result = await response.json();
      setShowFileUpload(false);
      return result;
    } catch (error: any) {
      alert(t('fileUploadFailed') + ': ' + error.message);
      throw error;
    } finally {
      setIsUploading(false);
    }
  };

  const runSmokeTest = async () => {
    // Check if this playbook supports smoke test
    // For now, only show test button for playbooks that have tests
    // This will be handled by the API returning 404 for unsupported playbooks

    // If needs files and no files uploaded, show upload dialog
    if (needsFileUpload && uploadedFiles.length === 0) {
      setShowFileUpload(true);
      return;
    }

    // Upload files first if needed
    if (needsFileUpload && uploadedFiles.length > 0) {
      try {
        await uploadTestFiles(uploadedFiles);
      } catch (error) {
        return; // Error already shown
      }
    }

    setIsTesting(true);
    setTestResult({ status: 'testing', message: t('testingInProgress') });

    try {
      const useUploaded = needsFileUpload && uploadedFiles.length > 0;
      const apiUrl = API_URL.startsWith('http') ? API_URL : '';
      const response = await fetch(
        `${apiUrl}/api/v1/playbooks/${playbookCode}/smoke-test?profile_id=${profileId}&use_uploaded_files=${useUploaded}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        let errorMessage = t('testFailed');
        try {
          const error = await response.json();
          errorMessage = error.detail || error.message || t('testFailed');
          // Add status code to error message for better handling
          if (response.status === 404) {
            errorMessage = `404: ${errorMessage}`;
          }
        } catch (e) {
          errorMessage = `HTTP ${response.status}: ${response.statusText}`;
        }
        throw new Error(errorMessage);
      }

      const result = await response.json();
      const testStatus = result.test_status || result.test_results?.status;

      if (testStatus === 'passed') {
        setTestResult({
          status: 'passed',
          message: t('testPassed')
        });
      } else if (testStatus === 'failed') {
        const errors = result.test_results?.errors || [];
        setTestResult({
          status: 'failed',
          message: t('testExecutionError', { error: errors.join('; ') })
        });
      } else {
        setTestResult({
          status: 'error',
          message: t('testError', { error: result.test_results?.error || t('unknownError') })
        });
      }
    } catch (error: any) {
      // Handle 404 (test not available) differently
      const errorMsg = error.message || '';
      if (errorMsg.includes('404') || errorMsg.includes('not available')) {
        setTestResult({
          status: 'error',
          message: t('smokeTestNotAvailable')
        });
      } else {
        setTestResult({
          status: 'error',
          message: t('testExecutionError', { error: errorMsg || t('unknownError') })
        });
      }
    } finally {
      setIsTesting(false);
      // Clear result after 5 seconds
      setTimeout(() => {
        setTestResult({ status: 'idle' });
      }, 5000);
    }
  };

  // Use data directly from backend API - backend already returns localized data based on target_language
  const localizedName = playbook.metadata.name;
  const localizedDescription = playbook.metadata.description;
  const localizedTags = playbook.metadata.tags || [];

  return (
    <div className="lg:col-span-2 bg-surface-secondary shadow rounded-lg p-6">
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-4xl">{playbook.metadata.icon || '📋'}</span>
            <h1 className="text-3xl font-bold text-gray-900">
              {localizedName}
            </h1>
          </div>
          <p className="text-sm text-gray-500 mb-2">
            {playbook.metadata.playbook_code} v{playbook.metadata.version}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={runSmokeTest}
            disabled={isTesting || isUploading}
            className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
              isTesting || isUploading
                ? 'bg-gray-300 text-gray-600 cursor-not-allowed'
                : testResult.status === 'passed'
                ? 'bg-green-100 text-green-700 hover:bg-green-200'
                : testResult.status === 'failed' || testResult.status === 'error'
                ? 'bg-red-100 text-red-700 hover:bg-red-200'
                : 'bg-blue-100 text-blue-700 hover:bg-blue-200'
            }`}
            title={needsFileUpload ? t('runSmokeTestWithFile') : t('runSmokeTest')}
          >
            {isTesting ? t('testing') : isUploading ? t('uploading') : t('test')}
          </button>
          <button
            onClick={onToggleFavorite}
            className="text-3xl hover:scale-110 transition-transform"
          >
            {isFavorite ? '⭐' : '☆'}
          </button>
        </div>
      </div>

      {testResult.status !== 'idle' && testResult.message && (
        <div className={`mb-4 p-3 rounded-md text-sm ${
          testResult.status === 'passed'
            ? 'bg-green-50 text-green-800 border border-green-200'
            : testResult.status === 'failed' || testResult.status === 'error'
            ? 'bg-red-50 text-red-800 border border-red-200'
            : 'bg-blue-50 text-blue-800 border border-blue-200'
        }`}>
          {testResult.message}
        </div>
      )}

      {/* File Upload Modal */}
      {showFileUpload && needsFileUpload && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-surface-accent dark:bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold mb-4">{t('uploadTestPdfFiles')}</h3>
            <p className="text-sm text-gray-600 mb-4">
              {t('pleaseUploadPdfFiles')}
            </p>

            <input
              type="file"
              accept=".pdf"
              multiple
              onChange={(e) => {
                const files = Array.from(e.target.files || []);
                setUploadedFiles(files);
              }}
              className="w-full mb-4 p-2 border rounded"
            />

            {uploadedFiles.length > 0 && (
              <div className="mb-4">
                <p className="text-sm font-medium mb-2">{t('selectedFiles')}</p>
                <ul className="text-sm text-gray-600 space-y-1">
                  {uploadedFiles.map((file, idx) => (
                    <li key={idx}>• {file.name} ({(file.size / 1024).toFixed(1)} KB)</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex gap-2 justify-end">
              <button
                onClick={() => {
                  setShowFileUpload(false);
                  setUploadedFiles([]);
                }}
                className="px-4 py-2 text-gray-700 border border-gray-300 rounded hover:bg-gray-50"
              >
                {t('cancel')}
              </button>
              <button
                onClick={async () => {
                  if (uploadedFiles.length === 0) {
                    alert(t('pleaseSelectFile'));
                    return;
                  }
                  try {
                    await uploadTestFiles(uploadedFiles);
                    // Auto-run test after upload
                    setTimeout(() => runSmokeTest(), 500);
                  } catch (error) {
                    // Error already shown
                  }
                }}
                disabled={uploadedFiles.length === 0 || isUploading}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-300"
              >
                {isUploading ? t('uploading') : t('uploadAndTest')}
              </button>
            </div>
          </div>
        </div>
      )}

      {localizedDescription && (
        <p className="text-gray-600 mb-4">{localizedDescription}</p>
      )}

      {localizedTags.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {localizedTags.map(tag => (
            <span
              key={tag}
              className="px-3 py-1 bg-blue-100 text-blue-800 text-sm rounded-full"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
