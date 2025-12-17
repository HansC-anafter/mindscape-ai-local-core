'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';

interface ResizablePanelProps {
  top: React.ReactNode;
  bottom: React.ReactNode;
  defaultTopHeight?: number; // 默认顶部高度百分比 (0-100)
  minTopHeight?: number; // 最小顶部高度百分比
  minBottomHeight?: number; // 最小底部高度百分比
  className?: string;
}

export function ResizablePanel({
  top,
  bottom,
  defaultTopHeight = 50,
  minTopHeight = 20,
  minBottomHeight = 20,
  className = '',
}: ResizablePanelProps) {
  const [topHeight, setTopHeight] = useState(defaultTopHeight);
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragStartY = useRef(0);
  const dragStartHeight = useRef(0);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    dragStartY.current = e.clientY;
    dragStartHeight.current = topHeight;
  }, [topHeight]);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging || !containerRef.current) return;

    const container = containerRef.current;
    const containerHeight = container.clientHeight;
    const deltaY = e.clientY - dragStartY.current;
    const deltaPercent = (deltaY / containerHeight) * 100;

    let newTopHeight = dragStartHeight.current + deltaPercent;

    // 限制在最小/最大范围内
    newTopHeight = Math.max(minTopHeight, Math.min(100 - minBottomHeight, newTopHeight));

    setTopHeight(newTopHeight);
  }, [isDragging, minTopHeight, minBottomHeight]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'row-resize';
      document.body.style.userSelect = 'none';

      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      };
    }
  }, [isDragging, handleMouseMove, handleMouseUp]);

  return (
    <div
      ref={containerRef}
      className={`flex flex-col overflow-hidden ${className}`}
      style={{ height: '100%' }}
    >
      {/* Top Panel */}
      <div
        className="overflow-hidden"
        style={{
          height: `${topHeight}%`,
          minHeight: `${minTopHeight}%`,
          maxHeight: `${100 - minBottomHeight}%`,
        }}
      >
        {top}
      </div>

      {/* Resizer */}
      <div
        className={`relative cursor-row-resize select-none ${
          isDragging ? 'bg-blue-500' : 'bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600'
        } transition-colors`}
        style={{
          height: '4px',
          flexShrink: 0,
        }}
        onMouseDown={handleMouseDown}
      >
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-8 h-1 bg-gray-400 dark:bg-gray-500 rounded-full" />
        </div>
      </div>

      {/* Bottom Panel */}
      <div
        className="overflow-hidden"
        style={{
          height: `${100 - topHeight}%`,
          minHeight: `${minBottomHeight}%`,
          maxHeight: `${100 - minTopHeight}%`,
        }}
      >
        {bottom}
      </div>
    </div>
  );
}

