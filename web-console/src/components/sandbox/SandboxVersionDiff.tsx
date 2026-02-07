'use client';

import React, { useState, useEffect } from 'react';
import { getSandboxFileContent, listSandboxFiles } from '@/lib/sandbox-api';

interface SandboxVersionDiffProps {
  workspaceId: string;
  sandboxId: string;
  fromVersion: string;
  toVersion: string;
}

export default function SandboxVersionDiff({
  workspaceId,
  sandboxId,
  fromVersion,
  toVersion,
}: SandboxVersionDiffProps) {
  const [fromFiles, setFromFiles] = useState<string[]>([]);
  const [toFiles, setToFiles] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fromContent, setFromContent] = useState<string>('');
  const [toContent, setToContent] = useState<string>('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadFiles = async () => {
      try {
        setLoading(true);
        const from = await listSandboxFiles(workspaceId, sandboxId, '', fromVersion);
        const to = await listSandboxFiles(workspaceId, sandboxId, '', toVersion);

        const fromPaths = from.map(f => f.path);
        const toPaths = to.map(f => f.path);

        setFromFiles(fromPaths);
        setToFiles(toPaths);
      } catch (err) {
        console.error('Failed to load files:', err);
      } finally {
        setLoading(false);
      }
    };

    loadFiles();
  }, [workspaceId, sandboxId, fromVersion, toVersion]);

  useEffect(() => {
    if (!selectedFile) {
      setFromContent('' as any);
      setToContent('' as any);
      return;
    }

    const loadFileContent = async () => {
      try {
        const [from, to] = await Promise.all([
          getSandboxFileContent(workspaceId, sandboxId, selectedFile, fromVersion).catch(() => null),
          getSandboxFileContent(workspaceId, sandboxId, selectedFile, toVersion).catch(() => null),
        ]);

        setFromContent(from?.content || '');
        setToContent(to?.content || '');
      } catch (err) {
        console.error('Failed to load file content:', err);
      }
    };

    loadFileContent();
  }, [selectedFile, workspaceId, sandboxId, fromVersion, toVersion]);

  const added = toFiles.filter(f => !fromFiles.includes(f));
  const removed = fromFiles.filter(f => !toFiles.includes(f));
  const modified = fromFiles.filter(f => toFiles.includes(f));

  if (loading) {
    return <div className="text-sm text-gray-500">Loading diff...</div>;
  }

  return (
    <div className="sandbox-version-diff h-full flex flex-col">
      <div className="border-b border-gray-200 dark:border-gray-800 p-4">
        <h3 className="font-semibold mb-2">Version Comparison</h3>
        <div className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
          <div>From: {fromVersion}</div>
          <div>To: {toVersion}</div>
          <div className="mt-2">
            <span className="text-green-600">+{added.length} added</span>
            {' '}
            <span className="text-red-600">-{removed.length} removed</span>
            {' '}
            <span className="text-blue-600">~{modified.length} modified</span>
          </div>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        <div className="w-64 border-r border-gray-200 dark:border-gray-800 overflow-y-auto p-2">
          <div className="space-y-1">
            {added.map(file => (
              <div
                key={file}
                onClick={() => setSelectedFile(file)}
                className={`p-2 text-sm cursor-pointer rounded ${
                  selectedFile === file ? 'bg-blue-100 dark:bg-blue-900' : 'hover:bg-gray-100 dark:hover:bg-gray-800'
                }`}
              >
                <span className="text-green-600">+</span> {file}
              </div>
            ))}
            {removed.map(file => (
              <div
                key={file}
                onClick={() => setSelectedFile(file)}
                className={`p-2 text-sm cursor-pointer rounded ${
                  selectedFile === file ? 'bg-blue-100 dark:bg-blue-900' : 'hover:bg-gray-100 dark:hover:bg-gray-800'
                }`}
              >
                <span className="text-red-600">-</span> {file}
              </div>
            ))}
            {modified.map(file => (
              <div
                key={file}
                onClick={() => setSelectedFile(file)}
                className={`p-2 text-sm cursor-pointer rounded ${
                  selectedFile === file ? 'bg-blue-100 dark:bg-blue-900' : 'hover:bg-gray-100 dark:hover:bg-gray-800'
                }`}
              >
                <span className="text-blue-600">~</span> {file}
              </div>
            ))}
          </div>
        </div>

        <div className="flex-1 flex overflow-hidden">
          {selectedFile && (
            <>
              <div className="flex-1 border-r border-gray-200 dark:border-gray-800 overflow-y-auto p-4">
                <div className="text-sm font-medium mb-2 text-red-600">{fromVersion}</div>
                <pre className="text-xs font-mono bg-gray-900 text-gray-100 p-4 rounded overflow-x-auto">
                  <code>{fromContent || '(file not found or empty)'}</code>
                </pre>
              </div>
              <div className="flex-1 overflow-y-auto p-4">
                <div className="text-sm font-medium mb-2 text-green-600">{toVersion}</div>
                <pre className="text-xs font-mono bg-gray-900 text-gray-100 p-4 rounded overflow-x-auto">
                  <code>{toContent || '(file not found or empty)'}</code>
                </pre>
              </div>
            </>
          )}
          {!selectedFile && (
            <div className="flex-1 flex items-center justify-center text-gray-500">
              Select a file to view diff
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

