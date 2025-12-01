'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useT } from '@/lib/i18n';

interface HelpIconProps {
  helpKey: string;
  className?: string;
}

const TOOLTIP_WIDTH = 288; // w-72 = 18rem = 288px

export default function HelpIcon({ helpKey, className = '' }: HelpIconProps) {
  const t = useT();
  const [isExpanded, setIsExpanded] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const helpText = t(helpKey as any);

  const updatePosition = useCallback(() => {
    if (!buttonRef.current) return;

    const rect = buttonRef.current.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    let left = rect.left;
    let top = rect.bottom + 4;

    // Adjust if tooltip would overflow right edge
    if (left + TOOLTIP_WIDTH > viewportWidth) {
      left = viewportWidth - TOOLTIP_WIDTH - 8;
    }

    // Ensure tooltip doesn't go off left edge
    if (left < 8) {
      left = 8;
    }

    // If tooltip would overflow bottom, show above button instead
    const tooltipHeight = 120; // Estimated height
    if (top + tooltipHeight > viewportHeight && rect.top > tooltipHeight) {
      top = rect.top - tooltipHeight - 4;
    }

    setPosition({ top, left });
  }, []);

  useEffect(() => {
    if (isExpanded) {
      updatePosition();
    }
  }, [isExpanded, updatePosition]);

  useEffect(() => {
    if (!isExpanded) return;

    const handleScroll = () => {
      updatePosition();
    };

    const handleResize = () => {
      updatePosition();
    };

    window.addEventListener('scroll', handleScroll, true);
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('scroll', handleScroll, true);
      window.removeEventListener('resize', handleResize);
    };
  }, [isExpanded]);

  if (!helpText || helpText === helpKey) {
    return null;
  }

  const renderFormattedText = (text: string) => {
    const parts: React.ReactNode[] = [];
    const lines = text.split('\n');

    lines.forEach((line, lineIndex) => {
      if (lineIndex > 0) {
        parts.push(<br key={`br-${lineIndex}`} />);
      }

      if (!line.trim()) {
        parts.push(<br key={`empty-${lineIndex}`} />);
        return;
      }

      let lastIndex = 0;
      const boldRegex = /\*\*([^*]+)\*\*/g;
      let match;
      let keyIndex = 0;

      while ((match = boldRegex.exec(line)) !== null) {
        if (match.index > lastIndex) {
          parts.push(
            <span key={`text-${lineIndex}-${keyIndex++}`}>
              {line.slice(lastIndex, match.index)}
            </span>
          );
        }

        parts.push(
          <strong
            key={`bold-${lineIndex}-${keyIndex++}`}
            className="font-semibold text-gray-900"
          >
            {match[1]}
          </strong>
        );

        lastIndex = match.index + match[0].length;
      }

      if (lastIndex < line.length) {
        parts.push(
          <span key={`text-end-${lineIndex}`}>
            {line.slice(lastIndex)}
          </span>
        );
      }
    });

    return parts;
  };

  const tooltipContent = isExpanded && position && typeof window !== 'undefined' ? (
    <>
      <div
        className="fixed inset-0 z-[9998]"
        onClick={() => setIsExpanded(false)}
      />
      <div
        className="fixed z-[9999] w-72 p-4 bg-white border border-gray-300 rounded-lg shadow-lg text-xs text-gray-700 leading-relaxed"
        style={{
          top: `${position.top}px`,
          left: `${position.left}px`
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 space-y-1.5">
          {renderFormattedText(helpText)}
        </div>
        <button
          onClick={() => setIsExpanded(false)}
          className="text-xs text-gray-500 hover:text-gray-700 underline"
        >
          {t('close') || 'Close'}
        </button>
      </div>
    </>
  ) : null;

  return (
    <div className={`relative inline-flex items-center ${className}`}>
      <button
        ref={buttonRef}
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setIsExpanded(!isExpanded);
        }}
        className="ml-1.5 text-gray-400 hover:text-gray-600 focus:outline-none focus:text-gray-600 transition-colors"
        aria-label="Show help"
        aria-expanded={isExpanded}
      >
        <svg
          className="w-3.5 h-3.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      </button>

      {typeof window !== 'undefined' && tooltipContent && createPortal(
        tooltipContent,
        document.body
      )}
    </div>
  );
}
