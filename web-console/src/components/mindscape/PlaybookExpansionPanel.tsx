'use client';

/**
 * Playbook Expansion Panel
 *
 * Displays playbook details and step DAG when expanding a node
 * with linked playbooks.
 */

import React from 'react';
import { usePlaybookDAG, type PlaybookStep } from '@/lib/mindscape-graph-api';

interface PlaybookExpansionPanelProps {
    playbookCode: string;
    onClose?: () => void;
}

export function PlaybookExpansionPanel({ playbookCode, onClose }: PlaybookExpansionPanelProps) {
    const { playbook, steps, isLoading, isError } = usePlaybookDAG(playbookCode);

    if (isLoading) {
        return (
            <div className="p-4 bg-indigo-50 rounded-lg border border-indigo-200 animate-pulse">
                <div className="h-4 bg-indigo-200 rounded w-1/3 mb-2"></div>
                <div className="h-3 bg-indigo-100 rounded w-2/3"></div>
            </div>
        );
    }

    if (isError || !playbook) {
        return (
            <div className="p-4 bg-red-50 rounded-lg border border-red-200">
                <span className="text-red-700 text-sm">
                    ⚠️ Failed to load playbook: {playbookCode}
                </span>
            </div>
        );
    }

    return (
        <div className="p-4 bg-gradient-to-br from-indigo-50 to-purple-50 rounded-lg border border-indigo-200">
            {/* Header */}
            <div className="flex items-start justify-between mb-3">
                <div>
                    <h4 className="font-semibold text-indigo-900">{playbook.name}</h4>
                    <code className="text-xs text-indigo-600 bg-indigo-100 px-1 rounded">
                        {playbook.playbook_code}
                    </code>
                </div>
                {onClose && (
                    <button
                        onClick={onClose}
                        className="text-gray-400 hover:text-gray-600 text-lg"
                    >
                        ×
                    </button>
                )}
            </div>

            {playbook.description && (
                <p className="text-sm text-gray-600 mb-3">{playbook.description}</p>
            )}

            {/* Step DAG Visualization */}
            {steps.length > 0 ? (
                <div className="mt-3">
                    <span className="text-sm font-medium text-indigo-800">
                        📋 Steps ({steps.length}):
                    </span>
                    <div className="mt-2 space-y-2">
                        {steps.map((step, idx) => (
                            <StepCard key={step.id} step={step} index={idx} />
                        ))}
                    </div>
                </div>
            ) : (
                <div className="text-sm text-gray-500 italic">
                    No steps defined
                </div>
            )}
        </div>
    );
}

interface StepCardProps {
    step: PlaybookStep;
    index: number;
}

function StepCard({ step, index }: StepCardProps) {
    const toolName = step.tool_slot || step.tool || 'Unknown';
    const hasGate = step.has_gate;
    const hasDeps = step.depends_on.length > 0;

    return (
        <div className={`
            p-2 rounded border text-sm
            ${hasGate ? 'bg-amber-50 border-amber-300' : 'bg-white border-gray-200'}
        `}>
            <div className="flex items-center gap-2">
                {/* Step number */}
                <span className="w-5 h-5 rounded-full bg-indigo-100 text-indigo-800 text-xs flex items-center justify-center font-medium">
                    {index + 1}
                </span>

                {/* Step ID */}
                <span className="font-medium text-gray-800">{step.id}</span>

                {/* Gate indicator */}
                {hasGate && (
                    <span className="px-1.5 py-0.5 bg-amber-200 text-amber-800 rounded text-xs font-medium">
                        🔐 {step.gate_type || 'gate'}
                    </span>
                )}
            </div>

            {/* Tool info */}
            <div className="mt-1 ml-7 text-xs text-gray-500">
                <span className="text-gray-400">→</span> {toolName}
            </div>

            {/* Dependencies */}
            {hasDeps && (
                <div className="mt-1 ml-7 text-xs text-gray-400">
                    depends on: {step.depends_on.join(', ')}
                </div>
            )}
        </div>
    );
}

export default PlaybookExpansionPanel;
