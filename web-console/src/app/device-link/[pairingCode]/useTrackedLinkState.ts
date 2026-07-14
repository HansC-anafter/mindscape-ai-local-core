import { useCallback, useRef, useState } from 'react';

import type { LinkState } from './useDeviceLinkCaptureSessionTypes';

export function useTrackedLinkState(initialState: LinkState) {
  const [state, setState] = useState<LinkState>(initialState);
  const stateRef = useRef<LinkState>(initialState);
  const setTrackedState = useCallback((
    nextState: LinkState | ((current: LinkState) => LinkState),
  ) => {
    setState((current) => {
      const resolved = typeof nextState === 'function' ? nextState(current) : nextState;
      stateRef.current = resolved;
      return resolved;
    });
  }, []);
  return { state, stateRef, setState: setTrackedState };
}
