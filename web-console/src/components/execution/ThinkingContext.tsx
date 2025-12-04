'use client';

import React, { useState, useEffect, useRef } from 'react';

export interface PipelineStage {
  stage: 'intent_extraction' | 'playbook_selection' | 'task_assignment' | 'execution_start' | 'no_action_needed' | 'no_playbook_found' | 'execution_error';
  message: string;
  streaming?: boolean;
}

interface ThinkingContextProps {
  summary?: string;
  pipelineStage?: PipelineStage | null;
  isLoading?: boolean;
  onViewFullPlan?: () => void;
  enableTypewriter?: boolean;
  typewriterSpeed?: number;
}

export default function ThinkingContext({
  summary,
  pipelineStage,
  isLoading = false,
  onViewFullPlan,
  enableTypewriter = true,
  typewriterSpeed = 30,
}: ThinkingContextProps) {
  const [displayedSummary, setDisplayedSummary] = useState('');
  const [displayedPipelineMessage, setDisplayedPipelineMessage] = useState('');
  const [isTypingSummary, setIsTypingSummary] = useState(false);
  const [isTypingPipeline, setIsTypingPipeline] = useState(false);
  const previousSummaryRef = useRef<string | undefined>(undefined);
  const previousPipelineStageRef = useRef<PipelineStage | null | undefined>(undefined);

  useEffect(() => {
    if (pipelineStage && pipelineStage !== previousPipelineStageRef.current && enableTypewriter) {
      previousPipelineStageRef.current = pipelineStage;
      setIsTypingPipeline(true);
      setDisplayedPipelineMessage('');

      const message = pipelineStage.message;
      let index = 0;
      const intervalMs = 1000 / typewriterSpeed;

      const intervalId = setInterval(() => {
        if (index < message.length) {
          setDisplayedPipelineMessage(message.slice(0, index + 1));
          index++;
        } else {
          clearInterval(intervalId);
          setIsTypingPipeline(false);
        }
      }, intervalMs);

      return () => {
        clearInterval(intervalId);
        setIsTypingPipeline(false);
      };
    } else if (pipelineStage && !enableTypewriter) {
      setDisplayedPipelineMessage(pipelineStage.message);
      previousPipelineStageRef.current = pipelineStage;
    } else if (!pipelineStage) {
      setDisplayedPipelineMessage('');
      previousPipelineStageRef.current = null;
    }
  }, [pipelineStage, enableTypewriter, typewriterSpeed]);

  useEffect(() => {
    if (summary && summary !== previousSummaryRef.current && enableTypewriter) {
      previousSummaryRef.current = summary;
      setIsTypingSummary(true);
      setDisplayedSummary('');

      let index = 0;
      const intervalMs = 1000 / typewriterSpeed;

      const intervalId = setInterval(() => {
        if (index < summary.length) {
          setDisplayedSummary(summary.slice(0, index + 1));
          index++;
        } else {
          clearInterval(intervalId);
          setIsTypingSummary(false);
        }
      }, intervalMs);

      return () => {
        clearInterval(intervalId);
        setIsTypingSummary(false);
      };
    } else if (summary && !enableTypewriter) {
      setDisplayedSummary(summary);
      previousSummaryRef.current = summary;
    } else if (!summary) {
      setDisplayedSummary('');
      previousSummaryRef.current = undefined;
    }
  }, [summary, enableTypewriter, typewriterSpeed]);

  if (!summary && !pipelineStage && !isLoading) {
    return null;
  }

  return (
    <div className="thinking-context mb-3">
      <div className="flex items-center justify-between mb-2">
        <h4 className="text-xs font-semibold text-gray-600 dark:text-gray-400 flex items-center gap-1">
          <span>🧠</span>
          <span>思考脈絡</span>
          {(isTypingPipeline || isTypingSummary) && (
            <span className="ml-1 w-1.5 h-3 bg-purple-500 animate-pulse" />
          )}
        </h4>
      </div>

      <div
        className="rounded-lg p-3"
        style={{
          background: 'rgba(139, 92, 246, 0.03)',
          borderLeft: '2px solid rgba(139, 92, 246, 0.3)',
        }}
      >
        {isLoading ? (
          <div className="text-xs text-gray-500 dark:text-gray-400 italic">
            <span className="inline-flex items-center gap-1">
              <span className="w-1 h-1 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1 h-1 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1 h-1 bg-purple-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </span>
            <span className="ml-2">AI 正在思考中...</span>
          </div>
        ) : (
          <>
            {displayedPipelineMessage && (
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                {displayedPipelineMessage}
                {isTypingPipeline && (
                  <span className="inline-block w-0.5 h-3 bg-gray-400 dark:bg-gray-500 ml-0.5 animate-pulse" />
                )}
              </div>
            )}

            {(displayedSummary || summary) && (
              <div className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                {displayedSummary || summary}
                {isTypingSummary && (
                  <span className="inline-block w-0.5 h-4 bg-purple-500 ml-0.5 animate-pulse" />
                )}
              </div>
            )}

            {onViewFullPlan && (
              <div className="mt-2">
                <button
                  onClick={onViewFullPlan}
                  className="text-[10px] text-purple-600 dark:text-purple-400 hover:underline"
                >
                  查看完整計畫
                </button>
              </div>
            )}
          </>
        )}
      </div>

      <style jsx>{`
        @keyframes fadeIn {
          from {
            opacity: 0;
            transform: translateY(-5px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  );
}
