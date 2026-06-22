import { useEffect, useRef, type MutableRefObject } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';

import { useFogCardClearZones } from './useFogCardClearZones';
import type { CardClearZone } from './types';

interface HarnessRefs {
  trailPointsRef: MutableRefObject<THREE.Vector3[]>;
  cardClearZonesRef: MutableRefObject<CardClearZone[]>;
  isAnyCardHoveredRef: MutableRefObject<boolean>;
}

function rect(left: number, top: number, width: number, height: number): DOMRect {
  return {
    x: left,
    y: top,
    left,
    top,
    width,
    height,
    right: left + width,
    bottom: top + height,
    toJSON: () => ({}),
  } as DOMRect;
}

function HookHarness({
  enabled = true,
  onRefs,
}: {
  enabled?: boolean;
  onRefs?: (refs: HarnessRefs) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const trailPointsRef = useRef<THREE.Vector3[]>([new THREE.Vector3(0.2, 0.2, 1)]);
  const cardClearZonesRef = useRef<CardClearZone[]>([]);
  const isAnyCardHoveredRef = useRef(false);

  useFogCardClearZones({
    enabled,
    contentRef,
    containerRef,
    trailPointsRef,
    cardClearZonesRef,
    isAnyCardHoveredRef,
  });

  useEffect(() => {
    onRefs?.({ trailPointsRef, cardClearZonesRef, isAnyCardHoveredRef });
  }, [onRefs]);

  return (
    <div ref={containerRef} data-testid="fog-container">
      <div ref={contentRef}>
        <button data-testid="fog-card" data-fog-card type="button">
          Card
        </button>
      </div>
    </div>
  );
}

describe('useFogCardClearZones', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('removes the same card listener references during cleanup', () => {
    const addSpy = vi.spyOn(HTMLElement.prototype, 'addEventListener');
    const removeSpy = vi.spyOn(HTMLElement.prototype, 'removeEventListener');

    const { unmount } = render(<HookHarness />);
    const card = screen.getByTestId('fog-card');
    const enterIndex = addSpy.mock.calls.findIndex((call, index) => (
      call[0] === 'mouseenter' && addSpy.mock.contexts[index] === card
    ));
    const leaveIndex = addSpy.mock.calls.findIndex((call, index) => (
      call[0] === 'mouseleave' && addSpy.mock.contexts[index] === card
    ));
    const enterHandler = addSpy.mock.calls[enterIndex]?.[1];
    const leaveHandler = addSpy.mock.calls[leaveIndex]?.[1];

    expect(enterHandler).toEqual(expect.any(Function));
    expect(leaveHandler).toEqual(expect.any(Function));

    unmount();

    expect(removeSpy).toHaveBeenCalledWith('mouseenter', enterHandler);
    expect(removeSpy).toHaveBeenCalledWith('mouseleave', leaveHandler);
  });

  it('clears pointer trail points when a fog card is hovered', () => {
    const frameCallbacks: FrameRequestCallback[] = [];
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      frameCallbacks.push(callback);
      return frameCallbacks.length;
    });
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => undefined);

    let refs: HarnessRefs | undefined;
    render(<HookHarness onRefs={(nextRefs) => { refs = nextRefs; }} />);

    const container = screen.getByTestId('fog-container');
    const card = screen.getByTestId('fog-card');
    vi.spyOn(container, 'getBoundingClientRect').mockReturnValue(rect(0, 0, 100, 100));
    vi.spyOn(card, 'getBoundingClientRect').mockReturnValue(rect(10, 10, 20, 20));

    expect(refs?.trailPointsRef.current).toHaveLength(1);

    fireEvent.mouseEnter(card);
    frameCallbacks.shift()?.(0);

    expect(refs?.trailPointsRef.current).toHaveLength(0);
    expect(refs?.isAnyCardHoveredRef.current).toBe(true);
    expect(refs?.cardClearZonesRef.current[0]?.strength).toBeGreaterThan(0);
  });

  it('does not attach card listeners when disabled', () => {
    const addSpy = vi.spyOn(HTMLElement.prototype, 'addEventListener');

    render(<HookHarness enabled={false} />);
    const card = screen.getByTestId('fog-card');
    const hasCardHoverListener = addSpy.mock.calls.some((call, index) => (
      (call[0] === 'mouseenter' || call[0] === 'mouseleave')
      && addSpy.mock.contexts[index] === card
    ));

    expect(hasCardHoverListener).toBe(false);
  });
});
