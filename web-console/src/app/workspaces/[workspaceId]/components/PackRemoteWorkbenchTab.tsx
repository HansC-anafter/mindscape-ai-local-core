'use client';

import React from 'react';

import { buildCapabilityWorkbenchPath } from '@/lib/capability-static-hosts';

interface PackRemoteWorkbenchTabProps {
  workspaceId: string;
  targetCapabilityCode: string | null;
  targetCapabilityLabel: string | null;
}

const GATEWAY_CONTROL_CAPABILITY_CODE = 'mindscape_cloud_integration';

export function buildGatewayControlPath(
  workspaceId: string,
  targetCapabilityCode: string | null = null,
): string {
  return buildCapabilityWorkbenchPath(
    workspaceId,
    GATEWAY_CONTROL_CAPABILITY_CODE,
    {
      searchParams: targetCapabilityCode
        ? {
            component: 'MindscapeMobileWorkbenchGatewayPage',
            target_capability: targetCapabilityCode,
          }
        : {
            component: 'MindscapeMobileWorkbenchGatewayPage',
          },
    },
  );
}

export function PackRemoteWorkbenchTab({
  workspaceId,
  targetCapabilityCode,
  targetCapabilityLabel,
}: PackRemoteWorkbenchTabProps) {
  const remoteWorkbenchUrl = React.useMemo(
    () => buildGatewayControlPath(workspaceId, targetCapabilityCode),
    [targetCapabilityCode, workspaceId],
  );

  return (
    <div className="flex h-full min-h-0 flex-col bg-[#f6f0e3]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#d7c7ae] bg-[#fffaf0] px-3 py-2">
        <div className="min-w-0">
          <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#8b6f48]">
            Remote Access
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[#5f513f]">
            <span className="font-medium text-[#2d2417]">Workspace allowlist console</span>
            <span className="text-[#b8ab97]">|</span>
            <span className="truncate">
              {targetCapabilityLabel || targetCapabilityCode || 'All eligible packs'}
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => window.open(remoteWorkbenchUrl, '_blank')}
          className="rounded-md border border-[#c9b598] bg-white px-3 py-1.5 text-[11px] font-medium text-[#5d4d38] hover:bg-[#f6ecdc]"
        >
          Open local console
        </button>
      </div>
      <div className="min-h-0 flex-1 bg-[#f6f0e3]">
        <iframe
          key={remoteWorkbenchUrl}
          title="Remote workbench control"
          src={remoteWorkbenchUrl}
          loading="lazy"
          className="h-full w-full border-0 bg-[#f6f0e3]"
          data-testid="pack-remote-workbench-iframe"
        />
      </div>
    </div>
  );
}

export default PackRemoteWorkbenchTab;
