'use client';

import './page.css';
import React, { useCallback, useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { getApiBaseUrl } from '../lib/api-url';

const API_URL = getApiBaseUrl();
const PROFILE_ID = 'default-user';

type BootState = 'loading' | 'first-time' | 'redirect';

export default function Home() {
  const router = useRouter();
  const apiUrl = API_URL.startsWith('http') ? API_URL : '';
  const [bootState, setBootState] = useState<BootState>('loading');
  const [fadeIn, setFadeIn] = useState(false);

  const checkOnboardingStatus = useCallback(async () => {
    try {
      const res = await fetch(`${apiUrl}/api/v1/mindscape/onboarding/status?user_id=${PROFILE_ID}`);
      if (res.ok) {
        const data = await res.json();
        const state = data.onboarding_state;
        const hasState = state?.has_state === true;
        const isOnboarding = state?.is_onboarding === true && !hasState;

        if (hasState && !isOnboarding) {
          // Returning user: redirect to first workspace
          setBootState('redirect');
          try {
            const wsRes = await fetch(`${apiUrl}/api/v1/workspaces?owner_user_id=${PROFILE_ID}&limit=1`);
            if (wsRes.ok) {
              const workspaces = await wsRes.json();
              if (workspaces.length > 0) {
                router.replace(`/workspaces/${workspaces[0].id}`);
                return;
              }
            }
          } catch { /* fall through */ }
          router.replace('/workspaces');
        } else {
          // First-time user: show welcome
          setBootState('first-time');
        }
      } else {
        // API error: show welcome as fallback
        setBootState('first-time');
      }
    } catch {
      setBootState('first-time');
    }
  }, [apiUrl, router]);

  useEffect(() => {
    checkOnboardingStatus();
  }, [checkOnboardingStatus]);

  useEffect(() => {
    if (bootState !== 'loading') {
      // trigger entrance animation
      requestAnimationFrame(() => setFadeIn(true));
    }
  }, [bootState]);

  // --- Loading state ---
  if (bootState === 'loading' || bootState === 'redirect') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-purple-950 to-slate-900">
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-white/10 text-2xl font-semibold text-white animate-pulse">
            MS
          </div>
          <p className="text-purple-300/80 text-sm animate-pulse">
            {bootState === 'redirect' ? 'Entering workspace...' : 'Loading...'}
          </p>
        </div>
      </div>
    );
  }

  // --- First-time welcome screen ---
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-950 to-slate-900 overflow-hidden">
      {/* Ambient background glow */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
      </div>

      <div
        className={`relative z-10 flex flex-col items-center justify-center min-h-screen px-4 transition-all duration-1000 ${fadeIn ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
          }`}
      >
        {/* Logo */}
        <div className="mb-8">
          <div className="flex h-24 w-24 items-center justify-center rounded-3xl bg-white/10 text-3xl font-semibold text-white drop-shadow-2xl" style={{ filter: 'drop-shadow(0 0 30px rgba(168,85,247,0.4))' }}>
            MS
          </div>
        </div>

        {/* Title */}
        <h1 className="text-5xl font-bold text-white mb-3 tracking-tight text-center">
          Mindscape AI
        </h1>
        <p className="text-lg text-purple-300/80 mb-12 text-center max-w-md">
          Your Personal AI Team Console
        </p>

        {/* Feature cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 max-w-3xl w-full mb-12">
          <FeatureCard
            icon="ID"
            title="Self Introduction"
            description="Tell AI who you are and what you're working on"
            step={1}
            delay={200}
            fadeIn={fadeIn}
          />
          <FeatureCard
            icon="GOAL"
            title="First Project"
            description="Set your first long-term goal for AI to track"
            step={2}
            delay={400}
            fadeIn={fadeIn}
          />
          <FeatureCard
            icon="FLOW"
            title="Work Rhythm"
            description="Configure your preferred workflow and tools"
            step={3}
            delay={600}
            fadeIn={fadeIn}
          />
        </div>

        {/* CTA */}
        <button
          onClick={() => router.push('/mindscape')}
          className="group relative px-8 py-3.5 rounded-xl text-white font-semibold text-lg overflow-hidden transition-all duration-300 hover:scale-105 hover:shadow-lg hover:shadow-purple-500/25 active:scale-95"
        >
          <div className="absolute inset-0 bg-gradient-to-r from-purple-600 to-cyan-500 rounded-xl" />
          <div className="absolute inset-0 bg-gradient-to-r from-purple-500 to-cyan-400 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity" />
          <span className="relative flex items-center gap-2">
            Get Started
            <svg className="w-5 h-5 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </span>
        </button>

        {/* Skip link */}
        <button
          onClick={async () => {
            try {
              const wsRes = await fetch(`${apiUrl}/api/v1/workspaces?owner_user_id=${PROFILE_ID}&limit=1`);
              if (wsRes.ok) {
                const workspaces = await wsRes.json();
                if (workspaces.length > 0) {
                  router.push(`/workspaces/${workspaces[0].id}`);
                  return;
                }
              }
            } catch { /* ignore */ }
            router.push('/workspaces');
          }}
          className="mt-4 text-sm text-purple-400/60 hover:text-purple-300 transition-colors"
        >
          Skip to workspace
        </button>

        {/* Version */}
        <div className="absolute bottom-6 text-xs text-purple-400/30">
          v1.0.0
        </div>
      </div>
    </div>
  );
}

/* --- Sub-components --- */

function FeatureCard({
  icon,
  title,
  description,
  step,
  delay,
  fadeIn,
}: {
  icon: string;
  title: string;
  description: string;
  step: number;
  delay: number;
  fadeIn: boolean;
}) {
  return (
    <div
      className={`relative bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-6 transition-all duration-700 hover:bg-white/10 hover:border-purple-400/30 hover:shadow-lg hover:shadow-purple-500/10 ${fadeIn ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'
        }`}
      style={{ transitionDelay: `${delay}ms` }}
    >
      <div className="absolute top-3 right-3 text-xs text-purple-400/40 font-mono">
        STEP {step}
      </div>
      <div className="mb-3 inline-flex min-h-8 min-w-8 items-center justify-center rounded bg-white/10 px-2 py-1 text-sm font-semibold text-purple-100">{icon}</div>
      <h3 className="text-white font-semibold mb-1.5">{title}</h3>
      <p className="text-sm text-purple-200/60 leading-relaxed">{description}</p>
    </div>
  );
}
