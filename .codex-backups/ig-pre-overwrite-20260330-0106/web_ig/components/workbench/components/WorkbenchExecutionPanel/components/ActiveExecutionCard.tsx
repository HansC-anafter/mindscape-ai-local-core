/**
 * Active Execution Card Wrapper
 * Active runs own their debug refresh lifecycle so the parent panel only has
 * to manage fallback/terminal pinned executions.
 */
import React, { useEffect, useRef, useState } from 'react';
import type { RunInfo } from '../types';
import { useIGDebug } from '../hooks/useIGDebug';
import { ExecutionDebugCard } from './ExecutionDebugCard';
import { supportsIGAnalyzerDebug } from '../utils';
import { useExecutionPolling } from '@/hooks/useExecutionPolling';

interface ActiveExecutionCardProps {
    workspaceId: string;
    apiUrl: string;
    igExecutionId: string;
    igPinnedRun: RunInfo;
    igRerunAllowPartial: boolean;
    setIgRerunAllowPartial: (value: boolean) => void;
    cancelExecution: (executionId: string) => Promise<void>;
    rerunExecution: (executionId: string, overrideInputs?: Record<string, any>) => Promise<void>;
    canRerunStatus: (status: any) => boolean;
    cancelBusyId: string | null;
    rerunBusyId: string | null;
}

export function ActiveExecutionCard({
    workspaceId,
    apiUrl,
    igExecutionId,
    igPinnedRun,
    igRerunAllowPartial,
    setIgRerunAllowPartial,
    cancelExecution,
    rerunExecution,
    canRerunStatus,
    cancelBusyId,
    rerunBusyId,
}: ActiveExecutionCardProps) {
    const showIGAnalyzerDebug = supportsIGAnalyzerDebug(igPinnedRun?.playbook_code);
    const cardRef = useRef<HTMLDivElement | null>(null);
    const [isVisible, setIsVisible] = useState(false);

    const {
        igDebug,
        igDebugLoading,
        igDebugError,
        igDebugExpanded,
        setIgDebugExpanded,
        fetchLatestIGDebug,
        copyExecutionId,
        screenshotUrl,
    } = useIGDebug({
        apiUrl,
        workspaceId,
        executionId: showIGAnalyzerDebug ? igExecutionId : null,
    });

    useEffect(() => {
        if (!showIGAnalyzerDebug) return;
        const node = cardRef.current;
        if (!node || typeof IntersectionObserver === 'undefined') {
            setIsVisible(true);
            return;
        }
        const observer = new IntersectionObserver((entries) => {
            setIsVisible(entries.some((entry) => entry.isIntersecting));
        }, {
            root: null,
            rootMargin: '300px 0px',
            threshold: 0,
        });
        observer.observe(node);
        return () => observer.disconnect();
    }, [showIGAnalyzerDebug]);

    const enableDebugTransport = showIGAnalyzerDebug && (isVisible || igDebugExpanded);

    useEffect(() => {
        if (!enableDebugTransport) return;
        void fetchLatestIGDebug();
    }, [enableDebugTransport, fetchLatestIGDebug]);

    useExecutionPolling({
        executionId: enableDebugTransport ? igExecutionId : null,
        workspaceId,
        apiUrl,
        onUpdate: () => {
            // SSE events debounce fetchLatestIGDebug via pollFn.
        },
        pollIntervalMs: 10_000,
        // Active cards no longer hold dedicated execution SSE connections.
        // That was exhausting browser connection slots and starving other IG API loads.
        enableSSE: false,
        enablePollingFallback: true,
        pollFn: fetchLatestIGDebug,
    });

    return (
        <div ref={cardRef}>
            <ExecutionDebugCard
                workspaceId={workspaceId}
                apiUrl={apiUrl}
                igExecutionId={igExecutionId}
                igPinnedRun={igPinnedRun}
                latestIGRun={null}
                forcedExecution={null}
                igDebug={igDebug}
                igDebugLoading={igDebugLoading}
                igDebugError={igDebugError}
                igDebugExpanded={igDebugExpanded}
                igRerunAllowPartial={igRerunAllowPartial}
                setIgDebugExpanded={setIgDebugExpanded}
                setIgRerunAllowPartial={setIgRerunAllowPartial}
                fetchLatestIGDebug={fetchLatestIGDebug}
                copyExecutionId={copyExecutionId}
                screenshotUrl={screenshotUrl}
                cancelExecution={cancelExecution}
                rerunExecution={rerunExecution}
                canRerunStatus={canRerunStatus}
                cancelBusyId={cancelBusyId}
                rerunBusyId={rerunBusyId}
                enableRunnerDebugTransport={false}
            />
        </div>
    );
}
