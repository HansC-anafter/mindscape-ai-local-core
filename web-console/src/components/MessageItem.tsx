'use client';

import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChatMessage } from '@/hooks/useChatEvents';
import { t } from '@/lib/i18n';

interface MessageItemProps {
  message: ChatMessage;
  onCopy?: (content: string) => void;
}

const markdownComponents = {
  p: ({ children }: any) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }: any) => <ul className="list-disc list-inside mb-2 space-y-1">{children}</ul>,
  ol: ({ children }: any) => <ol className="list-decimal list-inside mb-2 space-y-1">{children}</ol>,
  li: ({ children }: any) => <li className="ml-2">{children}</li>,
  strong: ({ children }: any) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }: any) => <em className="italic">{children}</em>,
  code: ({ children, className }: any) => {
    const isInline = !className;
    return isInline ? (
      <code className="bg-gray-200 dark:bg-gray-700 px-1 py-0.5 rounded text-xs font-mono">{children}</code>
    ) : (
      <code className="block bg-gray-100 dark:bg-gray-800 p-2 rounded text-xs font-mono overflow-x-auto">{children}</code>
    );
  },
  pre: ({ children }: any) => <pre className="bg-gray-100 dark:bg-gray-800 p-2 rounded text-xs font-mono overflow-x-auto mb-2">{children}</pre>,
  h1: ({ children }: any) => <h1 className="text-base font-bold mb-2">{children}</h1>,
  h2: ({ children }: any) => <h2 className="text-sm font-bold mb-2">{children}</h2>,
  h3: ({ children }: any) => <h3 className="text-xs font-bold mb-1">{children}</h3>,
  blockquote: ({ children }: any) => <blockquote className="border-l-4 border-gray-300 dark:border-gray-600 pl-2 italic mb-2">{children}</blockquote>,
  a: ({ href, children }: any) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 underline break-all"
      onClick={(e) => e.stopPropagation()}
    >
      {children}
    </a>
  ),
};

function MessageItemComponent({ message, onCopy }: MessageItemProps) {
  const [isVisible, setIsVisible] = useState(false);
  const [showCopyButton, setShowCopyButton] = useState(false);
  const [copied, setCopied] = useState(false);
  const messageRef = useRef<HTMLDivElement>(null);
  const messageContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!messageRef.current) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setIsVisible(true);
            observer.disconnect();
          }
        });
      },
      {
        rootMargin: '100px',
        threshold: 0.01
      }
    );

    observer.observe(messageRef.current);

    return () => {
      observer.disconnect();
    };
  }, []);

  const timestamp = message.timestamp instanceof Date
    ? message.timestamp
    : new Date(message.timestamp);

  const formattedTime = timestamp.toLocaleTimeString('zh-TW', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: true
  });

  const formattedDate = timestamp.toLocaleDateString('zh-TW', {
    day: 'numeric'
  });

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      if (onCopy) {
        onCopy(message.content);
      }
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy message:', err);
    }
  };

  return (
    <div
      ref={messageRef}
      className="space-y-2 pb-0 last:pb-0 group"
      onMouseEnter={() => setShowCopyButton(true)}
      onMouseLeave={() => setShowCopyButton(false)}
    >
      <div
        className={`flex ${
          message.role === 'user' ? 'justify-end' : 'justify-start'
        }`}
      >
        <div
          ref={messageContainerRef}
          className={`relative max-w-[80%] min-w-[200px] rounded-lg px-6 py-3 ${
            message.event_type === 'error'
              ? 'bg-red-50 dark:bg-red-900/20 border-2 border-red-200 dark:border-red-700 text-red-900 dark:text-red-200'
              : message.role === 'user'
              ? 'bg-blue-600 dark:bg-blue-700 text-white'
              : message.is_welcome
              ? 'bg-blue-50 dark:bg-blue-950/50 border-2 border-blue-200 dark:border-blue-800 text-gray-900 dark:text-gray-100'
              : 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100'
          }`}
          style={{
            wordBreak: 'break-word',
            overflowWrap: 'break-word',
            overflow: 'hidden',
            width: 'fit-content',
            maxWidth: '80%'
          }}
        >
          <div className="prose prose-sm max-w-none break-words text-sm" style={{
            wordBreak: 'break-word',
            overflowWrap: 'break-word',
            minWidth: 0,
            width: '100%'
          }}>
            {isVisible || message.role === 'user' ? (
              message.agentMode ? (
                // Agent Mode: Two-part response display
                <div className="space-y-4">
                  {/* Part 1: Understanding & Response */}
                  <div className="bg-blue-50 dark:bg-blue-900/20 p-4 rounded-lg border-l-4 border-blue-500">
                    <div className="text-xs font-semibold text-blue-700 dark:text-blue-300 mb-2">
                      理解與回應
                    </div>
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={markdownComponents}
                    >
                      {message.agentMode.part1}
                    </ReactMarkdown>
                  </div>

                  {/* Part 2: Executable Next Steps */}
                  {message.agentMode.part2 && (
                    <div className="bg-gray-50 dark:bg-gray-800/50 p-4 rounded-lg border-l-4 border-green-500">
                      <div className="text-xs font-semibold text-green-700 dark:text-green-300 mb-2">
                        可執行任務
                      </div>
                      {message.agentMode.executable_tasks && message.agentMode.executable_tasks.length > 0 ? (
                        <ul className="list-disc list-inside space-y-1 text-sm">
                          {message.agentMode.executable_tasks.map((task, idx) => (
                            <li key={idx} className="text-gray-700 dark:text-gray-300">{task}</li>
                          ))}
                        </ul>
                      ) : (
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={markdownComponents}
                        >
                          {message.agentMode.part2}
                        </ReactMarkdown>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                // Normal message display
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    ...markdownComponents,
                    a: ({ href, children }: any) => (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={
                        message.event_type === 'error'
                          ? 'text-red-700 hover:text-red-900 underline break-all font-medium'
                          : message.role === 'user'
                          ? 'text-blue-200 hover:text-white underline break-all'
                          : 'text-blue-600 hover:text-blue-800 underline break-all'
                      }
                      onClick={(e) => e.stopPropagation()}
                    >
                      {children}
                    </a>
                  ),
                }}
              >
                {message.is_welcome && (message.content.startsWith('welcome.') || message.content.includes('.'))
                  ? (t(message.content as any) || message.content)
                  : message.content}
              </ReactMarkdown>
              )
            ) : (
              <div className="text-gray-400 dark:text-gray-300 text-xs">Loading...</div>
            )}
          </div>

          {message.triggered_playbook && (
            <div className={`mt-2 text-xs ${
              message.role === 'user' ? 'text-blue-100' : 'text-blue-600'
            }`}>
              <div className="font-medium">Playbook: {message.triggered_playbook.playbook_code}</div>
              <div>Status: {message.triggered_playbook.status}</div>
              {message.triggered_playbook.execution_id && (
                <div className="text-xs opacity-75">Execution ID: {message.triggered_playbook.execution_id.slice(0, 8)}...</div>
              )}
            </div>
          )}

          {message.event_type && message.event_type !== 'message' && (
            <div className={`mt-1 text-xs ${
              message.role === 'user' ? 'text-blue-100' : 'text-gray-500 dark:text-gray-300'
            }`}>
              {message.event_type === 'playbook_step' && '📋 Playbook Step'}
              {message.event_type === 'tool_call' && '🔧 Tool Call'}
            </div>
          )}

          <div className={`flex items-center justify-between mt-1 gap-2 ${
            message.role === 'user' ? 'text-blue-100' : 'text-gray-500 dark:text-gray-300'
          }`} style={{ minWidth: 0, width: '100%' }}>
            <div className="flex items-center gap-1 flex-shrink-0 text-xs whitespace-nowrap">
              <span>{formattedDate}</span>
              <span>{formattedTime}</span>
            </div>
            {showCopyButton && (
              <button
                onClick={handleCopy}
                className={`flex-shrink-0 p-1 rounded-md transition-all ${
                  message.role === 'user'
                    ? 'bg-blue-700 hover:bg-blue-800 text-white'
                    : 'bg-gray-200 hover:bg-gray-300 text-gray-700'
                }`}
                style={{ flexShrink: 0 }}
                title={copied ? t('copied') : t('copyMessage')}
              >
                {copied ? (
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export const MessageItem = React.memo(MessageItemComponent, (prevProps, nextProps) => {
  const prev = prevProps.message;
  const next = nextProps.message;

  return (
    prev.id === next.id &&
    prev.content === next.content &&
    prev.role === next.role &&
    prev.event_type === next.event_type &&
    prev.is_welcome === next.is_welcome &&
    JSON.stringify(prev.triggered_playbook) === JSON.stringify(next.triggered_playbook) &&
    prev.timestamp.getTime() === next.timestamp.getTime() &&
    prevProps.onCopy === nextProps.onCopy
  );
});

MessageItem.displayName = 'MessageItem';
