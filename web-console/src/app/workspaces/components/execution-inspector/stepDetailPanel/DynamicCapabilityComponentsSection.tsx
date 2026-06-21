import React, { Suspense } from 'react';

import type { DynamicComponentState } from './stepDetailPanelTypes';

export function DynamicCapabilityComponentsSection({
  apiUrl,
  capabilityUIComponents,
  installedCapabilities,
  matchingComponentKeys,
  openModalKey,
  workspaceId,
  onOpenModal,
}: DynamicComponentState) {
  if (!workspaceId || !apiUrl) {
    return null;
  }

  return (
    <>
      {matchingComponentKeys.map((key) => {
        const [capabilityCode, componentCode] = key.split(':');
        const Component = capabilityUIComponents.get(key);
        const capability = installedCapabilities.find((candidate) => candidate.code === capabilityCode);
        const componentInfo = capability?.ui_components?.find((candidate: any) => candidate.code === componentCode);
        const isOpen = openModalKey === key;

        if (!Component || !componentInfo) {
          return null;
        }

        return (
          <div key={key} className="mb-3 p-2 border-b border-gray-200 dark:border-gray-700">
            <button
              onClick={() => onOpenModal(key)}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg transition-colors text-sm font-medium"
            >
              <span>{componentInfo.description || `View ${componentInfo.code}`}</span>
            </button>
            {isOpen && (
              <Suspense fallback={<div className="p-4 text-center">Loading...</div>}>
                <Component
                  isOpen={isOpen}
                  onClose={() => onOpenModal(null)}
                  workspaceId={workspaceId}
                />
              </Suspense>
            )}
          </div>
        );
      })}
    </>
  );
}
