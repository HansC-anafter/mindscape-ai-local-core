'use client';

import React from 'react';
import { UploadedFile } from '@/hooks/useFileUpload';

interface FilePreviewGridProps {
  files: UploadedFile[];
  onRemove: (fileId: string) => void;
  formatFileSize?: (bytes: number) => string;
}

/**
 * FilePreviewGrid Component
 * Displays a grid of file previews with status indicators and remove functionality.
 *
 * @param files Array of uploaded files to display.
 * @param onRemove Callback function when a file is removed.
 * @param formatFileSize Optional function to format file size.
 */
export function FilePreviewGrid({
  files,
  onRemove,
  formatFileSize,
}: FilePreviewGridProps) {
  const defaultFormatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const formatSize = formatFileSize || defaultFormatFileSize;

  if (files.length === 0) {
    return null;
  }

  return (
    <div className="px-4 py-2 border-b border-gray-200/60 dark:border-gray-700/60">
      <div className="flex flex-wrap gap-2">
        {files.map((file) => (
          <div
            key={file.id}
            className="group relative w-16 h-16 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 overflow-hidden hover:border-blue-400 dark:hover:border-blue-500 transition-colors"
          >
            {file.preview ? (
              <img
                src={file.preview}
                alt={file.name}
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex flex-col items-center justify-center bg-gray-100 dark:bg-gray-700">
                <svg className="w-6 h-6 text-gray-400 dark:text-gray-500 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-[8px] text-gray-600 dark:text-gray-400 text-center truncate w-full px-0.5" title={file.name}>
                  {file.name.length > 10 ? `${file.name.substring(0, 8)}...` : file.name}
                </p>
              </div>
            )}

            {/* Status indicator overlay */}
            <div className="absolute top-0.5 right-0.5 z-10">
              {file.analysisStatus === 'analyzing' && (
                <div className="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin bg-white dark:bg-gray-800 shadow-sm" />
              )}
              {file.analysisStatus === 'completed' && (
                <div className="w-3 h-3 bg-green-500 rounded-full flex items-center justify-center shadow-sm">
                  <svg className="w-2 h-2 text-white" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                  </svg>
                </div>
              )}
              {file.analysisStatus === 'failed' && (
                <div className="w-3 h-3 bg-red-500 rounded-full flex items-center justify-center shadow-sm">
                  <svg className="w-2 h-2 text-white" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                  </svg>
                </div>
              )}
              {(!file.analysisStatus || file.analysisStatus === 'pending') && (
                <div className="w-3 h-3 bg-gray-400 dark:bg-gray-600 rounded-full shadow-sm" />
              )}
            </div>

            {/* Remove button - shown on hover */}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onRemove(file.id);
              }}
              className="absolute top-0.5 left-0.5 w-3.5 h-3.5 bg-red-500 hover:bg-red-600 text-white rounded-full opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
              aria-label="Remove file"
              title="Remove file"
            >
              <svg className="w-2 h-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            {/* File info tooltip on hover */}
            <div className="absolute bottom-0 left-0 right-0 bg-black/75 text-white text-[8px] px-0.5 py-0.5 opacity-0 group-hover:opacity-100 transition-opacity truncate">
              {file.name} ({formatSize(file.size)})
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

