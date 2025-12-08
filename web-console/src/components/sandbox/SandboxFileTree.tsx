'use client';

import React from 'react';
import { SandboxFile } from '@/lib/sandbox-api';

interface SandboxFileTreeProps {
  files: SandboxFile[];
  selectedFile: string | null;
  onFileSelect: (filePath: string) => void;
}

export default function SandboxFileTree({
  files,
  selectedFile,
  onFileSelect,
}: SandboxFileTreeProps) {
  const buildTree = (files: SandboxFile[]) => {
    const tree: Record<string, any> = {};

    files.forEach((file) => {
      const parts = file.path.split('/');
      let current = tree;

      parts.forEach((part, index) => {
        if (index === parts.length - 1) {
          current[part] = file;
        } else {
          if (!current[part]) {
            current[part] = {};
          }
          current = current[part];
        }
      });
    });

    return tree;
  };

  const renderTree = (tree: Record<string, any>, path: string = '', level: number = 0) => {
    const entries = Object.entries(tree).sort(([a], [b]) => {
      const aIsFile = typeof tree[a] === 'object' && 'path' in tree[a];
      const bIsFile = typeof tree[b] === 'object' && 'path' in tree[b];
      if (aIsFile && !bIsFile) return 1;
      if (!aIsFile && bIsFile) return -1;
      return a.localeCompare(b);
    });

    return (
      <div className="pl-2">
        {entries.map(([name, value]) => {
          const fullPath = path ? `${path}/${name}` : name;
          const isFile = typeof value === 'object' && 'path' in value;
          const isSelected = selectedFile === fullPath;

          if (isFile) {
            return (
              <div
                key={fullPath}
                onClick={() => onFileSelect(fullPath)}
                className={`px-2 py-1 text-sm cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 ${
                  isSelected ? 'bg-blue-100 dark:bg-blue-900' : ''
                }`}
                style={{ paddingLeft: `${level * 16 + 8}px` }}
              >
                <span className="mr-2">📄</span>
                {name}
              </div>
            );
          } else {
            return (
              <div key={fullPath} style={{ paddingLeft: `${level * 16}px` }}>
                <div className="px-2 py-1 text-sm font-medium text-gray-600 dark:text-gray-400">
                  <span className="mr-2">📁</span>
                  {name}
                </div>
                {renderTree(value, fullPath, level + 1)}
              </div>
            );
          }
        })}
      </div>
    );
  };

  const tree = buildTree(files);

  return (
    <div className="sandbox-file-tree p-2">
      <div className="text-xs font-semibold text-gray-500 mb-2 px-2">Files</div>
      {files.length === 0 ? (
        <div className="text-xs text-gray-400 px-2">No files</div>
      ) : (
        renderTree(tree)
      )}
    </div>
  );
}

