'use client';

import { useRef, useState, useEffect, useMemo } from 'react';
import { Canvas, useFrame, extend } from '@react-three/fiber';
import { shaderMaterial } from '@react-three/drei';
import * as THREE from 'three';

const fragmentShader = `
uniform float u_time;
uniform vec2 u_resolution;
uniform float u_reveal;
uniform float u_speedMultiplier;  // 速度系数

// 鼠标轨迹点数组（最多记录20个点）
uniform vec3 u_trailPoints[20];  // xy=位置, z=强度(随时间衰减)
uniform int u_trailCount;

varying vec2 vUv;

// Perlin Noise 函数
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

    // === 基础雾层（移动速度由 u_speedMultiplier 控制）===
    // 添加时间偏移，让雾层漂移
    vec2 timeOffset = vec2(u_time * 0.01 * u_speedMultiplier, u_time * 0.008 * u_speedMultiplier);

    vec2 noiseUv = uv * 2.5 + timeOffset;
    float baseNoise = layeredNoise(noiseUv, u_time * 0.05 * u_speedMultiplier);  // 使用时间让噪声演变

    // 细节噪声（也根据速度系数移动）
    vec2 detailOffset = vec2(u_time * 0.015 * u_speedMultiplier, -u_time * 0.012 * u_speedMultiplier);
    vec2 detailUv = uv * 8.0 + detailOffset;
    float detailNoise = snoise(detailUv) * 0.1;

    // 基础雾密度
    float fogDensity = (baseNoise + detailNoise + 1.0) * 0.5;

    // === 邊緣堆積效果 ===
    // 計算到最近邊緣的距離（0-0.5，中心為0.5，邊緣為0）
    vec2 distToEdge = min(uv, 1.0 - uv);  // 到各個邊緣的距離
    float minDistToEdge = min(distToEdge.x, distToEdge.y);  // 最近邊緣的距離

    // 邊緣堆積：距離邊緣越近，霧越濃
    float edgeAccumulation = smoothstep(0.15, 0.0, minDistToEdge);  // 在邊緣15%範圍內開始堆積
    fogDensity += edgeAccumulation * 0.4;  // 增加邊緣霧密度

    // === 计算轨迹影响（雾被推开的效果）===
    float trailClearance = 0.0;

    for (int i = 0; i < 20; i++) {
        if (i >= u_trailCount) break;

        vec3 point = u_trailPoints[i];
        vec2 pointPos = point.xy;
        float pointStrength = point.z;  // 强度（随时间衰减）

        if (pointStrength <= 0.0) continue;

        // 计算当前像素到轨迹点的距离
        float dist = length(uv - pointPos);

        // 根據強度動態調整半徑：
        // - 滑鼠軌跡（strength 0~1）：小一點、貼著指標
        // - 卡片清除（strength > 1.5）：半徑大很多，掃開整塊區域
        float baseRadius = 0.08;
        float radius;
        if (pointStrength > 1.5) {
            // 卡片清除區：我們預期 strength 大約在 2~5
            // 映射成一個比較大的半徑範圍
            float t = clamp((pointStrength - 1.5) / 3.5, 0.0, 1.0);
            // 從大約 0.18 放大到 0.55（你可以再調）
            radius = mix(0.18, 0.55, t);
        } else {
            // 一般滑鼠軌跡：維持小圈圈
            float strengthFactor = clamp(pointStrength, 0.0, 1.0);
            radius = baseRadius * (0.3 + 0.7 * strengthFactor);
        }

        // 越近影響越大
        float influence = smoothstep(radius, 0.0, dist);

        // 高強度點（卡片清除）可以保留你原本做的邊緣柔化
        if (pointStrength > 1.5) {
            influence = pow(influence, 0.5);  // 让边缘扩散更远
        }

        // 添加噪声让边缘不规则（但对卡片清除区域减少噪声影响）
        vec2 noiseUv2 = uv * 10.0 + pointPos * 5.0;
        float edgeNoise = snoise(noiseUv2) * 0.2 + 0.8;  // 减少噪声波动

        // 对卡片清除区域，减少噪声影响
        if (pointStrength > 1.5) {
            edgeNoise = mix(1.0, edgeNoise, 0.3);  // 只保留30%的噪声影响
        }

        // 累积清除效果
        trailClearance += influence * pointStrength * edgeNoise;
    }

    // 限制清除范围（允许更高的清除强度）
    trailClearance = clamp(trailClearance, 0.0, 1.0);

    // 应用清除效果到雾密度
    fogDensity *= (1.0 - trailClearance);

    // 全局 reveal
    fogDensity *= (1.0 - u_reveal);

    // 雾颜色
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

// ========== Shader Material ==========
const FogMaterial = shaderMaterial(
  {
    u_time: 0,
    u_resolution: new THREE.Vector2(1, 1),
    u_reveal: 0,
    u_trailPoints: Array(20).fill(new THREE.Vector3(0, 0, 0)),
    u_trailCount: 0,
    u_speedMultiplier: 1.0,  // 默认速度系数
  },
  vertexShader,
  fragmentShader
);

extend({ FogMaterial });

// TypeScript 类型声明
declare module '@react-three/fiber' {
  interface ThreeElements {
    fogMaterial: any;
  }
}

// ========== Fog Plane Component ==========
function FogPlane({
  trailPointsRef,
  reveal,
  opacity = 0.80,
  speedMultiplier = 1.0,
  cardClearZonesRef,
}: {
  trailPointsRef: React.MutableRefObject<THREE.Vector3[]>;
  reveal: number;
  opacity?: number;
  speedMultiplier?: number;
  cardClearZonesRef: React.MutableRefObject<Array<{ center: THREE.Vector2; radius: number; strength: number }>>;
}) {
  const materialRef = useRef<any>();
  const meshRef = useRef<THREE.Mesh>(null);
  const prevTrailLengthRef = useRef(0);
  const prevRevealRef = useRef(0);
  useFrame((state, delta) => {
    if (!materialRef.current || !materialRef.current.uniforms) return;

    // ✅ 用 r3f 提供的 delta，比自己調 clock 穩定
    const dt = delta;
    const DECAY_PER_SECOND = 0.6;      // 衰減稍微慢一點，肉眼比較看得出來
    const MIN_STRENGTH = 0.05;         // 強度低到這裡就可以直接丟掉

    // ✅ 1. 在這裡做衰減 + 過濾
    const decayed = trailPointsRef.current
      .map((point) => {
        const newStrength = point.z - DECAY_PER_SECOND * dt;
        return new THREE.Vector3(point.x, point.y, newStrength);
      })
      .filter((p) => p.z > MIN_STRENGTH); // 小於門檻就直接移除

    trailPointsRef.current = decayed;

    // ✅ 2. 合併 trail + card zones（原本的邏輯保留）
    const allPoints = [...trailPointsRef.current];
    cardClearZonesRef.current.forEach((zone) => {
      if (zone.strength > 0) {
        allPoints.push(
          new THREE.Vector3(zone.center.x, zone.center.y, zone.strength)
        );
      }
    });

    // ✅ 3. 每一幀更新 uniforms
    const paddedPoints = [...allPoints];
    while (paddedPoints.length < 20) {
      paddedPoints.push(new THREE.Vector3(0, 0, 0));
    }

    // 注意這裡改用 elapsedTime 屬性，不再調 getElapsedTime()
    materialRef.current.uniforms.u_time.value = state.clock.elapsedTime;
    materialRef.current.uniforms.u_speedMultiplier.value = speedMultiplier;
    materialRef.current.uniforms.u_trailPoints.value = paddedPoints.slice(0, 20);
    materialRef.current.uniforms.u_trailCount.value = Math.min(
      allPoints.length,
      20
    );

    const roundedReveal = Math.round(reveal * 1000) / 1000;
    if (Math.abs(roundedReveal - prevRevealRef.current) > 0.001) {
      materialRef.current.uniforms.u_reveal.value = reveal;
      prevRevealRef.current = roundedReveal;
    }
  });

  // 根据传入的 opacity 调整 shader 的最终透明度
  useEffect(() => {
    if (materialRef.current && materialRef.current.uniforms) {
      // 可以通过自定义 uniform 传递透明度系数
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

// ========== Main Component ==========
export interface FogRevealCardProps {
  children: React.ReactNode;
  autoReveal?: boolean;
  revealDuration?: number;
  revealDelay?: number;
  onRevealComplete?: () => void;
  className?: string;
  enableCardClear?: boolean; // 是否启用卡片清除雾效果
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
  const cardClearZonesRef = useRef<Array<{ center: THREE.Vector2; radius: number; strength: number }>>([]);
  const emptyCardClearZonesRef = useRef<Array<{ center: THREE.Vector2; radius: number; strength: number }>>([]);
  const isAnyCardHoveredRef = useRef<boolean>(false);

  // 鼠标移动追踪 - 记录轨迹
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;

      // 如果有任何卡片處於 hover 狀態，不更新 trailPoints
      if (isAnyCardHoveredRef.current) return;

      const rect = containerRef.current.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width;
      const y = 1 - (e.clientY - rect.top) / rect.height;

      const newPos = new THREE.Vector2(
        Math.max(0, Math.min(1, x)),
        Math.max(0, Math.min(1, y))
      );

      // 计算移动距离
      const moveDistance = newPos.distanceTo(lastMousePosRef.current);

      // 只有移动距离足够大时才添加新的轨迹点
      if (moveDistance > 0.01) {
        const newPoint = new THREE.Vector3(newPos.x, newPos.y, 1.0);
        trailPointsRef.current = [...trailPointsRef.current, newPoint].slice(-20);
        lastMousePosRef.current = newPos;
      }
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  // ✅ 删除 setInterval，衰减逻辑移到 useFrame 里

  // 自动 reveal 动画
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

  // 卡片清除雾效果（鼠标 hover 时）
  useEffect(() => {
    if (!enableCardClear || !contentRef.current || !containerRef.current) return;

    const contentElement = contentRef.current;
    const containerElement = containerRef.current;

    // 找到所有可能的卡片元素
    const findCards = () => {
      return Array.from(contentElement.querySelectorAll('[data-fog-card]')) as HTMLElement[];
    };

    let animationFrameId: number | null = null;
    const cardStates = new Map<HTMLElement, { isHovered: boolean; strength: number }>();

    const updateCardClearZones = () => {
      const cards = findCards();
      const containerRect = containerElement.getBoundingClientRect();
      const zones: Array<{ center: THREE.Vector2; radius: number; strength: number }> = [];

      let needsUpdate = false;

      cards.forEach(card => {
        const state = cardStates.get(card);
        if (!state) return;

        // 平滑插值强度
        const targetStrength = state.isHovered ? 5.0 : 0.0;
        const delta = (targetStrength - state.strength) * 0.15;

        // 只有當差距夠大時才更新
        if (Math.abs(targetStrength - state.strength) > 0.01) {
          state.strength += delta;
          needsUpdate = true;
        } else {
          // 已經到達目標，直接設為目標值
          state.strength = targetStrength;
        }

        if (Math.abs(state.strength) > 0.01) {
          const cardRect = card.getBoundingClientRect();

          // 计算卡片中心在 Canvas 坐标系中的位置（0-1范围）
          const centerX = ((cardRect.left + cardRect.width / 2) - containerRect.left) / containerRect.width;
          const centerY = 1 - ((cardRect.top + cardRect.height / 2) - containerRect.top) / containerRect.height;

          // 计算清除半径（基于卡片大小，並增大範圍）
          const radius = Math.max(cardRect.width, cardRect.height) / containerRect.width * 1.2;

          zones.push({
            center: new THREE.Vector2(
              Math.max(0, Math.min(1, centerX)),
              Math.max(0, Math.min(1, centerY))
            ),
            radius,
            strength: state.strength,
          });
        }
      });

      // 直接更新 ref
      cardClearZonesRef.current = zones;

      // 只有當還在動畫中時才繼續更新
      if (needsUpdate) {
        animationFrameId = requestAnimationFrame(updateCardClearZones);
      } else {
        animationFrameId = null;
      }
    };

    const handleMouseEnter = (card: HTMLElement) => () => {
      let state = cardStates.get(card);
      if (!state) {
        state = { isHovered: true, strength: 0 };
        cardStates.set(card, state);
      } else {
        state.isHovered = true;
      }

      // 更新全局 hover 狀態
      isAnyCardHoveredRef.current = true;

      // 清空 trailPoints
      trailPointsRef.current = [];

      // 启动动画循环（如果还没启动）
      if (animationFrameId === null) {
        animationFrameId = requestAnimationFrame(updateCardClearZones);
      }
    };

    const handleMouseLeave = (card: HTMLElement) => () => {
      const state = cardStates.get(card);
      if (state) {
        state.isHovered = false;

        // 檢查是否還有其他卡片在 hover
        const anyHovered = Array.from(cardStates.values()).some(s => s.isHovered);
        isAnyCardHoveredRef.current = anyHovered;

        // 启动动画循环以平滑恢复
        if (animationFrameId === null) {
          animationFrameId = requestAnimationFrame(updateCardClearZones);
        }
      }
    };

    // 监听卡片的 hover 事件
    const setupListeners = () => {
      const cards = findCards();
      cards.forEach(card => {
        if (!cardStates.has(card)) {
          cardStates.set(card, { isHovered: false, strength: 0 });
        }
        card.addEventListener('mouseenter', handleMouseEnter(card));
        card.addEventListener('mouseleave', handleMouseLeave(card));
      });
    };

    // 使用 MutationObserver 监听 DOM 变化
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
      const cards = findCards();
      cards.forEach(card => {
        card.removeEventListener('mouseenter', handleMouseEnter(card));
        card.removeEventListener('mouseleave', handleMouseLeave(card));
      });
      cardStates.clear();
    };
  }, [enableCardClear]);

  // Canvas 配置保持稳定，避免重新创建
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
      {/* 第一层：背景雾（最浓厚，不受任何影響） */}
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

      {/* 第二层：对话框内容（可交互） */}
      <div
        ref={contentRef}
        className="absolute inset-0 flex items-center justify-center z-10 pointer-events-none"
      >
        <div
          className="transition-opacity duration-1000 ease-out pointer-events-auto"
          style={{
            opacity: 1
          }}
        >
          {children}
        </div>
      </div>

      {/* 第三层：前景薄雾（最轻薄，移动更快，显示轨迹+卡片效果） */}
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

      {/* 调试信息（可选） */}
      {process.env.NODE_ENV === 'development' && (
        <div className="absolute top-4 left-4 text-xs text-gray-600 bg-white/80 p-2 rounded z-30 space-y-1">
          <div>轨迹点数: {trailPointsRef.current.length}</div>
          <div>卡片清除区域: {cardClearZonesRef.current.length}</div>
          {cardClearZonesRef.current.map((zone, i) => (
            <div key={i} className="text-[10px]">
              Zone {i}: 强度={zone.strength.toFixed(2)}, 半径={zone.radius.toFixed(3)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ========== 便捷 Hooks ==========
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
