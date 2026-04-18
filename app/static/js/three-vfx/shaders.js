import * as ThreeLib from 'three';

export const ColorGradeShader = {
  uniforms: {
    tDiffuse: { value: null },
    saturation: { value: 1.1 },
    contrast: { value: 1.06 },
    tint: { value: new ThreeLib.Vector3(0.95, 1.0, 1.08) },
  },
  vertexShader: /* glsl */`
    varying vec2 vUv;
    void main() {
      vUv = uv;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `,
  fragmentShader: /* glsl */`
    uniform sampler2D tDiffuse;
    uniform float saturation;
    uniform float contrast;
    uniform vec3 tint;
    varying vec2 vUv;
    void main() {
      vec4 c = texture2D(tDiffuse, vUv);
      float luma = dot(c.rgb, vec3(0.299, 0.587, 0.114));
      c.rgb = mix(vec3(luma), c.rgb, saturation);
      c.rgb = (c.rgb - 0.5) * contrast + 0.5;
      c.rgb *= tint;
      gl_FragColor = c;
    }
  `,
};

export function createEnergyFlowMaterial(THREE, { color = 0x67d8ff, accent = 0xffd66b, opacity = 0.72 } = {}) {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uTime: { value: 0 },
      uColor: { value: new THREE.Color(color) },
      uAccent: { value: new THREE.Color(accent) },
      uOpacity: { value: opacity },
    },
    vertexShader: /* glsl */`
      varying vec2 vUv;
      varying vec3 vPos;
      void main() {
        vUv = uv;
        vPos = position;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: /* glsl */`
      uniform float uTime;
      uniform vec3 uColor;
      uniform vec3 uAccent;
      uniform float uOpacity;
      varying vec2 vUv;
      varying vec3 vPos;
      float ring(vec2 uv, float radius, float width) {
        float d = abs(length(uv - 0.5) - radius);
        return smoothstep(width, 0.0, d);
      }
      void main() {
        float sweep = smoothstep(0.0, 0.04, abs(fract(vUv.x * 2.0 - uTime * 0.34) - 0.5));
        float pulse = 0.55 + 0.45 * sin((vUv.x + vUv.y) * 16.0 + uTime * 2.2);
        float r = ring(vUv, 0.34, 0.035) + ring(vUv, 0.43, 0.018);
        vec3 color = mix(uColor, uAccent, pulse) * (0.55 + sweep * 0.65);
        float alpha = clamp((r + 0.16 * pulse) * uOpacity, 0.0, 1.0);
        gl_FragColor = vec4(color, alpha);
      }
    `,
  });
}

export function createDistortionMaterial(THREE, { color = 0x67d8ff } = {}) {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uTime: { value: 0 },
      uColor: { value: new THREE.Color(color) },
    },
    vertexShader: /* glsl */`
      varying vec2 vUv;
      void main() {
        vUv = uv;
        vec3 p = position;
        p.z += sin((position.x + position.y) * 4.0) * 0.015;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
      }
    `,
    fragmentShader: /* glsl */`
      uniform float uTime;
      uniform vec3 uColor;
      varying vec2 vUv;
      float wave(vec2 uv) {
        return sin((uv.x * 12.0 + uTime * 1.7)) * sin((uv.y * 10.0 - uTime * 1.2));
      }
      void main() {
        float d = length(vUv - 0.5);
        float aura = smoothstep(0.52, 0.08, d);
        float w = 0.5 + 0.5 * wave(vUv);
        gl_FragColor = vec4(uColor * (0.35 + w), aura * 0.35);
      }
    `,
  });
}

export function createDissolveMaterial(THREE, { color = 0xffd66b, base = 0x202638 } = {}) {
  return new THREE.ShaderMaterial({
    transparent: true,
    uniforms: {
      uTime: { value: 0 },
      uThreshold: { value: 0.0 },
      uColor: { value: new THREE.Color(color) },
      uBase: { value: new THREE.Color(base) },
    },
    vertexShader: /* glsl */`
      varying vec2 vUv;
      varying vec3 vWorld;
      void main() {
        vUv = uv;
        vec4 world = modelMatrix * vec4(position, 1.0);
        vWorld = world.xyz;
        gl_Position = projectionMatrix * viewMatrix * world;
      }
    `,
    fragmentShader: /* glsl */`
      uniform float uTime;
      uniform float uThreshold;
      uniform vec3 uColor;
      uniform vec3 uBase;
      varying vec2 vUv;
      varying vec3 vWorld;
      float noise(vec2 p) {
        return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
      }
      void main() {
        float n = noise(vUv * 18.0 + uTime * 0.08);
        float edge = smoothstep(uThreshold, uThreshold + 0.08, n);
        float glow = smoothstep(0.02, 0.0, abs(n - uThreshold));
        vec3 c = mix(uColor, uBase, edge) + uColor * glow * 1.8;
        float alpha = smoothstep(uThreshold - 0.03, uThreshold + 0.06, n);
        gl_FragColor = vec4(c, alpha);
      }
    `,
  });
}

export function createParticleMaterial(THREE, { color = 0xffd66b, size = 0.045 } = {}) {
  return new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uTime: { value: 0 },
      uColor: { value: new THREE.Color(color) },
      uSize: { value: size },
    },
    vertexShader: /* glsl */`
      uniform float uTime;
      uniform float uSize;
      attribute float aSeed;
      varying float vAlpha;
      void main() {
        vec3 p = position;
        p.y += sin(uTime * 0.7 + aSeed * 6.2831) * 0.04;
        vec4 mv = modelViewMatrix * vec4(p, 1.0);
        gl_PointSize = uSize * (320.0 / -mv.z) * (0.72 + aSeed * 0.56);
        vAlpha = 0.35 + 0.65 * sin(uTime + aSeed * 6.2831) * 0.5 + 0.5;
        gl_Position = projectionMatrix * mv;
      }
    `,
    fragmentShader: /* glsl */`
      uniform vec3 uColor;
      varying float vAlpha;
      void main() {
        vec2 p = gl_PointCoord - 0.5;
        float d = length(p);
        float alpha = smoothstep(0.5, 0.05, d) * vAlpha;
        gl_FragColor = vec4(uColor, alpha);
      }
    `,
  });
}
