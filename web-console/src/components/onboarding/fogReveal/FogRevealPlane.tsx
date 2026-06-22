'use client';

import { useEffect, useRef, type MutableRefObject } from 'react';
import { extend, useFrame } from '@react-three/fiber';
import { shaderMaterial } from '@react-three/drei';
import * as THREE from 'three';

import type { CardClearZone } from './types';

const fragmentShader = `
uniform float u_time;
uniform vec2 u_resolution;
uniform float u_reveal;
uniform float u_speedMultiplier;

uniform vec3 u_trailPoints[20];
uniform int u_trailCount;

varying vec2 vUv;

vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec2 mod289(vec2 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec3 permute(vec3 x) { return mod289(((x * 34.0) + 1.0) * x); }

float snoise(vec2 v) {
    const vec4 C = vec4(0.211324865405187, 0.366025403784439, -0.577350269189626, 0.024390243902439);
    vec2 i  = floor(v + dot(v, C.yy));
    vec2 x0 = v - i + dot(i, C.xx);
    vec2 i1;
    i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
    vec4 x12 = x0.xyxy + C.xxzz;
    x12.xy -= i1;
    i = mod289(i);
    vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0)) + i.x + vec3(0.0, i1.x, 1.0));
    vec3 m = max(0.5 - vec3(dot(x0, x0), dot(x12.xy, x12.xy), dot(x12.zw, x12.zw)), 0.0);
    m = m * m;
    m = m * m;
    vec3 x = 2.0 * fract(p * C.www) - 1.0;
    vec3 h = abs(x) - 0.5;
    vec3 ox = floor(x + 0.5);
    vec3 a0 = x - ox;
    m *= 1.79284291400159 - 0.85373472095314 * (a0 * a0 + h * h);
    vec3 g;
    g.x = a0.x * x0.x + h.x * x0.y;
    g.yz = a0.yz * x12.xz + h.yz * x12.yw;
    return 130.0 * dot(m, g);
}

float layeredNoise(vec2 uv, float time) {
    float noise = 0.0;
    float amplitude = 1.0;
    float frequency = 1.0;
    for (int i = 0; i < 4; i++) {
        noise += amplitude * snoise(uv * frequency + time * 0.1);
        amplitude *= 0.5;
        frequency *= 2.0;
    }
    return noise;
}

void main() {
    vec2 uv = vUv;

    vec2 timeOffset = vec2(u_time * 0.01 * u_speedMultiplier, u_time * 0.008 * u_speedMultiplier);
    vec2 noiseUv = uv * 2.5 + timeOffset;
    float baseNoise = layeredNoise(noiseUv, u_time * 0.05 * u_speedMultiplier);

    vec2 detailOffset = vec2(u_time * 0.015 * u_speedMultiplier, -u_time * 0.012 * u_speedMultiplier);
    vec2 detailUv = uv * 8.0 + detailOffset;
    float detailNoise = snoise(detailUv) * 0.1;

    float fogDensity = (baseNoise + detailNoise + 1.0) * 0.5;

    vec2 distToEdge = min(uv, 1.0 - uv);
    float minDistToEdge = min(distToEdge.x, distToEdge.y);
    float edgeAccumulation = smoothstep(0.15, 0.0, minDistToEdge);
    fogDensity += edgeAccumulation * 0.4;

    float trailClearance = 0.0;

    for (int i = 0; i < 20; i++) {
        if (i >= u_trailCount) break;

        vec3 point = u_trailPoints[i];
        vec2 pointPos = point.xy;
        float pointStrength = point.z;

        if (pointStrength <= 0.0) continue;

        float dist = length(uv - pointPos);

        float baseRadius = 0.08;
        float radius;
        if (pointStrength > 1.5) {
            float t = clamp((pointStrength - 1.5) / 3.5, 0.0, 1.0);
            radius = mix(0.18, 0.55, t);
        } else {
            float strengthFactor = clamp(pointStrength, 0.0, 1.0);
            radius = baseRadius * (0.3 + 0.7 * strengthFactor);
        }

        float influence = smoothstep(radius, 0.0, dist);

        if (pointStrength > 1.5) {
            influence = pow(influence, 0.5);
        }

        vec2 noiseUv2 = uv * 10.0 + pointPos * 5.0;
        float edgeNoise = snoise(noiseUv2) * 0.2 + 0.8;

        if (pointStrength > 1.5) {
            edgeNoise = mix(1.0, edgeNoise, 0.3);
        }

        trailClearance += influence * pointStrength * edgeNoise;
    }

    trailClearance = clamp(trailClearance, 0.0, 1.0);
    fogDensity *= (1.0 - trailClearance);
    fogDensity *= (1.0 - u_reveal);

    vec3 fogColor = vec3(0.92, 0.94, 0.96);

    gl_FragColor = vec4(fogColor, fogDensity * 0.80);
}
`;

const vertexShader = `
varying vec2 vUv;

void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const FogMaterial = shaderMaterial(
  {
    u_time: 0,
    u_resolution: new THREE.Vector2(1, 1),
    u_reveal: 0,
    u_trailPoints: Array(20).fill(new THREE.Vector3(0, 0, 0)),
    u_trailCount: 0,
    u_speedMultiplier: 1.0,
  },
  vertexShader,
  fragmentShader,
);

extend({ FogMaterial });

declare module '@react-three/fiber' {
  interface ThreeElements {
    fogMaterial: any;
  }
}

interface FogPlaneProps {
  trailPointsRef: MutableRefObject<THREE.Vector3[]>;
  reveal: number;
  opacity?: number;
  speedMultiplier?: number;
  cardClearZonesRef: MutableRefObject<CardClearZone[]>;
}

export function FogPlane({
  trailPointsRef,
  reveal,
  opacity = 0.80,
  speedMultiplier = 1.0,
  cardClearZonesRef,
}: FogPlaneProps) {
  const materialRef = useRef<any>();
  const meshRef = useRef<THREE.Mesh>(null);
  const prevRevealRef = useRef(0);

  useFrame((state, delta) => {
    if (!materialRef.current || !materialRef.current.uniforms) return;

    const decayPerSecond = 0.6;
    const minStrength = 0.05;
    const decayed = trailPointsRef.current
      .map((point) => {
        const newStrength = point.z - decayPerSecond * delta;
        return new THREE.Vector3(point.x, point.y, newStrength);
      })
      .filter((point) => point.z > minStrength);

    trailPointsRef.current = decayed;

    const allPoints = [...trailPointsRef.current];
    cardClearZonesRef.current.forEach((zone) => {
      if (zone.strength > 0) {
        allPoints.push(
          new THREE.Vector3(zone.center.x, zone.center.y, zone.strength),
        );
      }
    });

    const paddedPoints = [...allPoints];
    while (paddedPoints.length < 20) {
      paddedPoints.push(new THREE.Vector3(0, 0, 0));
    }

    materialRef.current.uniforms.u_time.value = state.clock.elapsedTime;
    materialRef.current.uniforms.u_speedMultiplier.value = speedMultiplier;
    materialRef.current.uniforms.u_trailPoints.value = paddedPoints.slice(0, 20);
    materialRef.current.uniforms.u_trailCount.value = Math.min(allPoints.length, 20);

    const roundedReveal = Math.round(reveal * 1000) / 1000;
    if (Math.abs(roundedReveal - prevRevealRef.current) > 0.001) {
      materialRef.current.uniforms.u_reveal.value = reveal;
      prevRevealRef.current = roundedReveal;
    }
  });

  useEffect(() => {
    if (materialRef.current && materialRef.current.uniforms) {
      materialRef.current.opacity = opacity;
    }
  }, [opacity]);

  return (
    <mesh ref={meshRef}>
      <planeGeometry args={[4, 3]} />
      <fogMaterial
        ref={materialRef}
        transparent
        depthWrite={false}
        side={THREE.DoubleSide}
        opacity={opacity}
      />
    </mesh>
  );
}
