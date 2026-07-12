'use client';

import React, { useEffect, useMemo, useState } from 'react';

import { getInstalledCapabilities } from '@/lib/capability-packs/installed-capabilities-cache';

import { StepDetailPanelView } from './stepDetailPanel/StepDetailPanelView';
import {
  buildCapabilityWorkbenchHref,
  capabilitySupportsWorkbenchRoute,
  deriveStepDetailState,
} from './stepDetailPanel/stepDetailPanelState';
import type { StepDetailPanelProps } from './stepDetailPanel/stepDetailPanelTypes';

export type { StepDetailPanelProps } from './stepDetailPanel/stepDetailPanelTypes';
export {
  buildCapabilityWorkbenchHref,
  capabilitySupportsWorkbenchRoute,
};

export default function StepDetailPanel({
  steps,
  playbookStepDefinitions,
  totalSteps,
  currentStepIndex,
  currentStepToolCalls,
  stepEvents,
  executionStatus,
  artifacts = [],
  reviewBundleArtifacts = [],
  reviewBundlesLoading = false,
  remoteChildExecutions = [],
  workspaceId,
  apiUrl,
  relatedGovernedMemory,
  onViewArtifact,
  t,
}: StepDetailPanelProps) {
  const [installedCapabilities, setInstalledCapabilities] = useState<any[]>([]);
  const [capabilityUIComponents, setCapabilityUIComponents] = useState<Map<string, React.ComponentType<any>>>(new Map());
  const [matchingComponentKeys, setMatchingComponentKeys] = useState<string[]>([]);
  const [openModalKey, setOpenModalKey] = useState<string | null>(null);
  const [selectedReviewBundleId, setSelectedReviewBundleId] = useState<string | null>(null);

  useEffect(() => {
    if (apiUrl == null) return;

    void getInstalledCapabilities(apiUrl, workspaceId)
      .then((capabilities) => {
        setInstalledCapabilities(capabilities);
      })
      .catch((err) => {
        console.warn('Failed to load installed capabilities:', err);
      });
  }, [apiUrl, workspaceId]);

  useEffect(() => {
    if (apiUrl == null || artifacts.length === 0 || installedCapabilities.length === 0) {
      setMatchingComponentKeys([]);
      return;
    }

    let cancelled = false;

    const loadMatchingComponents = async () => {
      const {
        artifactsMatchComponent,
        loadCapabilityUIComponent,
      } = await import('@/lib/capability-ui-loader');
      if (cancelled) {
        return;
      }

      const nextMatchingKeys: string[] = [];

      for (const capability of installedCapabilities) {
        if (capability.ui_components && capability.ui_components.length > 0) {
          for (const componentInfo of capability.ui_components) {
            if (artifactsMatchComponent(artifacts, componentInfo)) {
              const key = `${capability.code}:${componentInfo.code}`;
              nextMatchingKeys.push(key);

              setCapabilityUIComponents((prev) => {
                if (prev.has(key)) {
                  return prev;
                }
                return prev;
              });

              loadCapabilityUIComponent(
                capability.code,
                componentInfo.code,
                apiUrl,
                workspaceId,
              ).then((Component) => {
                if (cancelled) {
                  return;
                }
                if (Component) {
                  setCapabilityUIComponents((prev) => {
                    const nextMap = new Map(prev);
                    nextMap.set(key, Component);
                    return nextMap;
                  });
                }
              }).catch((err) => {
                console.warn(`Failed to load component ${key}:`, err);
              });
            }
          }
        }
      }

      setMatchingComponentKeys(nextMatchingKeys);
    };

    loadMatchingComponents();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifacts.length, installedCapabilities.length, apiUrl]);

  const {
    currentStep,
    currentStepInfo,
    remoteChildrenToShow,
  } = deriveStepDetailState({
    currentStepIndex,
    playbookStepDefinitions,
    remoteChildExecutions,
    steps,
    totalSteps,
  });

  const selectedReviewBundle = useMemo(
    () =>
      reviewBundleArtifacts.find((artifact) => artifact.id === selectedReviewBundleId)
      || reviewBundleArtifacts[0]
      || null,
    [reviewBundleArtifacts, selectedReviewBundleId],
  );

  useEffect(() => {
    if (!reviewBundleArtifacts.length) {
      setSelectedReviewBundleId(null);
      return;
    }
    if (!selectedReviewBundleId || !reviewBundleArtifacts.some((artifact) => artifact.id === selectedReviewBundleId)) {
      setSelectedReviewBundleId(reviewBundleArtifacts[0].id);
    }
  }, [reviewBundleArtifacts, selectedReviewBundleId]);

  return (
    <StepDetailPanelView
      apiUrl={apiUrl}
      artifacts={artifacts}
      capabilityUIComponents={capabilityUIComponents}
      currentStep={currentStep}
      currentStepIndex={currentStepIndex}
      currentStepInfo={currentStepInfo}
      currentStepToolCalls={currentStepToolCalls}
      executionStatus={executionStatus}
      installedCapabilities={installedCapabilities}
      matchingComponentKeys={matchingComponentKeys}
      openModalKey={openModalKey}
      relatedGovernedMemory={relatedGovernedMemory}
      remoteChildrenToShow={remoteChildrenToShow}
      reviewBundleArtifacts={reviewBundleArtifacts}
      reviewBundlesLoading={reviewBundlesLoading}
      selectedReviewBundle={selectedReviewBundle}
      stepEvents={stepEvents}
      workspaceId={workspaceId}
      t={t}
      onOpenModal={setOpenModalKey}
      onReviewBundleSelect={setSelectedReviewBundleId}
      onViewArtifact={onViewArtifact}
    />
  );
}
