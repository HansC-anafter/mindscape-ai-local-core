'use client';

import React, { useState, useEffect } from 'react';
import { ChapterDetail } from './ChapterDetail';
import { ChapterIntents } from './ChapterIntents';
import { EmptyState } from '../ui/EmptyState';
import './ChapterOutlineView.css';

export interface Chapter {
  id: string;
  name: string;
  status: 'planned' | 'in_progress' | 'completed';
  sections: Array<{
    id: string;
    name: string;
    status: 'draft' | 'review' | 'published';
  }>;
  relatedPlaybooks: string[];
  relatedIntents: string[];
}

interface ChapterOutlineViewProps {
  storyThreadId: string;
  apiUrl: string;
  chapters?: Chapter[];
}

export function ChapterOutlineView({
  storyThreadId,
  apiUrl,
  chapters: initialChapters,
}: ChapterOutlineViewProps) {
  const [chapters, setChapters] = useState<Chapter[]>(initialChapters || []);
  const [selectedChapterId, setSelectedChapterId] = useState<string | undefined>();
  const [loading, setLoading] = useState(!initialChapters);

  useEffect(() => {
    if (!initialChapters) {
      loadChapters();
    }
  }, [storyThreadId, apiUrl]);

  const loadChapters = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        `${apiUrl}/api/v1/story-threads/${storyThreadId}/chapters`
      );
      if (response.ok) {
        const data = await response.json();
        setChapters(data.chapters || []);
      } else {
        setChapters([]);
      }
    } catch (err) {
      setChapters([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectChapter = (chapterId: string) => {
    setSelectedChapterId(chapterId === selectedChapterId ? undefined : chapterId);
  };

  if (loading) {
    return (
      <div className="chapter-outline-view">
        <EmptyState customMessage="Loading chapters..." />
      </div>
    );
  }

  return (
    <div className="chapter-outline-view">
      <div className="outline-layout">
        <div className="chapters-tree">
          <div className="tree-header">Chapter Outline</div>
          {chapters.length === 0 ? (
            <EmptyState type="chapters" />
          ) : (
            chapters.map((chapter, index) => (
              <ChapterTreeItem
                key={chapter.id}
                chapter={chapter}
                index={index + 1}
                isSelected={chapter.id === selectedChapterId}
                onClick={() => handleSelectChapter(chapter.id)}
              />
            ))
          )}
        </div>

        <div className="chapter-detail">
          {selectedChapterId ? (
            <ChapterDetail
              chapterId={selectedChapterId}
              storyThreadId={storyThreadId}
              apiUrl={apiUrl}
            />
          ) : (
            <EmptyState customMessage="Select a chapter to view details" />
          )}
        </div>

        <div className="chapter-intents">
          {selectedChapterId && (
            <ChapterIntents
              chapterId={selectedChapterId}
              storyThreadId={storyThreadId}
              apiUrl={apiUrl}
            />
          )}
        </div>
      </div>
    </div>
  );
}

interface ChapterTreeItemProps {
  chapter: Chapter;
  index: number;
  isSelected: boolean;
  onClick: () => void;
}

function ChapterTreeItem({ chapter, index, isSelected, onClick }: ChapterTreeItemProps) {
  const completedSections = chapter.sections.filter(s => s.status === 'published').length;
  const totalSections = chapter.sections.length;

  return (
    <div
      className={`chapter-tree-item ${isSelected ? 'selected' : ''} ${chapter.status}`}
      onClick={onClick}
    >
      <div className="chapter-header">
        <span className="chapter-number">Chapter {index}:</span>
        <span className="chapter-name">{chapter.name}</span>
      </div>
      <div className="chapter-progress">
        ({completedSections}/{totalSections} sections completed)
      </div>
      {chapter.status === 'in_progress' && (
        <span className="status-badge">In Progress</span>
      )}
    </div>
  );
}

