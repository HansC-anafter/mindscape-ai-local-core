// Fog Fragment Shader
// 雾效果 + 鼠标交互 + Reveal 动画

uniform float u_time;
uniform vec2 u_resolution;
uniform vec2 u_mouse;           // 鼠标位置 (normalized 0-1)
uniform float u_reveal;         // 全局显现进度 (0-1)
uniform float u_mouseRadius;    // 鼠标影响半径
uniform float u_mouseStrength;  // 鼠标影响强度

varying vec2 vUv;

// ========== 2D Perlin Noise ==========
// 基于 Stefan Gustavson 的实现
vec3 mod289(vec3 x) {
    return x - floor(x * (1.0 / 289.0)) * 289.0;
}

vec2 mod289(vec2 x) {
    return x - floor(x * (1.0 / 289.0)) * 289.0;
}

vec3 permute(vec3 x) {
    return mod289(((x * 34.0) + 1.0) * x);
}

float snoise(vec2 v) {
    const vec4 C = vec4(
        0.211324865405187,  // (3.0-sqrt(3.0))/6.0
        0.366025403784439,  // 0.5*(sqrt(3.0)-1.0)
       -0.577350269189626,  // -1.0 + 2.0 * C.x
        0.024390243902439   // 1.0 / 41.0
    );

    vec2 i  = floor(v + dot(v, C.yy));
    vec2 x0 = v - i + dot(i, C.xx);

    vec2 i1;
    i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
    vec4 x12 = x0.xyxy + C.xxzz;
    x12.xy -= i1;

    i = mod289(i);
    vec3 p = permute(
        permute(i.y + vec3(0.0, i1.y, 1.0)) + i.x + vec3(0.0, i1.x, 1.0)
    );

    vec3 m = max(0.5 - vec3(
        dot(x0, x0),
        dot(x12.xy, x12.xy),
        dot(x12.zw, x12.zw)
    ), 0.0);
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

// ========== Layered Noise ==========
// 多层噪声叠加，产生更复杂的雾效
float layeredNoise(vec2 uv, float time) {
    float noise = 0.0;
    float amplitude = 1.0;
    float frequency = 1.0;

    // 3 层噪声，每层频率翻倍，振幅减半
    for (int i = 0; i < 3; i++) {
        noise += amplitude * snoise(uv * frequency + time * 0.1);
        amplitude *= 0.5;
        frequency *= 2.0;
    }

    return noise;
}

// ========== Main ==========
void main() {
    vec2 uv = vUv;

    // 1. 计算鼠标距离
    vec2 mousePos = u_mouse;
    float distToMouse = length(uv - mousePos);

    // 2. 生成基础雾（流动的噪声）
    vec2 noiseUv = uv * 3.0;  // 控制雾的密度（值越大，雾越细腻）
    float noise = layeredNoise(noiseUv, u_time * 0.5);

    // 3. 鼠标影响：warp 噪声坐标（产生"被吹动"的感觉）
    if (distToMouse < u_mouseRadius) {
        // 计算从鼠标指向当前点的方向
        vec2 direction = normalize(uv - mousePos);

        // 距离越近影响越强（smooth falloff）
        float influence = 1.0 - smoothstep(0.0, u_mouseRadius, distToMouse);

        // Warp 噪声坐标
        noiseUv += direction * influence * u_mouseStrength;

        // 重新计算噪声
        noise = layeredNoise(noiseUv, u_time * 0.5);
    }

    // 4. 雾的密度（noise 范围 [-1, 1]，映射到 [0, 1]）
    float fogDensity = (noise + 1.0) * 0.5;

    // 5. 鼠标附近雾变淡（被拨开）
    if (distToMouse < u_mouseRadius) {
        float clearAmount = 1.0 - smoothstep(0.0, u_mouseRadius, distToMouse);
        fogDensity *= (1.0 - clearAmount * 0.8);  // 最多清除 80%
    }

    // 6. 全局 reveal 控制（随时间逐渐显现卡片）
    fogDensity *= (1.0 - u_reveal);

    // 7. 雾的颜色（柔和的白色/浅灰）
    vec3 fogColor = vec3(0.9, 0.92, 0.95);

    // 可选：根据噪声值调整颜色深浅
    // fogColor *= (0.9 + noise * 0.1);

    // 8. 边缘柔化（中心雾浓，边缘渐隐）
    float distToCenter = length(uv - 0.5);
    float edgeFade = smoothstep(0.0, 0.3, distToCenter);
    fogDensity *= (1.0 - edgeFade * 0.5);

    // 9. 输出（alpha 通道控制透明度）
    gl_FragColor = vec4(fogColor, fogDensity * 0.85);
}
