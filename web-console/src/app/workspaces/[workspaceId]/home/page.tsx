'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { useWorkspaceDataOptional } from '@/contexts/WorkspaceDataContext';
import { useT } from '@/lib/i18n';
import {
  createWorkspaceFromWizard,
  fetchWorkspaceLaunchpad,
  postWorkspaceSeed,
  readWorkspaceResponseError,
} from './workspaceHomeApi';
import { canCompleteWorkspaceWizard, deriveWorkspaceHomeState } from './workspaceHomeState';
import type { LaunchpadData, WorkspaceHomeWorkspace, WorkspaceWizardData, WorkspaceWizardStep } from './workspaceHomeTypes';
import { WorkspaceHomeCreateView } from './WorkspaceHomeCreateView';
import { WorkspaceHomeLaunchpadView } from './WorkspaceHomeLaunchpadView';

export default function WorkspaceHomePage() {
  const t = useT();
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceId = params?.workspaceId as string;
  const isNewWorkspace = workspaceId === 'new';
  const workspaceData = useWorkspaceDataOptional();
  const workspace = (workspaceData?.workspace || null) as WorkspaceHomeWorkspace | null;
  const isLoadingWorkspace = isNewWorkspace ? false : (workspaceData?.isLoadingWorkspace || false);
  const workspaceError = workspaceData?.error || null;
  const refreshWorkspace = workspaceData?.refreshWorkspace || null;
  const [launchpadData, setLaunchpadData] = useState<LaunchpadData | null>(null);
  const [isLoadingLaunchpad, setIsLoadingLaunchpad] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showSetupDrawer, setShowSetupDrawer] = useState(false);
  const [setupSeedText, setSetupSeedText] = useState('');
  const [isProcessingSeed, setIsProcessingSeed] = useState(false);
  const [errorDialogMessage, setErrorDialogMessage] = useState<string | null>(null);
  const [wizardStep, setWizardStep] = useState<WorkspaceWizardStep>(isNewWorkspace ? 'method' : 'complete');
  const [wizardData, setWizardData] = useState<WorkspaceWizardData>({});
  const [wizardSeedText, setWizardSeedText] = useState('');

  useEffect(() => {
    if (searchParams?.get('setup') === 'true') {
      setShowSetupDrawer(true);
      const newSearchParams = new URLSearchParams(searchParams.toString());
      newSearchParams.delete('setup');
      router.replace(`${window.location.pathname}?${newSearchParams.toString()}`);
    }
  }, [searchParams, router]);

  useEffect(() => {
    if (isNewWorkspace) {
      setWizardStep('method');
    }
  }, [isNewWorkspace]);

  const fetchLaunchpadData = useCallback(async () => {
    if (!workspaceId || isNewWorkspace) return;
    setIsLoadingLaunchpad(true);
    setError(null);
    try {
      setLaunchpadData(await fetchWorkspaceLaunchpad(workspaceId));
    } catch (err) {
      console.error('Error fetching launchpad data:', err);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoadingLaunchpad(false);
    }
  }, [workspaceId, isNewWorkspace]);

  useEffect(() => {
    if (workspaceId && !isNewWorkspace && !isLoadingWorkspace) {
      fetchLaunchpadData();
    }
  }, [workspaceId, isNewWorkspace, isLoadingWorkspace, fetchLaunchpadData]);

  const handleStartWork = () => {
    if (workspaceId) {
      router.push(`/workspaces/${workspaceId}`);
    }
  };

  const handleRunFirstPlaybook = () => {
    if (workspaceId && launchpadData?.first_playbook) {
      router.push(`/workspaces/${workspaceId}/playbook/${launchpadData.first_playbook}`);
    }
  };

  const handleCreateWorkspace = async () => {
    if (!canCompleteWorkspaceWizard(wizardData)) return;

    try {
      const newWorkspace = await createWorkspaceFromWizard(wizardData);

      if (wizardSeedText.trim()) {
        await postWorkspaceSeed(String(newWorkspace.id), wizardSeedText, { trimPayload: false });
      }

      router.push(`/workspaces/${newWorkspace.id}/home`);
    } catch (err) {
      setErrorDialogMessage(t('creationFailed' as any) + ': ' + (err instanceof Error ? err.message : String(err)));
    }
  };

  const handleSubmitSetupSeed = async () => {
    if (!setupSeedText.trim() || !workspaceId) return;
    setIsProcessingSeed(true);
    try {
      const response = await postWorkspaceSeed(workspaceId, setupSeedText, { trimPayload: true });
      if (response.ok) {
        await fetchLaunchpadData();
        setSetupSeedText('');
        setShowSetupDrawer(false);
        alert(t('workspaceConfigured' as any));
      } else {
        const message = await readWorkspaceResponseError(response, t('retry' as any));
        setErrorDialogMessage(t('configurationFailed' as any) + ': ' + message);
      }
    } catch (err) {
      setErrorDialogMessage(t('configurationFailed' as any) + ': ' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setIsProcessingSeed(false);
    }
  };

  if (isNewWorkspace) {
    return (
      <WorkspaceHomeCreateView
        wizardStep={wizardStep}
        wizardData={wizardData}
        wizardSeedText={wizardSeedText}
        errorDialogMessage={errorDialogMessage}
        isCreateDisabled={!canCompleteWorkspaceWizard(wizardData)}
        onBack={() => router.push('/workspaces')}
        onSelectMethod={(method) => setWizardData({ method })}
        onWizardDataChange={setWizardData}
        onWizardSeedTextChange={setWizardSeedText}
        onCreate={handleCreateWorkspace}
        onCloseErrorDialog={() => setErrorDialogMessage(null)}
      />
    );
  }

  return (
    <WorkspaceHomeLaunchpadView
      workspace={workspace}
      launchpadData={launchpadData}
      homeState={deriveWorkspaceHomeState(launchpadData, workspace)}
      isLoading={isLoadingWorkspace || isLoadingLaunchpad}
      errorMessage={workspaceError || error}
      showSetupDrawer={showSetupDrawer}
      setupSeedText={setupSeedText}
      isProcessingSeed={isProcessingSeed}
      errorDialogMessage={errorDialogMessage}
      onRetry={refreshWorkspace || fetchLaunchpadData}
      onEditBlueprint={() => setShowSetupDrawer(true)}
      onStartWork={handleStartWork}
      onRunFirstPlaybook={handleRunFirstPlaybook}
      onOpenIntents={() => router.push(`/workspaces/${workspaceId}/intents`)}
      onOpenSetupDrawer={() => setShowSetupDrawer(true)}
      onCloseSetupDrawer={() => setShowSetupDrawer(false)}
      onSetupSeedTextChange={setSetupSeedText}
      onSubmitSetupSeed={handleSubmitSetupSeed}
      onClearSetupDrawer={() => {
        setSetupSeedText('');
        setShowSetupDrawer(false);
      }}
      onCloseErrorDialog={() => setErrorDialogMessage(null)}
    />
  );
}
