'use client';

/**
 * DesignSnapshotPreview - Secure preview component for Design Snapshot HTML/CSS
 *
 * Implements multi-layer security:
 * 1. HTML sanitization (removes scripts, dangerous attributes)
 * 2. CSS sanitization (removes @import, external URLs, expressions)
 * 3. iframe sandbox isolation (prevents script execution, external resource loading)
 * 4. Content Security Policy (CSP) for additional protection
 *
 * Two modes:
 * - Safe mode (default): Only shows screenshot if available
 * - Full mode: Renders HTML/CSS in sandboxed iframe (user must enable)
 */

import React, { useState, useMemo } from 'react';

// ============================================================================
// Types
// ============================================================================

interface DesignSnapshotPreviewProps {
  htmlContent: string;
  cssContent?: string;
  screenshotUrl?: string; // Optional screenshot for safe mode
  snapshotId?: string;
  mode?: 'safe' | 'full'; // Preview mode
  onModeChange?: (mode: 'safe' | 'full') => void;
  className?: string;
}

// ============================================================================
// CSS Sanitization
// ============================================================================

function sanitizeCSS(cssContent: string): string {
  if (!cssContent) return '';

  let sanitized = cssContent;

  // Remove @import rules (may load external resources)
  sanitized = sanitized.replace(/@import\s+[^;]+;?/gi, '');

  // Remove external url() (but keep data: URLs)
  sanitized = sanitized.replace(/url\(["']?https?:\/\/[^)]+["']?\)/gi, '');

  // Remove javascript: URLs
  sanitized = sanitized.replace(/javascript:/gi, '');

  // Remove expression() (IE's JavaScript execution)
  sanitized = sanitized.replace(/expression\([^)]+\)/gi, '');

  // Remove behavior: (IE-specific)
  sanitized = sanitized.replace(/behavior\s*:\s*[^;]+;?/gi, '');

  return sanitized.trim();
}

// ============================================================================
// HTML Sanitization (Basic - In production, use DOMPurify library)
// ============================================================================

function sanitizeHTML(htmlContent: string): string {
  if (!htmlContent) return '';

  // Create a temporary DOM element to parse HTML
  const parser = new DOMParser();
  const doc = parser.parseFromString(htmlContent, 'text/html');

  // Remove dangerous elements
  const dangerousTags = ['script', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'meta'];
  dangerousTags.forEach((tag) => {
    const elements = doc.getElementsByTagName(tag);
    while (elements.length > 0) {
      elements[0].remove();
    }
  });

  // Remove dangerous attributes
  const allElements = doc.getElementsByTagName('*');
  Array.from(allElements).forEach((el) => {
    const element = el as HTMLElement;

    // Remove event handlers
    Array.from(element.attributes).forEach((attr) => {
      if (attr.name.startsWith('on') || attr.name.startsWith('data-')) {
        // Remove on* handlers and data-* attributes (may contain malicious payloads)
        element.removeAttribute(attr.name);
      }
    });

    // Remove javascript: URLs from href and src
    if (element.hasAttribute('href')) {
      const href = element.getAttribute('href');
      if (href && href.toLowerCase().startsWith('javascript:')) {
        element.removeAttribute('href');
      }
    }
    if (element.hasAttribute('src')) {
      const src = element.getAttribute('src');
      if (src && src.toLowerCase().startsWith('javascript:')) {
        element.removeAttribute('src');
      }
    }

    // Convert external image sources to placeholders
    if (element.tagName === 'IMG' && element.hasAttribute('src')) {
      const src = element.getAttribute('src');
      if (src && !src.startsWith('data:') && !src.startsWith('blob:')) {
        // Replace with placeholder
        element.setAttribute('src', 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjEwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZGRkIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJBcmlhbCwgc2Fucy1zZXJpZiIgZm9udC1zaXplPSIxNCIgZmlsbD0iIzk5OSIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZHk9Ii4zZW0iPkltYWdlIFBsYWNlaG9sZGVyPC90ZXh0Pjwvc3ZnPg==');
        element.setAttribute('alt', 'External image blocked for security');
      }
    }
  });

  return doc.body.innerHTML;
}

// ============================================================================
// CSP Policy
// ============================================================================

const CSP_POLICY = [
  "default-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "script-src 'none'",
  "form-action 'none'",
  "frame-ancestors 'none'",
  "connect-src 'none'",
  "object-src 'none'",
  "base-uri 'self'",
].join('; ');

// ============================================================================
// Component
// ============================================================================

export function DesignSnapshotPreview({
  htmlContent,
  cssContent = '',
  screenshotUrl,
  snapshotId,
  mode: initialMode = 'safe',
  onModeChange,
  className = '',
}: DesignSnapshotPreviewProps) {
  const [mode, setMode] = useState<'safe' | 'full'>(initialMode);
  const [showWarning, setShowWarning] = useState(false);

  // Sanitize content
  const sanitizedHTML = useMemo(() => sanitizeHTML(htmlContent), [htmlContent]);
  const sanitizedCSS = useMemo(() => sanitizeCSS(cssContent), [cssContent]);

  // Generate iframe content
  const iframeContent = useMemo(() => {
    return `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="${CSP_POLICY}">
  <style>
    body {
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    ${sanitizedCSS}
  </style>
</head>
<body>
  ${sanitizedHTML}
</body>
</html>
    `.trim();
  }, [sanitizedHTML, sanitizedCSS]);

  const handleModeToggle = () => {
    const newMode = mode === 'safe' ? 'full' : 'safe';
    setMode(newMode);
    if (mode === 'safe' && !showWarning) {
      setShowWarning(true);
    }
    onModeChange?.(newMode);
  };

  // Safe mode: Show screenshot or placeholder
  if (mode === 'safe') {
    return (
      <div className={`relative border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden bg-gray-50 dark:bg-gray-800 ${className}`}>
        {screenshotUrl ? (
          <img
            src={screenshotUrl}
            alt="Design Snapshot Preview"
            className="w-full h-auto max-h-[600px] object-contain"
          />
        ) : (
          <div className="flex items-center justify-center h-64 text-gray-400 dark:text-gray-500">
            <div className="text-center">
              <div className="text-4xl mb-2">🎨</div>
              <div className="text-sm">No screenshot available</div>
              <button
                onClick={handleModeToggle}
                className="mt-3 px-3 py-1.5 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
              >
                Enable Full Preview
              </button>
            </div>
          </div>
        )}
        {screenshotUrl && (
          <div className="absolute top-2 right-2">
            <button
              onClick={handleModeToggle}
              className="px-3 py-1.5 text-xs bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors shadow-sm"
              title="Enable full HTML/CSS preview (sandboxed)"
            >
              🔍 Full Preview
            </button>
          </div>
        )}
        {showWarning && (
          <div className="absolute bottom-2 left-2 right-2 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded p-2 text-xs text-yellow-800 dark:text-yellow-200">
            ⚠️ Full preview renders HTML/CSS in a sandboxed iframe. External resources and scripts are blocked.
          </div>
        )}
      </div>
    );
  }

  // Full mode: Show sandboxed iframe
  return (
    <div className={`relative border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden bg-white dark:bg-gray-900 ${className}`}>
      {/* Header with mode toggle */}
      <div className="flex items-center justify-between px-3 py-2 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
          <span className="w-2 h-2 bg-green-500 rounded-full" title="Sandboxed and secure" />
          <span>Sandboxed Preview</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              setMode('safe');
              onModeChange?.('safe');
            }}
            className="px-3 py-1 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
          >
            Back to Safe Mode
          </button>
        </div>
      </div>

      {/* Security warning */}
      <div className="px-3 py-2 bg-yellow-50 dark:bg-yellow-900/20 border-b border-yellow-200 dark:border-yellow-800 text-xs text-yellow-800 dark:text-yellow-200">
        <div className="flex items-start gap-2">
          <span>🔒</span>
          <div>
            <strong>Secure Preview Mode:</strong> This preview is rendered in a sandboxed iframe with strict security policies.
            Scripts, external resources, and forms are blocked. Only sanitized HTML/CSS is displayed.
          </div>
        </div>
      </div>

      {/* Sandboxed iframe */}
      <iframe
        srcDoc={iframeContent}
        sandbox="allow-same-origin"
        className="w-full h-[600px] border-0"
        title={`Design Snapshot Preview - ${snapshotId || 'unknown'}`}
        loading="lazy"
      />

      {/* Footer with info */}
      <div className="px-3 py-2 bg-gray-50 dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400">
        <div className="flex items-center justify-between">
          <span>
            Content is sanitized and isolated. External images replaced with placeholders.
          </span>
          <span className="text-[10px]">
            CSP: Active | Sandbox: Active
          </span>
        </div>
      </div>
    </div>
  );
}
