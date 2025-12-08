'use client';

import React, { useState, useMemo } from 'react';
import { SandboxFile } from '@/lib/sandbox-api';

interface SandboxFileSearchProps {
  files: SandboxFile[];
  onFileSelect: (filePath: string) => void;
  selectedFile: string | null;
}

export default function SandboxFileSearch({
  files,
  onFileSelect,
  selectedFile,
}: SandboxFileSearchProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [fileTypeFilter, setFileTypeFilter] = useState<string>('all');

  const filteredFiles = useMemo(() => {
    let filtered = files;

    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(file =>
        file.path.toLowerCase().includes(query)
      );
    }

    if (fileTypeFilter !== 'all') {
      const ext = fileTypeFilter.toLowerCase();
      filtered = filtered.filter(file =>
        file.path.toLowerCase().endsWith(`.${ext}`)
      );
    }

    return filtered;
  }, [files, searchQuery, fileTypeFilter]);

  const fileTypes = useMemo(() => {
    const types = new Set<string>();
    files.forEach(file => {
      const ext = file.path.split('.').pop()?.toLowerCase();
      if (ext) types.add(ext);
    });
    return Array.from(types).sort();
  }, [files]);

  return (
    <div className="sandbox-file-search p-2">
      <div className="mb-4 space-y-2">
        <input
          type="text"
          placeholder="Search files..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded dark:bg-gray-700 dark:border-gray-600"
        />
        <select
          value={fileTypeFilter}
          onChange={(e) => setFileTypeFilter(e.target.value)}
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded dark:bg-gray-700 dark:border-gray-600"
        >
          <option value="all">All Types</option>
          {fileTypes.map(type => (
            <option key={type} value={type}>{type.toUpperCase()}</option>
          ))}
        </select>
      </div>

      <div className="text-xs text-gray-500 mb-2">
        {filteredFiles.length} of {files.length} files
      </div>

      <div className="space-y-1 max-h-96 overflow-y-auto">
        {filteredFiles.map((file) => (
          <div
            key={file.path}
            onClick={() => onFileSelect(file.path)}
            className={`px-2 py-1 text-sm cursor-pointer rounded ${
              selectedFile === file.path
                ? 'bg-blue-100 dark:bg-blue-900'
                : 'hover:bg-gray-100 dark:hover:bg-gray-800'
            }`}
          >
            <div className="truncate">{file.path}</div>
            <div className="text-xs text-gray-500">
              {(file.size / 1024).toFixed(2)} KB
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

