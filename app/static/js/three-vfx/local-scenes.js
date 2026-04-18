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
import { ColorGradeShader } from './shaders.js';

function canRunWebGL() {
  try {
    const canvas = document.createElement('canvas');
    return !!(window.WebGLRenderingContext && (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')));
  } catch (_) {
    return false;
  }
}

class LocalStage {
  constructor(container) {
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
    this.renderer.toneMappingExposure = 1.22;
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
    this.composer.addPass(new UnrealBloomPass(new THREE.Vector2(1, 1), this.kind === 'trophy' ? 1.15 : 0.82, 0.62, 0.38));
    this.composer.addPass(new ShaderPass(ColorGradeShader));

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(this.container);
    this.bindEvents();
    this.container.classList.add('three-local-ready');
    this.animate();
  }

  addLights() {
    this.scene.add(new THREE.AmbientLight(0xd6e8ff, 0.58));
    const key = new THREE.DirectionalLight(0xffffff, 2.35);
    key.position.set(3.4, 4.8, 4.6);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    this.scene.add(key);
    const rim = new THREE.PointLight(0x67d8ff, 2.4, 10);
    rim.position.set(-2.8, 1.8, 3.2);
    this.scene.add(rim);
    const gold = new THREE.PointLight(0xffd66b, 2.6, 10);
    gold.position.set(2.2, 1.1, 2.4);
    this.scene.add(gold);
  }

  buildScene() {
    if (this.kind === 'trophy') this.buildTrophy();
    else if (this.kind === 'practice') this.buildPractice();
    else this.buildHome();
  }

  buildHome() {
    this.camera.position.set(0, 0.55, 5.2);
    this.camera.lookAt(0, 0.1, 0);
    this.root = new THREE.Group();
    this.root.position.set(0, -0.05, 0);
    this.scene.add(this.root);

    const portal = createDistortionPortal({ color: 0x67d8ff, scale: 1.05 });
    portal.position.set(0, 0.08, -0.95);
    this.root.add(portal);
    this.portal = portal;

    const torii = createToriiGate({ scale: 0.72, color: 0xe14d3d });
    torii.position.set(0, -0.18, 0.08);
    this.root.add(torii);
    this.torii = torii;

    const core = createEnergyCore({ color: 0x67d8ff, accent: 0xffd66b, scale: 0.72 });
    core.position.set(0, 0.06, 0.68);
    this.root.add(core);
    this.core = core;

    const ground = new THREE.Mesh(
      new THREE.CylinderGeometry(1.55, 1.75, 0.08, 96),
      new THREE.MeshPhysicalMaterial({ color: 0x10182f, metalness: 0.6, roughness: 0.28, emissive: 0x0f3450, emissiveIntensity: 0.16 }),
    );
    ground.position.y = -1.02;
    ground.receiveShadow = true;
    this.root.add(ground);

    this.particles = createParticleField({ count: this.isMobile ? 170 : 420, radius: 3.2, color: 0xffd66b, size: 0.06 });
    this.particles.position.set(0, 0.15, 0);
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
    this.pointer.lerp(this.targetPointer, 0.08);
    if (this.root) {
      this.root.rotation.y = this.drag.ry + this.pointer.x * 0.18 + Math.sin(time * 0.3) * 0.04;
      this.root.rotation.x = this.drag.rx - this.pointer.y * 0.06;
      this.root.position.y = Math.sin(time * 1.0) * 0.035;
    }
    if (this.core) {
      this.core.rotation.y += delta * 0.72;
      this.core.children.forEach((child) => {
        if (child.material?.uniforms?.uTime) child.material.uniforms.uTime.value = time;
        if (child.userData.spin) child.rotation.z += delta * child.userData.spin;
      });
    }
    if (this.torii) this.torii.rotation.y = Math.sin(time * 0.7) * 0.07;
    if (this.trophy) {
      this.trophy.rotation.y += delta * 0.65;
      this.trophy.position.y = -0.36 + Math.sin(time * 1.25) * 0.07;
      this.trophy.userData.ring.rotation.z -= delta * 1.05;
      this.trophy.userData.orbit.rotation.z += delta * 0.62;
      this.trophy.userData.auraMat.uniforms.uTime.value = time;
    }
    if (this.portal?.material?.uniforms?.uTime) this.portal.material.uniforms.uTime.value = time;
    if (this.crystals) {
      this.crystals.forEach((crystal, index) => {
        crystal.rotation.y += delta * (0.75 + index * 0.08);
        crystal.rotation.x = Math.sin(time + index) * 0.18;
        crystal.position.y = crystal.userData.baseY + Math.sin(time * 1.4 + index) * 0.12;
        crystal.userData.ring.rotation.z += delta * (0.72 + index * 0.08);
      });
    }
    if (this.seal) {
      this.seal.rotation.x += delta * 0.6;
      this.seal.rotation.y -= delta * 0.8;
    }
    updateParticleObject(this.particles, delta, time);
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

export function initLocalThreeStages() {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduceMotion || !canRunWebGL()) return [];
  const stages = [];
  document.querySelectorAll('[data-three-local]').forEach((container) => {
    try {
      const stage = new LocalStage(container);
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
