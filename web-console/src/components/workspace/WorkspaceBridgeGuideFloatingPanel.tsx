'use client';

import React, { useState } from 'react';
import { Check, Copy } from 'lucide-react';

import { WorkspaceFloatingSettingsPanel } from './WorkspaceFloatingSettingsPanel';

interface WorkspaceBridgeGuideFloatingPanelProps {
  open: boolean;
  workspaceId: string;
  bridgeScriptPath?: string | null;
  onClose: () => void;
}

interface CommandRowProps {
  label: string;
  command: string;
}

function CommandRow({ label, command }: CommandRowProps) {
  const [copied, setCopied] = useState(false);

  const copyCommand = async () => {
    await navigator.clipboard.writeText(command);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="space-y-1 rounded border border-gray-200 p-3 dark:border-gray-800">
      <div className="text-xs font-semibold text-gray-700 dark:text-gray-300">{label}</div>
      <div className="flex items-start gap-2">
        <pre className="min-w-0 flex-1 overflow-x-auto whitespace-pre-wrap break-all rounded bg-gray-950 p-2 text-xs text-emerald-300">
          {command}
        </pre>
        <button
          type="button"
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded border border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-900"
          aria-label={`Copy ${label}`}
          onClick={() => void copyCommand()}
        >
          {copied ? <Check aria-hidden="true" className="h-4 w-4" /> : <Copy aria-hidden="true" className="h-4 w-4" />}
        </button>
      </div>
    </div>
  );
}

export function WorkspaceBridgeGuideFloatingPanel({
  open,
  workspaceId,
  bridgeScriptPath,
  onClose,
}: WorkspaceBridgeGuideFloatingPanelProps) {
  const unixBridgeScript = bridgeScriptPath || './scripts/start_cli_bridge.sh';

  return (
    <WorkspaceFloatingSettingsPanel
      open={open}
      title="Workspace CLI Bridge"
      closeLabel="Close CLI Bridge Guide"
      onClose={onClose}
    >
      <div className="space-y-4">
        <div className="rounded border border-gray-200 p-3 text-sm dark:border-gray-800">
          <div className="font-semibold text-gray-900 dark:text-gray-100">Connect local CLI runtimes</div>
          <div className="mt-1 text-xs leading-5 text-gray-500 dark:text-gray-400">
            Keep the bridge terminal open while Mindscape dispatches to local CLI agents.
          </div>
        </div>

        <div className="space-y-2">
          <CommandRow label="macOS / Linux all workspaces" command={`${unixBridgeScript} --all`} />
          <CommandRow label="macOS / Linux current workspace" command={`${unixBridgeScript} --workspace-id ${workspaceId}`} />
          <CommandRow label="Windows all workspaces" command=".\\scripts\\start_cli_bridge.ps1 -All" />
          <CommandRow label="Windows current workspace" command={`.\\scripts\\start_cli_bridge.ps1 -WorkspaceId ${workspaceId}`} />
        </div>
      </div>
    </WorkspaceFloatingSettingsPanel>
  );
}
