'use client';

import { useEffect, type MutableRefObject, type RefObject } from 'react';
import * as THREE from 'three';

import type { CardClearZone } from './types';

interface UseFogCardClearZonesArgs {
  enabled: boolean;
  contentRef: RefObject<HTMLDivElement | null>;
  containerRef: RefObject<HTMLDivElement | null>;
  trailPointsRef: MutableRefObject<THREE.Vector3[]>;
  cardClearZonesRef: MutableRefObject<CardClearZone[]>;
  isAnyCardHoveredRef: MutableRefObject<boolean>;
}

interface CardState {
  isHovered: boolean;
  strength: number;
}

interface ListenerRecord {
  enter: EventListener;
  leave: EventListener;
}

const clearStrength = 5.0;
const strengthLerp = 0.15;
const minStrengthDelta = 0.01;

function makeRectFallback(rect: DOMRect): { width: number; height: number } {
  return {
    width: rect.width || 1,
    height: rect.height || 1,
  };
}

export function useFogCardClearZones({
  enabled,
  contentRef,
  containerRef,
  trailPointsRef,
  cardClearZonesRef,
  isAnyCardHoveredRef,
}: UseFogCardClearZonesArgs) {
  useEffect(() => {
    if (!enabled || !contentRef.current || !containerRef.current) return;

    const contentElement = contentRef.current;
    const containerElement = containerRef.current;
    const cardStates = new Map<HTMLElement, CardState>();
    const listenerRecords = new Map<HTMLElement, ListenerRecord>();
    let animationFrameId: number | null = null;

    const findCards = () => (
      Array.from(contentElement.querySelectorAll('[data-fog-card]')) as HTMLElement[]
    );

    const updateHoverFlag = () => {
      isAnyCardHoveredRef.current = Array.from(cardStates.values()).some((state) => state.isHovered);
    };

    const updateCardClearZones = () => {
      const cards = findCards();
      const containerRect = containerElement.getBoundingClientRect();
      const containerSize = makeRectFallback(containerRect);
      const zones: CardClearZone[] = [];
      let needsUpdate = false;

      cards.forEach((card) => {
        const state = cardStates.get(card);
        if (!state) return;

        const targetStrength = state.isHovered ? clearStrength : 0.0;
        const delta = (targetStrength - state.strength) * strengthLerp;

        if (Math.abs(targetStrength - state.strength) > minStrengthDelta) {
          state.strength += delta;
          needsUpdate = true;
        } else {
          state.strength = targetStrength;
        }

        if (Math.abs(state.strength) > minStrengthDelta) {
          const cardRect = card.getBoundingClientRect();
          const centerX = ((cardRect.left + cardRect.width / 2) - containerRect.left) / containerSize.width;
          const centerY = 1 - ((cardRect.top + cardRect.height / 2) - containerRect.top) / containerSize.height;
          const radius = (Math.max(cardRect.width, cardRect.height) / containerSize.width) * 1.2;

          zones.push({
            center: new THREE.Vector2(
              Math.max(0, Math.min(1, centerX)),
              Math.max(0, Math.min(1, centerY)),
            ),
            radius,
            strength: state.strength,
          });
        }
      });

      cardClearZonesRef.current = zones;

      if (needsUpdate) {
        animationFrameId = requestAnimationFrame(updateCardClearZones);
      } else {
        animationFrameId = null;
      }
    };

    const scheduleUpdate = () => {
      if (animationFrameId === null) {
        animationFrameId = requestAnimationFrame(updateCardClearZones);
      }
    };

    const removeListeners = (card: HTMLElement) => {
      const record = listenerRecords.get(card);
      if (!record) return;

      card.removeEventListener('mouseenter', record.enter);
      card.removeEventListener('mouseleave', record.leave);
      listenerRecords.delete(card);
    };

    const setupListeners = () => {
      const cards = findCards();
      const currentCards = new Set(cards);

      Array.from(listenerRecords.keys()).forEach((card) => {
        if (!currentCards.has(card)) {
          removeListeners(card);
          cardStates.delete(card);
        }
      });

      cards.forEach((card) => {
        if (!cardStates.has(card)) {
          cardStates.set(card, { isHovered: false, strength: 0 });
        }

        if (listenerRecords.has(card)) return;

        const enter: EventListener = () => {
          const state = cardStates.get(card) ?? { isHovered: false, strength: 0 };
          state.isHovered = true;
          cardStates.set(card, state);
          updateHoverFlag();
          trailPointsRef.current = [];
          scheduleUpdate();
        };

        const leave: EventListener = () => {
          const state = cardStates.get(card);
          if (!state) return;

          state.isHovered = false;
          updateHoverFlag();
          scheduleUpdate();
        };

        listenerRecords.set(card, { enter, leave });
        card.addEventListener('mouseenter', enter);
        card.addEventListener('mouseleave', leave);
      });

      updateHoverFlag();
    };

    const observer = new MutationObserver(() => {
      setupListeners();
    });

    observer.observe(contentElement, { childList: true, subtree: true });
    setupListeners();

    return () => {
      observer.disconnect();
      if (animationFrameId !== null) {
        cancelAnimationFrame(animationFrameId);
      }

      Array.from(listenerRecords.keys()).forEach(removeListeners);
      listenerRecords.clear();
      cardStates.clear();
      cardClearZonesRef.current = [];
      isAnyCardHoveredRef.current = false;
    };
  }, [
    enabled,
    contentRef,
    containerRef,
    trailPointsRef,
    cardClearZonesRef,
    isAnyCardHoveredRef,
  ]);
}
