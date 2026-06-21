'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';

import {
  fetchAgentsStatus,
  fetchHostServicesStatus,
  shouldSkipBackgroundPoll,
} from './integratedSystemStatusApi';
import { IntegratedSystemStatusCardView } from './IntegratedSystemStatusCardView';
import type { AgentInfo, HostServiceStatus, IntegratedSystemStatusProps } from './integratedSystemStatusTypes';
import {
  COPY_RESET_MS,
  DEFAULT_UNIX_BRIDGE_COMMAND,
  DEFAULT_WINDOWS_BRIDGE_COMMAND,
  POLL_INTERVAL_MS,
} from './integratedSystemStatusTypes';

export default function IntegratedSystemStatusCard({
  systemStatus,
  workspace,
  workspaceId,
  onRefresh,
}: IntegratedSystemStatusProps) {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [bridgeScriptPath, setBridgeScriptPath] = useState<string | null>(null);
  const [showBridgeDialog, setShowBridgeDialog] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copiedAll, setCopiedAll] = useState(false);
  const [hostServices, setHostServices] = useState<HostServiceStatus[]>([]);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const agentsRequestRef = useRef<Promise<void> | null>(null);
  const hostServicesRequestRef = useRef<Promise<void> | null>(null);

  const fetchAgents = useCallback(async () => {
    if (shouldSkipBackgroundPoll()) {
      return;
    }
    if (agentsRequestRef.current) {
      return agentsRequestRef.current;
    }

    const request = (async () => {
      const snapshot = await fetchAgentsStatus(workspaceId);
      if (!snapshot) {
        return;
      }

      setAgents(snapshot.agents);
      if (snapshot.bridgeScriptPath) {
        setBridgeScriptPath(snapshot.bridgeScriptPath);
      }
    })();

    agentsRequestRef.current = request;
    try {
      await request;
    } finally {
      if (agentsRequestRef.current === request) {
        agentsRequestRef.current = null;
      }
    }
  }, [workspaceId]);

  const fetchHostServices = useCallback(async () => {
    if (shouldSkipBackgroundPoll()) {
      return;
    }
    if (hostServicesRequestRef.current) {
      return hostServicesRequestRef.current;
    }

    const request = (async () => {
      setHostServices(await fetchHostServicesStatus());
      setLastUpdated(new Date());
    })();

    hostServicesRequestRef.current = request;
    try {
      await request;
    } finally {
      if (hostServicesRequestRef.current === request) {
        hostServicesRequestRef.current = null;
      }
    }
  }, []);

  const handleManualRefresh = useCallback(async () => {
    setIsRefreshing(true);
    await Promise.all([fetchAgents(), fetchHostServices()]);
    onRefresh?.();
    setIsRefreshing(false);
  }, [fetchAgents, fetchHostServices, onRefresh]);

  useEffect(() => {
    fetchAgents();
    fetchHostServices();
    const interval = setInterval(() => {
      fetchAgents();
      fetchHostServices();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchAgents, fetchHostServices]);

  useEffect(() => {
    if (systemStatus) setLastUpdated(new Date());
  }, [systemStatus]);

  const handleCopyWindowsCommand = useCallback(() => {
    navigator.clipboard.writeText(DEFAULT_WINDOWS_BRIDGE_COMMAND);
    setCopiedAll(true);
    setTimeout(() => setCopiedAll(false), COPY_RESET_MS);
  }, []);

  const handleCopyUnixCommand = useCallback(() => {
    const command = bridgeScriptPath
      ? `${bridgeScriptPath} --all`
      : DEFAULT_UNIX_BRIDGE_COMMAND;
    navigator.clipboard.writeText(command);
    setCopied(true);
    setTimeout(() => setCopied(false), COPY_RESET_MS);
  }, [bridgeScriptPath]);

  return (
    <IntegratedSystemStatusCardView
      agents={agents}
      availableCount={agents.filter((agent) => agent.status === 'available').length}
      bridgeScriptPath={bridgeScriptPath}
      copied={copied}
      copiedAll={copiedAll}
      hostServices={hostServices}
      isRefreshing={isRefreshing}
      lastUpdated={lastUpdated}
      showBridgeDialog={showBridgeDialog}
      systemStatus={systemStatus}
      workspace={workspace}
      workspaceId={workspaceId}
      onCopyUnixCommand={handleCopyUnixCommand}
      onCopyWindowsCommand={handleCopyWindowsCommand}
      onHideBridgeDialog={() => setShowBridgeDialog(false)}
      onManualRefresh={handleManualRefresh}
      onRefresh={onRefresh}
      onShowBridgeDialog={() => setShowBridgeDialog(true)}
    />
  );
}
