'use client';

import { FogRevealCard } from '@/components/onboarding/FogRevealCard';

export default function FogDemoPage() {
  return (
    <div className="w-full h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-violet-900">
      <FogRevealCard enableCardClear={true}>
        <div className="flex flex-col gap-8 items-center">
          {/* 示例卡片 1 - 添加 data-fog-card 属性 */}
          <div 
            data-fog-card
            className="bg-white/90 backdrop-blur-sm rounded-2xl p-8 shadow-2xl max-w-md transition-all duration-300 hover:shadow-3xl hover:scale-105"
          >
            <h2 className="text-3xl font-bold text-gray-800 mb-4">
              ✨ 撥雲見卡
            </h2>
            <p className="text-gray-600 mb-6">
              移動鼠標到卡片上，看雲霧被吹散。
              <br />
              <br />
              保持 hover 時，雲霧不會遮擋。
              <br />
              移開後，雲霧緩慢恢復。
            </p>
            <button className="bg-gradient-to-r from-purple-500 to-pink-500 text-white px-6 py-3 rounded-lg font-semibold hover:shadow-lg transition-all">
              開始探索
            </button>
          </div>

          {/* 示例卡片 2 - 添加 data-fog-card 属性 */}
          <div 
            data-fog-card
            className="bg-white/90 backdrop-blur-sm rounded-2xl p-8 shadow-2xl max-w-md transition-all duration-300 hover:shadow-3xl hover:scale-105"
          >
            <h3 className="text-2xl font-bold text-gray-800 mb-3">
              🌫️ 互動雲霧效果
            </h3>
            <ul className="text-gray-600 space-y-2">
              <li>✓ 鼠標移動軌跡</li>
              <li>✓ 雲霧沿軌跡被推開</li>
              <li>✓ Hover 卡片時雲霧散開</li>
              <li>✓ 移開後雲霧自然回流</li>
            </ul>
          </div>
        </div>
      </FogRevealCard>

      {/* 返回首页链接 */}
      <div className="absolute bottom-8 left-8 z-30">
        <a
          href="/"
          className="text-white/70 hover:text-white transition-colors text-sm"
        >
          ← 返回首頁
        </a>
      </div>

      {/* 说明文字 */}
      <div className="absolute bottom-8 right-8 text-white/50 text-sm max-w-xs text-right z-30">
        <p>提示：移動鼠標在雲霧上畫出軌跡</p>
        <p className="mt-1">或者 Hover 到卡片上看雲霧散開</p>
      </div>
    </div>
  );
}
