'use client';

import React from 'react';

interface BrandFoundationCardsProps {
  workspaceId: string;
}

export default function BrandFoundationCards({ workspaceId }: BrandFoundationCardsProps) {
  return (
    <div className="border rounded-lg p-4 bg-gray-50 dark:bg-gray-800">
      <p className="text-sm text-gray-500 dark:text-gray-400">
        BrandFoundationCards component has been migrated to cloud capability.
        <br />
        Location: <code className="text-xs">mindscape-ai-cloud/capabilities/brand_identity/ui/BrandFoundationCards.tsx</code>
        <br />
        <br />
        Dynamic loading mechanism needs to be implemented to load this component.
      </p>
    </div>
  );
}
