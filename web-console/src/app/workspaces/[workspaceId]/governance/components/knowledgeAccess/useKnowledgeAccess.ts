'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import {
  loadKnowledgeAccessDetail,
  loadKnowledgeAccessSummary,
  replaceKnowledgeAccess,
  runKnowledgeProjectionAction,
} from './api';
import type {
  KnowledgeAccessDetail,
  KnowledgeAccessReplacement,
  KnowledgeAccessSummary,
  KnowledgeProjectionAction,
  KnowledgeProjectionActionReceipt,
} from './types';

export function useKnowledgeAccess(workspaceId: string) {
  const [summary, setSummary] = useState<KnowledgeAccessSummary | null>(null);
  const [detail, setDetail] = useState<KnowledgeAccessDetail | null>(null);
  const [selectedResourceId, setSelectedResourceId] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [mutationLoading, setMutationLoading] = useState(false);
  const [actionReceipt, setActionReceipt] =
    useState<KnowledgeProjectionActionReceipt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const detailAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setSummaryLoading(true);
    setError(null);
    void loadKnowledgeAccessSummary(workspaceId, controller.signal)
      .then(setSummary)
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : String(reason));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setSummaryLoading(false);
      });
    return () => controller.abort();
  }, [workspaceId]);

  useEffect(
    () => () => {
      detailAbortRef.current?.abort();
    },
    []
  );

  const selectResource = useCallback(
    async (resourceId: string) => {
      detailAbortRef.current?.abort();
      const controller = new AbortController();
      detailAbortRef.current = controller;
      setSelectedResourceId(resourceId);
      setDetail(null);
      setActionReceipt(null);
      setDetailLoading(true);
      setError(null);
      try {
        const loaded = await loadKnowledgeAccessDetail(
          workspaceId,
          resourceId,
          controller.signal
        );
        if (!controller.signal.aborted) setDetail(loaded);
      } catch (reason) {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : String(reason));
        }
      } finally {
        if (!controller.signal.aborted) setDetailLoading(false);
      }
    },
    [workspaceId]
  );

  const replace = useCallback(
    async (command: KnowledgeAccessReplacement) => {
      if (!selectedResourceId) return;
      setMutationLoading(true);
      setError(null);
      try {
        const replaced = await replaceKnowledgeAccess(
          workspaceId,
          selectedResourceId,
          command
        );
        setDetail(replaced);
        setSummary((current) =>
          current
            ? {
                ...current,
                items: current.items.map((item) =>
                  item.knowledge_resource_id === selectedResourceId
                    ? {
                        ...item,
                        authz_revision: replaced.resource.authz_revision,
                        grant_count: replaced.grant_count,
                        deny_count: replaced.grants.filter(
                          (grant) => grant.effect === 'deny'
                        ).length,
                        deny_present: replaced.grants.some(
                          (grant) => grant.effect === 'deny'
                        ),
                        projection_status: String(
                          replaced.projection?.status ||
                            item.projection_status ||
                            ''
                        ),
                      }
                    : item
                ),
              }
            : current
        );
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : String(reason));
        throw reason;
      } finally {
        setMutationLoading(false);
      }
    },
    [selectedResourceId, workspaceId]
  );

  const runAction = useCallback(
    async (action: KnowledgeProjectionAction) => {
      if (!selectedResourceId || !detail) return;
      setMutationLoading(true);
      setError(null);
      try {
        const receipt = await runKnowledgeProjectionAction(
          workspaceId,
          selectedResourceId,
          action,
          detail.resource.authz_revision,
          detail.resource.source_revision
        );
        setActionReceipt(receipt);
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : String(reason));
        throw reason;
      } finally {
        setMutationLoading(false);
      }
    },
    [detail, selectedResourceId, workspaceId]
  );

  return {
    summary,
    detail,
    selectedResourceId,
    summaryLoading,
    detailLoading,
    mutationLoading,
    actionReceipt,
    error,
    selectResource,
    replace,
    runAction,
  };
}
