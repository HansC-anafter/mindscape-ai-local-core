'use client';

import React from 'react';

interface InstructionPreviewProps {
    persona?: string;
    goals?: string[];
    antiGoals?: string[];
    styleRules?: string[];
    domainContext?: string;
}

/**
 * Read-only preview of workspace instruction in the same format
 * as _format_instruction() from workspace_instruction_helper.py.
 * Fields = source of truth; this is a pure render, no write-back.
 */
export default function InstructionPreview({
    persona,
    goals,
    antiGoals,
    styleRules,
    domainContext,
}: InstructionPreviewProps) {
    const hasContent = persona || (goals && goals.length > 0) || (antiGoals && antiGoals.length > 0) || (styleRules && styleRules.length > 0) || domainContext;

    if (!hasContent) {
        return (
            <div className="h-full flex items-center justify-center text-gray-400 dark:text-gray-500">
                <div className="text-center">
                    <div className="text-4xl mb-3">📝</div>
                    <div className="text-sm font-medium mb-1">指令預覽</div>
                    <div className="text-xs">在左側填入欄位後，此處會即時顯示 LLM 注入格式</div>
                </div>
            </div>
        );
    }

    // Render in the same format as _format_instruction()
    const lines: string[] = [];
    if (persona) {
        lines.push(`Persona: ${persona}`);
    }
    if (goals && goals.length > 0) {
        lines.push('Goals:');
        goals.forEach(g => lines.push(`  - ${g}`));
    }
    if (antiGoals && antiGoals.length > 0) {
        lines.push('Anti-goals (DO NOT):');
        antiGoals.forEach(a => lines.push(`  - ${a}`));
    }
    if (styleRules && styleRules.length > 0) {
        lines.push('Style:');
        styleRules.forEach(s => lines.push(`  - ${s}`));
    }
    if (domainContext) {
        lines.push(`Domain context:\n${domainContext}`);
    }

    const formattedBlock = `=== Workspace Instruction ===\n${lines.join('\n')}\n=== End Instruction ===`;

    return (
        <div className="h-full flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 border-b dark:border-gray-700 flex-shrink-0">
                <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">LLM Injection Preview</span>
                    <span className="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 rounded">read-only</span>
                </div>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
                <pre className="text-sm font-mono text-gray-800 dark:text-gray-200 whitespace-pre-wrap leading-relaxed bg-gray-50 dark:bg-gray-800/50 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                    {formattedBlock}
                </pre>
            </div>
        </div>
    );
}
