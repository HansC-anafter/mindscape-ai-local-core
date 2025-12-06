'use client';

import React, { createContext, useContext } from 'react';

interface SurfaceLayoutProps {
  type: 'three_column' | 'two_column' | 'single_column';
  children: React.ReactNode;
}

const SurfacePositionContext = createContext<string>('center');

/**
 * SurfaceLayout - Layout component for Playbook Surfaces
 *
 * Provides flexible column layouts for different playbook surfaces.
 * Supports three-column, two-column, and single-column layouts.
 */
export function SurfaceLayout({ type, children }: SurfaceLayoutProps) {
  const layoutClasses = {
    three_column: 'grid grid-cols-3 gap-0 h-full',
    two_column: 'grid grid-cols-2 gap-0 h-full',
    single_column: 'flex flex-col h-full'
  };

  return (
    <div className={layoutClasses[type]}>
      {React.Children.map(children, (child, index) => {
        if (React.isValidElement(child)) {
          const position = child.props.position ||
            (type === 'three_column' ? ['left', 'center', 'right'][index] : 'center');
          return (
            <SurfacePositionContext.Provider value={position}>
              {child}
            </SurfacePositionContext.Provider>
          );
        }
        return child;
      })}
    </div>
  );
}

/**
 * useSurfacePosition - Hook to get current position in SurfaceLayout
 */
export function useSurfacePosition(): string {
  return useContext(SurfacePositionContext);
}

