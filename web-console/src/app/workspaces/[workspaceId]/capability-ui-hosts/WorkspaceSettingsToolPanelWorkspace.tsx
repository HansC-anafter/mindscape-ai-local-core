'use client';

import React, { useEffect, useState } from 'react';
import { Save } from 'lucide-react';

import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { formatList, parseList } from './WorkspaceSettingsToolPanelUtils';

export function WorkspaceSection({ apiUrl }: { apiUrl: string }) {
  const workspaceData = useWorkspaceDataOptional();
  const workspace = workspaceData?.workspace;
  const [executionMode, setExecutionMode] = useState('hybrid');
  const [executionPriority, setExecutionPriority] = useState('medium');
  const [expectedArtifacts, setExpectedArtifacts] = useState('');
  const [intentAutoExecute, setIntentAutoExecute] = useState(false);
  const [intentThreshold, setIntentThreshold] = useState(0.8);
  const [sgrEnabled, setSgrEnabled] = useState(false);
  const [sgrMode, setSgrMode] = useState<'inline' | 'two_pass'>('inline');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const meta = workspace?.metadata || {};
    const intentConfig = workspace?.playbook_auto_execution_config?.intent_extraction || {};
    setExecutionMode(workspace?.execution_mode || 'hybrid');
    setExecutionPriority(workspace?.execution_priority || 'medium');
    setExpectedArtifacts(formatList(workspace?.expected_artifacts));
    setIntentAutoExecute(Boolean(intentConfig.auto_execute));
    setIntentThreshold(Number(intentConfig.confidence_threshold || 0.8));
    setSgrEnabled(Boolean(meta.sgr_enabled));
    setSgrMode(meta.sgr_mode === 'two_pass' ? 'two_pass' : 'inline');
  }, [workspace]);

  const saveWorkspace = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const updated = await workspaceData?.updateWorkspace?.({
        execution_mode: executionMode as any,
        execution_priority: executionPriority as any,
        expected_artifacts: parseList(expectedArtifacts),
        metadata: {
          ...(workspace?.metadata || {}),
          sgr_enabled: sgrEnabled,
          sgr_mode: sgrMode,
        },
      });
      const response = await fetch(`${apiUrl}/api/v1/workspaces/${workspace?.id || ''}/playbook-auto-exec-config`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          playbook_code: 'intent_extraction',
          auto_execute: intentAutoExecute,
          confidence_threshold: intentThreshold,
        }),
      });
      if (!updated || !response.ok) {
        throw new Error('Save failed');
      }
      setMessage('Saved');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3" data-testid="workspace-settings-workspace-section">
      <Field label="Execution Mode">
        <select
          className="w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900"
          value={executionMode}
          onChange={(event) => setExecutionMode(event.target.value)}
        >
          <option value="qa">QA</option>
          <option value="execution">Execution</option>
          <option value="hybrid">Hybrid</option>
          <option value="meeting">Meeting</option>
        </select>
      </Field>
      <Field label="Priority">
        <select
          className="w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900"
          value={executionPriority}
          onChange={(event) => setExecutionPriority(event.target.value)}
        >
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
        </select>
      </Field>
      <Field label="Expected Artifacts">
        <input
          className="w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900"
          value={expectedArtifacts}
          onChange={(event) => setExpectedArtifacts(event.target.value)}
        />
      </Field>
      <label className="flex items-center gap-2 rounded border border-gray-200 p-2 text-sm dark:border-gray-800">
        <input
          type="checkbox"
          checked={intentAutoExecute}
          onChange={(event) => setIntentAutoExecute(event.target.checked)}
        />
        <span>Intent auto-execute</span>
      </label>
      {intentAutoExecute ? (
        <Field label={`Confidence ${intentThreshold.toFixed(1)}`}>
          <input
            className="w-full"
            type="range"
            min={0.5}
            max={1}
            step={0.1}
            value={intentThreshold}
            onChange={(event) => setIntentThreshold(Number(event.target.value))}
          />
        </Field>
      ) : null}
      <label className="flex items-center gap-2 rounded border border-gray-200 p-2 text-sm dark:border-gray-800">
        <input
          type="checkbox"
          checked={sgrEnabled}
          onChange={(event) => setSgrEnabled(event.target.checked)}
        />
        <span>SGR</span>
      </label>
      {sgrEnabled ? (
        <Field label="SGR Mode">
          <select
            className="w-full rounded border border-gray-200 bg-white px-2 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900"
            value={sgrMode}
            onChange={(event) => setSgrMode(event.target.value === 'two_pass' ? 'two_pass' : 'inline')}
          >
            <option value="inline">Inline</option>
            <option value="two_pass">Two-pass</option>
          </select>
        </Field>
      ) : null}
      <button
        type="button"
        className="inline-flex w-full items-center justify-center gap-2 rounded bg-gray-900 px-3 py-2 text-sm font-semibold text-white hover:bg-gray-800 disabled:cursor-not-allowed disabled:bg-gray-400 dark:bg-gray-100 dark:text-gray-950 dark:hover:bg-white"
        disabled={saving || !workspace}
        onClick={() => void saveWorkspace()}
      >
        <Save aria-hidden="true" className="h-4 w-4" />
        {saving ? 'Saving' : 'Save'}
      </button>
      {message ? <div className="text-xs text-gray-500 dark:text-gray-400">{message}</div> : null}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">{label}</span>
      {children}
    </label>
  );
}
