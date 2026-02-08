'use client';

import React, { useState, useEffect } from 'react';
import { t } from '../../../../lib/i18n';
import { settingsApi } from '../../utils/settingsApi';
import { WizardShell } from './WizardShell';

interface GoogleDriveConnectionWizardProps {
  onClose: () => void;
  onSuccess: () => void;
}

export function GoogleDriveConnectionWizard({
  onClose,
  onSuccess,
}: GoogleDriveConnectionWizardProps) {
  const [form, setForm] = useState({
    connection_id: 'google-drive-1',
    name: 'My Google Drive',
    api_key: '',
    api_secret: '',
  });
  const [discovering, setDiscovering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [oauthConnecting, setOauthConnecting] = useState(false);
  const [useOAuth, setUseOAuth] = useState(true);

  // Listen for OAuth popup messages
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      // Verify origin for security (adjust if needed)
      // if (event.origin !== window.location.origin) return;

      if (event.data.success) {
        setSuccess(
          `Successfully connected via OAuth! Discovered ${event.data.tools_count || 0} tool(s).`
        );
        setOauthConnecting(false);
        setTimeout(() => {
          onSuccess();
        }, 1500);
      } else if (event.data.error) {
        setError(`OAuth authorization failed: ${event.data.error}`);
        setOauthConnecting(false);
      }
    };

    window.addEventListener('message', handleMessage);
    return () => {
      window.removeEventListener('message', handleMessage);
    };
  }, [onSuccess]);

  const handleOAuthConnect = () => {
    if (!form.connection_id || !form.name) {
      setError('Please enter connection ID and name first');
      return;
    }

    setOauthConnecting(true);
    setError(null);
    setSuccess(null);

    // Build OAuth authorization URL
    const authorizeUrl = new URL('/api/v1/tools/google-drive/oauth/authorize', settingsApi.baseURL);
    authorizeUrl.searchParams.set('connection_id', form.connection_id);
    authorizeUrl.searchParams.set('connection_name', form.name);

    // Open OAuth popup window
    const popup = window.open(
      authorizeUrl.toString(),
      'google-oauth',
      'width=500,height=600,left=' + (window.screen.width / 2 - 250) + ',top=' + (window.screen.height / 2 - 300)
    );

    if (!popup) {
      setError('Popup blocked. Please allow popups for this site and try again.');
      setOauthConnecting(false);
      return;
    }

    // Check if popup is closed manually
    const checkClosed = setInterval(() => {
      if (popup.closed) {
        clearInterval(checkClosed);
        setOauthConnecting((prev) => {
          if (prev) {
            setError('Authorization cancelled or popup was closed.');
          }
          return false;
        });
      }
    }, 1000);
  };

  const handleDiscover = async () => {
    setDiscovering(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await settingsApi.post<{ tools_count?: number }>(
        '/api/v1/tools/google-drive/discover',
        {
          connection_id: form.connection_id,
          name: form.name,
          api_key: form.api_key,
          api_secret: form.api_secret || undefined,
        }
      );

      setSuccess(
        `${t('successDiscovered' as any)} ${result.tools_count || 0} ${t('toolsCount' as any)}!`
      );
      setTimeout(() => {
        onSuccess();
      }, 1500);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Discovery failed';
      setError(errorMessage);
    } finally {
      setDiscovering(false);
    }
  };

  const footer = (
    <>
      <button
        onClick={onClose}
        className="px-4 py-2 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 bg-white dark:bg-gray-800"
      >
        {t('cancel' as any)}
      </button>
      {useOAuth ? (
        <button
          onClick={handleOAuthConnect}
          disabled={oauthConnecting || !form.connection_id || !form.name}
          className="px-4 py-2 bg-blue-600 dark:bg-blue-700 text-white rounded-md hover:bg-blue-700 dark:hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          {oauthConnecting ? (
            <>
              <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Authorizing...
            </>
          ) : (
            'Authorize with Google'
          )}
        </button>
      ) : (
        <button
          onClick={handleDiscover}
          disabled={discovering || !form.connection_id || !form.name || !form.api_key}
          className="px-4 py-2 bg-gray-600 dark:bg-gray-700 text-white rounded-md hover:bg-gray-700 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {discovering ? t('discovering' as any) : t('discoverAndRegister' as any)}
        </button>
      )}
    </>
  );

  return (
    <WizardShell
      title="Connect Google Drive"
      onClose={onClose}
      error={error}
      success={success}
      onDismissError={() => setError(null)}
      onDismissSuccess={() => setSuccess(null)}
      footer={footer}
    >
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          {t('connectionName' as any)}
        </label>
        <input
          type="text"
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
          placeholder="e.g., My Google Drive"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          {t('siteIdentifier' as any)}
        </label>
        <input
          type="text"
          value={form.connection_id}
          onChange={(e) => setForm({ ...form, connection_id: e.target.value })}
          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
          placeholder="e.g., google-drive-1"
        />
      </div>

      <div className="mb-4">
        <div className="flex items-center gap-3">
          <label className="inline-flex items-center">
            <input
              type="radio"
              checked={useOAuth}
              onChange={() => setUseOAuth(true)}
              className="form-radio h-4 w-4 text-blue-600 dark:text-blue-500"
            />
            <span className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
              Use OAuth 2.0 (Recommended)
            </span>
          </label>
          <label className="inline-flex items-center">
            <input
              type="radio"
              checked={!useOAuth}
              onChange={() => setUseOAuth(false)}
              className="form-radio h-4 w-4 text-blue-600 dark:text-blue-500"
            />
            <span className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
              Manual Token Input
            </span>
          </label>
        </div>
      </div>

      {useOAuth ? (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-4">
          <div className="flex items-start">
            <div className="flex-shrink-0">
              <svg className="h-5 w-5 text-blue-400 dark:text-blue-500" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="ml-3 flex-1">
              <h3 className="text-sm font-medium text-blue-800 dark:text-blue-300">
                OAuth 2.0 Authorization
              </h3>
              <div className="mt-2 text-sm text-blue-700 dark:text-blue-300">
                <p>
                  Click "Authorize with Google" to securely connect your Google Drive account.
                  You'll be redirected to Google to grant read-only access to your Drive files.
                </p>
                <p className="mt-2">
                  <strong className="font-semibold">Scopes requested:</strong> Google Drive (read-only)
                </p>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              OAuth 2.0 Access Token <span className="text-red-500 dark:text-red-400">*</span>
            </label>
            <input
              type="password"
              value={form.api_key}
              onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
              placeholder="ya29..."
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Obtain Access Token through OAuth 2.0 flow
            </p>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Currently supports read-only operations (list files, read files)
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Refresh Token ({t('optional' as any)})
            </label>
            <input
              type="password"
              value={form.api_secret}
              onChange={(e) => setForm({ ...form, api_secret: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:focus:ring-blue-400 focus:border-transparent"
              placeholder="1//..."
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Used for automatic Access Token refresh ({t('optional' as any)})
            </p>
          </div>
        </>
      )}
    </WizardShell>
  );
}
