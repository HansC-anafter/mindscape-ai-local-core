'use client';

import { FogRevealCard } from '@/components/onboarding/FogRevealCard';
import { useRouter } from 'next/navigation';

export default function IntroPage() {
  const router = useRouter();

  const handleStart = () => {
    // Navigate to start flow with Momo
    router.push('/mindscape');
  };

  return (
    <div className="w-full h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-violet-900">
      <FogRevealCard enableCardClear={true}>
        <div className="flex items-center justify-center">
          {/* 主入口卡片 */}
          <div
            data-fog-card
            className="bg-white/70 backdrop-blur-xl rounded-3xl p-12 shadow-2xl max-w-2xl transition-all duration-300 hover:shadow-3xl border border-white/20"
          >
            {/* Logo / 品牌 */}
            <div className="text-center mb-8">
              <div className="mb-4 flex justify-center">
                <img
                  src="/mindscapeai_logo_300x300.png"
                  alt="Mindscape Research Foundation"
                  className="w-20 h-20 rounded-2xl"
                />
              </div>
              <h1 className="text-4xl font-bold text-gray-800 mb-2">
                歡迎來到 Mindscape AI
              </h1>
              <p className="text-lg text-gray-500">
                Your Personal AI Workspace
              </p>
            </div>

            {/* 主要說明 */}
            <div className="text-center mb-10 space-y-3">
              <p className="text-lg text-gray-700 leading-snug">
                我會幫你建立一個 <span className="font-semibold text-purple-600">AI 的心智空間</span>，
              </p>
              <p className="text-lg text-gray-700 leading-snug">
                協調 <span className="font-semibold text-purple-600">AI 成員</span>一起幫你工作。
              </p>
            </div>

            {/* 主按鈕 */}
            <div className="flex flex-col items-center mb-8">
              <button
                onClick={handleStart}
                className="group relative bg-gradient-to-r from-purple-500 to-pink-500 text-white px-12 py-5 rounded-xl font-bold text-xl hover:shadow-2xl transition-all duration-300 hover:scale-105 active:scale-95"
              >
                <span className="relative z-10">開啟空間</span>
                <div className="absolute inset-0 bg-gradient-to-r from-purple-600 to-pink-600 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
              </button>
              <p className="text-xs mt-3 laser-text-rose tracking-wide">
                建議僅在個人電腦使用，資料會保存在本機。
              </p>
            </div>

            {/* 特色說明 */}
            <div className="grid grid-cols-3 gap-6 text-center mb-8 pt-8 border-t border-gray-200">
              <div>
                <div className="text-3xl mb-2">🧠</div>
                <p className="text-sm text-gray-600 font-medium">AI 心智空間</p>
              </div>
              <div>
                <div className="text-3xl mb-2">🤖</div>
                <p className="text-sm text-gray-600 font-medium">AI 團隊協作</p>
              </div>
              <div>
                <div className="text-3xl mb-2">📚</div>
                <p className="text-sm text-gray-600 font-medium">3000+ AI 工作流</p>
              </div>
            </div>

            {/* 開發者入口（低調小字） */}
            <div className="text-center pt-4 border-t border-gray-100">
              <a
                href="/settings"
                className="text-xs text-gray-400 hover:text-gray-600 transition-colors inline-flex items-center gap-1"
              >
                🛠 我已經有現成設定，想直接管理 config
                <span className="text-gray-300">→</span>
                <span className="underline">進入進階模式</span>
              </a>
            </div>
          </div>
        </div>
      </FogRevealCard>

      {/* 版本資訊 */}
      <div className="absolute bottom-8 left-8 z-30">
        <div className="text-white/30 text-xs">
          Mindscape AI v0.1.0-alpha
        </div>
      </div>

      {/* 說明提示 */}
      <div className="absolute bottom-8 right-8 text-white/40 text-sm max-w-xs text-right z-30">
        <p className="italic">Copyright © 2025 默默 AI / mindscapeai.app</p>
      </div>
    </div>
  );
}
