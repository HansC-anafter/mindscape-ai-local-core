'use client';

import React from 'react';

interface SectionProps {
  title?: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
  headerRight?: React.ReactNode;
}

export function Section({ title, description, children, className = '', headerRight }: SectionProps) {
  return (
    <div className={className}>
      {(title || description) && (
        <div className="mb-4 flex items-start justify-between gap-4">
          <div className="flex-1">
            {title && <h2 className="text-xl font-semibold text-gray-900">{title}</h2>}
            {description && <p className={`text-sm text-gray-600 ${title ? 'mt-1' : ''}`}>{description}</p>}
          </div>
          {headerRight && (
            <div className="flex-shrink-0">
              {headerRight}
            </div>
          )}
        </div>
      )}
      {children}
    </div>
  );
}
