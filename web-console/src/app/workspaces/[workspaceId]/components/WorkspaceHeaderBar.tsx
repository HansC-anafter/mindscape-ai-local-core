'use client';

import React from 'react';
import { DeviceStatusIndicator } from '../../components/DeviceStatusIndicator';
import TrainHeader from '../../../../components/execution/TrainHeader';
import VisibilityBadge from './VisibilityBadge';
import WorkspaceGroupIndicator from './WorkspaceGroupIndicator';
import { useWorkspaceGroup } from '@/contexts/WorkspaceGroupContext';
import type { WorkspaceVisibility } from '../workspace-page.types';

interface WorkspaceHeaderBarProps {
    workspace: {
        title: string;
        visibility?: WorkspaceVisibility;
        group_id?: string | null;
        workspace_role?: string | null;
    };
    workspaceId: string;
    apiUrl: string;
    executionState: {
        trainSteps: any[];
        overallProgress: number;
        isExecuting: boolean;
    };
    onWorkspaceNameEdit?: () => void;
}

export default function WorkspaceHeaderBar({
    workspace,
    workspaceId,
    apiUrl,
    executionState,
    onWorkspaceNameEdit,
}: WorkspaceHeaderBarProps) {
    const workspaceGroup = useWorkspaceGroup();
    return (
        <div className="relative">
            <TrainHeader
                workspaceName={workspace.title}
                steps={executionState.trainSteps}
                progress={executionState.overallProgress}
                isExecuting={executionState.isExecuting}
                workspaceId={workspaceId}
                onWorkspaceNameEdit={onWorkspaceNameEdit}
            />
            <div className="absolute left-0 top-1/2 -translate-y-1/2 flex items-center gap-1.5 z-20"
                style={{ left: 'var(--badge-left, auto)' }}
                ref={(el) => {
                    if (el) {
                        const header = el.parentElement;
                        const titleEl = header?.querySelector('h1');
                        if (titleEl) {
                            const titleRect = titleEl.getBoundingClientRect();
                            const headerRect = header!.getBoundingClientRect();
                            const left = titleRect.right - headerRect.left + 12;
                            el.style.left = `${left}px`;
                        }
                    }
                }}
            >
                <VisibilityBadge
                    workspaceId={workspaceId}
                    visibility={workspace.visibility || 'private'}
                    apiUrl={apiUrl}
                />
                {(workspaceGroup.isLoading || workspaceGroup.groups.length > 0) && (
                    <WorkspaceGroupIndicator
                        groups={workspaceGroup.groups}
                        activeGroup={workspaceGroup.activeGroup}
                        activeRole={workspaceGroup.activeRole}
                        isLoading={workspaceGroup.isLoading}
                        onSelect={workspaceGroup.selectGroup}
                    />
                )}
            </div>
            <div
                className="absolute right-14 top-1/2 z-20 flex -translate-y-1/2 items-center gap-2 md:right-4"
                data-testid="workspace-header-device-status-slot"
            >
                <DeviceStatusIndicator apiUrl={apiUrl} />
            </div>
        </div>
    );
}
