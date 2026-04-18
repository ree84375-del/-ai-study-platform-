import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import {
  createTrophyGroup,
  createToriiGate,
  createEnergyCore,
  createSubjectCrystal,
  createParticleField,
  createBurst,
  updateParticleObject,
  createDistortionPortal,
} from './objects.js';
import { ColorGradeShader, createParticleMaterial } from './shaders.js';

function canRunWebGL() {
  try {
    const canvas = document.createElement('canvas');
    return !!(window.WebGLRenderingContext && (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')));
  } catch (_) {
    return false;
  }
}

function createBalancedParticleField({ count = 360, radius = 2.8, color = 0x7fc9c5, size = 0.038 } = {}) {
  const geometry = new THREE.BufferGeometry();
  const positions = new Float32Array(count * 3);
  const seeds = new Float32Array(count);
  const velocities = new Float32Array(count * 3);
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i += 1) {
    const t = (i + 0.5) / count;
    const band = (i % 4) / 4;
    const r = radius * Math.sqrt(t) * (0.72 + band * 0.08);
    const theta = i * goldenAngle;
    const y = (t - 0.5) * radius * 0.92 + Math.sin(theta * 0.7) * 0.08;
    positions[i * 3] = Math.cos(theta) * r;
    positions[i * 3 + 1] = y;
    positions[i * 3 + 2] = Math.sin(theta) * r * 0.52;
    velocities[i * 3] = -Math.sin(theta) * 0.012;
    velocities[i * 3 + 1] = 0.028 + band * 0.008;
    velocities[i * 3 + 2] = Math.cos(theta) * 0.006;
    seeds[i] = (i % 97) / 97;
  }
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute('aSeed', new THREE.BufferAttribute(seeds, 1));
  const material = createParticleMaterial(THREE, { color, size });
  const points = new THREE.Points(geometry, material);
  points.userData = { velocities, radius, material, burst: false, age: 0, maxAge: 2.2, balanced: true };
  return points;
}

class LocalStage {
  constructor(container, options = {}) {
    this.container = container;
    this.kind = container.dataset.threeLocal;
    this.canvas = container.querySelector('[data-three-local-canvas]') || document.createElement('canvas');
    this.canvas.classList.add('three-local-canvas');
    if (!this.canvas.parentNode) this.container.prepend(this.canvas);
    this.clock = new THREE.Clock();
    // 3D SCENE: real Three.js scene, PerspectiveCamera, meshes, PBR materials, lights, shadows.
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(42, 1, 0.1, 80);
    this.pointer = new THREE.Vector2();
    this.targetPointer = new THREE.Vector2();
    this.drag = { active: false, x: 0, y: 0, rx: 0, ry: 0 };
    this.bursts = [];
    this.mixers = [];
    this.isMobile = window.matchMedia('(max-width: 760px)').matches;
    this.reducedMotion = !!options.reducedMotion || window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.motionScale = this.reducedMotion ? 0.45 : 1;
  }

  init() {
    // 3D RENDERER: WebGLRenderer draws into the local canvas, not CSS fake 3D.
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      alpha: true,
      antialias: true,
      powerPreference: 'high-performance',
    });
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = this.kind === 'home' ? 0.88 : 1.12;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    const pmrem = new THREE.PMREMGenerator(this.renderer);
    this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    pmrem.dispose();

    this.addLights();
    this.buildScene();
    this.resize();
    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    // VFX: real post-processing bloom + color grading on the WebGL output.
    this.composer.addPass(new UnrealBloomPass(new THREE.Vector2(1, 1), this.kind === 'trophy' ? 1.05 : (this.kind === 'home' ? 0.46 : 0.68), 0.72, this.kind === 'home' ? 0.54 : 0.38));
    this.composer.addPass(new ShaderPass(ColorGradeShader));

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(this.container);
    this.bindEvents();
    this.container.classList.add('three-local-ready');
    this.animate();
  }

  addLights() {
    this.scene.add(new THREE.AmbientLight(0xb7cbd8, 0.34));
    this.keyLight = new THREE.DirectionalLight(0xf4f0de, this.kind === 'home' ? 1.45 : 1.85);
    this.keyLight.position.set(2.8, 4.6, 4.2);
    this.keyLight.castShadow = true;
    this.keyLight.shadow.mapSize.set(1024, 1024);
    this.scene.add(this.keyLight);

    this.fillLight = new THREE.PointLight(0x74b8b3, this.kind === 'home' ? 1.18 : 1.65, 9);
    this.fillLight.position.set(-2.4, 1.0, 2.4);
    this.scene.add(this.fillLight);

    this.rimLight = new THREE.PointLight(0xc69b62, this.kind === 'home' ? 1.32 : 1.95, 10);
    this.rimLight.position.set(2.4, 1.8, -1.4);
    this.scene.add(this.rimLight);
  }

  buildScene() {
    if (this.kind === 'trophy') this.buildTrophy();
    else if (this.kind === 'practice') this.buildPractice();
    else this.buildHome();
  }

  buildHome() {
    this.camera.fov = 36;
    this.camera.position.set(0, 0.22, 5.35);
    this.camera.lookAt(0, 0.05, 0);
    this.root = new THREE.Group();
    this.root.position.set(0, -0.02, 0);
    this.scene.add(this.root);

    const portal = createDistortionPortal({ color: 0x6fbfba, scale: 1.18 });
    portal.position.set(0, 0.02, -1.12);
    portal.material.uniforms.uOpacity = portal.material.uniforms.uOpacity || { value: 0.38 };
    this.root.add(portal);
    this.portal = portal;

    const baseMaterial = new THREE.MeshPhysicalMaterial({
      color: 0x10283a,
      metalness: 0.72,
      roughness: 0.26,
      clearcoat: 0.55,
      emissive: 0x0b2a33,
      emissiveIntensity: 0.08,
    });
    const base = new THREE.Mesh(new THREE.CylinderGeometry(1.06, 1.28, 0.18, 96), baseMaterial);
    base.position.y = -1.06;
    base.receiveShadow = true;
    base.castShadow = true;
    this.root.add(base);
    this.heroBase = base;

    const plinth = new THREE.Mesh(
      new THREE.CylinderGeometry(0.62, 0.78, 0.16, 96),
      new THREE.MeshPhysicalMaterial({ color: 0x1b3a4d, metalness: 0.62, roughness: 0.22, clearcoat: 0.45, emissive: 0x12353b, emissiveIntensity: 0.08 }),
    );
    plinth.position.y = -0.83;
    plinth.castShadow = true;
    this.root.add(plinth);

    const core = createEnergyCore({ color: 0x73c7c3, accent: 0xc69b62, scale: 1.18 });
    core.position.set(0, -0.08, 0.36);
    core.userData.core.material.emissiveIntensity = 0.075;
    core.userData.core.material.roughness = 0.24;
    core.userData.core.material.color.setHex(0x68aaa7);
    this.root.add(core);
    this.core = core;

    const orbitMat = new THREE.MeshPhysicalMaterial({
      color: 0x6aa9a5,
      metalness: 0.5,
      roughness: 0.22,
      emissive: 0x2f6663,
      emissiveIntensity: 0.07,
      transparent: true,
      opacity: 0.72,
    });
    this.heroOrbits = [];
    [0.0, Math.PI / 2].forEach((rot, index) => {
      const orbit = new THREE.Mesh(new THREE.TorusGeometry(1.34 + index * 0.16, 0.012, 12, 160), orbitMat.clone());
      orbit.rotation.set(Math.PI / 2.25, rot, index * 0.35);
      orbit.userData.speed = index === 0 ? 0.18 : -0.135;
      this.root.add(orbit);
      this.heroOrbits.push(orbit);
    });

    const warmRing = new THREE.Mesh(
      new THREE.TorusGeometry(1.02, 0.018, 16, 160),
      new THREE.MeshBasicMaterial({ color: 0xc69b62, transparent: true, opacity: 0.32, blending: THREE.AdditiveBlending }),
    );
    warmRing.rotation.x = Math.PI / 2;
    warmRing.position.y = -0.58;
    warmRing.userData.speed = -0.24;
    this.root.add(warmRing);
    this.heroOrbits.push(warmRing);

    const glowDisc = new THREE.Mesh(
      new THREE.CircleGeometry(1.72, 128),
      new THREE.MeshBasicMaterial({ color: 0x6fbfba, transparent: true, opacity: 0.105, blending: THREE.AdditiveBlending, depthWrite: false }),
    );
    glowDisc.position.set(0, 0.02, -0.96);
    this.root.add(glowDisc);
    this.heroGlowDisc = glowDisc;

    this.particles = createBalancedParticleField({ count: this.isMobile ? 150 : 420, radius: 2.9, color: 0x8fcfca, size: 0.042 });
    this.particles.position.set(0, 0.02, 0);
    this.scene.add(this.particles);
  }

  buildTrophy() {
    this.camera.position.set(0, 0.45, 5.1);
    this.camera.lookAt(0, 0.05, 0);
    this.root = new THREE.Group();
    this.scene.add(this.root);

    const portal = createDistortionPortal({ color: 0xffd66b, scale: 1.28 });
    portal.position.set(0, 0.05, -1.15);
    this.root.add(portal);
    this.portal = portal;

    const trophy = createTrophyGroup({ rarity: this.container.dataset.rarity || 'ssr', scale: 1.08 });
    trophy.position.set(0, -0.36, 0.45);
    this.root.add(trophy);
    this.trophy = trophy;

    const floor = new THREE.Mesh(
      new THREE.CircleGeometry(1.65, 128),
      new THREE.MeshBasicMaterial({ color: 0xffd66b, transparent: true, opacity: 0.12, blending: THREE.AdditiveBlending }),
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -1.02;
    this.root.add(floor);

    this.particles = createParticleField({ count: this.isMobile ? 190 : 460, radius: 3.0, color: 0xffd66b, size: 0.062 });
    this.particles.position.set(0, 0.05, 0.2);
    this.scene.add(this.particles);
  }

  buildPractice() {
    this.camera.position.set(0, 0.7, 5.4);
    this.camera.lookAt(0, 0, 0);
    this.root = new THREE.Group();
    this.scene.add(this.root);

    const colors = [0x67d8ff, 0xffd66b, 0xff8eb3, 0xb088ff, 0x79dac8];
    this.crystals = [];
    colors.forEach((color, index) => {
      const angle = (index / colors.length) * Math.PI * 2;
      const crystal = createSubjectCrystal({ color, accent: index % 2 ? 0xffd66b : 0x67d8ff, label: String(index) });
      crystal.position.set(Math.cos(angle) * 1.28, Math.sin(angle) * 0.18, Math.sin(angle) * 0.58);
      crystal.scale.setScalar(0.86);
      crystal.userData.baseY = crystal.position.y;
      this.root.add(crystal);
      this.crystals.push(crystal);
    });

    const seal = new THREE.Mesh(
      new THREE.TorusKnotGeometry(0.42, 0.04, 112, 12),
      new THREE.MeshPhysicalMaterial({ color: 0xe14d3d, metalness: 0.5, roughness: 0.18, emissive: 0xe14d3d, emissiveIntensity: 0.22 }),
    );
    seal.position.set(0, -0.2, 0.35);
    this.root.add(seal);
    this.seal = seal;

    this.particles = createParticleField({ count: this.isMobile ? 150 : 330, radius: 3.4, color: 0x67d8ff, size: 0.052 });
    this.scene.add(this.particles);
  }

  // INTERACTION: pointer move parallax, drag rotation, click particle burst.
  bindEvents() {
    this.onMove = (event) => {
      const rect = this.container.getBoundingClientRect();
      this.targetPointer.x = ((event.clientX - rect.left) / Math.max(1, rect.width)) * 2 - 1;
      this.targetPointer.y = -(((event.clientY - rect.top) / Math.max(1, rect.height)) * 2 - 1);
      if (this.drag.active) {
        this.drag.ry += (event.clientX - this.drag.x) * 0.009;
        this.drag.rx += (event.clientY - this.drag.y) * 0.005;
        this.drag.rx = Math.max(-0.5, Math.min(0.5, this.drag.rx));
        this.drag.x = event.clientX;
        this.drag.y = event.clientY;
      }
    };
    this.onDown = (event) => {
      this.drag.active = true;
      this.drag.x = event.clientX;
      this.drag.y = event.clientY;
      this.container.setPointerCapture?.(event.pointerId);
    };
    this.onUp = (event) => {
      this.drag.active = false;
      this.container.releasePointerCapture?.(event.pointerId);
    };
    this.onClick = () => this.spawnBurst();
    this.container.addEventListener('pointermove', this.onMove, { passive: true });
    this.container.addEventListener('pointerdown', this.onDown, { passive: true });
    this.container.addEventListener('pointerup', this.onUp, { passive: true });
    this.container.addEventListener('pointercancel', this.onUp, { passive: true });
    this.container.addEventListener('click', this.onClick, { passive: true });
  }

  // VFX: click-triggered particle burst in real 3D space.
  spawnBurst() {
    const color = this.kind === 'practice' ? 0x67d8ff : 0xffd66b;
    const burst = createBurst({ count: this.isMobile ? 82 : (this.kind === 'trophy' ? 220 : 150), color, size: 0.08, origin: new THREE.Vector3(0, -0.05, 0.45) });
    this.scene.add(burst);
    this.bursts.push(burst);
  }

  resize() {
    const rect = this.container.getBoundingClientRect();
    const width = Math.max(220, Math.floor(rect.width));
    const height = Math.max(220, Math.floor(rect.height));
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, window.innerWidth < 760 ? 1.35 : 1.85));
    this.renderer.setSize(width, height, false);
    this.composer?.setSize(width, height);
  }

  // ANIMATION LOOP: smooth requestAnimationFrame rotation, floating, scale/pulse and shader time.
  animate() {
    const delta = Math.min(0.05, this.clock.getDelta());
    const time = this.clock.elapsedTime;
    const motion = this.motionScale;
    const d = delta * motion;
    this.pointer.lerp(this.targetPointer, 0.08);
    if (this.root) {
      this.root.rotation.y = this.drag.ry + this.pointer.x * 0.18 + Math.sin(time * 0.3 * motion) * 0.04;
      this.root.rotation.x = this.drag.rx - this.pointer.y * 0.06;
      this.root.position.y = Math.sin(time * 0.92 * motion) * 0.055;
    }
    if (this.core) {
      this.core.rotation.y += d * 0.52;
      this.core.children.forEach((child) => {
        if (child.material?.uniforms?.uTime) child.material.uniforms.uTime.value = time;
        if (child.userData.spin) child.rotation.z += d * child.userData.spin;
      });
    }
    if (this.torii) this.torii.rotation.y = Math.sin(time * 0.7 * motion) * 0.07;
    if (this.heroOrbits) {
      this.heroOrbits.forEach((orbit, index) => {
        orbit.rotation.z += d * (orbit.userData.speed || 0.12);
        orbit.rotation.y += Math.sin(time * (0.24 + index * 0.04)) * 0.0008;
      });
    }
    if (this.heroGlowDisc?.material) {
      this.heroGlowDisc.material.opacity = 0.09 + Math.sin(time * 0.82 * motion) * 0.025;
    }
    if (this.keyLight) this.keyLight.intensity = (this.kind === 'home' ? 1.38 : 1.85) + Math.sin(time * 0.7 * motion) * 0.08;
    if (this.fillLight) this.fillLight.intensity = (this.kind === 'home' ? 1.12 : 1.65) + Math.sin(time * 0.54 * motion + 1.4) * 0.06;
    if (this.rimLight) this.rimLight.intensity = (this.kind === 'home' ? 1.28 : 1.95) + Math.sin(time * 0.63 * motion + 2.1) * 0.07;
    if (this.trophy) {
      this.trophy.rotation.y += d * 0.65;
      this.trophy.position.y = -0.36 + Math.sin(time * 1.25) * 0.07;
      this.trophy.userData.ring.rotation.z -= d * 1.05;
      this.trophy.userData.orbit.rotation.z += d * 0.62;
      this.trophy.userData.auraMat.uniforms.uTime.value = time;
    }
    if (this.portal?.material?.uniforms?.uTime) this.portal.material.uniforms.uTime.value = time;
    if (this.crystals) {
      this.crystals.forEach((crystal, index) => {
        crystal.rotation.y += d * (0.75 + index * 0.08);
        crystal.rotation.x = Math.sin(time + index) * 0.18;
        crystal.position.y = crystal.userData.baseY + Math.sin(time * 1.4 + index) * 0.12;
        crystal.userData.ring.rotation.z += d * (0.72 + index * 0.08);
      });
    }
    if (this.seal) {
      this.seal.rotation.x += d * 0.6;
      this.seal.rotation.y -= d * 0.8;
    }
    updateParticleObject(this.particles, delta * Math.max(0.55, motion), time);
    for (let i = this.bursts.length - 1; i >= 0; i -= 1) {
      if (!updateParticleObject(this.bursts[i], delta, time)) {
        this.scene.remove(this.bursts[i]);
        this.bursts.splice(i, 1);
      }
    }
    this.composer.render(delta);
    this.frame = window.requestAnimationFrame(() => this.animate());
  }
}

export function initLocalThreeStages({ reducedMotion = false } = {}) {
  if (!canRunWebGL()) return [];
  const stages = [];
  document.querySelectorAll('[data-three-local]').forEach((container) => {
    try {
      const stage = new LocalStage(container, { reducedMotion });
      stage.init();
      stages.push(stage);
    } catch (error) {
      console.error('[three-vfx] local stage failed', error);
      container.classList.add('three-local-failed');
    }
  });
  if (stages.length) document.body.classList.add('three-local-ready-page');
  return stages;
}
