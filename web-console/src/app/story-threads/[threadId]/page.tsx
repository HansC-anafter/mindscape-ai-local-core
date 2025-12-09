'use client';

import React, { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import Header from '@/components/Header';
import { storyThreadAPI, StoryThread, Chapter, TimelineEvent } from '@/lib/story-thread-api';
import Timeline from '@/components/story-thread/Timeline';
import ChapterCard from '@/components/story-thread/ChapterCard';

export const dynamic = 'force-dynamic';
export const dynamicParams = true;

export default function StoryThreadPage() {
  const params = useParams();
  const router = useRouter();
  const threadId = params?.threadId as string;

  const [thread, setThread] = useState<StoryThread | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'chapters' | 'timeline' | 'context'>('chapters');

  useEffect(() => {
    if (threadId) {
      loadThreadData();
    }
  }, [threadId]);

  const loadThreadData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [threadData, chaptersData, timelineData] = await Promise.all([
        storyThreadAPI.getThread(threadId),
        storyThreadAPI.getChapters(threadId),
        storyThreadAPI.getTimeline(threadId),
      ]);

      setThread(threadData);
      setChapters(chaptersData);
      setTimeline(timelineData);
    } catch (err: any) {
      console.error('Failed to load thread data:', err);
      setError(err.message || '載入失敗');
    } finally {
      setLoading(false);
    }
  };

  const handleChapterSelect = (chapterId: string) => {
    console.log('Selected chapter:', chapterId);
  };

  const handleEventClick = (event: TimelineEvent) => {
    console.log('Clicked event:', event);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header />
        <div className="container mx-auto px-4 py-8">
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">載入中...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error || !thread) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header />
        <div className="container mx-auto px-4 py-8">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <h2 className="text-lg font-semibold text-red-800 mb-2">載入錯誤</h2>
            <p className="text-red-600">{error || 'Story Thread 不存在'}</p>
            <Link
              href="/workspaces"
              className="mt-4 inline-block text-blue-600 hover:text-blue-800"
            >
              ← 返回工作區
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <div className="container mx-auto px-4 py-8">
        <div className="mb-6">
          <Link
            href={`/workspaces/${thread.workspace_id}`}
            className="text-blue-600 hover:text-blue-800 mb-4 inline-block"
          >
            ← 返回工作區
          </Link>
          <h1 className="text-3xl font-bold text-gray-900 mt-2">{thread.name}</h1>
          {thread.description && (
            <p className="text-gray-600 mt-2">{thread.description}</p>
          )}
          <div className="mt-4 flex gap-4 text-sm text-gray-500">
            <span>Mind Lens: {thread.mind_lens_id}</span>
            <span>版本: {thread.version}</span>
            <span>創建: {new Date(thread.created_at).toLocaleDateString('zh-TW')}</span>
          </div>
        </div>

        <div className="tabs mb-6 border-b border-gray-200">
          <button
            className={`px-4 py-2 font-medium ${
              activeTab === 'chapters'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-600 hover:text-gray-900'
            }`}
            onClick={() => setActiveTab('chapters')}
          >
            章節 ({chapters.length})
          </button>
          <button
            className={`px-4 py-2 font-medium ${
              activeTab === 'timeline'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-600 hover:text-gray-900'
            }`}
            onClick={() => setActiveTab('timeline')}
          >
            時間線 ({timeline.length})
          </button>
          <button
            className={`px-4 py-2 font-medium ${
              activeTab === 'context'
                ? 'text-blue-600 border-b-2 border-blue-600'
                : 'text-gray-600 hover:text-gray-900'
            }`}
            onClick={() => setActiveTab('context')}
          >
            共享上下文
          </button>
        </div>

        <div className="content">
          {activeTab === 'chapters' && (
            <div className="chapters-section">
              <div className="mb-4 flex justify-between items-center">
                <h2 className="text-xl font-semibold">章節列表</h2>
              </div>
              <div className="space-y-4">
                {chapters.length === 0 ? (
                  <div className="text-center py-12 text-gray-500">
                    尚無章節
                  </div>
                ) : (
                  chapters.map((chapter) => (
                    <ChapterCard
                      key={chapter.chapter_id}
                      chapter={chapter}
                      isCurrent={chapter.chapter_id === thread.current_chapter_id}
                      onSelect={handleChapterSelect}
                    />
                  ))
                )}
              </div>
            </div>
          )}

          {activeTab === 'timeline' && (
            <div className="timeline-section">
              <Timeline
                threadId={threadId}
                events={timeline}
                onEventClick={handleEventClick}
              />
            </div>
          )}

          {activeTab === 'context' && (
            <div className="context-section">
              <h2 className="text-xl font-semibold mb-4">共享上下文</h2>
              <div className="bg-white rounded-lg border border-gray-200 p-6">
                <pre className="text-sm text-gray-700 overflow-auto">
                  {JSON.stringify(thread.shared_context, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

