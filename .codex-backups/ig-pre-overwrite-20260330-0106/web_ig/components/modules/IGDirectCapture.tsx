'use client';

/**
 * IG Direct Capture
 *
 * Opens Instagram in a popup/tab and guides user to capture data
 * directly from their already-logged-in browser session.
 */

import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { MindscapeAPIClient } from '@/api/client';
import { ExternalLink, Copy, CheckCircle2, Play, AlertCircle, Download } from 'lucide-react';

interface IGDirectCaptureProps {
  workspaceId: string;
  apiUrl: string;
  onCaptureComplete?: (data: CapturedData) => void;
}

interface CapturedData {
  username: string;
  following: FollowingAccount[];
  capturedAt: string;
}

interface FollowingAccount {
  username: string;
  fullName?: string;
  profilePicUrl?: string;
  isVerified?: boolean;
}

// Script to run in browser console to extract following list
const CAPTURE_SCRIPT = `
// IG Following List Capture Script
// Run this on instagram.com/{username}/following page

(async function captureFollowing() {
  const accounts = [];
  const dialog = document.querySelector('div[role="dialog"]');

  if (!dialog) {
    console.error('Please open the Following dialog first (click on "following" count)');
    return null;
  }

  const scrollContainer = dialog.querySelector('div[style*="overflow"]') ||
                          dialog.querySelector('._aano');

  if (!scrollContainer) {
    console.error('Could not find scroll container');
    return null;
  }

  // Scroll and collect
  let lastHeight = 0;
  let attempts = 0;

  while (attempts < 50) {
    const items = dialog.querySelectorAll('a[href^="/"][role="link"]');

    items.forEach(item => {
      const href = item.getAttribute('href');
      if (href && href !== '/' && !href.includes('/explore/')) {
        const username = href.replace(/\\//g, '');
        if (!accounts.find(a => a.username === username)) {
          const container = item.closest('div[role="button"]') || item.parentElement?.parentElement;
          const img = container?.querySelector('img');
          const nameSpan = container?.querySelectorAll('span');

          accounts.push({
            username,
            fullName: nameSpan?.[1]?.textContent || undefined,
            profilePicUrl: img?.src || undefined,
            isVerified: !!container?.querySelector('[aria-label="Verified"]')
          });
        }
      }
    });

    scrollContainer.scrollTop = scrollContainer.scrollHeight;
    await new Promise(r => setTimeout(r, 1000));

    if (scrollContainer.scrollHeight === lastHeight) {
      attempts++;
    } else {
      attempts = 0;
      lastHeight = scrollContainer.scrollHeight;
    }

    console.log(\`Captured \${accounts.length} accounts...\`);
  }

  console.log('Capture complete!', accounts);

  // Copy to clipboard
  const result = JSON.stringify({
    username: window.location.pathname.split('/')[1],
    following: accounts,
    capturedAt: new Date().toISOString()
  }, null, 2);

  await navigator.clipboard.writeText(result);
  console.log('Data copied to clipboard! Paste it back in the app.');

  return result;
})();
`.trim();

export default function IGDirectCapture({
  workspaceId,
  apiUrl,
  onCaptureComplete
}: IGDirectCaptureProps) {
  const client = useMemo(() => MindscapeAPIClient.fromBaseUrl(apiUrl), [apiUrl]);
  const [step, setStep] = useState<'intro' | 'waiting' | 'paste' | 'complete'>('intro');
  const [copiedScript, setCopiedScript] = useState(false);
  const [pastedData, setPastedData] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [capturedData, setCapturedData] = useState<CapturedData | null>(null);
  const [saving, setSaving] = useState(false);

  const copyScript = async () => {
    await navigator.clipboard.writeText(CAPTURE_SCRIPT);
    setCopiedScript(true);
    setTimeout(() => setCopiedScript(false), 2000);
  };

  const openInstagram = (username?: string) => {
    const url = username
      ? `https://www.instagram.com/${username}/following/`
      : 'https://www.instagram.com/';
    window.open(url, '_blank');
    setStep('waiting');
  };

  const handlePaste = () => {
    setStep('paste');
  };

  const processData = async () => {
    setError(null);
    try {
      const data = JSON.parse(pastedData) as CapturedData;

      if (!data.following || !Array.isArray(data.following)) {
        throw new Error('Invalid data format');
      }

      setCapturedData(data);
      setStep('complete');

      // Save to backend
      setSaving(true);
      try {
        const response = await client.post(
          `/api/v1/workspaces/${workspaceId}/artifacts`,
          {
            artifact_type: 'ig_following_analysis',
            title: `Following list of @${data.username}`,
            platform: 'instagram',
            content: {
              discovered_accounts: data.following.map(acc => ({
                handle: acc.username,
                name: acc.fullName,
                profile_picture_url: acc.profilePicUrl,
                is_verified: acc.isVerified,
                source: 'browser_capture'
              }))
            },
            metadata: {
              source: 'ig_direct_capture',
              target_username: data.username,
              account_count: data.following.length,
              captured_at: data.capturedAt
            }
          }
        );

        if (response.ok) {
          onCaptureComplete?.(data);
        }
      } catch (saveErr) {
        console.error('Failed to save to backend:', saveErr);
      } finally {
        setSaving(false);
      }

    } catch (err) {
      setError('Invalid JSON data. Please make sure you copied the complete output.');
    }
  };

  return (
    <div className="space-y-4">
      {step === 'intro' && (
        <>
          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
            <h3 className="font-semibold text-blue-900 dark:text-blue-100 mb-2">
              Direct Browser Capture
            </h3>
            <p className="text-sm text-blue-700 dark:text-blue-300">
              This method uses your existing Instagram login. No need for separate authentication.
            </p>
          </div>

          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-4">
            <div>
              <h4 className="font-medium text-gray-900 dark:text-gray-100 mb-2">Copy the capture script</h4>
              <div className="relative">
                <pre className="bg-gray-100 dark:bg-gray-900 rounded p-3 text-xs font-mono overflow-x-auto max-h-32">
                  <code>{CAPTURE_SCRIPT.slice(0, 200)}...</code>
                </pre>
                <button
                  onClick={copyScript}
                  className="absolute top-2 right-2 px-2 py-1 bg-blue-600 text-white text-xs rounded hover:bg-blue-700 flex items-center gap-1"
                >
                  {copiedScript ? (
                    <>
                      <CheckCircle2 className="w-3 h-3" />
                      Copied!
                    </>
                  ) : (
                    <>
                      <Copy className="w-3 h-3" />
                      Copy Script
                    </>
                  )}
                </button>
              </div>
            </div>

            <div>
              <h4 className="font-medium text-gray-900 dark:text-gray-100 mb-2">Open Instagram</h4>
              <div className="flex gap-2">
                <button
                  onClick={() => openInstagram()}
                  className="px-3 py-2 bg-gradient-to-r from-purple-500 to-pink-500 text-white text-sm rounded hover:from-purple-600 hover:to-pink-600 flex items-center gap-2"
                >
                  <ExternalLink className="w-4 h-4" />
                  Open Instagram
                </button>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                Go to any profile → Click &quot;following&quot; count to open the following list
              </p>
            </div>

            <div>
              <h4 className="font-medium text-gray-900 dark:text-gray-100 mb-2">Run the script</h4>
              <ol className="text-sm text-gray-700 dark:text-gray-300 list-decimal list-inside space-y-1">
                <li>Open DevTools (F12 or Cmd+Option+I)</li>
                <li>Go to Console tab</li>
                <li>Paste the script and press Enter</li>
                <li>Wait for &quot;Data copied to clipboard!&quot; message</li>
              </ol>
            </div>
          </div>
        </>
      )}

      {step === 'waiting' && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6 text-center space-y-4">
          <div className="animate-pulse">
            <Play className="w-12 h-12 mx-auto text-blue-500" />
          </div>
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">
            Waiting for capture...
          </h3>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Run the script in your Instagram browser tab, then come back here.
          </p>
          <button
            onClick={handlePaste}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
          >
            I&apos;ve captured the data
          </button>
          <button
            onClick={() => setStep('intro')}
            className="block mx-auto text-sm text-gray-500 hover:text-gray-700"
          >
            Start over
          </button>
        </div>
      )}

      {step === 'paste' && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-4">
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">
            Paste captured data
          </h3>
          <textarea
            value={pastedData}
            onChange={(e) => setPastedData(e.target.value)}
            placeholder="Paste the JSON data here..."
            rows={8}
            className="w-full px-3 py-2 text-sm border rounded-lg dark:bg-gray-700 dark:border-gray-600 font-mono"
          />
          {error && (
            <div className="flex items-center gap-2 text-red-600 dark:text-red-400 text-sm">
              <AlertCircle className="w-4 h-4" />
              {error}
            </div>
          )}
          <div className="flex gap-2">
            <button
              onClick={processData}
              disabled={!pastedData.trim()}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            >
              Process Data
            </button>
            <button
              onClick={() => setStep('waiting')}
              className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600"
            >
              Back
            </button>
          </div>
        </div>
      )}

      {step === 'complete' && capturedData && (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4 space-y-4">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />
            <h3 className="font-semibold text-green-900 dark:text-green-100">
              Capture Complete!
            </h3>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-gray-600 dark:text-gray-400">Target:</span>
              <span className="ml-2 font-medium text-gray-900 dark:text-gray-100">
                @{capturedData.username}
              </span>
            </div>
            <div>
              <span className="text-gray-600 dark:text-gray-400">Accounts:</span>
              <span className="ml-2 font-medium text-gray-900 dark:text-gray-100">
                {capturedData.following.length}
              </span>
            </div>
          </div>
          {saving ? (
            <p className="text-sm text-gray-600 dark:text-gray-400">Saving to workspace...</p>
          ) : (
            <p className="text-sm text-green-700 dark:text-green-300">
              Data saved to workspace artifacts. Check the Discovered tab to see the accounts.
            </p>
          )}
          <button
            onClick={() => {
              setStep('intro');
              setPastedData('');
              setCapturedData(null);
            }}
            className="text-sm text-green-700 dark:text-green-300 hover:underline"
          >
            Capture another profile
          </button>
        </div>
      )}
    </div>
  );
}
