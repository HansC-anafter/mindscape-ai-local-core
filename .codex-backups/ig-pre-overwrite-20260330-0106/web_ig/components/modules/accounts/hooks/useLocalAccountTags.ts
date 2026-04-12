import { useCallback, useEffect, useState } from 'react';

export function useLocalAccountTags(workspaceId: string) {
  const [localTags, setLocalTags] = useState<Record<string, string[]>>({});

  useEffect(() => {
    try {
      const raw = localStorage.getItem(`ig:account_tags:${workspaceId}`);
      if (!raw) {
        setLocalTags({});
        return;
      }
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object') {
        setLocalTags(parsed);
        return;
      }
      setLocalTags({});
    } catch {
      setLocalTags({});
    }
  }, [workspaceId]);

  const setTagsForHandle = useCallback((handle: string, tags: string[]) => {
    const key = handle.trim().replace(/^@/, '');
    setLocalTags((prev) => {
      const next = { ...prev, [key]: tags };
      try {
        localStorage.setItem(`ig:account_tags:${workspaceId}`, JSON.stringify(next));
      } catch {
        // ignore
      }
      return next;
    });
  }, [workspaceId]);

  const getTagsForHandle = useCallback((handle: string, fallbackTags?: string[]) => {
    const key = handle.trim().replace(/^@/, '');
    const merged = [...(fallbackTags || []), ...(localTags[key] || [])]
      .map((t) => t.trim())
      .filter((t) => t.length > 0);
    return Array.from(new Set(merged));
  }, [localTags]);

  return { localTags, setTagsForHandle, getTagsForHandle };
}

