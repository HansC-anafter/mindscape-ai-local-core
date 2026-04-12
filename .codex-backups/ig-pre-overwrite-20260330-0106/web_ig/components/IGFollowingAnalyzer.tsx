'use client';

import React, { useEffect, useState } from 'react';
import { BaseModal } from '@/components/BaseModal';
import { getApiBaseUrl } from '@/lib/api-url';

import type { AnalysisResult, IGFollowingAnalyzerProps } from './followingAnalyzer/types';
import { useFollowingAnalyzerExecution } from './followingAnalyzer/hooks/useFollowingAnalyzerExecution';
import { AnalyzerForm } from './followingAnalyzer/components/AnalyzerForm';
import { AnalyzerProgressView } from './followingAnalyzer/components/AnalyzerProgressView';
import { AnalyzerResultsView } from './followingAnalyzer/components/AnalyzerResultsView';

export default function IGFollowingAnalyzer({
  isOpen,
  onClose,
  workspaceId,
  apiUrl,
  onComplete,
  defaultUserDataDir,
  defaultUsername,
}: IGFollowingAnalyzerProps) {
  const [targetUsername, setTargetUsername] = useState('');
  const [executionBackend, setExecutionBackend] = useState<'auto' | 'runner'>('auto');
  const [visitAccountPages, setVisitAccountPages] = useState(true);
  const [maxAccounts, setMaxAccounts] = useState<number | null>(null);
  const [userDataDir, setUserDataDir] = useState('');
  const [runMode, setRunMode] = useState('full');
  const [allowPartialResume, setAllowPartialResume] = useState(false);
  const hasProfileMismatch = Boolean(defaultUserDataDir && userDataDir && userDataDir !== defaultUserDataDir);

  const resolvedUserDataDir =
    (userDataDir || '').trim() ||
    (defaultUserDataDir || '').trim() ||
    '/app/data/ig-browser-profiles/default';

  useEffect(() => {
    if (isOpen && defaultUserDataDir) {
      setUserDataDir((prev) => prev || defaultUserDataDir);
    }
    if (isOpen && defaultUsername) {
      setTargetUsername(defaultUsername);
    }
  }, [isOpen, defaultUserDataDir, defaultUsername]);

  useEffect(() => {
    if (!isOpen) return;
    try {
      const key = `ig.following_analyzer.execution_backend:${workspaceId}`;
      const raw = window.localStorage.getItem(key);
      const next = (raw || '').trim().toLowerCase();
      const normalized = next === 'runner' ? 'runner' : 'auto';
      setExecutionBackend(normalized);
      if (raw && raw.trim().toLowerCase() !== normalized) {
        window.localStorage.setItem(key, normalized);
      }
    } catch {
      // ignore
    }
  }, [isOpen, workspaceId]);

  useEffect(() => {
    if (!isOpen) return;
    try {
      const key = `ig.following_analyzer.execution_backend:${workspaceId}`;
      window.localStorage.setItem(key, executionBackend);
    } catch {
      // ignore
    }
  }, [isOpen, workspaceId, executionBackend]);

  const baseApiUrl = apiUrl || getApiBaseUrl();

  const {
    isExecuting,
    progress,
    result,
    error,
    startAnalysis,
  } = useFollowingAnalyzerExecution({
    workspaceId,
    baseApiUrl,
    onComplete,
    targetUsername,
    executionBackend,
    visitAccountPages,
    maxAccounts,
    resolvedUserDataDir,
    runMode,
    allowPartialResume,
  });

  const handleExportCSV = () => {
    if (!result) return;

    const csv = [
      '\uFEFF',
      'Username,Display Name,Bio,Verified,Avatar URL,Account Link,Follower Count,Following Count,Post Count\n',
      ...result.accounts.map((acc) => {
        return [
          `"${acc.username}"`,
          `"${acc.display_name.replace(/"/g, '""')}"`,
          `"${acc.bio.replace(/"/g, '""')}"`,
          acc.is_verified ? 'Yes' : 'No',
          `"${acc.avatar_url}"`,
          `"${acc.account_link}"`,
          `"${acc.follower_count_text || ''}"`,
          `"${acc.following_count_text || ''}"`,
          `"${acc.post_count_text || ''}"`,
        ].join(',');
      }),
    ].join('\n');

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `ig_following_analysis_${targetUsername}_${Date.now()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      title="IG Following Account Analysis"
      maxWidth="max-w-6xl"
    >
      <div className="h-[85vh] flex flex-col">
        {!isExecuting && !result && (
          <AnalyzerForm
            targetUsername={targetUsername}
            onTargetUsernameChange={setTargetUsername}
            executionBackend={executionBackend}
            onExecutionBackendChange={setExecutionBackend}
            visitAccountPages={visitAccountPages}
            onVisitAccountPagesChange={setVisitAccountPages}
            maxAccounts={maxAccounts}
            onMaxAccountsChange={setMaxAccounts}
            userDataDir={userDataDir}
            onUserDataDirChange={setUserDataDir}
            runMode={runMode}
            onRunModeChange={setRunMode}
            allowPartialResume={allowPartialResume}
            onAllowPartialResumeChange={setAllowPartialResume}
            hasProfileMismatch={hasProfileMismatch}
            error={error}
            isExecuting={isExecuting}
            startDisabled={isExecuting || !targetUsername.trim()}
            onStart={startAnalysis}
          />
        )}

        {isExecuting && !result && (
          <AnalyzerProgressView progress={progress} />
        )}

        {result && (
          <AnalyzerResultsView result={result} onExportCSV={handleExportCSV} />
        )}
      </div>
    </BaseModal>
  );
}
