'use client';

import React, { useState, useEffect } from 'react';
import {
  Sandbox,
  SandboxFile,
  SandboxFileContent,
  getSandbox,
  listSandboxFiles,
  getSandboxFileContent,
  listVersions,
} from '@/lib/sandbox-api';
import SandboxFileTree from './SandboxFileTree';
import SandboxFilePreview from './SandboxFilePreview';
import SandboxVersionTimeline from './SandboxVersionTimeline';
import DeployModal from '../deployment/DeployModal';
import MarkdownPreview from './renderers/MarkdownPreview';
import CodeDiffPreview from './renderers/CodeDiffPreview';
import ThreeJSPreview from './renderers/ThreeJSPreview';
import WebPagePreview from './renderers/WebPagePreview';
import SandboxVersionDiff from './SandboxVersionDiff';
import SandboxFileSearch from './SandboxFileSearch';

interface SandboxViewerProps {
  workspaceId: string;
  sandboxId: string;
  projectId?: string;
  executionId?: string;
  onDeploy?: () => void;
  apiUrl?: string;
}

type TabType = 'preview' | 'source' | 'history' | 'chat';

export default function SandboxViewer({
  workspaceId,
  sandboxId,
  projectId,
  executionId,
  onDeploy,
  apiUrl = '',
}: SandboxViewerProps) {
  const [sandbox, setSandbox] = useState<Sandbox | null>(null);
  const [files, setFiles] = useState<SandboxFile[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<SandboxFileContent | null>(null);
  const [versions, setVersions] = useState<string[]>([]);
  const [currentVersion, setCurrentVersion] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('source');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showDeployModal, setShowDeployModal] = useState(false);

  useEffect(() => {
    loadSandbox();
  }, [workspaceId, sandboxId]);

  useEffect(() => {
    if (sandbox) {
      loadFiles();
      loadVersions();
    }
  }, [sandbox, currentVersion]);

  useEffect(() => {
    if (selectedFile && sandbox) {
      loadFileContent(selectedFile);
    }
  }, [selectedFile, currentVersion, sandbox]);

  const loadSandbox = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getSandbox(workspaceId, sandboxId);
      setSandbox(data);
      setCurrentVersion(data.current_version || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sandbox');
    } finally {
      setLoading(false);
    }
  };

  const loadFiles = async () => {
    try {
      const data = await listSandboxFiles(
        workspaceId,
        sandboxId,
        '',
        currentVersion || undefined
      );
      setFiles(data);
    } catch (err) {
      console.error('Failed to load files:', err);
    }
  };

  const loadFileContent = async (filePath: string) => {
    try {
      const data = await getSandboxFileContent(
        workspaceId,
        sandboxId,
        filePath,
        currentVersion || undefined
      );
      setFileContent(data);
    } catch (err) {
      console.error('Failed to load file content:', err);
      setFileContent(null);
    }
  };

  const loadVersions = async () => {
    try {
      const data = await listVersions(workspaceId, sandboxId);
      setVersions(data);
    } catch (err) {
      console.error('Failed to load versions:', err);
    }
  };

  const handleFileSelect = (filePath: string) => {
    setSelectedFile(filePath);
    setActiveTab('source');
  };

  const handleVersionSelect = (version: string) => {
    setCurrentVersion(version);
    setSelectedFile(null);
    setFileContent(null);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="text-sm text-gray-500">Loading sandbox...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="text-sm text-red-500">Error: {error}</div>
      </div>
    );
  }

  if (!sandbox) {
    return null;
  }

  return (
    <div className="sandbox-viewer h-full flex flex-col">
      <div className="flex items-center justify-between border-b border-gray-200 dark:border-gray-800 p-4">
        <div>
          <h2 className="text-lg font-semibold">
            Sandbox: {sandbox.sandbox_type}
          </h2>
          <p className="text-sm text-gray-500">ID: {sandboxId}</p>
        </div>
        <button
          onClick={() => setShowDeployModal(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Deploy
        </button>
      </div>

      <div className="flex border-b border-gray-200 dark:border-gray-800">
        {(['preview', 'source', 'history', 'chat'] as TabType[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium ${
              activeTab === tab
                ? 'border-b-2 border-blue-600 text-blue-600'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      <div className="flex-1 flex overflow-hidden">
        {activeTab === 'source' && (
          <div className="flex-1 flex">
            <div className="w-64 border-r border-gray-200 dark:border-gray-800 overflow-y-auto flex flex-col">
              <div className="flex-1 overflow-y-auto">
                <SandboxFileTree
                  files={files}
                  selectedFile={selectedFile}
                  onFileSelect={handleFileSelect}
                />
              </div>
              <div className="border-t border-gray-200 dark:border-gray-800">
                <SandboxFileSearch
                  files={files}
                  selectedFile={selectedFile}
                  onFileSelect={handleFileSelect}
                />
              </div>
            </div>
            <div className="flex-1 overflow-y-auto">
              {fileContent ? (
                <SandboxFilePreview
                  file={fileContent}
                  filePath={selectedFile || ''}
                />
              ) : (
                <div className="flex items-center justify-center h-full text-gray-500">
                  Select a file to view
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'preview' && (
          <div className="flex-1 p-4">
            {sandbox.sandbox_type === 'threejs_hero' && (
              <ThreeJSPreview files={fileContent ? [fileContent] : []} />
            )}
            {sandbox.sandbox_type === 'writing_project' && fileContent && (
              <MarkdownPreview file={fileContent} />
            )}
            {sandbox.sandbox_type === 'project_repo' && fileContent && (
              <CodeDiffPreview file={fileContent} />
            )}
            {sandbox.sandbox_type === 'web_page' && (
              <WebPagePreview
                workspaceId={workspaceId}
                sandboxId={sandboxId}
                version={currentVersion || undefined}
              />
            )}
            {!['threejs_hero', 'writing_project', 'project_repo', 'web_page'].includes(sandbox.sandbox_type) && (
              <div className="text-sm text-gray-500">
                Preview renderer for {sandbox.sandbox_type} not available
              </div>
            )}
          </div>
        )}

        {activeTab === 'history' && (
          <div className="flex-1 flex flex-col">
            <div className="border-b border-gray-200 dark:border-gray-800 p-4">
              <SandboxVersionTimeline
                versions={versions}
                currentVersion={currentVersion}
                onVersionSelect={handleVersionSelect}
                workspaceId={workspaceId}
                sandboxId={sandboxId}
              />
            </div>
            {versions.length >= 2 && (
              <div className="flex-1 overflow-hidden">
                <SandboxVersionDiff
                  workspaceId={workspaceId}
                  sandboxId={sandboxId}
                  fromVersion={versions[versions.length - 2]}
                  toVersion={versions[versions.length - 1]}
                />
              </div>
            )}
          </div>
        )}

        {activeTab === 'chat' && (
          <div className="flex-1 p-4">
            <div className="text-sm text-gray-500">
              Chat interface will be implemented here
            </div>
          </div>
        )}
      </div>

      {showDeployModal && projectId && (
        <DeployModal
          workspaceId={workspaceId}
          projectId={projectId}
          sandboxId={sandboxId}
          isOpen={showDeployModal}
          onClose={() => setShowDeployModal(false)}
        />
      )}
    </div>
  );
}

