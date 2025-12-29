'use client';

import React, { useState, useEffect } from 'react';
import dynamic from 'next/dynamic';
import Header from '@/components/Header';
import { useEffectiveLens } from '@/lib/lens-api';
import type { EffectiveLens, LensNodeState, LensNode } from '@/lib/lens-api';
import { NodeDetailPanel } from '@/components/mindscape/lens/NodeDetailPanel';

// Disable SSR for components that use Sigma.js (WebGL)
const PresetPanel = dynamic(() => import('@/components/mindscape/lens/PresetPanel').then(mod => ({ default: mod.PresetPanel })), { ssr: false });
const PalettePanel = dynamic(() => import('@/components/mindscape/lens/PalettePanel').then(mod => ({ default: mod.PalettePanel })), { ssr: false });
const InteractionPanel = dynamic(() => import('@/components/mindscape/lens/InteractionPanel').then(mod => ({ default: mod.InteractionPanel })), { ssr: false });

const PROFILE_ID = 'default-user';

export default function MindLensPage() {
  const [workspaceId, setWorkspaceId] = useState<string | undefined>();
  const [sessionId, setSessionId] = useState<string>(() => {
    if (typeof window !== 'undefined') {
      let sid = sessionStorage.getItem('mind-lens-session-id');
      if (!sid) {
        sid = `session-${Date.now()}`;
        sessionStorage.setItem('mind-lens-session-id', sid);
      }
      return sid;
    }
    return `session-${Date.now()}`;
  });

  const { lens, isLoading, refresh } = useEffectiveLens({
    profile_id: PROFILE_ID,
    workspace_id: workspaceId,
    session_id: sessionId,
  });

  const [selectedNodes, setSelectedNodes] = useState<string[]>([]);
  const [viewMode, setViewMode] = useState<'graph' | 'matrix'>('graph');
  const [tabMode, setTabMode] = useState<'mirror' | 'experiment' | 'writeback' | 'drift'>('mirror');
  const [selectedNodeDetail, setSelectedNodeDetail] = useState<LensNode | null>(null);
  const [lockedNodeId, setLockedNodeId] = useState<string | null>(null); // Track clicked/locked node
  const [lockedNode, setLockedNode] = useState<LensNode | null>(null); // Store locked node data
  // Use refs to track locked state synchronously (React state updates are async)
  const lockedNodeIdRef = React.useRef<string | null>(null);
  const lockedNodeRef = React.useRef<LensNode | null>(null);
  const lastClickTimeRef = React.useRef<number>(0); // Track last click time to prevent hover override

  const handleNodeSelect = (nodeId: string) => {
    // Check if node is currently selected
    const isCurrentlySelected = selectedNodes.includes(nodeId);
    const isCurrentlyLocked = lockedNodeId === nodeId;

    // Update selected nodes for highlighting (for multi-select in Matrix mode)
    const newSelectedNodes = isCurrentlySelected
      ? selectedNodes.filter((id) => id !== nodeId)
      : [...selectedNodes, nodeId];

    setSelectedNodes(newSelectedNodes);

    // Handle locking logic
    if (nodeId && lens) {
      const node = lens.nodes.find(n => n.node_id === nodeId);

      if (node) {
        if (isCurrentlySelected && isCurrentlyLocked) {
          // Clicking the same locked node again - deselecting it
          // Check if there are other selected nodes
          const remainingSelected = newSelectedNodes.filter(id => id !== nodeId);

          if (remainingSelected.length > 0) {
            // Lock the first remaining selected node
            const nextNodeId = remainingSelected[0];
            const nextNode = lens.nodes.find(n => n.node_id === nextNodeId);

            if (nextNode) {
              setLockedNodeId(nextNodeId);
              setLockedNode(nextNode);
              lockedNodeIdRef.current = nextNodeId;
              lockedNodeRef.current = nextNode;
              setSelectedNodeDetail(nextNode);
            } else {
              setLockedNodeId(null);
              setLockedNode(null);
              lockedNodeIdRef.current = null;
              lockedNodeRef.current = null;
              setSelectedNodeDetail(null);
            }
          } else {
            // No other selected nodes, unlock
            setLockedNodeId(null);
            setLockedNode(null);
            lockedNodeIdRef.current = null;
            lockedNodeRef.current = null;
            setSelectedNodeDetail(null);
          }
        } else if (!isCurrentlySelected) {
          // Clicking a new node - add to selection and lock it
          lastClickTimeRef.current = Date.now(); // Record click time
          setLockedNodeId(nodeId);
          setLockedNode(node);
          lockedNodeIdRef.current = nodeId;
          lockedNodeRef.current = node;
          setSelectedNodeDetail(node);
        } else {
          // Node is selected but not locked - lock it (keep other selections for AI context)
          lastClickTimeRef.current = Date.now(); // Record click time
          setLockedNodeId(nodeId);
          setLockedNode(node);
          lockedNodeIdRef.current = nodeId;
          lockedNodeRef.current = node;
          setSelectedNodeDetail(node);
        }
      }
    }
  };

  const handleNodeHover = (nodeId: string | null) => {
    // 如果剛剛點擊過（200ms 內），忽略 hover 以避免覆蓋點擊的節點
    const timeSinceLastClick = Date.now() - lastClickTimeRef.current;
    if (timeSinceLastClick < 200) {
      return;
    }

    // Hover 邏輯：
    // 1. 如果有鎖定節點，hover 到其他節點時顯示臨時預覽，hover 離開時恢復鎖定節點
    // 2. 如果沒有鎖定節點，hover 顯示預覽，hover 離開時清除

    if (nodeId && lens) {
      // Hover 到某個節點
      const node = lens.nodes.find(n => n.node_id === nodeId);
      if (node) {
        // 如果 hover 的是鎖定節點本身，不需要改變（已經顯示）
        if (lockedNodeIdRef.current === nodeId) {
          return;
        }
        // 顯示 hover 預覽（臨時覆蓋鎖定節點）
        setSelectedNodeDetail(node);
      }
    } else {
      // Hover 離開
      if (lockedNodeRef.current) {
        // 有鎖定節點，恢復顯示鎖定節點
        setSelectedNodeDetail(lockedNodeRef.current);
      } else {
        // 沒有鎖定節點，清除面板
        setSelectedNodeDetail(null);
      }
    }
  };

  const handleNodeStateChange = async (nodeId: string, state: LensNodeState) => {
    try {
      const { setSessionOverride } = await import('@/lib/lens-api');
      await setSessionOverride(sessionId, nodeId, state);
      await refresh();
    } catch (error) {
      console.error('Failed to change node state:', error);
      alert('Failed to change node state');
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="text-center py-12">
            <p className="text-gray-600">Loading...</p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main className="max-w-[1920px] mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900 mb-2">Mind-Lens 管理</h1>
              <p className="text-gray-600">三欄式布局：Preset + Graph/Matrix + Preview/ChangeSet</p>
            </div>
            <div className="flex items-center space-x-2">
              <span className="text-sm text-gray-500">Session:</span>
              <code className="text-xs bg-gray-100 px-2 py-1 rounded text-gray-700">
                {sessionId.slice(0, 12)}...
              </code>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-12 gap-6 h-[calc(100vh-200px)]">
          {/* Left Panel: Preset + Dirty/Diff */}
          <div className="col-span-3">
            <PresetPanel
              activePreset={lens ? { id: lens.global_preset_id, name: lens.global_preset_name } : null}
              sessionId={sessionId}
              profileId={PROFILE_ID}
              workspaceId={workspaceId}
              onPresetSelect={(id) => {
                // TODO: Implement preset selection
              }}
              onRefresh={refresh}
            />
          </div>

          {/* Middle Panel: Graph + Matrix */}
          <div className="col-span-5">
            <PalettePanel
              effectiveLens={lens}
              viewMode={viewMode}
              onViewModeChange={setViewMode}
              onNodeStateChange={viewMode === 'matrix' ? handleNodeStateChange : undefined}
              selectedNodes={selectedNodes}
              onNodeSelect={handleNodeSelect}
              onNodeHover={handleNodeHover}
            />
          </div>

          {/* Right Panel: Preview + ChangeSet */}
          <div className="col-span-4">
            <InteractionPanel
              effectiveLens={lens}
              tabMode={tabMode}
              onTabChange={setTabMode}
              sessionId={sessionId}
              profileId={PROFILE_ID}
              workspaceId={workspaceId}
              onRefresh={refresh}
              selectedNodeIds={selectedNodes}
            />
          </div>
        </div>
      </main>

      {/* Node Detail Panel */}
      {selectedNodeDetail && (
        <NodeDetailPanel
          node={selectedNodeDetail}
          onClose={() => {
            setLockedNodeId(null);
            setLockedNode(null);
            lockedNodeIdRef.current = null;
            lockedNodeRef.current = null;
            setSelectedNodeDetail(null);
          }}
          profileId={PROFILE_ID}
          workspaceId={workspaceId}
        />
      )}
    </div>
  );
}

