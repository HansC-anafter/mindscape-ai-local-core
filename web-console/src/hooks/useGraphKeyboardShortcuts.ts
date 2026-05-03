import { useEffect, useCallback, useRef } from 'react';
import { undoChange, useGraphHistory } from '@/lib/graph-changelog-api';

export interface UseGraphKeyboardShortcutsOptions {
    workspaceId: string;
    enabled?: boolean;
    onUndo?: (changeId: string) => void;
    onRedo?: (changeId: string) => void;
    onError?: (error: Error) => void;
}

export function useGraphKeyboardShortcuts({
    workspaceId,
    enabled = true,
    onUndo,
    onRedo,
    onError,
}: UseGraphKeyboardShortcutsOptions) {
    const { history, refresh } = useGraphHistory({
        workspaceId,
        limit: 10,
        enabled: enabled && !!workspaceId,
    });

    const isProcessingRef = useRef(false);

    const lastAppliedChange = history.find(h => h.status === 'applied');
    const lastUndoneChange = history.find(h => h.status === 'undone');

    const handleUndo = useCallback(async () => {
        if (!lastAppliedChange || isProcessingRef.current) return;

        isProcessingRef.current = true;
        try {
            await undoChange(lastAppliedChange.id);
            await refresh();
            onUndo?.(lastAppliedChange.id);
        } catch (error) {
            onError?.(error as Error);
        } finally {
            isProcessingRef.current = false;
        }
    }, [lastAppliedChange, refresh, onUndo, onError]);

    const handleRedo = useCallback(async () => {
        if (!lastUndoneChange) return;

        onRedo?.(lastUndoneChange.id);
    }, [lastUndoneChange, onRedo]);

    useEffect(() => {
        if (!enabled) return;

        const handleKeyDown = (event: KeyboardEvent) => {
            const isUndo = (event.ctrlKey || event.metaKey) && event.key === 'z' && !event.shiftKey;
            const isRedo = (event.ctrlKey || event.metaKey) && event.key === 'z' && event.shiftKey;

            if (isUndo) {
                event.preventDefault();
                handleUndo();
            } else if (isRedo) {
                event.preventDefault();
                handleRedo();
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => {
            window.removeEventListener('keydown', handleKeyDown);
        };
    }, [enabled, handleUndo, handleRedo]);

    return {
        canUndo: !!lastAppliedChange,
        canRedo: !!lastUndoneChange,
        undo: handleUndo,
        redo: handleRedo,
    };
}

export default useGraphKeyboardShortcuts;
