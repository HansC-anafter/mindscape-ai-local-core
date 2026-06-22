'use client';

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Canvas } from '@react-three/fiber';
import * as THREE from 'three';

import { FogPlane } from './fogReveal/FogRevealPlane';
import { useFogCardClearZones } from './fogReveal/useFogCardClearZones';
import type { CardClearZone } from './fogReveal/types';

export interface FogRevealCardProps {
  children: ReactNode;
  autoReveal?: boolean;
  revealDuration?: number;
  revealDelay?: number;
  onRevealComplete?: () => void;
  className?: string;
  enableCardClear?: boolean;
}

export function FogRevealCard({
  children,
  autoReveal = false,
  revealDuration = 3000,
  revealDelay = 500,
  onRevealComplete,
  className = '',
  enableCardClear = true,
}: FogRevealCardProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const trailPointsRef = useRef<THREE.Vector3[]>([]);
  const emptyTrailPointsRef = useRef<THREE.Vector3[]>([]);
  const [reveal, setReveal] = useState(0);
  const lastMousePosRef = useRef(new THREE.Vector2(0.5, 0.5));
  const cardClearZonesRef = useRef<CardClearZone[]>([]);
  const emptyCardClearZonesRef = useRef<CardClearZone[]>([]);
  const isAnyCardHoveredRef = useRef(false);

  useEffect(() => {
    const handleMouseMove = (event: MouseEvent) => {
      if (!containerRef.current) return;
      if (isAnyCardHoveredRef.current) return;

      const rect = containerRef.current.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width;
      const y = 1 - (event.clientY - rect.top) / rect.height;

      const newPosition = new THREE.Vector2(
        Math.max(0, Math.min(1, x)),
        Math.max(0, Math.min(1, y)),
      );

      const moveDistance = newPosition.distanceTo(lastMousePosRef.current);

      if (moveDistance > 0.01) {
        const newPoint = new THREE.Vector3(newPosition.x, newPosition.y, 1.0);
        trailPointsRef.current = [...trailPointsRef.current, newPoint].slice(-20);
        lastMousePosRef.current = newPosition;
      }
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  useEffect(() => {
    if (!autoReveal) return;

    const startTime = Date.now();

    const animate = () => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / revealDuration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setReveal(eased);

      if (progress < 1) {
        requestAnimationFrame(animate);
      } else {
        onRevealComplete?.();
      }
    };

    const timer = setTimeout(animate, revealDelay);
    return () => clearTimeout(timer);
  }, [autoReveal, revealDuration, revealDelay, onRevealComplete]);

  useFogCardClearZones({
    enabled: enableCardClear,
    contentRef,
    containerRef,
    trailPointsRef,
    cardClearZonesRef,
    isAnyCardHoveredRef,
  });

  const canvasConfig = useMemo(() => ({
    camera: { position: [0, 0, 2] as [number, number, number], fov: 50 },
    dpr: [1, 2] as [number, number],
    gl: {
      alpha: true,
      antialias: true,
      powerPreference: 'high-performance' as const,
    },
  }), []);

  return (
    <div
      ref={containerRef}
      className={`relative w-full h-screen overflow-hidden ${className}`}
    >
      <div className="absolute inset-0 pointer-events-none z-0">
        <Canvas
          {...canvasConfig}
          frameloop="always"
        >
          <FogPlane
            trailPointsRef={emptyTrailPointsRef}
            reveal={reveal}
            opacity={0.80}
            speedMultiplier={1.0}
            cardClearZonesRef={emptyCardClearZonesRef}
          />
        </Canvas>
      </div>

      <div
        ref={contentRef}
        className="absolute inset-0 flex items-center justify-center z-10 pointer-events-none"
      >
        <div
          className="transition-opacity duration-1000 ease-out pointer-events-auto"
          style={{
            opacity: 1,
          }}
        >
          {children}
        </div>
      </div>

      <div className="absolute inset-0 pointer-events-none z-20">
        <Canvas
          {...canvasConfig}
          frameloop="always"
          style={{ pointerEvents: 'none' }}
        >
          <FogPlane
            trailPointsRef={trailPointsRef}
            reveal={reveal}
            opacity={0.15}
            speedMultiplier={2.5}
            cardClearZonesRef={cardClearZonesRef}
          />
        </Canvas>
      </div>

      {process.env.NODE_ENV === 'development' && (
        <div className="absolute top-4 left-4 text-xs text-gray-600 bg-white/80 p-2 rounded z-30 space-y-1">
          <div>Trail points: {trailPointsRef.current.length}</div>
          <div>Card clear zones: {cardClearZonesRef.current.length}</div>
          {cardClearZonesRef.current.map((zone, index) => (
            <div key={index} className="text-[10px]">
              Zone {index}: strength={zone.strength.toFixed(2)}, radius={zone.radius.toFixed(3)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function useManualReveal() {
  const [reveal, setReveal] = useState(0);

  const startReveal = (duration = 3000) => {
    const startTime = Date.now();

    const animate = () => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setReveal(eased);

      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    };

    animate();
  };

  return { reveal, startReveal };
}
