'use client';

import Header from '../components/Header'
import HabitSuggestionToast from '../components/HabitSuggestionToast'
import ReviewSuggestionToast from '../components/ReviewSuggestionToast'

export default function Home() {
  const profileId = 'default-user';

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="text-center">
          <h1 className="text-4xl font-bold text-gray-900 mb-4">
            Welcome to Mindscape AI
          </h1>
          <p className="text-xl text-gray-600 mb-8">
            Your personal AI team console
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-12">
            <div className="bg-white p-6 rounded-lg shadow">
              <h2 className="text-2xl font-semibold mb-4">Mindscape</h2>
              <p className="text-gray-600">
                Manage your profile, preferences, and intent cards
              </p>
            </div>
            <div className="bg-white p-6 rounded-lg shadow">
              <h2 className="text-2xl font-semibold mb-4">AI Agents</h2>
              <p className="text-gray-600">
                Run your AI team: Planner, Writer, Coach, and Coder
              </p>
            </div>
          </div>
        </div>
      </main>

      {/* Habit Suggestion Toast */}
      <HabitSuggestionToast
        profileId={profileId}
        autoShow={true}
        checkInterval={30000} // 30 秒檢查一次
      />

      {/* Review Suggestion Toast */}
      <ReviewSuggestionToast
        profileId={profileId}
        autoShow={true}
        checkInterval={60000} // 60 秒檢查一次
      />
    </div>
  )
}
