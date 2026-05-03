'use client';

import { FogRevealCard } from '@/components/onboarding/FogRevealCard';
import Image from 'next/image';
import { useRouter } from 'next/navigation';

export default function IntroPage() {
  const router = useRouter();

  const handleStart = () => {
    router.push('/mindscape');
  };

  return (
    <div className="w-full h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900">
      <FogRevealCard enableCardClear={true}>
        <div className="flex items-center justify-center">
          <div
            data-fog-card
            className="bg-white/70 backdrop-blur-xl rounded-3xl p-12 shadow-2xl max-w-2xl transition-all duration-300 hover:shadow-3xl border border-white/20"
          >
            <div className="text-center mb-8">
              <div className="mb-4 flex justify-center">
                <Image
                  src="/mindscapeai_logo_300x300.png"
                  alt="Mindscape Research Foundation"
                  width={80}
                  height={80}
                  className="w-20 h-20 rounded-2xl"
                  priority
                />
              </div>
              <h1 className="text-4xl font-bold text-gray-800 mb-2">
                Welcome to Mindscape AI
              </h1>
              <p className="text-lg text-gray-500">
                Your Personal AI Workspace
              </p>
            </div>

            <div className="text-center mb-10 space-y-3">
              <p className="text-lg text-gray-700 leading-snug">
                Build an <span className="font-semibold text-gray-600">AI mindscape</span> for your work.
              </p>
              <p className="text-lg text-gray-700 leading-snug">
                Coordinate <span className="font-semibold text-gray-600">AI members</span> across projects, tools, and decisions.
              </p>
            </div>

            <div className="flex flex-col items-center mb-8">
              <button
                onClick={handleStart}
                className="group relative bg-gradient-to-r from-gray-500 to-pink-500 text-white px-12 py-5 rounded-xl font-bold text-xl hover:shadow-2xl transition-all duration-300 hover:scale-105 active:scale-95"
              >
                <span className="relative z-10">Open workspace</span>
                <div className="absolute inset-0 bg-gradient-to-r from-gray-600 to-pink-600 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
              </button>
              <p className="text-xs mt-3 laser-text-rose tracking-wide">
                Recommended for personal devices. Data stays on this machine.
              </p>
            </div>

            <div className="grid grid-cols-3 gap-6 text-center mb-8 pt-8 border-t border-gray-200">
              <div>
                <div className="mb-2 text-sm font-semibold text-gray-500">MS</div>
                <p className="text-sm text-gray-600 font-medium">AI Mindscape</p>
              </div>
              <div>
                <div className="mb-2 text-sm font-semibold text-gray-500">AI</div>
                <p className="text-sm text-gray-600 font-medium">AI Teamwork</p>
              </div>
              <div>
                <div className="mb-2 text-sm font-semibold text-gray-500">WF</div>
                <p className="text-sm text-gray-600 font-medium">3000+ AI Workflows</p>
              </div>
            </div>

            <div className="text-center pt-4 border-t border-gray-100">
              <a
                href="/settings"
                className="text-xs text-gray-400 hover:text-gray-600 transition-colors inline-flex items-center gap-1"
              >
                I already have configuration and want to manage settings
                <span className="text-gray-300">&gt;</span>
                <span className="underline">Advanced mode</span>
              </a>
            </div>
          </div>
        </div>
      </FogRevealCard>

      <div className="absolute bottom-8 left-8 z-30">
        <div className="text-white/30 text-xs">
          Mindscape AI v0.1.0-alpha
        </div>
      </div>

      <div className="absolute bottom-8 right-8 text-white/40 text-sm max-w-xs text-right z-30">
        <p className="italic">Copyright 2025 Mindscape AI / mindscapeai.app</p>
      </div>
    </div>
  );
}
