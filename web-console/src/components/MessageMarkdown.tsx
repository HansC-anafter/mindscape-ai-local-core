'use client';

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MessageMarkdownProps {
  content: string;
  linkClassName?: string;
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
};

export default function MessageMarkdown({ content, linkClassName }: MessageMarkdownProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        ...markdownComponents,
        a: ({ href, children }: any) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className={linkClassName || 'text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 underline break-all'}
            onClick={(e) => e.stopPropagation()}
          >
            {children}
          </a>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
