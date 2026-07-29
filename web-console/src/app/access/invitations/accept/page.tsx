'use client';

import { useLayoutEffect, useState } from 'react';

import { getApiBaseUrl } from '@/lib/api-url';

type AcceptanceState = 'ready' | 'missing' | 'submitting' | 'accepted' | 'failed';

export default function InvitationAcceptancePage() {
  const [token, setToken] = useState<string | null>(null);
  const [state, setState] = useState<AcceptanceState>('ready');
  const [message, setMessage] = useState(
    'Confirm this invitation after signing in with the invited email address.',
  );

  useLayoutEffect(() => {
    const parameters = new URLSearchParams(window.location.hash.slice(1));
    const rawToken = parameters.get('token');
    window.history.replaceState(
      null,
      '',
      `${window.location.pathname}${window.location.search}`,
    );
    if (!rawToken || rawToken.length < 32 || rawToken.length > 512) {
      setState('missing');
      setMessage('This invitation link is missing or malformed.');
      return;
    }
    setToken(rawToken);
  }, []);

  const accept = async () => {
    if (!token || state === 'submitting') return;
    setState('submitting');
    const response = await fetch(
      `${getApiBaseUrl()}/api/v1/access-control/invitations/accept`,
      {
        method: 'POST',
        headers: {
          accept: 'application/json',
          'content-type': 'application/json',
        },
        cache: 'no-store',
        body: JSON.stringify({ invitation_token: token }),
      },
    );
    setToken(null);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      setState('failed');
      setMessage(String(payload?.detail || 'Invitation acceptance failed.'));
      return;
    }
    setState('accepted');
    setMessage('Access granted. You can now open the invited workspace.');
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-lg items-center p-6">
      <section className="w-full space-y-4 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold">Accept workspace invitation</h1>
        <p role={state === 'failed' || state === 'missing' ? 'alert' : 'status'}>
          {message}
        </p>
        {state === 'ready' ? (
          <button
            type="button"
            className="rounded bg-blue-600 px-4 py-2 font-semibold text-white"
            onClick={() => void accept()}
          >
            Accept invitation
          </button>
        ) : null}
      </section>
    </main>
  );
}
