'use client';

import React from 'react';

interface ToolGridProps {
  children: React.ReactNode;
}

export function ToolGrid({ children }: ToolGridProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {children}
    </div>
  );
}
